"""N4.1 LLDP 真实 WALK 解析单测。

覆盖：
- lldpd AgentX 实际布局（1.0.8802.1.1.2.1.4.1.1，列 4..12）的列映射；
- 行索引按 time_mark.local_port.lldp_index 解析（time_mark 是 TimeFilter
  tick，不是墙钟/Unix 时间戳，原样保留）；
- port_desc 列（lldpd 特有）被保留；
- 标准 lldpRemTable（1.0.8802.1.1.2.1.3.7）回退布局仍可解析；
- 表不存在时返回不支持/空，不误报。
"""
import asyncio

from app.services.snmpv3_collector import (
    LLDP_REM_LLDPD_COLUMNS,
    LLDP_REM_STANDARD_COLUMNS,
    LLDP_REM_TABLE_LLDPD,
    _parse_lldp_index,
)


def _asyncio_run(coro):
    return asyncio.run(coro)


def _neighbors_from(result):
    assert result["status"] == "ok"
    return result["neighbors"]


def _build_lldpd_rows(time_mark=23300, local_port=1157, lldp_index=1):
    """按 lldpd 真实 WALK 证据构造各列 OID→值。"""
    rows = {}
    base = f"{LLDP_REM_TABLE_LLDPD}"
    # 列 4..12（lldpd 布局）：chassis_subtype..sys_cap_enabled
    cols = [
        ("4", "4"),            # chassis_subtype = macAddress
        ("5", "0x6AC454158335"),  # chassis_id = 远端 MAC
        ("6", "5"),            # port_subtype = ifName
        ("7", "vethA2"),       # port_id
        ("8", "vethA2"),       # port_desc
        ("9", "56e964baa0f6"),   # sysname
        ("10", "Alpine Linux v3.22"),  # sysdesc
        ("11", "9"),           # sys_cap_supported
        ("12", "0x08"),        # sys_cap_enabled
    ]
    for col, val in cols:
        rows[f"{base}.{col}.{time_mark}.{local_port}.{lldp_index}"] = val
    return rows


def _build_standard_rows(time_mark=4400, local_port=2, lldp_index=1):
    """按标准 lldpRemTable 列 3..10 布局构造数据。"""
    rows = {}
    base = "1.0.8802.1.1.2.1.3.7.1"
    cols = [
        ("3", "4"),               # chassis_subtype
        ("4", "0x001122334455"),  # chassis_id
        ("5", "5"),               # port_subtype
        ("6", "gi0/1"),           # port_id
        ("7", "edge-router"),     # sysname
        ("8", "some sysdescr"),   # sysdesc
        ("9", "9"),               # sys_cap_supported
        ("10", "0x08"),           # sys_cap_enabled
    ]
    for col, val in cols:
        rows[f"{base}.{col}.{time_mark}.{local_port}.{lldp_index}"] = val
    return rows


class FakeTransport:
    """Agent 端：对每个列 OID 返回对应子树的 WALK 行。"""

    def __init__(self, rows: dict[str, str]):
        # rows: full_oid -> value
        self.rows = rows

    async def walk(self, col_oid: str, subtree: str):
        prefix = subtree
        out = []
        for full_oid, value in self.rows.items():
            if full_oid.startswith(prefix + ".") or full_oid == prefix:
                out.append((full_oid, value))
        return out, None, None


async def _run_collect(rows: dict[str, str], **kw):
    from app.services import snmpv3_collector as sc
    transport = FakeTransport(rows)
    # 替换 _walk 为传输层 walk
    orig = sc._walk
    async def fake_walk(t, user, oid, subtree=None):
        return await t.walk(oid, subtree or oid)
    sc._walk = fake_walk
    try:
        return await sc._collect_lldp_via_transport(
            transport, "u", "a", "p", "SHA-256", "AES-128", **kw)
    finally:
        sc._walk = orig


def test_lldpd_layout_real_walk_shape():
    """lldpd 真实 WALK 形状（1.4.1.1 列 4..12）解析出完整邻居。"""
    rows = _build_lldpd_rows()
    result = _asyncio_run(_run_collect(rows))
    assert result["status"] == "ok"
    assert result["layout"] == "lldpd"
    ns = _neighbors_from(result)
    assert len(ns) == 1
    n = ns[0]
    # 行索引三段
    assert n["time_mark"] == 23300
    assert n["local_port"] == 1157
    assert n["lldp_index"] == 1
    # subtype 原值保留（4=macAddress, 5=ifName）
    assert n["chassis_subtype"] == 4
    assert n["port_subtype"] == 5
    assert n["chassis_id"] == "0x6AC454158335"
    assert n["port_id"] == "vethA2"
    # port_desc 列（lldpd 特有）保留
    assert n["port_desc"] == "vethA2"
    assert n["sysname"] == "56e964baa0f6"


def test_standard_layout_fallback():
    """标准 lldpRemTable 布局（1.3.7 列 3..10）可回退解析。"""
    rows = _build_standard_rows()
    result = _asyncio_run(_run_collect(rows))
    assert result["status"] == "ok"
    assert result["layout"] == "standard"
    ns = _neighbors_from(result)
    assert len(ns) == 1
    n = ns[0]
    assert n["time_mark"] == 4400  # 原样保留（tick，非时间戳）
    assert n["local_port"] == 2
    assert n["sysname"] == "edge-router"
    assert n["port_id"] == "gi0/1"
    # 标准布局无 port_desc 列 → 为空
    assert n.get("port_desc") is None


def test_time_mark_is_tick_not_timestamp():
    """time_mark 是 TimeFilter tick（非 epoch/墙钟），原样保留可比较。"""
    rows = _build_lldpd_rows(time_mark=899)
    n = _neighbors_from(_asyncio_run(_run_collect(rows)))[0]
    assert n["time_mark"] == 899
    rows2 = _build_lldpd_rows(time_mark=5500)
    n2 = _neighbors_from(_asyncio_run(_run_collect(rows2)))[0]
    assert n2["time_mark"] == 5500
    # 不是 Unix 时间戳（10 位秒级或 13 位毫秒级）
    assert n["time_mark"] < 10_000_000_000


def test_multiple_neighbors_rows_grouped():
    """同一个 time_mark.local_port 下多个 lldp_index 各行独立保留。"""
    rows = {}
    for idx in (1, 2):
        rows.update(_build_lldpd_rows(time_mark=2500, local_port=1173, lldp_index=idx))
    ns = _neighbors_from(_asyncio_run(_run_collect(rows)))
    assert len(ns) == 2
    assert {n["lldp_index"] for n in ns} == {1, 2}


def test_lldp_table_absent_returns_empty_not_error():
    """两种布局都不存在时返回空邻居（不误报错误）。"""
    result = _asyncio_run(_run_collect({}))
    assert result["status"] == "ok"
    assert result["neighbors"] == []
    assert result["layout"] is None


def test_transport_failure_propagates_timeout():
    """WALK 传输超时直接上抛 timeout，而非当作空表。"""
    class TimeoutTransport:
        async def walk(self, col_oid, subtree=None):
            return None, "timeout", None

    from app.services import snmpv3_collector as sc
    orig = sc._walk
    sc._walk = lambda t, user, oid, subtree=None: t.walk(oid, subtree)
    try:
        result = _asyncio_run(sc._collect_lldp_via_transport(
            TimeoutTransport(), "u", "a", "p", "SHA-256", "AES-128"))
    finally:
        sc._walk = orig
    assert result["status"] == "timeout"
    assert result["neighbors"] == []
    assert result["unsupported"] == "timeout"


def test_index_parser_rejects_short_or_non_numeric():
    assert _parse_lldp_index("1.0.8802.1.1.2.1.4.1.1.4.2500.1173.1",
                             "1.0.8802.1.1.2.1.4.1.1.4") == (2500, 1173, 1)
    assert _parse_lldp_index("1.0.8802.1.1.2.1.4.1.1.4.2500", "1.0.8802.1.1.2.1.4.1.1.4") is None
    assert _parse_lldp_index("1.0.8802.1.1.2.1.4.1.1.4.a.b.c", "1.0.8802.1.1.2.1.4.1.1.4") is None


def test_lldpd_column_mapping_fields():
    """lldpd 布局列映射与真实 WALK 一致（列 4..12 → 字段）。"""
    # 从映射中抽取"列号 → 字段名"
    col_to_field = {
        oid.rsplit(".", 1)[-1]: field
        for oid, field in LLDP_REM_LLDPD_COLUMNS.items()
    }
    assert col_to_field["4"] == "chassis_subtype"
    assert col_to_field["5"] == "chassis_id"
    assert col_to_field["6"] == "port_subtype"
    assert col_to_field["7"] == "port_id"
    assert col_to_field["8"] == "port_desc"
    assert col_to_field["9"] == "sysname"
    assert col_to_field["10"] == "sysdesc"


def test_standard_column_mapping_fields():
    assert "1.0.8802.1.1.2.1.3.7.1.3" in LLDP_REM_STANDARD_COLUMNS
    assert LLDP_REM_STANDARD_COLUMNS["1.0.8802.1.1.2.1.3.7.1.3"] == "chassis_subtype"
    assert LLDP_REM_STANDARD_COLUMNS["1.0.8802.1.1.2.1.3.7.1.7"] == "sysname"
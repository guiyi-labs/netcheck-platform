"""接口速率计算：基于相邻样本与真实时间间隔。

边界处理：
- 计数器回绕（wrap）：curr < prev 时按 2^64 模修正（64 位计数器周期）；
- 修正后速率 > 100 Gbps（≈100 Gbps 为 sanity 上界）视为不可信，返回 None；
- 设备重启由调用方比对 sysUpTime 变化判定（本函数不负责）；
- 缺样本/首样本：返回 None（unknown），绝不用 0 冒充健康。
"""
from datetime import datetime, timezone

COUNTER64_MAX = 2**64
# 合理速率上界：100 Gbps
RATE_SANITY_MAX = 100_000_000_000.0


def compute_rate(
    prev_octets: int | None,
    curr_octets: int | None,
    prev_at: datetime | None,
    curr_at: datetime | None,
) -> float | None:
    """计算字节速率 (bps)。任一前提缺失返回 None。"""
    if curr_octets is None or prev_octets is None or prev_at is None or curr_at is None:
        return None
    if prev_at >= curr_at:
        return None

    elapsed = (curr_at - prev_at).total_seconds()
    if elapsed <= 0:
        return None

    if curr_octets < prev_octets:
        # 64 位计数器回绕：delta = (2^64 - prev) + curr
        delta = curr_octets + (COUNTER64_MAX - prev_octets)
    else:
        delta = curr_octets - prev_octets

    bps = (delta / elapsed) * 8
    if bps > RATE_SANITY_MAX:
        # 修正后速率异常高，可能并非正常回绕（疑似设备重启），丢弃
        return None
    return round(bps, 2)


def classify_interface(admin_status: int | None, oper_status: int | None) -> str:
    """接口状态分类：ok / down / unknown。"""
    # RFC2863: ifAdminStatus 1=up 2=down; ifOperStatus 1=up 2=down
    if admin_status == 1 and oper_status == 1:
        return "ok"
    if admin_status == 2:
        return "down"
    if oper_status == 2:
        return "down"
    return "unknown"


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
"""N4 接口指标趋势查询：时间序列样本降采样 + 语义渲染。

- 只从 InterfaceMetricSample（append-only 历史表）查询；
- API 层先做范围校验/跨度上限，本服务负责 SQL 聚合降采样；
- 缺样本 → 返回 null（不补 0，图表显示真实采集空洞）；
- sample_marker = restart/wrap 的样本在返回中带标记，前端可描点提示。
"""
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.device import InterfaceMetricSample

# 趋势查询跨度上限：默认 7 天
MAX_TREND_SPAN_SECONDS = 7 * 24 * 3600
# 降采样最小桶数（间隔太细时按点数合并）
DEFAULT_MAX_POINTS = 720

SERIES_FIELDS = ("in_bps", "out_bps", "in_errors", "out_errors",
                 "in_discards", "out_discards")


def query_interface_trend(
    db: Session,
    device_id: int,
    interface_index: int | None,
    start: datetime,
    end: datetime,
    interval_seconds: int = 60,
    max_points: int = DEFAULT_MAX_POINTS,
) -> dict:
    """按时间桶聚合返回趋势序列。返回 {"interfaces": [...]}。"""
    if end <= start:
        return {"interfaces": [], "meta": {"from": start.isoformat(), "to": end.isoformat()}}
    span = (end - start).total_seconds()
    if span > MAX_TREND_SPAN_SECONDS:
        span = float(MAX_TREND_SPAN_SECONDS)
        end = start + timedelta(seconds=span)
    if interval_seconds < 1:
        interval_seconds = 1

    q = db.query(InterfaceMetricSample).filter(
        InterfaceMetricSample.device_id == device_id,
        InterfaceMetricSample.collected_at >= start,
        InterfaceMetricSample.collected_at < end,
    )
    if interface_index is not None:
        q = q.filter(InterfaceMetricSample.interface_index == interface_index)
    samples = q.order_by(InterfaceMetricSample.collected_at.asc()).all()

    # 按接口分组 → 时间桶聚合（桶内取末次样本值，缺样本桶为 None）
    interfaces: dict[int, dict] = {}
    for s in samples:
        idx = s.interface_index
        entry = interfaces.setdefault(idx, {
            "interface_index": idx,
            "interface_name": s.interface_name or f"if{idx}",
            "points": [],
            "markers": {},
        })
        bucket = int((s.collected_at - start).total_seconds() // interval_seconds)
        entry["points"].append({
            "t": bucket * interval_seconds,
            "in_bps": s.in_bps,
            "out_bps": s.out_bps,
            "in_errors": s.in_errors,
            "out_errors": s.out_errors,
            "in_discards": s.in_discards,
            "out_discards": s.out_discards,
            "marker": s.sample_marker,
        })

    # 聚合到桶：同一桶保留最后一条（避免重复点），并合并 markers
    out_interfaces = []
    for idx in sorted(interfaces):
        entry = interfaces[idx]
        buckets: dict[int, dict] = {}
        for p in entry["points"]:
            key = p.pop("t")
            if p.get("marker") not in ("ok", None):
                entry["markers"][key] = p["marker"]
            prev = buckets.get(key)
            if prev is None:
                buckets[key] = p
            else:
                # 桶内多条：保留最后一条（时间最新）
                buckets[key] = p
        out_interfaces.append({
            "interface_index": idx,
            "interface_name": entry["interface_name"],
            "points": [buckets[k] for k in sorted(buckets)],
            "markers": entry["markers"],
        })
    return {
        "interfaces": out_interfaces,
        "meta": {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "interval_seconds": interval_seconds,
            "max_points": max_points,
        },
    }


def parse_iso(dt_str: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None
"""Prometheus 指标导出（零依赖）：/metrics 返回 text/plain 格式。

为避免引入外部库，指标通过一次数据库聚合实时生成（演示规模足够）。
未启用 Redis/内存计数；如需高频采样，建议后续接入 prometheus_client。
"""
from collections import Counter

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.asset import Asset
from app.models.inspection import DiagnosisRecord, InspectionResult, InspectionRun, InspectionTask


def _line(name: str, help_text: str, value) -> str:
    return f"# HELP {name} {help_text}\n# TYPE {name} gauge\n{name} {value}\n"


def collect_metrics(db: Session) -> str:
    parts = []

    asset_total = db.query(Asset).count()
    parts.append(_line("netcheck_assets_total", "资产总数", asset_total))
    assets_by_status = Counter(row[0] for row in db.query(Asset.status).all())
    for status, count in sorted(assets_by_status.items()):
        parts.append(_line(f"netcheck_assets_by_status{{status=\"{status}\"}}", "按状态统计资产数", count))

    task_total = db.query(InspectionTask).count()
    task_enabled = db.query(InspectionTask).filter(InspectionTask.enabled.is_(True)).count()
    parts.append(_line("netcheck_tasks_total", "巡检任务总数", task_total))
    parts.append(_line("netcheck_tasks_enabled", "已启用任务数", task_enabled))

    run_total = db.query(InspectionRun).count()
    parts.append(_line("netcheck_runs_total", "巡检运行总数", run_total))
    runs_by_status = Counter(row[0] for row in db.query(InspectionRun.status).all())
    for status, count in sorted(runs_by_status.items()):
        parts.append(_line(f"netcheck_runs_by_status{{status=\"{status}\"}}", "按状态统计运行数", count))

    result_total = db.query(InspectionResult).count()
    parts.append(_line("netcheck_results_total", "检测结果总数", result_total))
    results_by_status = Counter(row[0] for row in db.query(InspectionResult.status).all())
    for status, count in sorted(results_by_status.items()):
        parts.append(_line(f"netcheck_results_by_status{{status=\"{status}\"}}", "按状态统计结果数", count))
    avg_rtt_row = db.query(InspectionResult.response_time).filter(InspectionResult.response_time.isnot(None)).all()
    if avg_rtt_row:
        avg = sum(r[0] for r in avg_rtt_row) / len(avg_rtt_row)
        parts.append(_line("netcheck_results_avg_response_ms", "平均响应耗时 ms", round(avg, 2)))

    alerts_total = db.query(Alert).count()
    parts.append(_line("netcheck_alerts_total", "告警总数", alerts_total))
    alerts_by_status = Counter(row[0] for row in db.query(Alert.alert_status).all())
    for status, count in sorted(alerts_by_status.items()):
        parts.append(_line(f"netcheck_alerts_by_status{{status=\"{status}\"}}", "按状态统计告警数", count))
    alerts_by_level = Counter(row[0] for row in db.query(Alert.alert_level).all())
    for level, count in sorted(alerts_by_level.items()):
        parts.append(_line(f"netcheck_alerts_by_level{{level=\"{level}\"}}", "按等级统计告警数", count))

    diag_total = db.query(DiagnosisRecord).count()
    parts.append(_line("netcheck_diagnoses_total", "诊断记录总数", diag_total))

    return "".join(parts)
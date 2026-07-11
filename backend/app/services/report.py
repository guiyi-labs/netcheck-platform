import os
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.asset import Asset
from app.models.inspection import DiagnosisRecord, InspectionResult, InspectionRun, InspectionTask
from app.models.report import Report


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)


def _append_section(ws, title: str, headers: list[str], rows: list[list[object]]) -> None:
    ws.append([title])
    ws.append(headers)
    for row in rows:
        ws.append(row)
    ws.append([])


def generate_run_report(db: Session, run: InspectionRun) -> Report:
    task = db.get(InspectionTask, run.task_id)
    report_date = (run.started_at or datetime.now()).date().isoformat()
    report_name = f"巡检报告-{task.name if task else run.task_id}-{report_date}"
    file_name = f"run_{run.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    file_path = reports_dir / _safe_name(file_name)

    wb = Workbook()
    ws = wb.active
    ws.title = "巡检报告"

    total = db.query(InspectionResult).filter(InspectionResult.run_id == run.id).count()
    abnormal = db.query(InspectionResult).filter(InspectionResult.run_id == run.id, InspectionResult.status != "success").count()
    diagnosis_count = db.query(DiagnosisRecord).filter(DiagnosisRecord.run_id == run.id).count()
    _append_section(
        ws,
        "巡检概况",
        ["报告名称", "任务名称", "运行ID", "运行状态", "开始时间", "结束时间", "结果总数", "异常结果数", "诊断数"],
        [[report_name, task.name if task else "", run.id, run.status, run.started_at, run.finished_at, total, abnormal, diagnosis_count]],
    )

    abnormal_rows = (
        db.query(InspectionResult, Asset)
        .join(Asset, InspectionResult.asset_id == Asset.id)
        .filter(InspectionResult.run_id == run.id, InspectionResult.status != "success")
        .order_by(InspectionResult.id)
        .all()
    )
    _append_section(
        ws,
        "异常资产",
        ["资产名称", "IP", "检测类型", "状态", "目标", "消息", "错误", "检测时间"],
        [[asset.name, asset.ip, result.check_type, result.status, result.target, result.message, result.error_message, result.checked_at] for result, asset in abnormal_rows],
    )

    fault_rows = (
        db.query(DiagnosisRecord.fault_type, func.count(DiagnosisRecord.id))
        .filter(DiagnosisRecord.run_id == run.id)
        .group_by(DiagnosisRecord.fault_type)
        .order_by(func.count(DiagnosisRecord.id).desc())
        .all()
    )
    _append_section(ws, "故障类型", ["故障类型", "数量"], [[fault_type, count] for fault_type, count in fault_rows])

    suggestion_rows = (
        db.query(DiagnosisRecord, Asset)
        .join(Asset, DiagnosisRecord.asset_id == Asset.id)
        .filter(DiagnosisRecord.run_id == run.id)
        .order_by(DiagnosisRecord.id)
        .all()
    )
    _append_section(
        ws,
        "处理建议",
        ["资产名称", "检测类型", "故障类型", "级别", "建议", "证据"],
        [[asset.name, record.check_type, record.fault_type, record.severity, record.suggestion, record.evidence] for record, asset in suggestion_rows],
    )

    wb.save(file_path)
    report = Report(
        report_name=report_name,
        report_type="run",
        report_date=report_date,
        run_id=run.id,
        task_id=run.task_id,
        file_name=file_name,
        file_path=str(file_path),
        file_size=os.path.getsize(file_path),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def generate_daily_report(db: Session, report_date: date | None = None) -> Report:
    target_date = report_date or date.today()
    run = db.query(InspectionRun).filter(func.date(InspectionRun.started_at) == target_date.isoformat()).order_by(InspectionRun.id.desc()).first()
    if run is None:
        run = db.query(InspectionRun).order_by(InspectionRun.id.desc()).first()
    if run is None:
        raise ValueError("暂无可生成报告的巡检记录")
    report = generate_run_report(db, run)
    report.report_type = "daily"
    report.report_date = target_date.isoformat()
    report.report_name = f"日报-{target_date.isoformat()}"
    db.commit()
    db.refresh(report)
    return report

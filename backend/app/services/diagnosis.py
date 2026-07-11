from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.asset import Asset
from app.models.inspection import DiagnosisRecord, InspectionResult, InspectionRun


def diagnose_result(result: InspectionResult) -> tuple[str, str, str] | None:
    evidence = result.error_message or result.message
    if result.status == "success":
        return None
    if result.check_type == "ping" and result.status == "failed":
        return "主机离线或链路异常", "critical", "检查主机连通性、网络链路及设备电源状态"
    if result.check_type == "port" and result.status == "failed":
        return "服务未启动或防火墙拦截", "major", "确认服务已启动，并检查防火墙和安全组放行规则"
    if result.check_type == "http" and result.status == "failed":
        if evidence and "4" in evidence and any(f"4{code}" in evidence for code in range(10)):
            return "请求路径或访问权限异常", "minor", "检查请求路径、访问权限及认证配置"
        if evidence and "5" in evidence and any(f"5{code}" in evidence for code in range(10)):
            return "Web应用内部错误", "major", "检查Web应用日志、依赖服务和应用配置"
    if result.check_type == "dns" and result.status == "failed":
        return "DNS配置或解析服务异常", "major", "检查域名配置、DNS服务器及解析链路"
    if result.check_type == "dns" and result.status == "warning":
        return "DNS解析响应较慢", "warning", "检查DNS服务器性能、网络延迟及解析缓存配置"
    if result.status == "warning" or (result.response_time is not None and result.response_time > settings.slow_response_threshold):
        return "网络拥塞或服务性能下降", "warning", "检查网络带宽、链路质量及服务资源使用情况"
    if result.check_type == "http" and result.status == "failed":
        return "Web服务访问异常", "major", "检查Web服务进程、网络连接及访问配置"
    return None


def generate_diagnoses(run_id: int, db: Session) -> list[DiagnosisRecord]:
    db.query(DiagnosisRecord).filter(DiagnosisRecord.run_id == run_id).delete(synchronize_session=False)
    results = db.query(InspectionResult).filter(InspectionResult.run_id == run_id).order_by(InspectionResult.id).all()
    records = []
    for result in results:
        diagnosis = diagnose_result(result)
        if diagnosis is None:
            continue
        fault_type, severity, suggestion = diagnosis
        record = DiagnosisRecord(
            run_id=run_id,
            result_id=result.id,
            asset_id=result.asset_id,
            check_type=result.check_type,
            fault_type=fault_type,
            severity=severity,
            suggestion=suggestion,
            evidence=result.error_message or result.message,
        )
        db.add(record)
        records.append(record)
    db.flush()
    return records


def update_asset_statuses(run_id: int, db: Session) -> None:
    results = db.query(InspectionResult).filter(InspectionResult.run_id == run_id).all()
    by_asset: dict[int, list[InspectionResult]] = {}
    for result in results:
        by_asset.setdefault(result.asset_id, []).append(result)
    for asset_id, asset_results in by_asset.items():
        asset = db.get(Asset, asset_id)
        if asset is None:
            continue
        if any(result.check_type == "ping" and result.status == "failed" for result in asset_results):
            asset.status = "offline"
        elif any(result.status == "failed" for result in asset_results):
            asset.status = "warning"
        elif any(result.status == "warning" for result in asset_results):
            asset.status = "warning"
        else:
            asset.status = "online"

    run = db.get(InspectionRun, run_id)
    if run is not None:
        task_asset_ids = [asset.id for asset in run.task.assets]
        for asset_id in set(task_asset_ids) - set(by_asset):
            asset = db.get(Asset, asset_id)
            if asset is not None:
                asset.status = "unknown"

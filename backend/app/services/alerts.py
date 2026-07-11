from datetime import datetime

from sqlalchemy.orm import Session

from app.models.alert import Alert, AlertPolicy
from app.models.inspection import DiagnosisRecord, InspectionResult, InspectionRun

ABNORMAL_STATUSES = {"failed", "warning"}
DEFAULT_POLICY_NAME = "默认告警策略"


def get_default_policy(db: Session) -> AlertPolicy:
    policy = db.query(AlertPolicy).order_by(AlertPolicy.id).first()
    if policy is not None:
        return policy
    policy = AlertPolicy(
        name=DEFAULT_POLICY_NAME,
        enabled=True,
        slow_response_threshold=2000,
        failure_threshold=3,
        recovery_threshold=2,
        deduplicate_enabled=True,
    )
    db.add(policy)
    db.flush()
    return policy


def _count_recent_results(asset_id: int, check_type: str, db: Session, abnormal: bool) -> int:
    results = (
        db.query(InspectionResult)
        .filter(InspectionResult.asset_id == asset_id, InspectionResult.check_type == check_type)
        .order_by(InspectionResult.id.desc())
        .limit(100)
        .all()
    )
    count = 0
    for result in results:
        is_abnormal = result.status in ABNORMAL_STATUSES
        if is_abnormal == abnormal:
            count += 1
        else:
            break
    return count


def _apply_recoveries(run_id: int, policy: AlertPolicy, db: Session) -> None:
    results = db.query(InspectionResult).filter(InspectionResult.run_id == run_id).all()
    seen_keys = set()
    for result in results:
        if result.status != "success":
            continue
        key_prefix = f"{result.asset_id}:{result.check_type}:"
        if key_prefix in seen_keys:
            continue
        seen_keys.add(key_prefix)
        successes = _count_recent_results(result.asset_id, result.check_type, db, abnormal=False)
        if successes < policy.recovery_threshold:
            continue
        alerts = (
            db.query(Alert)
            .filter(
                Alert.asset_id == result.asset_id,
                Alert.check_type == result.check_type,
                Alert.alert_status.in_(["active", "confirmed"]),
            )
            .all()
        )
        now = datetime.now()
        for alert in alerts:
            alert.consecutive_successes = successes
            alert.consecutive_failures = 0
            alert.alert_status = "recovered"
            alert.recovered_at = now
            alert.recovery_reason = "连续正常自动恢复"


def _upsert_alert(diagnosis: DiagnosisRecord, failures: int, db: Session, deduplicate_enabled: bool) -> Alert | None:
    alert_key = f"{diagnosis.asset_id}:{diagnosis.check_type}:{diagnosis.fault_type}"
    existing = None
    if deduplicate_enabled:
        existing = (
            db.query(Alert)
            .filter(Alert.alert_key == alert_key, Alert.alert_status != "recovered")
            .order_by(Alert.id.desc())
            .first()
        )
    now = datetime.now()
    if existing is not None:
        existing.run_id = diagnosis.run_id
        existing.result_id = diagnosis.result_id
        existing.diagnosis_id = diagnosis.id
        existing.alert_title = diagnosis.fault_type
        existing.alert_level = diagnosis.severity
        existing.evidence = diagnosis.evidence
        existing.suggestion = diagnosis.suggestion
        existing.last_triggered_at = now
        existing.trigger_count += 1
        existing.consecutive_failures = failures
        existing.consecutive_successes = 0
        return existing

    alert = Alert(
        asset_id=diagnosis.asset_id,
        run_id=diagnosis.run_id,
        result_id=diagnosis.result_id,
        diagnosis_id=diagnosis.id,
        alert_title=diagnosis.fault_type,
        alert_level=diagnosis.severity,
        alert_status="active",
        alert_key=alert_key,
        check_type=diagnosis.check_type,
        fault_type=diagnosis.fault_type,
        evidence=diagnosis.evidence,
        suggestion=diagnosis.suggestion,
        first_triggered_at=now,
        last_triggered_at=now,
        trigger_count=1,
        consecutive_failures=failures,
        consecutive_successes=0,
    )
    db.add(alert)
    return alert


def evaluate_alerts(run_id: int, db: Session) -> list[Alert]:
    run = db.get(InspectionRun, run_id)
    if run is None:
        return []
    policy = get_default_policy(db)
    if not policy.enabled:
        return []

    _apply_recoveries(run_id, policy, db)
    diagnoses = db.query(DiagnosisRecord).filter(DiagnosisRecord.run_id == run_id).order_by(DiagnosisRecord.id).all()
    alerts = []
    seen_keys = set()
    for diagnosis in diagnoses:
        alert_key = f"{diagnosis.asset_id}:{diagnosis.check_type}:{diagnosis.fault_type}"
        if alert_key in seen_keys:
            continue
        seen_keys.add(alert_key)
        failures = _count_recent_results(diagnosis.asset_id, diagnosis.check_type, db, abnormal=True)
        existing = (
            db.query(Alert)
            .filter(Alert.alert_key == alert_key, Alert.alert_status != "recovered")
            .order_by(Alert.id.desc())
            .first()
            if policy.deduplicate_enabled
            else None
        )
        if existing is None and failures < policy.failure_threshold:
            continue
        alert = _upsert_alert(diagnosis, failures, db, policy.deduplicate_enabled)
        if alert is not None:
            alerts.append(alert)
    db.flush()
    return alerts

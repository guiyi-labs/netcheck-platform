from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.alert import Alert, AlertPolicy
from app.models.inspection import InspectionRun
from app.models.user import User
from app.schemas.alert import AlertOut, AlertPolicyOut, AlertPolicyUpdate, AlertRecoverRequest, AlertSummary
from app.schemas.common import PageData, Response
from app.services.alerts import evaluate_alerts, get_default_policy

alerts_router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
    dependencies=[Depends(get_current_user)],
)

policy_router = APIRouter(
    prefix="/api/alert-policy",
    tags=["alerts"],
    dependencies=[Depends(get_current_user)],
)


def get_alert(alert_id: int, db: Session) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="告警不存在")
    return alert


@alerts_router.get("/summary", response_model=Response[AlertSummary])
def get_alert_summary(db: Session = Depends(get_db)) -> Response[AlertSummary]:
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    data = AlertSummary(
        active_alerts=db.query(Alert).filter(Alert.alert_status == "active").count(),
        unconfirmed_alerts=db.query(Alert).filter(Alert.alert_status == "active").count(),
        recovered_alerts_today=db.query(Alert).filter(Alert.alert_status == "recovered", Alert.recovered_at >= today_start).count(),
    )
    return Response(data=data)


@alerts_router.get("", response_model=Response[PageData[AlertOut]])
def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    alert_status: str | None = None,
    alert_level: str | None = None,
    asset_id: int | None = None,
    check_type: str | None = None,
    fault_type: str | None = None,
    db: Session = Depends(get_db),
) -> Response[PageData[AlertOut]]:
    q = db.query(Alert)
    if alert_status:
        q = q.filter(Alert.alert_status == alert_status)
    if alert_level:
        q = q.filter(Alert.alert_level == alert_level)
    if asset_id is not None:
        q = q.filter(Alert.asset_id == asset_id)
    if check_type:
        q = q.filter(Alert.check_type == check_type)
    if fault_type:
        q = q.filter(Alert.fault_type == fault_type)
    total = q.count()
    alerts = q.order_by(Alert.last_triggered_at.desc(), Alert.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[AlertOut.model_validate(alert) for alert in alerts]))


@alerts_router.post("/evaluate/runs/{run_id}", response_model=Response[PageData[AlertOut]])
def evaluate_run_alerts(run_id: int, db: Session = Depends(get_db)) -> Response[PageData[AlertOut]]:
    if db.get(InspectionRun, run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="运行记录不存在")
    alerts = evaluate_alerts(run_id, db)
    db.commit()
    for alert in alerts:
        db.refresh(alert)
    return Response(message="已评估告警", data=PageData(total=len(alerts), page=1, page_size=len(alerts), items=[AlertOut.model_validate(alert) for alert in alerts]))


@alerts_router.get("/{alert_id}", response_model=Response[AlertOut])
def get_alert_detail(alert_id: int, db: Session = Depends(get_db)) -> Response[AlertOut]:
    return Response(data=AlertOut.model_validate(get_alert(alert_id, db)))


@alerts_router.post("/{alert_id}/confirm", response_model=Response[AlertOut])
def confirm_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response[AlertOut]:
    alert = get_alert(alert_id, db)
    if alert.alert_status == "recovered":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已恢复告警不能确认")
    alert.alert_status = "confirmed"
    alert.confirmed_by = current_user.username
    alert.confirmed_at = datetime.now()
    db.commit()
    db.refresh(alert)
    return Response(message="告警已确认", data=AlertOut.model_validate(alert))


@alerts_router.post("/{alert_id}/recover", response_model=Response[AlertOut])
def recover_alert(alert_id: int, payload: AlertRecoverRequest | None = None, db: Session = Depends(get_db)) -> Response[AlertOut]:
    alert = get_alert(alert_id, db)
    alert.alert_status = "recovered"
    alert.recovered_at = datetime.now()
    alert.recovery_reason = payload.recovery_reason if payload and payload.recovery_reason else "手动恢复"
    alert.consecutive_successes = 0
    db.commit()
    db.refresh(alert)
    return Response(message="告警已恢复", data=AlertOut.model_validate(alert))


@policy_router.get("", response_model=Response[AlertPolicyOut])
def get_policy(db: Session = Depends(get_db)) -> Response[AlertPolicyOut]:
    policy = get_default_policy(db)
    db.commit()
    db.refresh(policy)
    return Response(data=AlertPolicyOut.model_validate(policy))


@policy_router.put("", response_model=Response[AlertPolicyOut])
def update_policy(payload: AlertPolicyUpdate, db: Session = Depends(get_db)) -> Response[AlertPolicyOut]:
    policy = get_default_policy(db)
    for field in payload.model_fields_set:
        setattr(policy, field, getattr(payload, field))
    db.commit()
    db.refresh(policy)
    return Response(message="告警策略已更新", data=AlertPolicyOut.model_validate(policy))

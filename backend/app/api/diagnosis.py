from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.inspection import DiagnosisRecord, InspectionRun
from app.schemas.common import PageData, Response
from app.schemas.diagnosis import DiagnosisOut
from app.services.diagnosis import generate_diagnoses, update_asset_statuses

router = APIRouter(
    prefix="/api/diagnosis",
    tags=["diagnosis"],
    dependencies=[Depends(get_current_user)],
)


def get_run(run_id: int, db: Session) -> InspectionRun:
    run = db.get(InspectionRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="运行记录不存在")
    return run


@router.get("", response_model=Response[PageData[DiagnosisOut]])
def list_diagnoses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    run_id: int | None = None,
    asset_id: int | None = None,
    severity: str | None = None,
    check_type: str | None = None,
    fault_type: str | None = None,
    db: Session = Depends(get_db),
) -> Response[PageData[DiagnosisOut]]:
    q = db.query(DiagnosisRecord)
    if run_id is not None:
        q = q.filter(DiagnosisRecord.run_id == run_id)
    if asset_id is not None:
        q = q.filter(DiagnosisRecord.asset_id == asset_id)
    if severity:
        q = q.filter(DiagnosisRecord.severity == severity)
    if check_type:
        q = q.filter(DiagnosisRecord.check_type == check_type)
    if fault_type:
        q = q.filter(DiagnosisRecord.fault_type == fault_type)
    total = q.count()
    records = q.order_by(DiagnosisRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[DiagnosisOut.model_validate(record) for record in records]))


@router.get("/runs/{run_id}", response_model=Response[PageData[DiagnosisOut]])
def list_run_diagnoses(
    run_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> Response[PageData[DiagnosisOut]]:
    get_run(run_id, db)
    q = db.query(DiagnosisRecord).filter(DiagnosisRecord.run_id == run_id)
    total = q.count()
    records = q.order_by(DiagnosisRecord.id).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[DiagnosisOut.model_validate(record) for record in records]))


@router.post("/runs/{run_id}/generate", response_model=Response[PageData[DiagnosisOut]])
def regenerate_run_diagnoses(run_id: int, db: Session = Depends(get_db)) -> Response[PageData[DiagnosisOut]]:
    get_run(run_id, db)
    records = generate_diagnoses(run_id, db)
    update_asset_statuses(run_id, db)
    db.commit()
    for record in records:
        db.refresh(record)
    return Response(message="已重新生成诊断", data=PageData(total=len(records), page=1, page_size=len(records), items=[DiagnosisOut.model_validate(record) for record in records]))


@router.get("/{diagnosis_id}", response_model=Response[DiagnosisOut])
def get_diagnosis(diagnosis_id: int, db: Session = Depends(get_db)) -> Response[DiagnosisOut]:
    record = db.get(DiagnosisRecord, diagnosis_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="诊断记录不存在")
    return Response(data=DiagnosisOut.model_validate(record))

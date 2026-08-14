from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_write
from app.models.inspection import InspectionRun
from app.models.report import Report
from app.models.user import User
from app.schemas.common import PageData, Response
from app.schemas.report import ReportGenerateIn, ReportOut
from app.services import audit
from app.services.report import generate_daily_report, generate_run_report

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/generate", response_model=Response[ReportOut], status_code=status.HTTP_201_CREATED)
def generate_report(
    payload: ReportGenerateIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> Response[ReportOut]:
    if payload.report_type == "run":
        if payload.run_id is None:
            raise HTTPException(status_code=422, detail="run 类型报告必须提供 run_id")
        run = db.get(InspectionRun, payload.run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行记录不存在")
        report = generate_run_report(db, run)
    else:
        try:
            report = generate_daily_report(db, payload.report_date)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit.record(db, current_user.username, "report.generate", target_type="report", target_id=report.id, detail=f"生成报告 {report.report_name}", request=request)
    db.commit()
    return Response(message="报告已生成", data=ReportOut.model_validate(report))


@router.get("", response_model=Response[PageData[ReportOut]])
def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    report_type: str | None = None,
    db: Session = Depends(get_db),
) -> Response[PageData[ReportOut]]:
    q = db.query(Report)
    if report_type:
        q = q.filter(Report.report_type == report_type)
    total = q.count()
    reports = q.order_by(Report.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Response(data=PageData(total=total, page=page, page_size=page_size, items=[ReportOut.model_validate(report) for report in reports]))


@router.get("/{report_id}/download")
def download_report(report_id: int, db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    path = Path(report.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")
    return FileResponse(path, filename=report.file_name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.delete("/{report_id}", response_model=Response[ReportOut])
def delete_report(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_write),
) -> Response[ReportOut]:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    data = ReportOut.model_validate(report)
    path = Path(report.file_path)
    if path.exists():
        path.unlink()
    audit.record(db, current_user.username, "report.delete", target_type="report", target_id=report_id, detail=f"删除报告 {report.report_name}", request=request)
    db.delete(report)
    db.commit()
    return Response(message="报告已删除", data=data)

"""Prometheus /metrics：无鉴权，供抓取器轮询（与 /health 同级）。"""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.metrics import collect_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> PlainTextResponse:
    db: Session = SessionLocal()
    try:
        body = collect_metrics(db)
    finally:
        db.close()
    return PlainTextResponse(body, media_type="text/plain; version=0.0.4")
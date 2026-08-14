from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.alerts import alerts_router, policy_router
from app.api.assets import router as assets_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.diagnosis import router as diagnosis_router
from app.api.discovery import router as discovery_router
from app.api.inspection import router as inspection_router
from app.api.reports import router as reports_router
from app.api.results import router as results_router
from app.api.routes import router as api_router
from app.api.scheduler import router as scheduler_router
from app.api.topology import router as topology_router
from app.core.config import settings
from app.core.database import init_db
from app.services import executor
from app.services.scheduler import scheduler_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表并写入演示数据（幂等）
    init_db()
    executor.start()
    scheduler_service.start()
    scheduler_service.reload_all()
    try:
        yield
    finally:
        scheduler_service.shutdown()
        executor.shutdown()


app = FastAPI(
    title="Network Check Platform",
    version=settings.version,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.version,
    }


app.include_router(api_router)
app.include_router(auth_router)
app.include_router(alerts_router)
app.include_router(policy_router)
app.include_router(audit_router)
app.include_router(inspection_router)
app.include_router(diagnosis_router)
app.include_router(dashboard_router)
app.include_router(results_router)
app.include_router(reports_router)
app.include_router(assets_router)
app.include_router(scheduler_router)
app.include_router(discovery_router)
app.include_router(topology_router)

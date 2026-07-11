from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/api")


@router.get("/health")
def api_health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.version,
        "database": settings.database_url,
    }

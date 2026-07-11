from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.schemas.common import Response
from app.services.scheduler import scheduler_service

router = APIRouter(
    prefix="/api/scheduler",
    tags=["scheduler"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/status", response_model=Response[dict])
def scheduler_status() -> Response[dict]:
    return Response(data=scheduler_service.get_status())

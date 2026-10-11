from fastapi import APIRouter
from pydantic import BaseModel

from feedback_hub import __version__

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: str
    version: str


@router.get("/live", response_model=HealthStatus)
async def live() -> HealthStatus:
    return HealthStatus(status="ok", version=__version__)


@router.get("/ready", response_model=HealthStatus)
async def ready() -> HealthStatus:
    return HealthStatus(status="ok", version=__version__)

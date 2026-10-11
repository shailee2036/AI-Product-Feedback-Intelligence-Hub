from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from feedback_hub import __version__
from feedback_hub.db.engine import Database

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: str
    version: str
    checks: dict[str, str] = {}


@router.get("/live", response_model=HealthStatus)
async def live() -> HealthStatus:
    return HealthStatus(status="ok", version=__version__)


@router.get("/ready", response_model=HealthStatus)
async def ready(request: Request, response: Response) -> HealthStatus:
    checks: dict[str, str] = {}
    database: Database | None = getattr(request.app.state, "database", None)
    if database is not None:
        try:
            await database.ping()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "unavailable"

    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthStatus(status="ok" if healthy else "degraded", version=__version__, checks=checks)

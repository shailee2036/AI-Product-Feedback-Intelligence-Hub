from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from feedback_hub.auth import CurrentUser
from feedback_hub.db.engine import UserConnection
from feedback_hub.db.workspaces import ensure_workspace

router = APIRouter(prefix="/v1", tags=["me"])


class WorkspaceOut(BaseModel):
    id: UUID
    name: str
    role: str


class MeResponse(BaseModel):
    user_id: UUID
    email: str | None
    workspace: WorkspaceOut


def default_workspace_name(email: str | None) -> str:
    if email and "@" in email:
        return f"{email.split('@', 1)[0]}'s workspace"
    return "My workspace"


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser, conn: UserConnection) -> MeResponse:
    workspace = await ensure_workspace(conn, default_workspace_name(user.email))
    return MeResponse(
        user_id=user.id,
        email=user.email,
        workspace=WorkspaceOut(id=workspace.tenant_id, name=workspace.name, role=workspace.role),
    )

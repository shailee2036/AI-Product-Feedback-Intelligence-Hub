from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from feedback_hub.api.me import default_workspace_name
from feedback_hub.auth import CurrentUser
from feedback_hub.db.audit import load_audit_events
from feedback_hub.db.engine import UserConnection
from feedback_hub.db.workspaces import ensure_workspace

router = APIRouter(tags=["audit"])

AUDIT_LIMIT = 20

_SUMMARIES = {
    "product.registered": "Registered the GitHub repository.",
    "product.registration_rejected": "Rejected a repository registration.",
    "import.started": "Started a GitHub issue import.",
    "import.completed": "Finished the GitHub issue import.",
    "import.failed": "GitHub issue import failed.",
    "import.cancelled": "Cancelled the GitHub issue import.",
    "csv.imported": "Imported a customer-feedback CSV.",
    "embedding.started": "Started embedding feedback.",
    "embedding.completed": "Finished embedding feedback.",
    "embedding.failed": "Embedding feedback failed.",
    "dedupe.completed": "Rebuilt duplicate links.",
    "cluster.completed": "Found candidate themes.",
    "cluster.named": "Named untitled themes.",
    "cluster.relabeled": "Saved a theme name.",
    "cluster.approved": "Approved a theme.",
    "cluster.dismissed": "Dismissed a theme.",
    "cluster.merged": "Merged two themes.",
    "cluster.split": "Split a theme.",
    "cluster.briefed": "Wrote a product brief.",
    "cluster.brief_edited": "Saved an edited brief.",
    "cluster.suggestion_saved": "Saved a suggested issue comment.",
    "cluster.issue_draft_saved": "Saved a new-issue draft.",
}


class AuditEventOut(BaseModel):
    id: int
    action: str
    summary: str
    created_at: datetime


class AuditReport(BaseModel):
    events: list[AuditEventOut]


def audit_summary(action: str) -> str:
    return _SUMMARIES.get(action, action)


@router.get("/v1/audit", response_model=AuditReport)
async def list_audit_events(user: CurrentUser, conn: UserConnection) -> AuditReport:
    """Show recent workspace actions. Reading the list does not add an event."""
    await ensure_workspace(conn, default_workspace_name(user.email))
    events = await load_audit_events(conn, limit=AUDIT_LIMIT)
    return AuditReport(
        events=[
            AuditEventOut(
                id=event.id,
                action=event.action,
                summary=audit_summary(event.action),
                created_at=event.created_at,
            )
            for event in events
        ]
    )

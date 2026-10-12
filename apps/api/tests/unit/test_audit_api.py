from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest

from feedback_hub.auth import SupabaseJwtVerifier
from feedback_hub.config import Settings
from feedback_hub.db.audit import StoredAuditEvent
from feedback_hub.db.engine import get_database
from feedback_hub.db.workspaces import Workspace
from feedback_hub.main import create_app
from tests.auth_helpers import SUPABASE_URL, TokenFactory


class _Conn:
    async def execute(self, statement: object, params: object = None) -> object:
        raise AssertionError(statement)


@pytest.fixture
async def audit_api(monkeypatch: pytest.MonkeyPatch) -> Any:
    app = create_app(
        Settings(
            environment="test",
            database_url=None,
            supabase_url=SUPABASE_URL,
            gemini_api_key=None,
        )
    )

    class _Database:
        @asynccontextmanager
        async def user_transaction(self, user: object) -> Any:
            yield _Conn()

    app.state.database = _Database()
    app.dependency_overrides[get_database] = lambda: app.state.database
    seen: list[str] = []

    async def workspace(connection: object, name: str) -> Workspace:
        seen.append(name)
        return Workspace(tenant_id=uuid4(), name=name, role="owner")

    async def load(connection: object, *, limit: int) -> list[StoredAuditEvent]:
        seen.append(str(limit))
        return [
            StoredAuditEvent(
                id=8,
                action="cluster.approved",
                created_at=datetime(2026, 10, 12, 15, 4, tzinfo=UTC),
            ),
            StoredAuditEvent(
                id=3,
                action="theme.reopened",
                created_at=datetime(2026, 10, 11, 12, 0, tzinfo=UTC),
            ),
        ]

    monkeypatch.setattr("feedback_hub.api.audit.ensure_workspace", workspace)
    monkeypatch.setattr("feedback_hub.api.audit.load_audit_events", load)
    tokens = TokenFactory()
    async with httpx.AsyncClient() as http:
        app.state.jwt_verifier = SupabaseJwtVerifier(
            http,
            supabase_url=SUPABASE_URL,
            audience="authenticated",
            cache_seconds=600,
            static_keys={tokens.kid: tokens.pyjwk()},
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, tokens, seen


async def test_audit_list_requires_a_user(audit_api: Any) -> None:
    client, _tokens, _seen = audit_api

    response = await client.get("/v1/audit")

    assert response.status_code == 401


async def test_audit_list_returns_summaries_without_writing(audit_api: Any) -> None:
    client, tokens, seen = audit_api
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    response = await client.get("/v1/audit", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["events"][0]["action"] == "cluster.approved"
    assert body["events"][0]["summary"] == "Approved a theme."
    assert body["events"][1]["summary"] == "theme.reopened"
    assert "metadata" not in body["events"][0]
    assert seen[-1] == "20"

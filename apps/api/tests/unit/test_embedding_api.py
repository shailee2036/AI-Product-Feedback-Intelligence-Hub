from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from feedback_hub.auth import SupabaseJwtVerifier
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.engine import get_database
from feedback_hub.db.products import RegisteredProduct
from feedback_hub.db.workspaces import Workspace
from feedback_hub.main import create_app
from tests.auth_helpers import SUPABASE_URL, TokenFactory


class _Database:
    @asynccontextmanager
    async def user_transaction(self, user: object) -> Any:
        yield None


@pytest.fixture
async def embedding_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    tokens = TokenFactory()
    settings = Settings(environment="test", database_url=None, supabase_url=SUPABASE_URL)
    app = create_app(settings)
    app.state.database = _Database()
    app.state.gemini = object()
    app.state.import_tasks = set()
    app.dependency_overrides[get_database] = lambda: app.state.database

    async def idle(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr("feedback_hub.api.embeddings.run_embeddings", idle)
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
            yield client, tokens, app


async def test_embedding_requires_a_gemini_api_key(embedding_client: Any) -> None:
    client, tokens, _app = embedding_client
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    response = await client.post("/v1/feedback/embeddings", headers=headers)

    assert response.status_code == 503
    assert "FEEDBACK_HUB_GEMINI_API_KEY" in response.json()["detail"]


async def test_embedding_is_queued(embedding_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, tokens, app = embedding_client
    run_id = uuid4()
    product_id = uuid4()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url=None,
        supabase_url=SUPABASE_URL,
        gemini_api_key=SecretStr("gemini-test-key"),
    )

    async def workspace(conn: object, name: str) -> Workspace:
        return Workspace(tenant_id=uuid4(), name=name, role="owner")

    async def product(conn: object) -> RegisteredProduct:
        return RegisteredProduct(
            id=product_id,
            name="Appwrite",
            created_at=datetime(2026, 10, 11, tzinfo=UTC),
            repository_id=uuid4(),
            github_node_id="R_1",
            full_name="appwrite/appwrite",
            html_url="https://github.com/appwrite/appwrite",
            default_branch="main",
            license_spdx="BSD-3-Clause",
            license_checked_at=None,
        )

    async def create(conn: object, **kwargs: object) -> Any:
        return run_id

    async def count(conn: object) -> int:
        return 4

    async def audit(conn: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr("feedback_hub.api.embeddings.ensure_workspace", workspace)
    monkeypatch.setattr("feedback_hub.api.embeddings.get_product", product)
    monkeypatch.setattr("feedback_hub.api.embeddings.create_embedding_run", create)
    monkeypatch.setattr("feedback_hub.api.embeddings.count_embeddings", count)
    monkeypatch.setattr("feedback_hub.api.embeddings.record_audit_event", audit)
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    response = await client.post("/v1/feedback/embeddings", headers=headers)

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["stored_count"] == 4

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from feedback_hub.auth import SupabaseJwtVerifier
from feedback_hub.config import Settings
from feedback_hub.db.engine import get_database
from feedback_hub.db.products import RegisteredProduct
from feedback_hub.db.workspaces import Workspace
from feedback_hub.main import create_app
from tests.auth_helpers import SUPABASE_URL, TokenFactory


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class _Row:
    def __init__(self, **kwargs: Any) -> None:
        self._mapping = kwargs


class _Conn:
    def __init__(self, items: list[dict[str, Any]], pairs: list[tuple[UUID, UUID, float]]) -> None:
        self.items = items
        self.pairs = pairs
        self.edges: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: object = None) -> _Result:
        sql = " ".join(str(statement).split())
        if "from public.feedback_items" in sql:
            return _Result([_Row(**item) for item in self.items])
        if "from public.feedback_embeddings" in sql:
            return _Result(
                [
                    _Row(left_id=left, right_id=right, score=score)
                    for left, right, score in self.pairs
                ]
            )
        if sql.startswith("delete from public.duplicate_edges"):
            self.edges.clear()
            return _Result([])
        if sql.startswith("insert into public.duplicate_edges") and isinstance(params, list):
            self.edges = [row for row in params if isinstance(row, dict)]
            return _Result([])
        if sql.startswith("insert into public.dedupe_runs") and isinstance(params, dict):
            self.runs.append(params)
            return _Result([])
        if "from public.dedupe_runs" in sql:
            if not self.runs:
                return _Result([])
            last = self.runs[-1]
            return _Result(
                [
                    _Row(
                        exact_count=last["exact_count"],
                        semantic_count=last["semantic_count"],
                        group_count=last["group_count"],
                        threshold=last["threshold"],
                        neighbor_count=last["neighbor_count"],
                    )
                ]
            )
        if "from public.duplicate_edges" in sql:
            return _Result(
                [
                    _Row(
                        left_item_id=edge["left_item_id"],
                        right_item_id=edge["right_item_id"],
                        kind=edge["kind"],
                        score=edge["score"],
                    )
                    for edge in self.edges
                ]
            )
        raise AssertionError(sql)


def _product() -> RegisteredProduct:
    return RegisteredProduct(
        id=uuid4(),
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


def _item(item_id: UUID, external_id: str, digest: str, title: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "source": "csv",
        "external_id": external_id,
        "title": title,
        "body": title,
        "language": "en",
        "content_hash": digest,
    }


@pytest.fixture
async def duplicate_api(monkeypatch: pytest.MonkeyPatch) -> Any:
    left, right, near, far = uuid4(), uuid4(), uuid4(), uuid4()
    conn = _Conn(
        items=[
            _item(left, "AW-SYN-001", "a" * 64, "Callback checklist"),
            _item(right, "AW-SYN-002", "a" * 64, "Why the callback was rejected"),
            _item(near, "AW-SYN-011", "b" * 64, "Resume a dropped upload"),
            _item(far, "AW-SYN-012", "c" * 64, "Continue an interrupted upload"),
            _item(uuid4(), "AW-SYN-006", "d" * 64, "A different request"),
        ],
        pairs=[(left, right, 0.99), (near, far, 0.91), (left, near, 0.4)],
    )
    holder: dict[str, RegisteredProduct | None] = {"product": _product()}
    audits: list[dict[str, object]] = []
    settings = Settings(
        environment="test",
        database_url=None,
        supabase_url=SUPABASE_URL,
        duplicate_similarity_threshold=0.86,
        duplicate_neighbor_count=2,
    )
    app = create_app(settings)

    class _Database:
        @asynccontextmanager
        async def user_transaction(self, user: object) -> Any:
            yield conn

    app.state.database = _Database()
    app.dependency_overrides[get_database] = lambda: app.state.database

    async def workspace(connection: object, name: str) -> Workspace:
        return Workspace(tenant_id=uuid4(), name=name, role="owner")

    async def product(connection: object) -> RegisteredProduct | None:
        return holder["product"]

    async def audit(connection: object, **kwargs: object) -> None:
        audits.append(kwargs)

    monkeypatch.setattr("feedback_hub.api.duplicates.ensure_workspace", workspace)
    monkeypatch.setattr("feedback_hub.api.duplicates.get_product", product)
    monkeypatch.setattr("feedback_hub.api.duplicates.record_audit_event", audit)
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
            yield client, tokens, conn, holder, audits


async def test_duplicate_search_requires_a_product(duplicate_api: Any) -> None:
    client, tokens, _conn, holder, _audits = duplicate_api
    holder["product"] = None
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    response = await client.post("/v1/feedback/duplicates", headers=headers)

    assert response.status_code == 404


async def test_duplicate_search_stores_exact_and_semantic_links(duplicate_api: Any) -> None:
    client, tokens, conn, _holder, audits = duplicate_api
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    before = await client.get("/v1/feedback/duplicates", headers=headers)
    created = await client.post("/v1/feedback/duplicates", headers=headers)
    again = await client.get("/v1/feedback/duplicates", headers=headers)

    assert before.status_code == 200
    assert before.json()["ran"] is False
    assert created.status_code == 200
    body = created.json()
    assert body["ran"] is True
    assert body["exact_edges"] == 1
    assert body["semantic_edges"] == 1
    assert body["group_count"] == 2
    assert body["evaluation"]["true_positives"] == 2
    assert body["evaluation"]["false_positives"] == 0
    assert {group["kind"] for group in body["groups"]} == {"exact", "semantic"}
    assert again.json()["group_count"] == 2
    assert len(conn.edges) == 2
    assert audits[-1]["action"] == "dedupe.completed"

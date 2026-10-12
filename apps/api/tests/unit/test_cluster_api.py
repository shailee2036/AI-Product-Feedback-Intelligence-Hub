from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr

from feedback_hub.auth import SupabaseJwtVerifier
from feedback_hub.config import Settings
from feedback_hub.db.engine import get_database
from feedback_hub.db.products import RegisteredProduct
from feedback_hub.db.workspaces import Workspace
from feedback_hub.feedback.groq import GroqError
from feedback_hub.main import create_app
from tests.auth_helpers import SUPABASE_URL, TokenFactory


class _Result:
    def __init__(self, rows: list[Any] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def all(self) -> list[Any]:
        return self._rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._scalar


class _Row:
    def __init__(self, **kwargs: Any) -> None:
        self._mapping = kwargs


class _Conn:
    def __init__(self, items: list[dict[str, Any]], pairs: list[tuple[UUID, UUID, float]]) -> None:
        self.items = items
        self.pairs = pairs
        self.run: dict[str, Any] | None = None
        self.clusters: list[tuple[UUID, list[UUID]]] = []
        self.labels: dict[UUID, tuple[str | None, str | None, bool]] = {}
        self._cluster_id: UUID | None = None

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
        if sql.startswith("delete from public.candidate_cluster_members"):
            self.clusters.clear()
            return _Result()
        if sql.startswith("delete from public.candidate_clusters"):
            self.labels.clear()
            return _Result()
        if sql.startswith("delete from public.analysis_runs"):
            self.run = None
            return _Result()
        if sql.startswith("insert into public.analysis_runs") and isinstance(params, dict):
            self.run = params
            return _Result(scalar=uuid4())
        if sql.startswith("insert into public.candidate_clusters"):
            self._cluster_id = uuid4()
            self.clusters.append((self._cluster_id, []))
            return _Result(scalar=self._cluster_id)
        if sql.startswith("insert into public.candidate_cluster_members") and isinstance(
            params, list
        ):
            member_ids = [row["feedback_item_id"] for row in params if isinstance(row, dict)]
            if self._cluster_id is not None:
                self.clusters[-1] = (self._cluster_id, member_ids)
            return _Result()
        if "from public.analysis_runs" in sql:
            if self.run is None:
                return _Result()
            return _Result(
                [
                    _Row(
                        cluster_count=self.run["cluster_count"],
                        member_count=self.run["member_count"],
                        threshold=self.run["threshold"],
                        neighbor_count=self.run["neighbor_count"],
                        minimum_size=self.run["minimum_size"],
                    )
                ]
            )
        if sql.startswith("update public.candidate_clusters") and isinstance(params, list):
            for row in params:
                if not isinstance(row, dict):
                    continue
                cluster_id = row["id"]
                current = self.labels.get(cluster_id, (None, None, False))
                if current[0] is None and not current[2]:
                    self.labels[cluster_id] = (row["name"], row["summary"], False)
            return _Result()
        if "from public.candidate_clusters" in sql:
            rows: list[_Row] = []
            for cluster_id, member_ids in self.clusters:
                name, summary, edited = self.labels.get(cluster_id, (None, None, False))
                rows.extend(
                    _Row(
                        cluster_id=cluster_id,
                        feedback_item_id=member_id,
                        name=name,
                        summary=summary,
                        name_edited=edited,
                    )
                    for member_id in member_ids
                )
            return _Result(rows)
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


def _item(item_id: UUID, external_id: str, title: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "source": "csv",
        "external_id": external_id,
        "title": title,
        "body": title,
        "language": "en",
        "content_hash": "a" * 64,
    }


@pytest.fixture
async def cluster_api(monkeypatch: pytest.MonkeyPatch) -> Any:
    first, second, third = uuid4(), uuid4(), uuid4()
    conn = _Conn(
        items=[
            _item(first, "AW-SYN-007", "Import progress"),
            _item(second, "AW-SYN-008", "Rejected import rows"),
            _item(third, "AW-SYN-041", "Progreso de importacion"),
        ],
        pairs=[(first, second, 0.95), (second, third, 0.93), (first, third, 0.91)],
    )
    holder: dict[str, RegisteredProduct | None] = {"product": _product()}
    audits: list[dict[str, object]] = []
    settings = Settings(
        environment="test",
        database_url=None,
        supabase_url=SUPABASE_URL,
        gemini_api_key=None,
        groq_api_key=SecretStr("groq-test-key"),
        cluster_similarity_threshold=0.82,
        cluster_neighbor_count=3,
        cluster_minimum_size=3,
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

    monkeypatch.setattr("feedback_hub.api.clusters.ensure_workspace", workspace)
    monkeypatch.setattr("feedback_hub.api.clusters.get_product", product)
    monkeypatch.setattr("feedback_hub.api.clusters.record_audit_event", audit)

    class _Groq:
        def __init__(self) -> None:
            self.prompts: list[str] = []
            self.fail: Exception | None = None

        async def complete(self, prompt: str) -> str:
            self.prompts.append(prompt)
            if self.fail is not None:
                raise self.fail
            return (
                '{"themes":[{"id":"1","name":"Import progress",'
                '"summary":"People want import progress and rejected rows."}]}'
            )

    groq = _Groq()
    app.state.groq = groq
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
            yield client, tokens, conn, holder, audits, groq, settings


async def test_clustering_requires_a_product(cluster_api: Any) -> None:
    client, tokens, _conn, holder, _audits, _groq, _settings = cluster_api
    holder["product"] = None
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    response = await client.post("/v1/feedback/clusters", headers=headers)

    assert response.status_code == 404


async def test_clustering_requires_feedback(cluster_api: Any) -> None:
    client, tokens, conn, _holder, _audits, _groq, _settings = cluster_api
    conn.items = []
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    response = await client.post("/v1/feedback/clusters", headers=headers)

    assert response.status_code == 409
    assert "Import feedback" in response.json()["detail"]


async def test_clustering_requires_embeddings(cluster_api: Any) -> None:
    client, tokens, conn, _holder, _audits, _groq, _settings = cluster_api
    conn.pairs = []
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    response = await client.post("/v1/feedback/clusters", headers=headers)

    assert response.status_code == 409
    assert "Embed feedback" in response.json()["detail"]


async def test_clustering_stores_a_candidate_theme(cluster_api: Any) -> None:
    client, tokens, conn, _holder, audits, _groq, _settings = cluster_api
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    before = await client.get("/v1/feedback/clusters", headers=headers)
    created = await client.post("/v1/feedback/clusters", headers=headers)
    again = await client.get("/v1/feedback/clusters", headers=headers)

    assert before.json()["ran"] is False
    assert created.status_code == 200
    body = created.json()
    assert body["ran"] is True
    assert body["cluster_count"] == 1
    assert body["member_count"] == 3
    assert body["evaluation"]["gathered"] == 1
    assert body["evaluation"]["labeled"] == 1
    assert len(body["clusters"][0]["members"]) == 3
    assert again.json()["cluster_count"] == 1
    assert len(conn.clusters) == 1
    assert audits[-1]["action"] == "cluster.completed"


async def test_naming_requires_a_groq_key(cluster_api: Any) -> None:
    client, tokens, _conn, _holder, _audits, _groq, settings = cluster_api
    settings.groq_api_key = None
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    response = await client.post("/v1/feedback/clusters/names", headers=headers)

    assert response.status_code == 503
    assert "FEEDBACK_HUB_GROQ_API_KEY" in response.json()["detail"]


async def test_naming_requires_themes(cluster_api: Any) -> None:
    client, tokens, _conn, _holder, _audits, groq, _settings = cluster_api
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    response = await client.post("/v1/feedback/clusters/names", headers=headers)

    assert response.status_code == 409
    assert "Find themes" in response.json()["detail"]
    assert groq.prompts == []


async def test_naming_fills_a_blank_theme_and_skips_it_later(cluster_api: Any) -> None:
    client, tokens, conn, _holder, audits, groq, _settings = cluster_api
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}
    conn.items[0]["title"] = "Email ada@example.com about import progress"
    await client.post("/v1/feedback/clusters", headers=headers)

    named = await client.post("/v1/feedback/clusters/names", headers=headers)
    again = await client.post("/v1/feedback/clusters/names", headers=headers)

    assert named.status_code == 200
    assert named.json()["named_count"] == 1
    assert named.json()["clusters"][0]["name"] == "Import progress"
    assert "[email]" in groq.prompts[0]
    assert "ada@example.com" not in groq.prompts[0]
    assert len(groq.prompts) == 1
    assert again.json()["clusters"][0]["name"] == "Import progress"
    assert audits[-1]["action"] == "cluster.named"


async def test_naming_keeps_an_edited_blank(cluster_api: Any) -> None:
    client, tokens, conn, _holder, _audits, groq, _settings = cluster_api
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}
    await client.post("/v1/feedback/clusters", headers=headers)
    conn.labels[conn.clusters[0][0]] = (None, None, True)

    named = await client.post("/v1/feedback/clusters/names", headers=headers)

    assert named.status_code == 200
    assert named.json()["named_count"] == 0
    assert named.json()["clusters"][0]["name"] is None
    assert groq.prompts == []


async def test_naming_keeps_a_stored_name(cluster_api: Any) -> None:
    client, tokens, conn, _holder, _audits, groq, _settings = cluster_api
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}
    await client.post("/v1/feedback/clusters", headers=headers)
    conn.labels[conn.clusters[0][0]] = ("Custom import", "Kept by hand.", False)

    named = await client.post("/v1/feedback/clusters/names", headers=headers)

    assert named.status_code == 200
    assert named.json()["clusters"][0]["name"] == "Custom import"
    assert groq.prompts == []


async def test_naming_reports_a_provider_failure(cluster_api: Any) -> None:
    client, tokens, conn, _holder, _audits, groq, _settings = cluster_api
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}
    await client.post("/v1/feedback/clusters", headers=headers)
    groq.fail = GroqError("Groq did not respond in time.")

    named = await client.post("/v1/feedback/clusters/names", headers=headers)

    assert named.status_code == 502
    assert named.json()["detail"] == "Groq did not respond in time."
    assert conn.labels == {}

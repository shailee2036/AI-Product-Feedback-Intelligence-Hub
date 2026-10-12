import asyncio
from typing import Any

import asyncpg
import httpx
import pytest
import respx

from tests.auth_helpers import TokenFactory
from tests.integration.conftest import CreateUser
from tests.integration.test_product import GITHUB_REPO_URL, bearer

MODEL = "gemini-embedding-001"
EMBED_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents"
CSV = (
    "feedback_id,created_at,language,feedback\n"
    "F-1,2026-06-03T09:15:00Z,en,"
    '"Email ada@example.com about the OAuth callback checklist."\n'
)


@pytest.fixture
def github(appwrite_repo_payload: dict[str, Any]) -> Any:
    with respx.mock(assert_all_called=False) as router:
        router.get(GITHUB_REPO_URL).respond(200, json=appwrite_repo_payload)
        router.post(EMBED_URL).respond(200, json={"embeddings": [{"values": [0.01] * 768}]})
        yield router


async def test_embedding_requires_a_product(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser
) -> None:
    headers = bearer(tokens.token(await create_user("pm@example.com")))

    response = await api.post("/v1/feedback/embeddings", headers=headers)

    assert response.status_code == 404


async def test_embedding_redacts_before_storing_a_vector(
    api: httpx.AsyncClient,
    tokens: TokenFactory,
    create_user: CreateUser,
    github: respx.Router,
    database_url: str,
) -> None:
    headers = bearer(tokens.token(await create_user("pm@example.com")))
    created = await api.post(
        "/v1/product/github", json={"repository": "appwrite/appwrite"}, headers=headers
    )
    assert created.status_code == 201
    uploaded = await api.post(
        "/v1/product/csv",
        headers=headers,
        files={"file": ("feedback.csv", CSV.encode(), "text/csv")},
    )
    assert uploaded.status_code == 201

    started = await api.post("/v1/feedback/embeddings", headers=headers)
    assert started.status_code == 202

    body: dict[str, Any] = {}
    for _ in range(50):
        current = await api.get("/v1/feedback/embeddings/current", headers=headers)
        body = current.json()
        if body["status"] in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.05)

    assert body["status"] == "succeeded", body
    assert body["embedded_count"] == 1
    assert body["redaction_count"] == 1
    assert body["stored_count"] == 1
    sent = github.calls.last.request
    assert b"ada@example.com" not in sent.content
    assert b"[email]" in sent.content

    conn = await asyncpg.connect(database_url)
    try:
        row = await conn.fetchrow(
            "select body, redaction_count from public.feedback_items "
            "where product_id = $1 and source = 'csv'",
            created.json()["id"],
        )
    finally:
        await conn.close()
    assert row is not None
    assert "ada@example.com" in row["body"]
    assert row["redaction_count"] == 1

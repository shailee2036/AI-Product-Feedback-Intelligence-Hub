from typing import Any

import asyncpg
import httpx
import pytest
import respx

from tests.auth_helpers import TokenFactory
from tests.integration.conftest import CreateUser
from tests.integration.test_product import GITHUB_REPO_URL, bearer

CSV = (
    "feedback_id,created_at,language,feedback\n"
    "D-1,2026-06-03T09:15:00Z,en,"
    '"The callback checklist is hard to follow for production."\n'
    "D-2,2026-06-03T09:16:00Z,en,"
    '"The callback checklist is hard to follow for production."\n'
    "D-3,2026-06-03T09:17:00Z,en,"
    '"Storage quotas should be visible per bucket for each feature."\n'
    "D-4,2026-06-03T09:18:00Z,en,"
    '"Please show which bucket is using the storage quota."\n'
)


def _vector(index: int) -> str:
    values = ["0"] * 768
    values[index] = "1"
    return "[" + ",".join(values) + "]"


@pytest.fixture
def github(appwrite_repo_payload: dict[str, Any]) -> Any:
    with respx.mock(assert_all_called=False) as router:
        router.get(GITHUB_REPO_URL).respond(200, json=appwrite_repo_payload)
        yield router


async def test_duplicate_search_requires_a_product(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser
) -> None:
    headers = bearer(tokens.token(await create_user("dedupe@example.com")))

    response = await api.post("/v1/feedback/duplicates", headers=headers)

    assert response.status_code == 404


async def test_duplicate_search_links_exact_text_and_close_vectors(
    api: httpx.AsyncClient,
    tokens: TokenFactory,
    create_user: CreateUser,
    github: respx.Router,
    database_url: str,
) -> None:
    del github
    headers = bearer(tokens.token(await create_user("dedupe@example.com")))
    created = await api.post(
        "/v1/product/github", json={"repository": "appwrite/appwrite"}, headers=headers
    )
    assert created.status_code == 201
    product_id = created.json()["id"]
    uploaded = await api.post(
        "/v1/product/csv",
        headers=headers,
        files={"file": ("feedback.csv", CSV.encode(), "text/csv")},
    )
    assert uploaded.status_code == 201

    conn = await asyncpg.connect(database_url)
    try:
        product = await conn.fetchrow(
            "select tenant_id from public.products where id = $1", product_id
        )
        assert product is not None
        run_id = await conn.fetchval(
            "insert into public.embedding_runs (tenant_id, product_id, status, provider, "
            "model, model_version, dimensions) values ($1, $2, 'succeeded', 'gemini', "
            "'gemini-embedding-001', '1', 768) returning id",
            product["tenant_id"],
            product_id,
        )
        rows = await conn.fetch(
            "select id, external_id from public.feedback_items "
            "where product_id = $1 and source = 'csv'",
            product_id,
        )
        for row in rows:
            slot = 0 if row["external_id"] in {"D-3", "D-4"} else 1
            await conn.execute(
                "insert into public.feedback_embeddings (tenant_id, product_id, "
                "feedback_item_id, embedding_run_id, provider, model, model_version, "
                "dimensions, embedding, content_hash) values ($1, $2, $3, $4, 'gemini', "
                "'gemini-embedding-001', '1', 768, $5::extensions.vector, $6)",
                product["tenant_id"],
                product_id,
                row["id"],
                run_id,
                _vector(slot),
                "a" * 64,
            )
    finally:
        await conn.close()

    found = await api.post("/v1/feedback/duplicates", headers=headers)
    assert found.status_code == 200, found.text
    body = found.json()
    assert body["exact_edges"] == 1
    assert body["semantic_edges"] == 1
    assert body["group_count"] == 2
    assert body["evaluation"] is None

    again = await api.post("/v1/feedback/duplicates", headers=headers)
    assert again.status_code == 200
    current = await api.get("/v1/feedback/duplicates", headers=headers)
    assert current.json()["group_count"] == 2

    conn = await asyncpg.connect(database_url)
    try:
        stored = await conn.fetchval(
            "select count(*) from public.duplicate_edges where product_id = $1", product_id
        )
    finally:
        await conn.close()
    assert stored == 2

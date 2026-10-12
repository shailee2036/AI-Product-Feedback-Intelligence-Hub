import json
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
    "T-1,2026-06-03T09:15:00Z,en,"
    '"Show import progress and let me download the rejected rows."\n'
    "T-2,2026-06-03T09:16:00Z,en,"
    '"A large import should report progress and rejected rows."\n'
    "T-3,2026-06-03T09:17:00Z,en,"
    '"Quiero ver el progreso de una importacion y las filas rechazadas."\n'
    "T-4,2026-06-03T09:18:00Z,en,"
    '"Realtime should warn me when a reconnect may have missed events."\n'
    "T-5,2026-06-03T09:19:00Z,en,"
    '"After reconnect the app should show that data may be stale."\n'
    "T-6,2026-06-03T09:20:00Z,en,"
    '"Una reconexion deberia indicar si hay que sincronizar otra vez."\n'
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


async def test_clustering_requires_a_product(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser
) -> None:
    headers = bearer(tokens.token(await create_user("themes@example.com")))

    response = await api.post("/v1/feedback/clusters", headers=headers)

    assert response.status_code == 404


async def test_clustering_groups_close_vectors(
    api: httpx.AsyncClient,
    tokens: TokenFactory,
    create_user: CreateUser,
    github: respx.Router,
    database_url: str,
) -> None:
    github.post("https://api.groq.com/openai/v1/chat/completions").respond(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "themes": [
                                    {
                                        "id": "1",
                                        "name": "Import progress",
                                        "summary": "People want import progress and rejected rows.",
                                    },
                                    {
                                        "id": "2",
                                        "name": "Reconnect warning",
                                        "summary": "People want a warning after reconnect.",
                                    },
                                ]
                            }
                        )
                    }
                }
            ]
        },
    )
    headers = bearer(tokens.token(await create_user("themes-rows@example.com")))
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

    missing = await api.post("/v1/feedback/clusters", headers=headers)
    assert missing.status_code == 409
    unnamed = await api.post("/v1/feedback/clusters/names", headers=headers)
    assert unnamed.status_code == 409

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
            slot = 0 if row["external_id"] in {"T-1", "T-2", "T-3"} else 1
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
                "b" * 64,
            )
    finally:
        await conn.close()

    found = await api.post("/v1/feedback/clusters", headers=headers)
    assert found.status_code == 200, found.text
    body = found.json()
    assert body["cluster_count"] == 2
    assert body["member_count"] == 6
    assert body["evaluation"] is None

    again = await api.post("/v1/feedback/clusters", headers=headers)
    assert again.status_code == 200
    current = await api.get("/v1/feedback/clusters", headers=headers)
    assert current.json()["cluster_count"] == 2

    named = await api.post("/v1/feedback/clusters/names", headers=headers)
    assert named.status_code == 200, named.text
    assert named.json()["named_count"] == 2
    names = {cluster["name"] for cluster in named.json()["clusters"]}
    assert names == {"Import progress", "Reconnect warning"}

    repeated = await api.post("/v1/feedback/clusters/names", headers=headers)
    assert repeated.status_code == 200
    assert repeated.json()["named_count"] == 2
    groq_calls = [
        call for call in github.calls if str(call.request.url).endswith("/chat/completions")
    ]
    assert len(groq_calls) == 1

    conn = await asyncpg.connect(database_url)
    try:
        stored = await conn.fetchval(
            "select count(*) from public.candidate_clusters where product_id = $1", product_id
        )
        filled = await conn.fetchval(
            "select count(*) from public.candidate_clusters "
            "where product_id = $1 and name is not null and name_edited = false",
            product_id,
        )
    finally:
        await conn.close()
    assert stored == 2
    assert filled == 2

    themes = named.json()["clusters"]
    import_theme = next(theme for theme in themes if theme["name"] == "Import progress")
    renamed = await api.patch(
        f"/v1/feedback/clusters/{import_theme['id']}",
        headers=headers,
        json={"name": "Import status", "summary": "People want import progress."},
    )
    assert renamed.status_code == 200
    approved = await api.post(
        f"/v1/feedback/clusters/{import_theme['id']}/decision",
        headers=headers,
        json={"decision": "approve"},
    )
    assert approved.status_code == 200

    refound = await api.post("/v1/feedback/clusters", headers=headers)
    assert refound.status_code == 200, refound.text
    kept = next(theme for theme in refound.json()["clusters"] if theme["id"] == import_theme["id"])
    assert kept["status"] == "approved"
    assert kept["name"] == "Import status"
    open_theme = next(theme for theme in refound.json()["clusters"] if theme["status"] == "open")
    split = await api.post(
        f"/v1/feedback/clusters/{open_theme['id']}/split",
        headers=headers,
        json={"member_ids": [open_theme["members"][0]["id"]]},
    )
    assert split.status_code == 200
    assert split.json()["cluster_count"] == 3
    created = next(
        theme
        for theme in split.json()["clusters"]
        if theme["id"] not in {import_theme["id"], open_theme["id"]}
    )
    merged = await api.post(
        f"/v1/feedback/clusters/{created['id']}/merge",
        headers=headers,
        json={"target_id": open_theme["id"]},
    )
    assert merged.status_code == 200
    assert merged.json()["cluster_count"] == 2
    assert any(theme["id"] == import_theme["id"] for theme in merged.json()["clusters"])

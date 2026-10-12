import asyncio
import uuid
from typing import Any

import asyncpg
import httpx
import pytest
import respx

from tests.auth_helpers import TokenFactory
from tests.integration.conftest import CreateUser
from tests.integration.test_product import GITHUB_REPO_URL, bearer

ISSUES_URL = "https://api.github.com/repos/appwrite/appwrite/issues"


def _issue(number: int, *, pull_request: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "node_id": f"I_kwDO{number}",
        "number": number,
        "title": f"Issue {number}",
        "body": "Customers cannot complete login.",
        "state": "open",
        "html_url": f"https://github.com/appwrite/appwrite/issues/{number}",
        "user": {"login": "ada", "node_id": "U_ada", "type": "User"},
        "labels": [{"name": "bug"}],
        "comments": 1,
        "reactions": {"total_count": 2},
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-11T00:00:00Z",
    }
    if pull_request:
        payload["pull_request"] = {"url": "https://api.github.com/pulls/1"}
    return payload


@pytest.fixture
def github(appwrite_repo_payload: dict[str, Any]) -> Any:
    with respx.mock(assert_all_called=False) as router:
        router.get(GITHUB_REPO_URL).respond(200, json=appwrite_repo_payload)
        router.get(ISSUES_URL).respond(
            200,
            json=[_issue(7), _issue(8, pull_request=True), _issue(9)],
            headers={"etag": '"page-1"'},
        )
        yield router


async def _register(api: httpx.AsyncClient, headers: dict[str, str]) -> None:
    created = await api.post(
        "/v1/product/github", json={"repository": "appwrite/appwrite"}, headers=headers
    )
    assert created.status_code == 201


async def _wait(api: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for _ in range(50):
        response = await api.get("/v1/imports/current", headers=headers)
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"succeeded", "failed", "cancelled"}:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError(body)


async def test_import_requires_a_product(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser
) -> None:
    headers = bearer(tokens.token(await create_user("pm@example.com")))

    response = await api.post("/v1/imports", headers=headers)

    assert response.status_code == 404


async def test_import_stores_issues_and_skips_pull_requests(
    api: httpx.AsyncClient,
    tokens: TokenFactory,
    create_user: CreateUser,
    github: respx.Router,
    database_url: str,
) -> None:
    user_id = await create_user("pm@example.com")
    headers = bearer(tokens.token(user_id))
    await _register(api, headers)

    started = await api.post("/v1/imports", headers={**headers, "Idempotency-Key": "import-key-1"})
    assert started.status_code == 202
    replay = await api.post("/v1/imports", headers={**headers, "Idempotency-Key": "import-key-1"})
    assert replay.status_code == 200
    assert replay.json()["id"] == started.json()["id"]

    finished = await _wait(api, headers)
    assert finished["status"] == "succeeded"
    assert finished["imported_count"] == 2
    assert finished["skipped_count"] == 1

    feedback = await api.get("/v1/feedback", headers=headers)
    assert feedback.status_code == 200
    body = feedback.json()
    assert body["total"] == 2
    assert {item["number"] for item in body["items"]} == {7, 9}
    visible = " ".join(
        value
        for item in body["items"]
        for key, value in item.items()
        if key != "id" and isinstance(value, str)
    )
    assert "ada" not in visible

    conn = await asyncpg.connect(database_url)
    try:
        actions = await conn.fetch(
            "select action from public.audit_events where actor_id = $1 order by id", user_id
        )
    finally:
        await conn.close()
    assert [row["action"] for row in actions] == [
        "product.registered",
        "import.started",
        "import.completed",
    ]


async def test_running_import_conflicts_and_can_be_cancelled(
    api: httpx.AsyncClient,
    tokens: TokenFactory,
    create_user: CreateUser,
    github: respx.Router,
    database_url: str,
) -> None:
    headers = bearer(tokens.token(await create_user("pm@example.com")))
    await _register(api, headers)

    product_id = (await api.get("/v1/product", headers=headers)).json()["id"]
    conn = await asyncpg.connect(database_url)
    try:
        ids = await conn.fetchrow(
            "select p.tenant_id, p.id as product_id, r.id as repository_id "
            "from public.products p join public.github_repositories r on r.product_id = p.id "
            "where p.id = $1",
            uuid.UUID(product_id),
        )
        assert ids is not None
        import_id = uuid.uuid4()
        await conn.execute(
            "insert into public.imports (id, tenant_id, product_id, repository_id, source, "
            "status, issue_limit) values ($1, $2, $3, $4, 'github_issues', 'running', 100)",
            import_id,
            ids["tenant_id"],
            ids["product_id"],
            ids["repository_id"],
        )
    finally:
        await conn.close()

    conflict = await api.post("/v1/imports", headers=headers)
    assert conflict.status_code == 409

    cancelled = await api.post(f"/v1/imports/{import_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

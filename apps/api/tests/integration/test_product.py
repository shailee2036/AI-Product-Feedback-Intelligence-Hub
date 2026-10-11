import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import asyncpg
import httpx
import pytest
import respx

from tests.auth_helpers import TokenFactory
from tests.integration.conftest import CreateUser

GITHUB_REPO_URL = "https://api.github.com/repos/appwrite/appwrite"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def audit_actions(database_url: str, user_id: uuid.UUID) -> list[str]:
    conn = await asyncpg.connect(database_url)
    try:
        rows = await conn.fetch(
            "select action from public.audit_events where actor_id = $1 order by id", user_id
        )
    finally:
        await conn.close()
    return [row["action"] for row in rows]


@pytest.fixture
def github(appwrite_repo_payload: dict[str, Any]) -> Iterator[respx.Router]:
    with respx.mock(assert_all_called=False) as router:
        router.get(GITHUB_REPO_URL).respond(200, json=appwrite_repo_payload)
        yield router


async def test_register_and_read_product(
    api: httpx.AsyncClient,
    tokens: TokenFactory,
    create_user: CreateUser,
    github: respx.Router,
    database_url: str,
) -> None:
    user_id = await create_user("pm@example.com")
    headers = bearer(tokens.token(user_id))

    assert (await api.get("/v1/product", headers=headers)).status_code == 404

    created = await api.post(
        "/v1/product/github",
        json={"repository": "https://github.com/appwrite/appwrite"},
        headers=headers,
    )

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "appwrite"
    assert body["repository"]["full_name"] == "appwrite/appwrite"
    assert body["repository"]["license_spdx"] == "BSD-3-Clause"
    assert body["repository"]["license_checked_at"] is not None

    read = await api.get("/v1/product", headers=headers)
    assert read.json() == body
    assert await audit_actions(database_url, user_id) == ["product.registered"]


async def test_second_registration_conflicts(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser, github: respx.Router
) -> None:
    headers = bearer(tokens.token(await create_user("pm@example.com")))
    payload = {"repository": "appwrite/appwrite"}

    first = await api.post("/v1/product/github", json=payload, headers=headers)
    second = await api.post("/v1/product/github", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409


async def test_concurrent_registrations_create_one_product(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser, github: respx.Router
) -> None:
    headers = bearer(tokens.token(await create_user("pm@example.com")))
    await api.get("/v1/me", headers=headers)
    payload = {"repository": "appwrite/appwrite"}

    responses = await asyncio.gather(
        *(api.post("/v1/product/github", json=payload, headers=headers) for _ in range(3))
    )

    assert sorted(r.status_code for r in responses) == [201, 409, 409]


async def test_ineligible_repository_is_rejected_and_audited(
    api: httpx.AsyncClient,
    tokens: TokenFactory,
    create_user: CreateUser,
    appwrite_repo_payload: dict[str, Any],
    database_url: str,
) -> None:
    user_id = await create_user("pm@example.com")
    headers = bearer(tokens.token(user_id))

    with respx.mock:
        respx.get(GITHUB_REPO_URL).respond(
            200, json={**appwrite_repo_payload, "archived": True, "license": None}
        )
        response = await api.post(
            "/v1/product/github", json={"repository": "appwrite/appwrite"}, headers=headers
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert set(detail["reasons"]) == {"archived", "license_missing"}
    assert (await api.get("/v1/product", headers=headers)).status_code == 404
    assert await audit_actions(database_url, user_id) == ["product.registration_rejected"]


async def test_products_are_isolated_between_workspaces(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser, github: respx.Router
) -> None:
    alice = bearer(tokens.token(await create_user("alice@example.com")))
    bob = bearer(tokens.token(await create_user("bob@example.com")))

    await api.post("/v1/product/github", json={"repository": "appwrite/appwrite"}, headers=alice)

    assert (await api.get("/v1/product", headers=bob)).status_code == 404
    registered = await api.post(
        "/v1/product/github", json={"repository": "appwrite/appwrite"}, headers=bob
    )
    assert registered.status_code == 201


async def test_registration_requires_authentication(api: httpx.AsyncClient) -> None:
    response = await api.post("/v1/product/github", json={"repository": "appwrite/appwrite"})

    assert response.status_code == 401


async def test_invalid_reference_is_rejected_before_github(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser, github: respx.Router
) -> None:
    headers = bearer(tokens.token(await create_user("pm@example.com")))

    response = await api.post(
        "/v1/product/github", json={"repository": "../../etc"}, headers=headers
    )

    assert response.status_code == 422
    assert not github.routes[0].called

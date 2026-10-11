import httpx

from tests.auth_helpers import TokenFactory
from tests.integration.conftest import CreateUser


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_first_call_provisions_workspace_idempotently(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser
) -> None:
    user_id = await create_user("maya@example.com")
    token = tokens.token(user_id, email="maya@example.com")

    first = await api.get("/v1/me", headers=bearer(token))
    second = await api.get("/v1/me", headers=bearer(token))

    assert first.status_code == 200
    body = first.json()
    assert body["user_id"] == str(user_id)
    assert body["workspace"]["name"] == "maya's workspace"
    assert body["workspace"]["role"] == "owner"
    assert second.json()["workspace"]["id"] == body["workspace"]["id"]


async def test_users_get_separate_workspaces(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser
) -> None:
    alice = await create_user("alice@example.com")
    bob = await create_user("bob@example.com")

    alice_ws = (await api.get("/v1/me", headers=bearer(tokens.token(alice)))).json()
    bob_ws = (await api.get("/v1/me", headers=bearer(tokens.token(bob)))).json()

    assert alice_ws["workspace"]["id"] != bob_ws["workspace"]["id"]


async def test_requires_authentication(api: httpx.AsyncClient) -> None:
    response = await api.get("/v1/me")

    assert response.status_code == 401


async def test_readiness_checks_database(api: httpx.AsyncClient) -> None:
    response = await api.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok"}

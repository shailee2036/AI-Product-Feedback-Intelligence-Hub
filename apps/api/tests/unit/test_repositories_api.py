from typing import Any

import httpx
import pytest
import respx

GITHUB_REPO_URL = "https://api.github.com/repos/appwrite/appwrite"


@respx.mock
async def test_eligible_repository(
    client: httpx.AsyncClient, appwrite_repo_payload: dict[str, Any]
) -> None:
    route = respx.get(GITHUB_REPO_URL).respond(200, json=appwrite_repo_payload)

    response = await client.post(
        "/v1/repositories/eligibility",
        json={"repository": "https://github.com/appwrite/appwrite"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["eligible"] is True
    assert body["repository"]["full_name"] == "appwrite/appwrite"
    sent = route.calls.last.request
    assert sent.headers["X-GitHub-Api-Version"]
    assert sent.headers["Accept"] == "application/vnd.github+json"


@respx.mock
async def test_ineligible_repository_returns_reasons(
    client: httpx.AsyncClient, appwrite_repo_payload: dict[str, Any]
) -> None:
    respx.get(GITHUB_REPO_URL).respond(200, json={**appwrite_repo_payload, "archived": True})

    response = await client.post(
        "/v1/repositories/eligibility", json={"repository": "appwrite/appwrite"}
    )

    assert response.status_code == 200
    assert response.json()["reasons"] == ["archived"]


async def test_invalid_reference_never_calls_github(client: httpx.AsyncClient) -> None:
    with respx.mock(assert_all_called=False) as mock:
        github = mock.route(host="api.github.com")
        response = await client.post(
            "/v1/repositories/eligibility", json={"repository": "../../users/me"}
        )

    assert response.status_code == 422
    assert not github.called


@pytest.mark.parametrize(
    ("github_response", "expected_status"),
    [
        (httpx.Response(404), 404),
        (httpx.Response(403, headers={"x-ratelimit-remaining": "0"}), 503),
        (httpx.Response(429, headers={"retry-after": "30"}), 503),
        (httpx.Response(403), 502),
        (httpx.Response(301, headers={"location": "https://api.github.com/x"}), 502),
        (httpx.Response(500), 502),
    ],
)
@respx.mock
async def test_github_failures_map_to_api_errors(
    client: httpx.AsyncClient, github_response: httpx.Response, expected_status: int
) -> None:
    respx.get(GITHUB_REPO_URL).mock(return_value=github_response)

    response = await client.post(
        "/v1/repositories/eligibility", json={"repository": "appwrite/appwrite"}
    )

    assert response.status_code == expected_status


@respx.mock
async def test_rate_limit_reset_is_parsed(client: httpx.AsyncClient) -> None:
    from feedback_hub.github.client import GitHubClient, GitHubRateLimitedError
    from feedback_hub.github.refs import RepositoryRef

    respx.get(GITHUB_REPO_URL).respond(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000000"}
    )

    async with httpx.AsyncClient(base_url="https://api.github.com") as http:
        with pytest.raises(GitHubRateLimitedError) as caught:
            await GitHubClient(http).get_repository(RepositoryRef("appwrite", "appwrite"))

    assert caught.value.reset_at is not None
    assert caught.value.reset_at.year == 2023

import httpx
import pytest
import respx

from feedback_hub.github.client import GitHubClient, GitHubError, GitHubRateLimitedError

ISSUES_URL = "https://api.github.com/repos/appwrite/appwrite/issues"


@respx.mock
async def test_issue_page_requests_newest_updates_and_reads_the_next_link() -> None:
    route = respx.get(ISSUES_URL).respond(
        200,
        json=[{"number": 1}, {"number": 2}],
        headers={
            "etag": '"page-1"',
            "link": '<https://api.github.com/repos/appwrite/appwrite/issues?page=2>; rel="next"',
        },
    )
    async with httpx.AsyncClient(base_url="https://api.github.com") as http:
        page = await GitHubClient(http).list_issues_page(
            "appwrite", "appwrite", page=1, per_page=100
        )

    assert [item["number"] for item in page.issues] == [1, 2]
    assert page.etag == '"page-1"'
    assert page.has_next is True
    assert page.not_modified is False
    sent = route.calls.last.request
    assert sent.url.params["state"] == "all"
    assert sent.url.params["sort"] == "updated"
    assert sent.url.params["direction"] == "desc"
    assert "if-none-match" not in sent.headers


@respx.mock
async def test_matching_etag_short_circuits_the_page() -> None:
    route = respx.get(ISSUES_URL).respond(304)
    async with httpx.AsyncClient(base_url="https://api.github.com") as http:
        page = await GitHubClient(http).list_issues_page(
            "appwrite", "appwrite", page=1, per_page=100, etag='"page-1"'
        )

    assert page.not_modified is True
    assert page.issues == []
    assert route.calls.last.request.headers["if-none-match"] == '"page-1"'


@respx.mock
async def test_rate_limit_on_issue_pages_is_reported() -> None:
    respx.get(ISSUES_URL).respond(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "0"}
    )
    async with httpx.AsyncClient(base_url="https://api.github.com") as http:
        with pytest.raises(GitHubRateLimitedError):
            await GitHubClient(http).list_issues_page("appwrite", "appwrite", page=1, per_page=100)


@respx.mock
async def test_issue_page_ignores_entries_that_are_not_objects() -> None:
    respx.get(ISSUES_URL).respond(200, json=[{"number": 1}, "nope", None])
    async with httpx.AsyncClient(base_url="https://api.github.com") as http:
        page = await GitHubClient(http).list_issues_page(
            "appwrite", "appwrite", page=1, per_page=100
        )

    assert page.issues == [{"number": 1}]


@respx.mock
async def test_unexpected_issue_payloads_are_rejected() -> None:
    respx.get(ISSUES_URL).respond(200, json={"message": "nope"})
    async with httpx.AsyncClient(base_url="https://api.github.com") as http:
        with pytest.raises(GitHubError, match="not a list"):
            await GitHubClient(http).list_issues_page("appwrite", "appwrite", page=1, per_page=100)


@respx.mock
async def test_an_unreachable_issue_page_hides_the_connection_detail() -> None:
    respx.get(ISSUES_URL).mock(side_effect=httpx.ConnectError("dial tcp secret.example:443"))
    async with httpx.AsyncClient(base_url="https://api.github.com") as http:
        with pytest.raises(GitHubError, match="did not respond") as caught:
            await GitHubClient(http).list_issues_page("appwrite", "appwrite", page=1, per_page=100)

    assert "secret.example" not in str(caught.value)


@respx.mock
async def test_issue_page_http_errors_are_reported() -> None:
    respx.get(ISSUES_URL).respond(500)
    async with httpx.AsyncClient(base_url="https://api.github.com") as http:
        with pytest.raises(GitHubError, match="HTTP 500"):
            await GitHubClient(http).list_issues_page("appwrite", "appwrite", page=1, per_page=100)

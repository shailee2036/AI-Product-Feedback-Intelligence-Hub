from datetime import UTC, datetime
from typing import Any

import httpx

from feedback_hub import __version__
from feedback_hub.config import Settings
from feedback_hub.github.refs import RepositoryRef


class GitHubError(Exception):
    pass


class RepositoryNotFoundError(GitHubError):
    pass


class GitHubRateLimitedError(GitHubError):
    def __init__(self, reset_at: datetime | None) -> None:
        super().__init__("GitHub API rate limit exceeded.")
        self.reset_at = reset_at


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": settings.github_api_version,
        "User-Agent": f"feedback-hub/{__version__}",
    }
    if settings.github_token is not None:
        headers["Authorization"] = f"Bearer {settings.github_token.get_secret_value()}"
    return httpx.AsyncClient(
        base_url=settings.github_api_base_url,
        headers=headers,
        timeout=settings.github_timeout_seconds,
        follow_redirects=False,
    )


class IssuePage:
    def __init__(
        self,
        issues: list[dict[str, Any]],
        *,
        etag: str | None,
        has_next: bool,
        not_modified: bool,
    ) -> None:
        self.issues = issues
        self.etag = etag
        self.has_next = has_next
        self.not_modified = not_modified


class GitHubClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def get_repository(self, ref: RepositoryRef) -> dict[str, Any]:
        response = await self._http.get(f"/repos/{ref.owner}/{ref.name}")
        if response.status_code == 404:
            raise RepositoryNotFoundError(ref.full_name)
        if response.status_code in {403, 429} and _is_rate_limited(response):
            raise GitHubRateLimitedError(_reset_time(response))
        if response.status_code == 301:
            raise GitHubError("Repository has moved; register its current owner/name.")
        if response.is_error:
            raise GitHubError(f"GitHub returned HTTP {response.status_code}.")
        payload: dict[str, Any] = response.json()
        return payload

    async def list_issues_page(
        self,
        owner: str,
        name: str,
        *,
        page: int,
        per_page: int,
        etag: str | None = None,
    ) -> IssuePage:
        """One page of issues, newest update first. Callers skip pull requests."""
        headers = {"If-None-Match": etag} if etag else None
        response = await self._http.get(
            f"/repos/{owner}/{name}/issues",
            params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
            },
            headers=headers,
        )
        if response.status_code == 304:
            return IssuePage([], etag=etag, has_next=False, not_modified=True)
        if response.status_code in {403, 429} and _is_rate_limited(response):
            raise GitHubRateLimitedError(_reset_time(response))
        if response.is_error:
            raise GitHubError(f"GitHub returned HTTP {response.status_code}.")
        payload = response.json()
        if not isinstance(payload, list):
            raise GitHubError("GitHub issues response was not a list.")
        issues = [item for item in payload if isinstance(item, dict)]
        return IssuePage(
            issues,
            etag=response.headers.get("etag"),
            has_next=_has_next_page(response),
            not_modified=False,
        )


def _has_next_page(response: httpx.Response) -> bool:
    return any('rel="next"' in part for part in response.headers.get("link", "").split(","))


def _is_rate_limited(response: httpx.Response) -> bool:
    return response.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in response.headers


def _reset_time(response: httpx.Response) -> datetime | None:
    reset = response.headers.get("x-ratelimit-reset")
    if reset is None or not reset.isdigit():
        return None
    return datetime.fromtimestamp(int(reset), tz=UTC)

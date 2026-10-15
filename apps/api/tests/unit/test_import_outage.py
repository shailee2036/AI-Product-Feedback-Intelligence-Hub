from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import httpx
import pytest
import respx

from feedback_hub.auth import AuthenticatedUser
from feedback_hub.db.imports import ImportTarget
from feedback_hub.github.client import GitHubClient
from feedback_hub.importing import runner

ISSUES_URL = "https://api.github.com/repos/appwrite/appwrite/issues"


class _Database:
    @asynccontextmanager
    async def user_transaction(self, user: AuthenticatedUser) -> Any:
        yield object()


@respx.mock
async def test_an_unreachable_github_fails_the_import_without_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import_id = uuid4()
    target = ImportTarget(
        id=import_id,
        status="queued",
        issue_limit=10,
        tenant_id=uuid4(),
        product_id=uuid4(),
        owner="appwrite",
        name="appwrite",
    )
    failed: dict[str, str] = {}
    audits: list[str] = []

    async def load_target(conn: object, requested: object) -> ImportTarget:
        assert requested == import_id
        return target

    async def mark_running(conn: object, requested: object) -> None:
        assert requested == import_id

    async def previous_page_etag(conn: object, product_id: object) -> None:
        assert product_id == target.product_id

    async def is_cancelled(conn: object, requested: object) -> bool:
        assert requested == import_id
        return False

    async def mark_failed(conn: object, requested: object, message: str) -> None:
        assert requested == import_id
        failed["message"] = message

    async def record_audit_event(conn: object, **kwargs: object) -> None:
        audits.append(str(kwargs["action"]))

    monkeypatch.setattr(runner, "load_target", load_target)
    monkeypatch.setattr(runner, "mark_running", mark_running)
    monkeypatch.setattr(runner, "previous_page_etag", previous_page_etag)
    monkeypatch.setattr(runner, "is_cancelled", is_cancelled)
    monkeypatch.setattr(runner, "mark_failed", mark_failed)
    monkeypatch.setattr(runner, "record_audit_event", record_audit_event)
    respx.get(ISSUES_URL).mock(side_effect=httpx.ConnectError("dial tcp secret.example:443"))

    async with httpx.AsyncClient(base_url="https://api.github.com") as http:
        await runner.run_import(
            _Database(),  # type: ignore[arg-type]
            GitHubClient(http),
            AuthenticatedUser(id=uuid4(), email=None, claims={}),
            import_id,
        )

    assert failed["message"] == "GitHub did not respond."
    assert "secret.example" not in failed["message"]
    assert audits == ["import.failed"]

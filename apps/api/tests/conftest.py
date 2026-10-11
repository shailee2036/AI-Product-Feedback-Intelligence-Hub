from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from feedback_hub.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            yield http


@pytest.fixture
def appwrite_repo_payload() -> dict[str, Any]:
    """Trimmed `GET /repos/appwrite/appwrite` response with the fields the gate reads."""
    return {
        "node_id": "MDEwOlJlcG9zaXRvcnkxNjE3NDQ1MjA=",
        "name": "appwrite",
        "full_name": "appwrite/appwrite",
        "html_url": "https://github.com/appwrite/appwrite",
        "private": False,
        "visibility": "public",
        "owner": {"login": "appwrite", "type": "Organization"},
        "license": {"key": "bsd-3-clause", "spdx_id": "BSD-3-Clause"},
        "has_issues": True,
        "archived": False,
        "disabled": False,
        "default_branch": "main",
        "open_issues_count": 812,
    }

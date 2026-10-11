from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from tests.auth_helpers import TokenFactory
from tests.integration.conftest import CreateUser
from tests.integration.test_product import GITHUB_REPO_URL, bearer

SEED = Path(__file__).resolve().parents[4] / "seed-data" / "appwrite-customer-feedback.csv"


@pytest.fixture
def github(appwrite_repo_payload: dict[str, Any]) -> Any:
    with respx.mock(assert_all_called=False) as router:
        router.get(GITHUB_REPO_URL).respond(200, json=appwrite_repo_payload)
        yield router


async def _register(api: httpx.AsyncClient, headers: dict[str, str]) -> None:
    created = await api.post(
        "/v1/product/github", json={"repository": "appwrite/appwrite"}, headers=headers
    )
    assert created.status_code == 201


async def test_csv_upload_requires_a_product(
    api: httpx.AsyncClient, tokens: TokenFactory, create_user: CreateUser
) -> None:
    headers = bearer(tokens.token(await create_user("pm@example.com")))

    response = await api.post(
        "/v1/product/csv",
        headers=headers,
        files={
            "file": (
                "feedback.csv",
                b"feedback_id,created_at,feedback\nF-1,2026-01-01T00:00:00Z,hi\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 404


async def test_seed_csv_is_stored_and_a_bad_file_changes_nothing(
    api: httpx.AsyncClient,
    tokens: TokenFactory,
    create_user: CreateUser,
    github: respx.Router,
) -> None:
    headers = bearer(tokens.token(await create_user("pm@example.com")))
    await _register(api, headers)

    uploaded = await api.post(
        "/v1/product/csv",
        headers=headers,
        files={"file": ("appwrite-customer-feedback.csv", SEED.read_bytes(), "text/csv")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["imported_count"] == 42

    saved = await api.get("/v1/feedback", headers=headers, params={"source": "csv", "limit": 50})
    body = saved.json()
    assert body["total"] == 42
    assert all(item["is_synthetic"] for item in body["items"])
    assert all(item["source"] == "csv" for item in body["items"])
    assert all(item["html_url"] is None for item in body["items"])

    rejected = await api.post(
        "/v1/product/csv",
        headers=headers,
        files={"file": ("bad.csv", b"not,a,feedback,file\n1,2,3,4\n", "text/csv")},
    )
    assert rejected.status_code == 422
    again = await api.get("/v1/feedback", headers=headers, params={"source": "csv", "limit": 1})
    assert again.json()["total"] == 42

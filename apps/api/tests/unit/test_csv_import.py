from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest

from feedback_hub.auth import SupabaseJwtVerifier
from feedback_hub.config import Settings
from feedback_hub.db.engine import get_database
from feedback_hub.db.products import RegisteredProduct
from feedback_hub.db.workspaces import Workspace
from feedback_hub.feedback.csv_import import (
    CsvEncodingError,
    CsvTooLargeError,
    csv_title,
    decode_csv,
)
from feedback_hub.feedback.csv_schema import FeedbackRow
from feedback_hub.main import create_app
from tests.auth_helpers import SUPABASE_URL, TokenFactory

SEED = (
    "feedback_id,created_at,source,product_area,is_synthetic,feedback\n"
    "AW-SYN-001,2026-06-03T09:15:00Z,survey,Auth,true,OAuth setup was straightforward.\n"
)


def test_decode_csv_accepts_a_bom_and_rejects_size_and_encoding() -> None:
    assert decode_csv(b"\xef\xbb\xbfhello", max_bytes=20) == "hello"
    with pytest.raises(CsvTooLargeError):
        decode_csv(b"abcdef", max_bytes=3)
    with pytest.raises(CsvEncodingError):
        decode_csv(b"\xff", max_bytes=10)


def test_csv_title_uses_the_product_area() -> None:
    row = FeedbackRow(
        feedback_id="F-1",
        created_at=datetime(2026, 6, 3, 9, 15, tzinfo=UTC),
        feedback="  OAuth   setup  ",
        product_area="Auth",
    )

    assert csv_title(row) == "Auth: OAuth setup"


class _Database:
    @asynccontextmanager
    async def user_transaction(self, user: object) -> Any:
        yield None


@pytest.fixture
async def csv_client() -> Any:
    tokens = TokenFactory()
    settings = Settings(environment="test", database_url=None, supabase_url=SUPABASE_URL)
    app = create_app(settings)
    app.dependency_overrides[get_database] = lambda: _Database()
    async with httpx.AsyncClient() as http:
        app.state.jwt_verifier = SupabaseJwtVerifier(
            http,
            supabase_url=SUPABASE_URL,
            audience="authenticated",
            cache_seconds=600,
            static_keys={tokens.kid: tokens.pyjwk()},
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, tokens


async def test_invalid_csv_is_rejected_before_anything_is_saved(csv_client: Any) -> None:
    client, tokens = csv_client
    headers = {"Authorization": f"Bearer {tokens.token(uuid4())}"}

    response = await client.post(
        "/v1/product/csv",
        headers=headers,
        files={"file": ("feedback.csv", b"feedback_id,created_at\n", "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["reasons"]


async def test_csv_requires_a_registered_product(
    csv_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, tokens = csv_client

    async def workspace(conn: object, name: str) -> Workspace:
        return Workspace(tenant_id=uuid4(), name=name, role="owner")

    async def product(conn: object) -> None:
        return None

    monkeypatch.setattr("feedback_hub.api.csv_import.ensure_workspace", workspace)
    monkeypatch.setattr("feedback_hub.api.csv_import.get_product", product)
    headers = {"Authorization": f"Bearer {tokens.token(uuid4(), email='pm@example.com')}"}

    response = await client.post(
        "/v1/product/csv",
        headers=headers,
        files={"file": ("feedback.csv", SEED.encode(), "text/csv")},
    )

    assert response.status_code == 404


async def test_valid_csv_is_stored_on_the_product(
    csv_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, tokens = csv_client
    saved: dict[str, Any] = {}

    async def workspace(conn: object, name: str) -> Workspace:
        return Workspace(tenant_id=uuid4(), name=name, role="owner")

    async def product(conn: object) -> RegisteredProduct:
        return RegisteredProduct(
            id=uuid4(),
            name="appwrite",
            created_at=datetime(2026, 10, 11, tzinfo=UTC),
            repository_id=uuid4(),
            github_node_id="node",
            full_name="appwrite/appwrite",
            html_url="https://github.com/appwrite/appwrite",
            default_branch="main",
            license_spdx="BSD-3-Clause",
            license_checked_at=None,
        )

    async def create_import(conn: object, **kwargs: Any) -> Any:
        saved["count"] = kwargs["row_count"]
        return uuid4()

    async def upsert(conn: object, **kwargs: Any) -> None:
        saved["rows"] = kwargs["rows"]

    async def audit(conn: object, **kwargs: Any) -> None:
        saved["action"] = kwargs["action"]

    monkeypatch.setattr("feedback_hub.api.csv_import.ensure_workspace", workspace)
    monkeypatch.setattr("feedback_hub.api.csv_import.get_product", product)
    monkeypatch.setattr("feedback_hub.api.csv_import.create_csv_import", create_import)
    monkeypatch.setattr("feedback_hub.api.csv_import.upsert_csv_rows", upsert)
    monkeypatch.setattr("feedback_hub.api.csv_import.record_audit_event", audit)
    headers = {"Authorization": f"Bearer {tokens.token(uuid4(), email='pm@example.com')}"}

    response = await client.post(
        "/v1/product/csv",
        headers=headers,
        files={"file": ("feedback.csv", SEED.encode(), "text/csv")},
    )

    assert response.status_code == 201
    assert response.json()["imported_count"] == 1
    assert saved["count"] == 1
    assert saved["rows"][0].feedback_id == "AW-SYN-001"
    assert saved["action"] == "csv.imported"

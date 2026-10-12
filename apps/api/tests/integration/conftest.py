import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

import asyncpg
import httpx
import pytest
from pydantic import SecretStr

from feedback_hub.auth import SupabaseJwtVerifier
from feedback_hub.config import Settings
from feedback_hub.main import create_app
from tests.auth_helpers import SUPABASE_URL, TokenFactory

SUPABASE_DIR = Path(__file__).resolve().parents[4] / "supabase"
ADMIN_URL_ENV = "FEEDBACK_HUB_TEST_DATABASE_URL"

CreateUser = Callable[[str], Awaitable[uuid.UUID]]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)


def _schema_sql() -> str:
    files = [SUPABASE_DIR / "tests" / "auth_stub.sql"]
    files += sorted((SUPABASE_DIR / "migrations").glob("*.sql"))
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


async def _create_database(admin_url: str, name: str) -> None:
    admin = await asyncpg.connect(admin_url)
    try:
        await admin.execute(f'create database "{name}"')
    finally:
        await admin.close()
    conn = await asyncpg.connect(_with_database(admin_url, name))
    try:
        await conn.execute(_schema_sql())
    finally:
        await conn.close()


async def _drop_database(admin_url: str, name: str) -> None:
    admin = await asyncpg.connect(admin_url)
    try:
        await admin.execute(f'drop database if exists "{name}" with (force)')
    finally:
        await admin.close()


def _with_database(url: str, name: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{name}"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    admin_url = os.environ.get(ADMIN_URL_ENV)
    if not admin_url:
        pytest.skip(f"{ADMIN_URL_ENV} is not set; start `docker compose up -d` to run.")
    name = f"feedback_hub_it_{uuid.uuid4().hex[:8]}"
    asyncio.run(_create_database(admin_url, name))
    try:
        yield _with_database(admin_url, name)
    finally:
        asyncio.run(_drop_database(admin_url, name))


@pytest.fixture
def tokens() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def create_user(database_url: str) -> CreateUser:
    async def _create(email: str) -> uuid.UUID:
        user_id = uuid.uuid4()
        conn = await asyncpg.connect(database_url)
        try:
            await conn.execute("insert into auth.users (id, email) values ($1, $2)", user_id, email)
        finally:
            await conn.close()
        return user_id

    return _create


@pytest.fixture
async def api(database_url: str, tokens: TokenFactory) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        environment="test",
        database_url=SecretStr(database_url),
        supabase_url=SUPABASE_URL,
        huggingface_token=SecretStr("hf-test-token"),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app), httpx.AsyncClient() as http:
        app.state.jwt_verifier = SupabaseJwtVerifier(
            http,
            supabase_url=SUPABASE_URL,
            audience="authenticated",
            cache_seconds=600,
            static_keys={tokens.kid: tokens.pyjwk()},
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

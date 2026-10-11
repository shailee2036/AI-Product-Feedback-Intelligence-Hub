import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from feedback_hub.auth import AuthenticatedUser, CurrentUser


def to_async_url(url: str) -> str:
    for prefix in ("postgresql://", "postgres://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url.removeprefix(prefix)
    return url


class Database:
    def __init__(self, url: str, *, pool_size: int) -> None:
        self.engine: AsyncEngine = create_async_engine(
            to_async_url(url),
            pool_size=pool_size,
            max_overflow=pool_size,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("select 1"))

    @asynccontextmanager
    async def user_transaction(self, user: AuthenticatedUser) -> AsyncIterator[AsyncConnection]:
        """Run as Supabase's `authenticated` role so row-level security applies to every query."""
        claims = json.dumps({"sub": str(user.id), "role": "authenticated", "email": user.email})
        async with self.engine.begin() as conn:
            await conn.execute(
                text("select set_config('request.jwt.claims', :claims, true)"), {"claims": claims}
            )
            await conn.execute(text("set local role authenticated"))
            yield conn

    async def dispose(self) -> None:
        await self.engine.dispose()


def get_database(request: Request) -> Database:
    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database is not configured.")
    return database


async def get_user_connection(
    user: CurrentUser, database: Annotated[Database, Depends(get_database)]
) -> AsyncIterator[AsyncConnection]:
    async with database.user_transaction(user) as conn:
        yield conn


UserConnection = Annotated[AsyncConnection, Depends(get_user_connection)]

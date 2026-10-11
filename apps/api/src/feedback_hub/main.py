from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from feedback_hub import __version__
from feedback_hub.api import health, me, repositories
from feedback_hub.auth import SupabaseJwtVerifier
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.engine import Database
from feedback_hub.github.client import GitHubClient, build_http_client
from feedback_hub.observability import metrics_middleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    async with AsyncExitStack() as stack:
        github_http = await stack.enter_async_context(build_http_client(settings))
        app.state.github = GitHubClient(github_http)

        if settings.supabase_url is not None:
            auth_http = await stack.enter_async_context(httpx.AsyncClient(timeout=5.0))
            app.state.jwt_verifier = SupabaseJwtVerifier(
                auth_http,
                supabase_url=str(settings.supabase_url),
                audience=settings.jwt_audience,
                cache_seconds=settings.jwks_cache_seconds,
            )

        if settings.database_url is not None:
            database = Database(
                settings.database_url.get_secret_value(), pool_size=settings.database_pool_size
            )
            stack.push_async_callback(database.dispose)
            app.state.database = database
        yield


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    docs_enabled = resolved.environment in {"local", "test"}
    app = FastAPI(
        title="Feedback Intelligence Hub API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = resolved
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    app.middleware("http")(metrics_middleware)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(repositories.router)
    app.mount("/metrics", make_asgi_app())
    return app


app = create_app()

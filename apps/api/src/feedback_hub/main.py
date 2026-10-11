from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from feedback_hub import __version__
from feedback_hub.api import health, repositories
from feedback_hub.auth import SupabaseJwtVerifier
from feedback_hub.config import get_settings
from feedback_hub.github.client import GitHubClient, build_http_client
from feedback_hub.observability import metrics_middleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
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
        yield


def create_app() -> FastAPI:
    settings = get_settings()
    docs_enabled = settings.environment in {"local", "test"}
    app = FastAPI(
        title="Feedback Intelligence Hub API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.middleware("http")(metrics_middleware)
    app.include_router(health.router)
    app.include_router(repositories.router)
    app.mount("/metrics", make_asgi_app())
    return app


app = create_app()

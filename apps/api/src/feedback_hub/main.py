from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from feedback_hub import __version__
from feedback_hub.api import health, repositories
from feedback_hub.config import get_settings
from feedback_hub.github.client import GitHubClient, build_http_client
from feedback_hub.observability import metrics_middleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with build_http_client(get_settings()) as http:
        app.state.github = GitHubClient(http)
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

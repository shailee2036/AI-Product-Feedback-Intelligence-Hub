from fastapi import FastAPI
from prometheus_client import make_asgi_app

from feedback_hub import __version__
from feedback_hub.api import health
from feedback_hub.config import get_settings
from feedback_hub.observability import metrics_middleware


def create_app() -> FastAPI:
    settings = get_settings()
    docs_enabled = settings.environment in {"local", "test"}
    app = FastAPI(
        title="Feedback Intelligence Hub API",
        version=__version__,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.middleware("http")(metrics_middleware)
    app.include_router(health.router)
    app.mount("/metrics", make_asgi_app())
    return app


app = create_app()

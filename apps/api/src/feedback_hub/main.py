import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from sqlalchemy import text

from feedback_hub import __version__
from feedback_hub.api import (
    audit,
    clusters,
    csv_import,
    duplicates,
    embeddings,
    health,
    imports,
    me,
    product,
    repositories,
)
from feedback_hub.auth import SupabaseJwtVerifier
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.engine import Database
from feedback_hub.feedback.embeddings import EmbeddingClient, build_gemini_client
from feedback_hub.feedback.groq import GroqClient, build_groq_client, generation_target
from feedback_hub.github.client import GitHubClient, build_http_client
from feedback_hub.observability import configure_logging, configure_tracing, metrics_middleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    async with AsyncExitStack() as stack:
        github_http = await stack.enter_async_context(build_http_client(settings))
        app.state.github = GitHubClient(github_http)
        gemini_http = await stack.enter_async_context(build_gemini_client(settings))
        app.state.gemini = EmbeddingClient(
            gemini_http,
            base_url=settings.gemini_api_base_url,
            model=settings.gemini_embedding_model,
            dimensions=settings.gemini_embedding_dimensions,
            usd_per_million_texts=settings.embedding_usd_per_million_texts,
        )
        groq_http = await stack.enter_async_context(build_groq_client(settings))
        target = generation_target(settings)
        app.state.groq = GroqClient(
            groq_http,
            base_url=target.base_url,
            model=target.model,
            provider=target.provider,
            prompt_usd_per_million=settings.prompt_usd_per_million_tokens,
            completion_usd_per_million=settings.completion_usd_per_million_tokens,
        )

        if settings.supabase_url is not None:
            auth_http = await stack.enter_async_context(httpx.AsyncClient(timeout=5.0))
            app.state.jwt_verifier = SupabaseJwtVerifier(
                auth_http,
                supabase_url=str(settings.supabase_url),
                audience=settings.jwt_audience,
                cache_seconds=settings.jwks_cache_seconds,
            )

        app.state.import_tasks = set()
        if settings.database_url is not None:
            database = Database(
                settings.database_url.get_secret_value(), pool_size=settings.database_pool_size
            )
            stack.push_async_callback(database.dispose)
            app.state.database = database
            try:
                async with database.engine.begin() as conn:
                    await conn.execute(
                        text(
                            "update public.imports set status = 'failed', "
                            "error_message = 'Import was interrupted before it finished.', "
                            "finished_at = now() where status in ('queued', 'running')"
                        )
                    )
            except Exception:
                logger.warning("Could not recover interrupted imports.", exc_info=True)
            try:
                async with database.engine.begin() as conn:
                    await conn.execute(
                        text(
                            "update public.embedding_runs set status = 'failed', "
                            "error_message = 'Embedding was interrupted before it finished.', "
                            "finished_at = now() where status in ('queued', 'running')"
                        )
                    )
            except Exception:
                logger.warning("Could not recover interrupted embedding runs.", exc_info=True)
        yield
        tasks: set[asyncio.Task[None]] = app.state.import_tasks
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    resolved = settings or get_settings()
    configure_tracing(resolved.otel_exporter_otlp_endpoint)
    docs_enabled = resolved.environment in {"local", "test"}
    app = FastAPI(
        title="Feedback Intelligence Hub API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
        telemetry={"tracing": False, "metrics": False, "logs": False},
    )
    app.state.settings = resolved
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    app.middleware("http")(metrics_middleware)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(audit.router)
    app.include_router(product.router)
    app.include_router(csv_import.router)
    app.include_router(repositories.router)
    app.include_router(imports.router)
    app.include_router(embeddings.router)
    app.include_router(duplicates.router)
    app.include_router(clusters.router)
    app.mount("/metrics", make_asgi_app())
    return app


app = create_app()

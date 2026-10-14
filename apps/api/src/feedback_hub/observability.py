import json
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from prometheus_client import Counter, Histogram

_LOG = logging.getLogger(__name__)
_LOG_FIELDS = (
    "environment",
    "operation",
    "method",
    "route",
    "status",
    "duration_ms",
    "provider",
    "model",
    "result",
    "prompt_tokens",
    "completion_tokens",
    "texts",
    "error_category",
)


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Only the allowlisted fields are copied from the record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "service": "feedback-hub-api",
            "event": record.getMessage(),
        }
        for field in _LOG_FIELDS:
            value = record.__dict__.get(field)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"))


def configure_logging() -> None:
    """Send feedback_hub logs to stdout as JSON. Safe to call more than once."""
    logger = logging.getLogger("feedback_hub")
    logger.setLevel(logging.INFO)
    if any(
        isinstance(getattr(handler, "formatter", None), JsonFormatter)
        for handler in logger.handlers
    ):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False


_SPAN_FIELDS = frozenset(
    {
        "http.method",
        "http.route",
        "http.status_code",
        "error_category",
        "operation",
        "provider",
        "model",
        "result",
        "duration_ms",
    }
)


def configure_tracing(endpoint: str | None = None, *, exporter: SpanExporter | None = None) -> None:
    """Export spans when a collector or test exporter is supplied. Safe to call again."""
    if not isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider):
        return
    if exporter is None and not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "feedback-hub-api"}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        base = endpoint.rstrip("/") if endpoint else ""
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces"))
        )
    trace.set_tracer_provider(provider)


def _record_span(name: str, attributes: dict[str, str | int]) -> None:
    span = trace.get_tracer("feedback_hub").start_span(name)
    for key, value in attributes.items():
        if key in _SPAN_FIELDS:
            span.set_attribute(key, value)
    span.end()


def log_event(event: str, **fields: object) -> None:
    """Log one structured event. Fields outside the allowlist are dropped."""
    extra = {
        key: value for key, value in fields.items() if key in _LOG_FIELDS and value is not None
    }
    _LOG.info(event, extra=extra)


HTTP_REQUESTS = Counter(
    "feedback_hub_http_requests_total",
    "HTTP requests handled by the API.",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "feedback_hub_http_request_duration_seconds",
    "HTTP request latency by route.",
    ["method", "route"],
)
PROVIDER_REQUESTS = Counter(
    "feedback_hub_provider_requests_total",
    "Calls to a model provider.",
    ["operation", "provider", "model", "result"],
)
PROVIDER_LATENCY = Histogram(
    "feedback_hub_provider_request_duration_seconds",
    "Provider call latency, including retries.",
    ["operation", "provider", "model"],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
PROVIDER_TOKENS = Counter(
    "feedback_hub_provider_tokens_total",
    "Tokens reported by a generation provider.",
    ["operation", "provider", "model", "direction"],
)
EMBEDDING_TEXTS = Counter(
    "feedback_hub_embedding_texts_total",
    "Texts sent to the embedding provider.",
    ["provider", "model", "result"],
)

_OPERATIONS = frozenset({"generation", "theme_names", "brief", "embedding"})
_RESULTS = frozenset({"ok", "timeout", "rate_limited", "rejected", "error", "invalid"})


def provider_result(status_code: int) -> str:
    """Collapse an HTTP status into a low-cardinality metric result."""
    if status_code in {401, 403}:
        return "rejected"
    if status_code == 429:
        return "rate_limited"
    return "error"


def observe_provider_call(
    *,
    operation: str,
    provider: str,
    model: str,
    result: str,
    seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    texts: int = 0,
) -> None:
    """Record one provider call. Labels are config values, never request content."""
    operation = operation if operation in _OPERATIONS else "generation"
    result = result if result in _RESULTS else "error"
    PROVIDER_REQUESTS.labels(operation, provider, model, result).inc()
    PROVIDER_LATENCY.labels(operation, provider, model).observe(seconds)
    if result == "ok" and prompt_tokens > 0:
        PROVIDER_TOKENS.labels(operation, provider, model, "prompt").inc(prompt_tokens)
    if result == "ok" and completion_tokens > 0:
        PROVIDER_TOKENS.labels(operation, provider, model, "completion").inc(completion_tokens)
    if texts > 0:
        EMBEDDING_TEXTS.labels(provider, model, result).inc(texts)
    log_event(
        "provider_call",
        operation=operation,
        provider=provider,
        model=model,
        result=result,
        duration_ms=int(seconds * 1000),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        texts=texts,
    )
    _record_span(
        "provider_call",
        {
            "operation": operation,
            "provider": provider,
            "model": model,
            "result": result,
            "duration_ms": int(seconds * 1000),
        },
    )


def _error_category(status: str) -> str | None:
    if status.startswith("5"):
        return "server_error"
    if status.startswith("4"):
        return "client_error"
    return None


def _route_template(request: Request) -> str:
    """Use the route template, never the raw path, to keep label cardinality bounded."""
    route = request.scope.get("route")
    return str(getattr(route, "path", "unmatched"))


async def metrics_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.url.path.startswith("/metrics"):
        return await call_next(request)

    start = time.perf_counter()
    status = "500"
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        route = _route_template(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        HTTP_REQUESTS.labels(request.method, route, status).inc()
        HTTP_LATENCY.labels(request.method, route).observe(duration_ms / 1000)
        settings = getattr(request.app.state, "settings", None)
        category = _error_category(status)
        log_event(
            "request",
            environment=getattr(settings, "environment", None),
            method=request.method,
            route=route,
            status=status,
            duration_ms=duration_ms,
            error_category=category,
        )
        attributes: dict[str, str | int] = {
            "http.method": request.method,
            "http.route": route,
            "http.status_code": int(status) if status.isdigit() else 500,
            "duration_ms": duration_ms,
        }
        if category is not None:
            attributes["error_category"] = category
        _record_span("request", attributes)

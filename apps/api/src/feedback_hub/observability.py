import json
import logging
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager

from fastapi import Request, Response
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from prometheus_client import Counter, Gauge, Histogram

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
    "cost_usd",
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
        "records",
        "skipped",
        "pages",
        "clusters",
    }
)
_SPAN_RESULTS = frozenset({"ok", "error", "cancelled"})
_SPAN_OPERATIONS = frozenset(
    {"generation", "theme_names", "brief", "embedding", "import", "clustering", "duplicates"}
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


def _span_value(key: str, value: object) -> str | int | None:
    """Keep counts and known categories. Drop names, ids, and free text."""
    if key not in _SPAN_FIELDS or isinstance(value, bool):
        return None
    if key == "result":
        return value if isinstance(value, str) and value in _SPAN_RESULTS else None
    if key == "operation":
        return value if isinstance(value, str) and value in _SPAN_OPERATIONS else None
    if key in {"records", "skipped", "pages", "clusters", "duration_ms", "http.status_code"}:
        return value if isinstance(value, int) else None
    if isinstance(value, str | int):
        return value
    return None


def _record_span(name: str, attributes: dict[str, str | int]) -> None:
    span = trace.get_tracer("feedback_hub").start_span(name)
    _apply_span(span, attributes)
    span.end()


def _apply_span(span: trace.Span, attributes: dict[str, object]) -> None:
    for key, value in attributes.items():
        allowed = _span_value(key, value)
        if allowed is not None:
            span.set_attribute(key, allowed)


@contextmanager
def trace_operation(name: str) -> Iterator[dict[str, str | int]]:
    """One span for a whole import page, embedding run, or analysis. Content stays out."""
    span = trace.get_tracer("feedback_hub").start_span(name)
    token = otel_context.attach(trace.set_span_in_context(span))
    fields: dict[str, str | int] = {}
    try:
        yield fields
        fields.setdefault("result", "ok")
    except Exception:
        fields["result"] = "error"
        raise
    finally:
        _apply_span(span, fields)
        span.end()
        otel_context.detach(token)


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
CLUSTER_CORRECTIONS = Counter(
    "feedback_hub_cluster_corrections_total",
    "Human changes to a saved theme.",
    ["action"],
)
PROVIDER_COST = Counter(
    "feedback_hub_provider_cost_usd_total",
    "Configured token or text rates applied to a successful provider call. Not an invoice.",
    ["operation", "provider", "model"],
)
IMPORT_RECORDS = Counter(
    "feedback_hub_import_records_total",
    "Feedback rows an import imported, skipped, or failed.",
    ["result"],
)
IMPORT_DURATION = Histogram(
    "feedback_hub_import_duration_seconds",
    "Wall time of one import, from start through the last saved page.",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
)
IMPORT_QUEUE_AGE = Histogram(
    "feedback_hub_import_queue_age_seconds",
    "Time an import waited after it was scheduled before the runner started.",
    buckets=(0.01, 0.1, 0.5, 1, 5, 30),
)
GITHUB_PAGE_DURATION = Histogram(
    "feedback_hub_github_page_duration_seconds",
    "Time to fetch one GitHub issues page.",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10),
)
GITHUB_RATE_LIMIT = Gauge(
    "feedback_hub_github_rate_limit_remaining",
    "GitHub rate-limit units remaining on the latest response.",
)
REDACTIONS = Counter(
    "feedback_hub_redactions_total",
    "PII spans replaced before text is stored or sent. The original text is not a label.",
    ["category"],
)
CLUSTER_DURATION = Histogram(
    "feedback_hub_cluster_duration_seconds",
    "Wall time to group embedded feedback into themes.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
CLUSTER_SIZE = Histogram(
    "feedback_hub_cluster_size",
    "Members in one saved theme.",
    buckets=(2, 3, 5, 8, 13, 21, 50),
)
CLUSTER_COUNT = Gauge(
    "feedback_hub_cluster_count",
    "Themes saved by the latest clustering run.",
)
DUPLICATE_RATIO = Gauge(
    "feedback_hub_duplicate_ratio",
    "Duplicate edges divided by the number of possible pairs.",
    ["kind"],
)
EMBEDDING_RUN_DURATION = Histogram(
    "feedback_hub_embedding_run_duration_seconds",
    "Wall time of one embedding run, including pauses between batches.",
    buckets=(1, 5, 15, 30, 60, 120, 300),
)

_OPERATIONS = frozenset({"generation", "theme_names", "brief", "embedding"})
_RESULTS = frozenset({"ok", "timeout", "rate_limited", "rejected", "error", "invalid"})
_CORRECTIONS = frozenset({"approved", "dismissed", "merged", "split", "relabeled"})
_IMPORT_RESULTS = frozenset({"imported", "skipped", "failed"})
_REDACTION_CATEGORIES = frozenset({"email", "phone", "secret"})
_DUPLICATE_KINDS = frozenset({"exact", "semantic"})


def observe_cluster_correction(action: str) -> None:
    """Count one human theme change. The label is the action, never an id or name."""
    CLUSTER_CORRECTIONS.labels(action if action in _CORRECTIONS else "other").inc()


def observe_import_records(result: str, count: int) -> None:
    if count <= 0:
        return
    IMPORT_RECORDS.labels(result if result in _IMPORT_RESULTS else "failed").inc(count)


def observe_import_timing(seconds: float, queue_seconds: float) -> None:
    IMPORT_DURATION.observe(max(seconds, 0))
    IMPORT_QUEUE_AGE.observe(max(queue_seconds, 0))


def observe_github_page(seconds: float) -> None:
    GITHUB_PAGE_DURATION.observe(max(seconds, 0))


def observe_github_quota(remaining: str | None) -> None:
    if remaining is not None and remaining.isdigit():
        GITHUB_RATE_LIMIT.set(int(remaining))


def observe_redaction(category: str, count: int) -> None:
    if count > 0 and category in _REDACTION_CATEGORIES:
        REDACTIONS.labels(category).inc(count)


def observe_cluster_run(*, seconds: float, sizes: list[int]) -> None:
    CLUSTER_DURATION.observe(max(seconds, 0))
    CLUSTER_COUNT.set(len(sizes))
    for size in sizes:
        if size > 0:
            CLUSTER_SIZE.observe(size)


def observe_duplicate_rate(kind: str, *, edges: int, items: int) -> None:
    if kind not in _DUPLICATE_KINDS:
        return
    possible = items * (items - 1) / 2
    DUPLICATE_RATIO.labels(kind).set(0 if possible <= 0 else edges / possible)


def observe_embedding_run(seconds: float) -> None:
    EMBEDDING_RUN_DURATION.observe(max(seconds, 0))


def provider_result(status_code: int) -> str:
    """Collapse an HTTP status into a low-cardinality metric result."""
    if status_code in {401, 403}:
        return "rejected"
    if status_code == 429:
        return "rate_limited"
    return "error"


def provider_cost_usd(
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    texts: int = 0,
    prompt_usd_per_million: float = 0,
    completion_usd_per_million: float = 0,
    embedding_usd_per_million_texts: float = 0,
) -> float:
    """Apply configured rates. A rate of zero means this deployment does not price that call."""
    return (
        prompt_tokens * prompt_usd_per_million
        + completion_tokens * completion_usd_per_million
        + texts * embedding_usd_per_million_texts
    ) / 1_000_000


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
    cost_usd: float = 0,
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
    priced = cost_usd if result == "ok" and cost_usd > 0 else 0
    if priced > 0:
        PROVIDER_COST.labels(operation, provider, model).inc(priced)
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
        cost_usd=priced or None,
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

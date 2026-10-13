import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from prometheus_client import Counter, Histogram

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
        HTTP_REQUESTS.labels(request.method, route, status).inc()
        HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - start)

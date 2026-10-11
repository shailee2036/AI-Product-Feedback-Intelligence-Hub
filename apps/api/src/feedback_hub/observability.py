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

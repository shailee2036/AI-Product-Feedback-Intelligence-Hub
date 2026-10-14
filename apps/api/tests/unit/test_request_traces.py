import json

import httpx
import pytest
import respx
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from feedback_hub.feedback.groq import GroqClient
from feedback_hub.observability import configure_tracing

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def _install_span_exporter() -> None:
    configure_tracing(exporter=_EXPORTER)


@pytest.fixture
def spans() -> InMemorySpanExporter:
    _EXPORTER.clear()
    return _EXPORTER


def _attributes(exporter: InMemorySpanExporter, name: str) -> dict[str, object]:
    finished = [span for span in exporter.get_finished_spans() if span.name == name]
    assert finished, f"no span named {name}"
    return dict(finished[-1].attributes or {})


@pytest.mark.asyncio
async def test_request_span_uses_the_route_and_drops_the_query(
    client: httpx.AsyncClient, spans: InMemorySpanExporter
) -> None:
    response = await client.get("/health/live?token=secret-value")
    missing = await client.get("/not-a-route")

    assert response.status_code == 200
    routes = [
        dict(span.attributes or {}) for span in spans.get_finished_spans() if span.name == "request"
    ]
    live = next(item for item in routes if item["http.route"] == "/health/live")
    assert live["http.method"] == "GET"
    assert live["http.status_code"] == 200
    assert "error_category" not in live
    assert "secret-value" not in json.dumps(live)
    assert missing.status_code == 404
    missed = next(item for item in routes if item["http.route"] == "unmatched")
    assert missed["error_category"] == "client_error"


@pytest.mark.asyncio
async def test_provider_span_records_the_call_and_not_the_prompt(
    spans: InMemorySpanExporter,
) -> None:
    with respx.mock() as router:
        router.post(GROQ_URL).respond(
            200,
            json={
                "choices": [{"message": {"content": '{"themes": []}'}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )
        async with httpx.AsyncClient() as http:
            client = GroqClient(
                http, base_url="https://api.groq.com/openai/v1", model="theme-writer"
            )
            await client.complete("private feedback text", operation="theme_names")

    event = _attributes(spans, "provider_call")
    assert event["operation"] == "theme_names"
    assert event["provider"] == "groq"
    assert event["model"] == "theme-writer"
    assert event["result"] == "ok"
    assert "private feedback text" not in json.dumps(event)

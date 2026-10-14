import io
import json
import logging

import httpx
import pytest
import respx

from feedback_hub.feedback.groq import GroqClient
from feedback_hub.observability import JsonFormatter

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _attached_log() -> tuple[logging.Logger, logging.Handler, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("feedback_hub.observability")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger, handler, stream


def _events(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


@pytest.mark.asyncio
async def test_request_log_uses_the_route_and_drops_the_query(client: httpx.AsyncClient) -> None:
    logger, handler, stream = _attached_log()
    try:
        response = await client.get("/health/live?token=secret-value")
        missing = await client.get("/not-a-route")
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 200
    event = next(item for item in _events(stream) if item["route"] == "/health/live")
    assert event["method"] == "GET"
    assert event["status"] == "200"
    assert event["environment"] == "test"
    assert "secret-value" not in json.dumps(event)
    assert "error_category" not in event
    assert missing.status_code == 404
    missed = next(item for item in _events(stream) if item["route"] == "unmatched")
    assert missed["error_category"] == "client_error"


@pytest.mark.asyncio
async def test_provider_log_records_the_call_and_not_the_prompt() -> None:
    logger, handler, stream = _attached_log()
    try:
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
    finally:
        logger.removeHandler(handler)

    event = next(item for item in _events(stream) if item["event"] == "provider_call")
    assert event["operation"] == "theme_names"
    assert event["provider"] == "groq"
    assert event["model"] == "theme-writer"
    assert event["result"] == "ok"
    assert event["prompt_tokens"] == 3
    assert "private feedback text" not in json.dumps(event)


def test_formatter_drops_fields_outside_the_allowlist() -> None:
    record = logging.LogRecord(
        name="feedback_hub.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="provider_call",
        args=(),
        exc_info=None,
    )
    record.prompt = "private feedback text"
    record.operation = "brief"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "provider_call"
    assert payload["operation"] == "brief"
    assert "prompt" not in payload
    assert "private feedback text" not in json.dumps(payload)

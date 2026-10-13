import httpx
import pytest
import respx
from prometheus_client import REGISTRY

from feedback_hub.feedback.embeddings import EmbeddingClient, EmbeddingError
from feedback_hub.feedback.groq import GroqClient, GroqError
from feedback_hub.observability import observe_provider_call

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/metric-model:batchEmbedContents"
)


def _value(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.mark.asyncio
async def test_generation_records_latency_and_tokens() -> None:
    labels = {
        "operation": "theme_names",
        "provider": "litellm",
        "model": "theme-writer",
        "result": "ok",
    }
    before = _value("feedback_hub_provider_requests_total", labels)
    token_labels = {
        "operation": "theme_names",
        "provider": "litellm",
        "model": "theme-writer",
        "direction": "prompt",
    }
    prompt_before = _value("feedback_hub_provider_tokens_total", token_labels)
    with respx.mock() as router:
        router.post(GROQ_URL).respond(
            200,
            json={
                "choices": [{"message": {"content": '{"themes": []}'}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
            },
        )
        async with httpx.AsyncClient() as http:
            client = GroqClient(
                http,
                base_url="https://api.groq.com/openai/v1",
                model="theme-writer",
                provider="litellm",
            )
            await client.complete("private feedback text", operation="theme_names")

    assert _value("feedback_hub_provider_requests_total", labels) == before + 1
    assert _value("feedback_hub_provider_tokens_total", token_labels) == prompt_before + 11
    assert (
        _value(
            "feedback_hub_provider_request_duration_seconds_count",
            {"operation": "theme_names", "provider": "litellm", "model": "theme-writer"},
        )
        > 0
    )
    assert (
        _value(
            "feedback_hub_provider_requests_total",
            {**labels, "model": "private feedback text"},
        )
        == 0
    )


@pytest.mark.asyncio
async def test_generation_records_a_rate_limit_without_tokens() -> None:
    labels = {
        "operation": "brief",
        "provider": "groq",
        "model": "metric-brief",
        "result": "rate_limited",
    }
    before = _value("feedback_hub_provider_requests_total", labels)
    with respx.mock() as router:
        router.post("https://api.groq.com/openai/v1/chat/completions").respond(429, json={})
        async with httpx.AsyncClient() as http:
            client = GroqClient(
                http, base_url="https://api.groq.com/openai/v1", model="metric-brief"
            )
            with pytest.raises(GroqError):
                await client.complete("private feedback text", operation="brief")

    assert _value("feedback_hub_provider_requests_total", labels) == before + 1
    assert (
        _value(
            "feedback_hub_provider_tokens_total",
            {
                "operation": "brief",
                "provider": "groq",
                "model": "metric-brief",
                "direction": "prompt",
            },
        )
        == 0
    )


@pytest.mark.asyncio
async def test_generation_records_a_timeout() -> None:
    labels = {
        "operation": "generation",
        "provider": "groq",
        "model": "metric-timeout",
        "result": "timeout",
    }
    before = _value("feedback_hub_provider_requests_total", labels)
    with respx.mock() as router:
        router.post(GROQ_URL).mock(side_effect=httpx.ConnectError("down"))
        async with httpx.AsyncClient() as http:
            client = GroqClient(
                http, base_url="https://api.groq.com/openai/v1", model="metric-timeout"
            )
            with pytest.raises(GroqError, match="did not respond"):
                await client.complete("Name the themes.")

    assert _value("feedback_hub_provider_requests_total", labels) == before + 1


@pytest.mark.asyncio
async def test_embedding_records_the_batch_and_a_rejection() -> None:
    ok_labels = {"provider": "gemini", "model": "metric-model", "result": "ok"}
    rejected_labels = {**ok_labels, "result": "rejected"}
    texts_before = _value("feedback_hub_embedding_texts_total", ok_labels)
    rejected_texts_before = _value("feedback_hub_embedding_texts_total", rejected_labels)
    request_labels = {
        "operation": "embedding",
        "provider": "gemini",
        "model": "metric-model",
        "result": "rejected",
    }
    rejected_before = _value("feedback_hub_provider_requests_total", request_labels)
    with respx.mock() as router:
        router.post(GEMINI_URL).respond(
            200, json={"embeddings": [{"values": [3.0, 4.0]}, {"values": [0.0, 2.0]}]}
        )
        async with httpx.AsyncClient() as http:
            client = EmbeddingClient(
                http,
                base_url="https://generativelanguage.googleapis.com/v1beta",
                model="metric-model",
                dimensions=2,
            )
            await client.embed(["login fails", "storage quota"])
            router.post(GEMINI_URL).respond(403, json={"error": "secret"})
            with pytest.raises(EmbeddingError):
                await client.embed(["login fails"])

    assert _value("feedback_hub_embedding_texts_total", ok_labels) == texts_before + 2
    assert (
        _value("feedback_hub_embedding_texts_total", rejected_labels) == rejected_texts_before + 1
    )
    assert _value("feedback_hub_provider_requests_total", request_labels) == rejected_before + 1


@pytest.mark.asyncio
async def test_generation_records_an_unreadable_body_and_a_provider_error() -> None:
    invalid = {
        "operation": "generation",
        "provider": "groq",
        "model": "metric-invalid",
        "result": "invalid",
    }
    failed = {**invalid, "model": "metric-failed", "result": "error"}
    invalid_before = _value("feedback_hub_provider_requests_total", invalid)
    failed_before = _value("feedback_hub_provider_requests_total", failed)
    with respx.mock() as router:
        router.post(GROQ_URL).respond(200, text="not-json")
        async with httpx.AsyncClient() as http:
            client = GroqClient(
                http, base_url="https://api.groq.com/openai/v1", model="metric-invalid"
            )
            with pytest.raises(GroqError, match="could not be read"):
                await client.complete("Name the themes.")
    with respx.mock() as router:
        router.post(GROQ_URL).respond(502, text="upstream")
        async with httpx.AsyncClient() as http:
            client = GroqClient(
                http, base_url="https://api.groq.com/openai/v1", model="metric-failed"
            )
            with pytest.raises(GroqError, match="HTTP 502"):
                await client.complete("Name the themes.")

    assert _value("feedback_hub_provider_requests_total", invalid) == invalid_before + 1
    assert _value("feedback_hub_provider_requests_total", failed) == failed_before + 1


def test_unexpected_labels_are_collapsed() -> None:
    before = _value(
        "feedback_hub_provider_requests_total",
        {"operation": "generation", "provider": "groq", "model": "collapsed", "result": "error"},
    )

    observe_provider_call(
        operation="user supplied text",
        provider="groq",
        model="collapsed",
        result="also free text",
        seconds=0.01,
    )

    assert (
        _value(
            "feedback_hub_provider_requests_total",
            {
                "operation": "generation",
                "provider": "groq",
                "model": "collapsed",
                "result": "error",
            },
        )
        == before + 1
    )

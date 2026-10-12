import httpx
import pytest
import respx

from feedback_hub.feedback.embeddings import (
    EmbeddingClient,
    EmbeddingError,
    EmbeddingProviderError,
    parse_gemini_embeddings,
)

URL = "https://generativelanguage.googleapis.com/v1beta/models/test-model:batchEmbedContents"


def test_parse_gemini_embeddings_normalizes_each_vector() -> None:
    payload = {"embeddings": [{"values": [3.0, 4.0]}, {"values": [0.0, 5.0]}]}

    vectors = parse_gemini_embeddings(payload, count=2, dimensions=2)

    assert vectors[0] == pytest.approx([0.6, 0.8])
    assert vectors[1] == pytest.approx([0.0, 1.0])


def test_parse_gemini_embeddings_rejects_the_wrong_width() -> None:
    with pytest.raises(EmbeddingError):
        parse_gemini_embeddings({"embeddings": [{"values": [1.0, 2.0]}]}, count=1, dimensions=4)


@respx.mock
async def test_client_posts_a_batch_and_keeps_the_key_out_of_the_url() -> None:
    route = respx.post(URL).respond(
        200, json={"embeddings": [{"values": [3.0, 4.0]}, {"values": [0.0, 2.0]}]}
    )
    async with httpx.AsyncClient(headers={"x-goog-api-key": "gemini-test-key"}) as http:
        client = EmbeddingClient(
            http,
            base_url="https://generativelanguage.googleapis.com/v1beta",
            model="test-model",
            dimensions=2,
        )
        vectors = await client.embed(["login fails", "storage quota"])

    assert vectors[0] == pytest.approx([0.6, 0.8])
    sent = route.calls.last.request
    assert sent.headers["x-goog-api-key"] == "gemini-test-key"
    assert b"gemini-test-key" not in sent.url.raw_path
    assert b'"taskType":"CLUSTERING"' in sent.content or b'"taskType": "CLUSTERING"' in sent.content


@respx.mock
async def test_client_reports_provider_status_without_the_body() -> None:
    respx.post(URL).respond(403, json={"error": {"message": "bad key gemini-secret"}})
    async with httpx.AsyncClient(headers={"x-goog-api-key": "gemini-test-key"}) as http:
        client = EmbeddingClient(
            http,
            base_url="https://generativelanguage.googleapis.com/v1beta",
            model="test-model",
            dimensions=2,
        )
        with pytest.raises(EmbeddingProviderError, match="rejected") as raised:
            await client.embed(["login fails"])

    assert "gemini-secret" not in str(raised.value)


def test_quota_is_explained() -> None:
    assert "quota" in str(EmbeddingProviderError(429))

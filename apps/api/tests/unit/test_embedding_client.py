import httpx
import pytest
import respx

from feedback_hub.feedback.embeddings import (
    EmbeddingClient,
    EmbeddingError,
    EmbeddingProviderError,
    parse_embeddings,
)

URL = "https://router.huggingface.co/hf-inference/models/test-model"


def test_parse_embeddings_accepts_vectors_and_token_matrices() -> None:
    vector = [0.5] * 4
    matrix = [[1.0, 3.0], [3.0, 5.0]]

    assert parse_embeddings([vector], count=1, dimensions=4) == [vector]
    assert parse_embeddings(vector, count=1, dimensions=4) == [vector]
    assert parse_embeddings([matrix], count=1, dimensions=2) == [[2.0, 4.0]]


def test_parse_embeddings_rejects_the_wrong_shape() -> None:
    with pytest.raises(EmbeddingError):
        parse_embeddings([[1.0, 2.0]], count=1, dimensions=4)


@respx.mock
async def test_client_posts_a_batch_and_reads_vectors() -> None:
    route = respx.post(URL).respond(200, json=[[0.25, 0.75], [0.5, 0.5]])
    async with httpx.AsyncClient(headers={"Authorization": "Bearer test-token"}) as http:
        client = EmbeddingClient(
            http, base_url="https://router.huggingface.co", model="test-model", dimensions=2
        )
        vectors = await client.embed(["login fails", "storage quota"])

    assert vectors == [[0.25, 0.75], [0.5, 0.5]]
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer test-token"
    assert b'"normalize":true' in sent.content or b'"normalize": true' in sent.content


@respx.mock
async def test_client_reports_provider_status_without_the_body() -> None:
    respx.post(URL).respond(401, json={"error": "bad token hf_secret"})
    async with httpx.AsyncClient(headers={"Authorization": "Bearer test-token"}) as http:
        client = EmbeddingClient(
            http, base_url="https://router.huggingface.co", model="test-model", dimensions=2
        )
        with pytest.raises(EmbeddingProviderError, match="rejected") as raised:
            await client.embed(["login fails"])

    assert "hf_secret" not in str(raised.value)


def test_missing_credits_are_explained() -> None:
    assert "credits" in str(EmbeddingProviderError(402))

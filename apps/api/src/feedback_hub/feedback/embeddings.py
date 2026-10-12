from typing import Any, TypeGuard

import httpx

from feedback_hub.config import Settings


class EmbeddingError(Exception):
    pass


class EmbeddingProviderError(EmbeddingError):
    def __init__(self, status_code: int) -> None:
        super().__init__(_provider_message(status_code))
        self.status_code = status_code


def build_huggingface_client(settings: Settings) -> httpx.AsyncClient:
    headers = {"Accept": "application/json"}
    if settings.huggingface_token is not None:
        token = settings.huggingface_token.get_secret_value()
        headers["Authorization"] = f"Bearer {token}"
    return httpx.AsyncClient(timeout=settings.huggingface_timeout_seconds, headers=headers)


class EmbeddingClient:
    def __init__(
        self, http: httpx.AsyncClient, *, base_url: str, model: str, dimensions: int
    ) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/hf-inference/models/{model}"
        self._dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._http.post(
            self._url,
            json={"inputs": texts, "normalize": True, "truncate": True},
        )
        if response.is_error:
            raise EmbeddingProviderError(response.status_code)
        return parse_embeddings(response.json(), count=len(texts), dimensions=self._dimensions)


def parse_embeddings(payload: object, *, count: int, dimensions: int) -> list[list[float]]:
    """Accept a batch of sentence vectors or token matrices from feature extraction."""
    if count == 1 and _is_vector(payload, dimensions):
        return [payload]
    if not isinstance(payload, list) or len(payload) != count:
        raise EmbeddingError("Embedding response did not match the batch size.")
    vectors: list[list[float]] = []
    for item in payload:
        if _is_vector(item, dimensions):
            vectors.append([float(value) for value in item])
        elif _is_token_matrix(item):
            pooled = _mean_pool(item)
            if len(pooled) != dimensions:
                raise EmbeddingError("Embedding width did not match the configured model.")
            vectors.append(pooled)
        else:
            raise EmbeddingError("Embedding response had an unexpected shape.")
    return vectors


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _is_vector(value: object, dimensions: int) -> TypeGuard[list[float]]:
    return (
        isinstance(value, list)
        and len(value) == dimensions
        and all(isinstance(item, int | float) and not isinstance(item, bool) for item in value)
    )


def _is_token_matrix(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(row, list) and row and _row_is_numeric(row) for row in value)
    )


def _row_is_numeric(row: list[Any]) -> bool:
    return all(isinstance(item, int | float) and not isinstance(item, bool) for item in row)


def _mean_pool(matrix: list[list[float]]) -> list[float]:
    width = len(matrix[0])
    totals = [0.0] * width
    for row in matrix:
        if len(row) != width:
            raise EmbeddingError("Token embeddings in one text had different widths.")
        for index, value in enumerate(row):
            totals[index] += float(value)
    count = len(matrix)
    return [value / count for value in totals]


def _provider_message(status_code: int) -> str:
    if status_code == 401:
        return "The Hugging Face token was rejected."
    if status_code == 402:
        return "Hugging Face has no credits left for embeddings. Add credits, then try again."
    if status_code == 429:
        return "Hugging Face rate limit reached. Try again in a minute."
    if status_code in {503, 504}:
        return "The embedding model is unavailable. Try again in a minute."
    return f"Hugging Face returned HTTP {status_code}."

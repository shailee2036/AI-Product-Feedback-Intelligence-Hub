import asyncio
import math
import time
from typing import Any, TypeGuard

import httpx

from feedback_hub.config import Settings
from feedback_hub.observability import observe_provider_call, provider_result


class EmbeddingError(Exception):
    pass


class EmbeddingProviderError(EmbeddingError):
    def __init__(self, status_code: int) -> None:
        super().__init__(_provider_message(status_code))
        self.status_code = status_code


def build_gemini_client(settings: Settings) -> httpx.AsyncClient:
    headers = {"Accept": "application/json"}
    if settings.gemini_api_key is not None:
        headers["x-goog-api-key"] = settings.gemini_api_key.get_secret_value()
    return httpx.AsyncClient(timeout=settings.gemini_timeout_seconds, headers=headers)


_RETRY_DELAYS_SECONDS = (15.0, 30.0, 60.0)


class EmbeddingClient:
    def __init__(
        self, http: httpx.AsyncClient, *, base_url: str, model: str, dimensions: int
    ) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/models/{model}:batchEmbedContents"
        self._model = f"models/{model}"
        self._metric_model = model
        self._dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        body = {
            "requests": [
                {
                    "model": self._model,
                    "content": {"parts": [{"text": text}]},
                    "taskType": "CLUSTERING",
                    "outputDimensionality": self._dimensions,
                }
                for text in texts
            ]
        }
        started = time.perf_counter()
        result = "error"
        try:
            try:
                response = await self._post_with_backoff(body)
            except httpx.RequestError:
                result = "timeout"
                raise
            if response.is_error:
                raise EmbeddingProviderError(response.status_code)
            try:
                payload = response.json()
            except ValueError:
                result = "invalid"
                raise EmbeddingError("Embedding response had an unexpected shape.") from None
            vectors = parse_gemini_embeddings(
                payload, count=len(texts), dimensions=self._dimensions
            )
            result = "ok"
            return vectors
        except EmbeddingProviderError as exc:
            result = provider_result(exc.status_code)
            raise
        except EmbeddingError:
            if result == "error":
                result = "invalid"
            raise
        finally:
            observe_provider_call(
                operation="embedding",
                provider="gemini",
                model=self._metric_model,
                result=result,
                seconds=time.perf_counter() - started,
                texts=len(texts),
            )

    async def _post_with_backoff(self, body: dict[str, Any]) -> httpx.Response:
        delays = iter(_RETRY_DELAYS_SECONDS)
        response = await self._http.post(self._url, json=body)
        while response.status_code == 429:
            try:
                delay = next(delays)
            except StopIteration:
                return response
            await asyncio.sleep(_retry_delay(response, delay))
            response = await self._http.post(self._url, json=body)
        return response


def parse_gemini_embeddings(payload: object, *, count: int, dimensions: int) -> list[list[float]]:
    """Read a Gemini batchEmbedContents body and L2-normalize each vector.

    gemini-embedding-001 only normalizes 3072-dimension output itself. Shorter
    vectors have to be normalized here so later comparisons use cosine distance.
    """
    if not isinstance(payload, dict):
        raise EmbeddingError("Embedding response had an unexpected shape.")
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != count:
        raise EmbeddingError("Embedding response did not match the batch size.")
    vectors: list[list[float]] = []
    for item in embeddings:
        values = item.get("values") if isinstance(item, dict) else None
        if not _is_vector(values, dimensions):
            raise EmbeddingError("Embedding width did not match the configured model.")
        vectors.append(_normalize([float(value) for value in values]))
    return vectors


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _retry_delay(response: httpx.Response, fallback: float) -> float:
    try:
        hinted = float(response.headers.get("retry-after", ""))
    except ValueError:
        return fallback
    return hinted if hinted > 0 else fallback


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return values
    return [value / norm for value in values]


def _is_vector(value: object, dimensions: int) -> TypeGuard[list[float]]:
    return (
        isinstance(value, list)
        and len(value) == dimensions
        and all(isinstance(item, int | float) and not isinstance(item, bool) for item in value)
    )


def _provider_message(status_code: int) -> str:
    if status_code in {401, 403}:
        return "The Gemini API key was rejected."
    if status_code == 429:
        return (
            "Gemini's free-tier quota was reached. Saved embeddings are kept. "
            "Try again in a minute."
        )
    if status_code in {503, 504}:
        return "The embedding model is unavailable. Try again in a minute."
    return f"Gemini returned HTTP {status_code}."

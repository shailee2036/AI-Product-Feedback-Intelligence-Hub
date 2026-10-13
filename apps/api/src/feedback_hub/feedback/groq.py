import time
from typing import Any, NamedTuple

import httpx
from pydantic import SecretStr

from feedback_hub.config import Settings
from feedback_hub.observability import observe_provider_call, provider_result


class GroqError(Exception):
    pass


class GroqProviderError(GroqError):
    def __init__(self, status_code: int) -> None:
        super().__init__(_provider_message(status_code))
        self.status_code = status_code


class GenerationTarget(NamedTuple):
    provider: str
    base_url: str
    model: str


def generation_target(settings: Settings) -> GenerationTarget:
    if settings.litellm_base_url:
        return GenerationTarget("litellm", settings.litellm_base_url, settings.litellm_model)
    return GenerationTarget("groq", settings.groq_api_base_url, settings.groq_theme_model)


def generation_key(settings: Settings) -> SecretStr | None:
    return settings.litellm_api_key if settings.litellm_base_url else settings.groq_api_key


def build_groq_client(settings: Settings) -> httpx.AsyncClient:
    headers = {"Accept": "application/json"}
    key = generation_key(settings)
    if key is not None:
        headers["Authorization"] = f"Bearer {key.get_secret_value()}"
    return httpx.AsyncClient(timeout=settings.groq_timeout_seconds, headers=headers)


NAMING_SYSTEM = "You name product feedback themes. Reply with JSON only."


class GroqClient:
    def __init__(
        self, http: httpx.AsyncClient, *, base_url: str, model: str, provider: str = "groq"
    ) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._provider = provider

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        operation: str = "generation",
    ) -> str:
        model_name = model or self._model
        body = {
            "model": model_name,
            "temperature": 0.2,
            "max_tokens": 2048,
            "reasoning_effort": "low",
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system or NAMING_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        }
        started = time.perf_counter()
        result: str | None = None
        prompt_tokens = 0
        completion_tokens = 0
        try:
            try:
                response = await self._http.post(self._url, json=body)
            except httpx.RequestError as exc:
                result = "timeout"
                raise GroqError("Groq did not respond in time.") from exc
            if response.is_error:
                result = provider_result(response.status_code)
                raise GroqProviderError(response.status_code)
            try:
                payload = response.json()
            except ValueError:
                result = "invalid"
                raise GroqError("Groq returned a response that could not be read.") from None
            prompt_tokens, completion_tokens = _usage_tokens(payload)
            content = message_content(payload)
            result = "ok"
            return content
        except GroqError:
            if result is None:
                result = "invalid"
            raise
        finally:
            observe_provider_call(
                operation=operation,
                provider=self._provider,
                model=model_name,
                result=result or "error",
                seconds=time.perf_counter() - started,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )


def message_content(payload: object) -> str:
    if not isinstance(payload, dict):
        raise GroqError("Groq returned a response that could not be read.")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise GroqError("Groq returned a response that could not be read.")
    message: Any = choices[0].get("message")
    if not isinstance(message, dict):
        raise GroqError("Groq returned a response that could not be read.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GroqError("Groq returned a response that could not be read.")
    return content


def _usage_tokens(payload: object) -> tuple[int, int]:
    if not isinstance(payload, dict):
        return (0, 0)
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return (0, 0)
    return (_token_count(usage.get("prompt_tokens")), _token_count(usage.get("completion_tokens")))


def _token_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _provider_message(status_code: int) -> str:
    if status_code in {401, 403}:
        return "The Groq API key was rejected."
    if status_code == 429:
        return "Groq's free-tier limit was reached. Try again in a minute."
    return f"Groq returned HTTP {status_code}."

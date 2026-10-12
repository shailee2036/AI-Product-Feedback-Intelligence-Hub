import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from feedback_hub.config import Settings
from feedback_hub.feedback.groq import (
    GroqClient,
    build_groq_client,
    generation_key,
    generation_target,
)

PROXY = "http://feedback-hub-litellm:4000/v1"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "gemini_api_key": None,
        "groq_api_key": None,
        "litellm_base_url": None,
        "litellm_api_key": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_groq_is_the_default_target() -> None:
    settings = _settings(groq_api_key=SecretStr("groq-key"))

    target = generation_target(settings)

    assert target.provider == "groq"
    assert target.base_url == "https://api.groq.com/openai/v1"
    assert target.model == "openai/gpt-oss-20b"
    assert generation_key(settings) == settings.groq_api_key


def test_a_proxy_url_routes_generation_through_litellm() -> None:
    settings = _settings(
        groq_api_key=SecretStr("groq-key"),
        litellm_base_url=PROXY,
        litellm_api_key=SecretStr("sk-proxy"),
    )

    target = generation_target(settings)

    assert target == ("litellm", PROXY, "theme-writer")
    assert generation_key(settings) == settings.litellm_api_key


def test_a_proxy_without_its_key_is_not_configured() -> None:
    settings = _settings(groq_api_key=SecretStr("groq-key"), litellm_base_url=PROXY)

    assert generation_key(settings) is None


@pytest.mark.asyncio
async def test_proxy_requests_use_the_master_key_and_model_alias() -> None:
    settings = _settings(
        groq_api_key=SecretStr("groq-key"),
        litellm_base_url=PROXY,
        litellm_api_key=SecretStr("sk-proxy"),
    )
    target = generation_target(settings)
    with respx.mock() as router:
        route = router.post(f"{PROXY}/chat/completions").respond(
            200, json={"choices": [{"message": {"content": "{}"}}]}
        )
        async with build_groq_client(settings) as http:
            client = GroqClient(http, base_url=target.base_url, model=target.model)
            await client.complete("Name the themes.")

    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer sk-proxy"
    assert json.loads(request.content)["model"] == "theme-writer"


@pytest.mark.asyncio
async def test_brief_requests_do_not_override_the_proxy_model() -> None:
    with respx.mock() as router:
        route = router.post(f"{PROXY}/chat/completions").respond(
            200, json={"choices": [{"message": {"content": "{}"}}]}
        )
        async with httpx.AsyncClient() as http:
            client = GroqClient(http, base_url=PROXY, model="theme-writer")
            await client.complete("Write the brief.", system="Reply with JSON only.")

    assert json.loads(route.calls[0].request.content)["model"] == "theme-writer"

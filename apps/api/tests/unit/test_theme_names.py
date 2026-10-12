import json

import httpx
import pytest
import respx

from feedback_hub.feedback.groq import GroqClient, GroqError, GroqProviderError, message_content
from feedback_hub.feedback.theme_names import (
    naming_prompt,
    parse_theme_names,
    representative_lines,
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def test_representative_lines_redact_emails_and_keep_six() -> None:
    titles = [f"ada{index}@example.com import {index}" for index in range(8)]

    lines = representative_lines(titles)

    assert len(lines) == 6
    assert all("@example.com" not in line for line in lines)
    assert all("[email]" in line for line in lines)


def test_parse_theme_names_reads_json_and_fences() -> None:
    raw = (
        "```json\n"
        + json.dumps(
            {
                "themes": [
                    {
                        "id": "1",
                        "name": "Import progress",
                        "summary": "People want import progress.",
                    },
                    {"id": "2", "name": "", "summary": "Missing a name."},
                    "skip",
                ]
            }
        )
        + "\n```"
    )

    parsed = parse_theme_names(raw)

    assert parsed == {"1": ("Import progress", "People want import progress.")}


def test_parse_theme_names_redacts_a_copied_email() -> None:
    raw = json.dumps(
        {
            "themes": [
                {
                    "id": "1",
                    "name": "Mail ada@example.com",
                    "summary": "Write ada@example.com for help with imports.",
                }
            ]
        }
    )

    name, summary = parse_theme_names(raw)["1"]

    assert "ada@example.com" not in name
    assert "ada@example.com" not in summary
    assert "[email]" in name


def test_parse_theme_names_rejects_prose() -> None:
    with pytest.raises(ValueError, match="could not be read"):
        parse_theme_names("Here are the themes.")


def test_naming_prompt_lists_samples() -> None:
    prompt = naming_prompt([("1", ["Import progress"])])

    assert "Theme 1" in prompt
    assert "Import progress" in prompt


def test_message_content_requires_text() -> None:
    with pytest.raises(GroqError, match="could not be read"):
        message_content({"choices": [{"message": {"content": "  "}}]})


@pytest.mark.asyncio
async def test_groq_client_reads_json_content() -> None:
    with respx.mock() as router:
        route = router.post(GROQ_URL).respond(
            200,
            json={"choices": [{"message": {"content": '{"themes": []}'}}]},
        )
        async with httpx.AsyncClient() as http:
            client = GroqClient(http, base_url="https://api.groq.com/openai/v1", model="m")
            content = await client.complete("Name the themes.")

    assert content == '{"themes": []}'
    assert route.calls[0].request.headers["content-type"].startswith("application/json")
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "m"
    assert sent["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_groq_client_hides_provider_bodies() -> None:
    with respx.mock() as router:
        router.post(GROQ_URL).respond(401, json={"error": "rejected sk-secretvalue"})
        async with httpx.AsyncClient() as http:
            client = GroqClient(http, base_url="https://api.groq.com/openai/v1", model="m")
            with pytest.raises(GroqProviderError, match="rejected") as caught:
                await client.complete("Name the themes.")

    assert "sk-secretvalue" not in str(caught.value)


@pytest.mark.asyncio
async def test_groq_client_reports_the_free_tier_limit() -> None:
    with respx.mock() as router:
        router.post(GROQ_URL).respond(429, json={"error": "slow down"})
        async with httpx.AsyncClient() as http:
            client = GroqClient(http, base_url="https://api.groq.com/openai/v1", model="m")
            with pytest.raises(GroqProviderError, match="free-tier"):
                await client.complete("Name the themes.")

import json

from feedback_hub.feedback.normalize import prepare_text

NAME_LIMIT = 80
SUMMARY_LIMIT = 400
SAMPLE_LIMIT = 6
SAMPLE_CHARS = 160
UNREADABLE = "Groq returned a response that could not be read."


def representative_lines(titles: list[str], *, limit: int = SAMPLE_LIMIT) -> list[str]:
    """Redacted titles only. Bodies stay in the database."""
    lines: list[str] = []
    for title in titles:
        text = prepare_text(title).text[:SAMPLE_CHARS].strip()
        if text and text not in lines:
            lines.append(text)
        if len(lines) == limit:
            break
    return lines


def naming_prompt(themes: list[tuple[str, list[str]]]) -> str:
    lines = [
        "Name each product-feedback theme from the short samples.",
        "Reply with JSON only: "
        '{"themes":[{"id":"1","name":"short name","summary":"one sentence"}]}',
        "Each name is at most 6 words. Each summary is one sentence.",
    ]
    for theme_id, samples in themes:
        lines.append(f"Theme {theme_id}")
        lines.extend(f"- {sample}" for sample in samples)
    return "\n".join(lines)


def parse_theme_names(raw: str) -> dict[str, tuple[str, str]]:
    payload = _load_json(raw)
    themes = payload.get("themes") if isinstance(payload, dict) else None
    if not isinstance(themes, list):
        raise ValueError(UNREADABLE)
    parsed: dict[str, tuple[str, str]] = {}
    for item in themes:
        if not isinstance(item, dict):
            continue
        theme_id = item.get("id")
        name = _label(item.get("name"), NAME_LIMIT)
        summary = _label(item.get("summary"), SUMMARY_LIMIT)
        if isinstance(theme_id, str) and name and summary:
            parsed[theme_id] = (name, summary)
    return parsed


def _label(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return prepare_text(value).text[:limit].strip()


def _load_json(raw: str) -> object:
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(UNREADABLE) from exc
    return loaded

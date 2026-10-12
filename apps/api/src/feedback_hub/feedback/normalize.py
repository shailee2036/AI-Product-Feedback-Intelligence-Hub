import hashlib
import re
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_NOISE = re.compile(r"[*_`>#]+")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-])?(?:\(?\d{3}\)?[\s.-])\d{3}[\s.-]\d{4}(?!\w)")
_SECRET = re.compile(r"\b(?:hf_|ghp_|github_pat_|sk-)[A-Za-z0-9_\-]{10,}\b")
_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
_MIN_CHARS = 12
_MAX_CHARS = 2_000


@dataclass(frozen=True, slots=True)
class PreparedText:
    text: str
    language: str
    content_hash: str
    redaction_count: int
    skip_reason: str | None


def source_text(*, source: str, title: str, body: str) -> str:
    """CSV rows already repeat the feedback in the title. Issues need both."""
    if source == "csv":
        return body or title
    return f"{title}\n{body}".strip()


def prepare_text(raw: str, *, declared_language: str | None = None) -> PreparedText:
    """Canonicalize markup and whitespace, redact obvious PII, and hash the result.

    The hash is of the redacted text. The original email, phone, or token is not stored.
    """
    text = _MARKDOWN_LINK.sub(r"\1", raw)
    text, emails = _EMAIL.subn("[email]", text)
    text, phones = _PHONE.subn("[phone]", text)
    text, secrets = _SECRET.subn("[secret]", text)
    text = _WHITESPACE.sub(" ", _MARKDOWN_NOISE.sub("", text)).strip()
    text = text[:_MAX_CHARS]
    redactions = emails + phones + secrets
    language = _language(text, declared_language)
    digest = hashlib.sha256(text.encode()).hexdigest()
    skip = "too_short" if len(text) < _MIN_CHARS else None
    return PreparedText(text, language, digest, redactions, skip)


def _language(text: str, declared: str | None) -> str:
    if declared and _LANGUAGE.fullmatch(declared):
        return declared
    lowered = text.casefold()
    if any(mark in lowered for mark in ("á", "é", "í", "ó", "ú", "ñ", "¿", "¡")):
        return "es"
    letters = [char for char in text if char.isalpha()]
    if letters and all(char.isascii() for char in letters):
        return "en"
    return "und"

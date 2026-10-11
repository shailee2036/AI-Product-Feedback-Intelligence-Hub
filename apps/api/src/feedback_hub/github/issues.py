import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

_WHITESPACE = re.compile(r"\s+")
_MAX_TITLE = 300
_MAX_BODY = 100_000
_MAX_LABELS = 50
_MAX_LABEL_LENGTH = 100


@dataclass(frozen=True, slots=True)
class ImportedIssue:
    external_id: str
    number: int
    title: str
    body: str
    body_normalized: str
    state: str
    html_url: str
    labels: list[str]
    comment_count: int
    reactions_total: int
    author_hash: str | None
    source_created_at: datetime
    source_updated_at: datetime


@dataclass(frozen=True, slots=True)
class PreparedIssue:
    issue: ImportedIssue | None
    skip_reason: str | None


def prepare_issue(payload: dict[str, object]) -> PreparedIssue:
    """Turn one GitHub issue payload into a stored record, or a reason to skip it.

    The author login is never stored. A hash of the GitHub user node id is kept instead.
    """
    if "pull_request" in payload:
        return PreparedIssue(None, "pull_request")

    user = payload.get("user")
    if isinstance(user, dict) and user.get("type") == "Bot":
        return PreparedIssue(None, "bot")

    labels = _labels(payload.get("labels"))
    if any(label.casefold().startswith("security") for label in labels):
        return PreparedIssue(None, "security")

    external_id = payload.get("node_id")
    number = payload.get("number")
    title = payload.get("title")
    state = payload.get("state")
    html_url = payload.get("html_url")
    created = _timestamp(payload.get("created_at"))
    updated = _timestamp(payload.get("updated_at"))
    if (
        not isinstance(external_id, str)
        or not isinstance(number, int)
        or number < 1
        or not isinstance(title, str)
        or state not in {"open", "closed"}
        or not isinstance(html_url, str)
        or not html_url.startswith("https://github.com/")
        or created is None
        or updated is None
    ):
        return PreparedIssue(None, "invalid")

    cleaned_title = _collapse(title)[:_MAX_TITLE]
    if not cleaned_title:
        return PreparedIssue(None, "invalid")

    body = payload.get("body")
    raw_body = body if isinstance(body, str) else ""
    reactions = payload.get("reactions")
    total = reactions.get("total_count") if isinstance(reactions, dict) else 0
    comments = payload.get("comments")

    return PreparedIssue(
        ImportedIssue(
            external_id=external_id[:200],
            number=number,
            title=cleaned_title,
            body=raw_body[:_MAX_BODY],
            body_normalized=_collapse(raw_body)[:_MAX_BODY],
            state=state,
            html_url=html_url,
            labels=labels,
            comment_count=comments if isinstance(comments, int) and comments >= 0 else 0,
            reactions_total=total if isinstance(total, int) and total >= 0 else 0,
            author_hash=_author_hash(user),
            source_created_at=created,
            source_updated_at=updated,
        ),
        None,
    )


def _labels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip()[:_MAX_LABEL_LENGTH])
        if len(names) == _MAX_LABELS:
            break
    return names


def _author_hash(user: object) -> str | None:
    if not isinstance(user, dict):
        return None
    node_id = user.get("node_id")
    if not isinstance(node_id, str) or not node_id:
        return None
    return hashlib.sha256(node_id.encode()).hexdigest()


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _collapse(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()

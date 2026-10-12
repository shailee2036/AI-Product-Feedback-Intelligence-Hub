"""Draft a new issue from a theme. GitHub is not written."""

import re
from dataclasses import dataclass

from feedback_hub.feedback.normalize import prepare_text

TITLE_LIMIT = 120
BODY_LIMIT = 2000
LABEL_LIMIT = 5
_REPORTS = 6
_NON_LABEL = re.compile(r"[^a-z0-9-]+")
_HYPHENS = re.compile(r"-+")


@dataclass(frozen=True, slots=True)
class NewIssueText:
    title: str
    body: str
    labels: tuple[str, ...]


def draft_new_issue(
    *,
    theme_name: str | None,
    theme_summary: str | None,
    brief_problem: str | None,
    brief_impact: str | None,
    brief_evidence: str | None,
    reports: list[str],
    areas: list[str | None],
) -> NewIssueText:
    """Build a title and body from the theme. Each piece is redacted before it is joined."""
    title = (
        _one_line(theme_name)
        or _one_line(brief_problem)
        or _one_line(theme_summary)
        or "Feedback theme"
    )
    title = title[:TITLE_LIMIT].rstrip()
    parts: list[str] = []
    for piece in (brief_problem, theme_summary, brief_impact, brief_evidence):
        cleaned = _one_line(piece)
        if not cleaned or cleaned == title or cleaned in parts:
            continue
        parts.append(cleaned)
    cleaned_reports: list[str] = []
    for report in reports:
        cleaned = _one_line(report)
        if not cleaned or cleaned in cleaned_reports:
            continue
        cleaned_reports.append(cleaned)
        if len(cleaned_reports) == _REPORTS:
            break
    if cleaned_reports:
        parts.append("Related reports:")
        parts.extend(f"- {report}" for report in cleaned_reports)
    if not parts:
        parts.append(title)
    body = "\n".join(parts)
    if len(body) > BODY_LIMIT:
        body = body[:BODY_LIMIT].rstrip()
    return NewIssueText(title=title, body=body, labels=tuple(_labels(areas)))


def clean_issue_title(value: str) -> str:
    return _one_line(value)[:TITLE_LIMIT].rstrip()


def clean_issue_body(value: str) -> str:
    lines: list[str] = []
    for line in value.splitlines():
        cleaned = _one_line(line)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)[:BODY_LIMIT].rstrip()


def _one_line(value: str | None) -> str:
    if not value:
        return ""
    return prepare_text(value).text


def _labels(areas: list[str | None]) -> list[str]:
    labels: list[str] = []
    for area in areas:
        slug = _HYPHENS.sub("-", _NON_LABEL.sub("-", _one_line(area).lower())).strip("-")
        slug = slug[:50].strip("-")
        if not slug or slug in labels:
            continue
        labels.append(slug)
        if len(labels) == LABEL_LIMIT:
            break
    return labels

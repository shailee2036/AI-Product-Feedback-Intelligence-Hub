"""Draft a comment and labels for a canonical issue. GitHub is not written."""

import re
from dataclasses import dataclass

from feedback_hub.feedback.normalize import prepare_text

COMMENT_LIMIT = 2000
LABEL_LIMIT = 5
_REPORTS = 6
_NON_LABEL = re.compile(r"[^a-z0-9-]+")
_HYPHENS = re.compile(r"-+")


@dataclass(frozen=True, slots=True)
class IssueDraft:
    comment: str
    labels: tuple[str, ...]


def suggest_issue_update(
    *,
    number: int,
    theme_name: str | None,
    theme_summary: str | None,
    brief_problem: str | None,
    brief_evidence: str | None,
    reports: list[str],
    areas: list[str | None],
) -> IssueDraft:
    """Build a short comment from the brief and related CSV titles.

    Each piece is redacted before it is joined. The result is a draft, not a GitHub write.
    """
    parts = [f"Related feedback for #{number}."]
    lead = _clean(brief_problem) or _clean(theme_summary) or _clean(theme_name)
    if lead:
        parts.append(lead)
    evidence = _clean(brief_evidence)
    if evidence and evidence != lead:
        parts.append(evidence)
    cleaned_reports: list[str] = []
    for title in reports:
        cleaned = _clean(title)
        if not cleaned or cleaned in cleaned_reports:
            continue
        cleaned_reports.append(cleaned)
        if len(cleaned_reports) == _REPORTS:
            break
    if cleaned_reports:
        parts.append("Related reports:")
        parts.extend(f"- {title}" for title in cleaned_reports)
    comment = "\n".join(parts)
    if len(comment) > COMMENT_LIMIT:
        comment = comment[:COMMENT_LIMIT].rstrip()
    return IssueDraft(comment=comment, labels=tuple(_labels(areas)))


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return prepare_text(value).text


def _labels(areas: list[str | None]) -> list[str]:
    labels: list[str] = []
    for area in areas:
        slug = _HYPHENS.sub("-", _NON_LABEL.sub("-", _clean(area).lower())).strip("-")
        slug = slug[:50].strip("-")
        if not slug or slug in labels:
            continue
        labels.append(slug)
        if len(labels) == LABEL_LIMIT:
            break
    return labels

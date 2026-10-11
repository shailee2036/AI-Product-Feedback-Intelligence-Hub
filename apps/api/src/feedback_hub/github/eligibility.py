from collections.abc import Collection
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class IneligibilityReason(StrEnum):
    NOT_PUBLIC = "not_public"
    NOT_ORGANIZATION_OWNED = "not_organization_owned"
    LICENSE_MISSING = "license_missing"
    LICENSE_NOT_ALLOWED = "license_not_allowed"
    ISSUES_DISABLED = "issues_disabled"
    ARCHIVED = "archived"
    DISABLED = "disabled"


class RepositorySummary(BaseModel):
    node_id: str
    owner: str
    name: str
    full_name: str
    html_url: str
    default_branch: str
    license_spdx: str | None
    open_issues_count: int


class EligibilityResult(BaseModel):
    eligible: bool
    reasons: list[IneligibilityReason]
    repository: RepositorySummary


def evaluate_eligibility(
    payload: dict[str, Any], allowed_licenses: Collection[str]
) -> EligibilityResult:
    """Apply the v1 eligibility gate to a GitHub `GET /repos/{owner}/{repo}` payload."""
    reasons: list[IneligibilityReason] = []

    if payload.get("private", True) or payload.get("visibility", "public") != "public":
        reasons.append(IneligibilityReason.NOT_PUBLIC)

    owner = payload.get("owner") or {}
    if owner.get("type") != "Organization":
        reasons.append(IneligibilityReason.NOT_ORGANIZATION_OWNED)

    license_info = payload.get("license") or {}
    spdx = license_info.get("spdx_id")
    if not spdx or spdx == "NOASSERTION":
        reasons.append(IneligibilityReason.LICENSE_MISSING)
        spdx = None
    elif spdx not in allowed_licenses:
        reasons.append(IneligibilityReason.LICENSE_NOT_ALLOWED)

    if not payload.get("has_issues", False):
        reasons.append(IneligibilityReason.ISSUES_DISABLED)
    if payload.get("archived", False):
        reasons.append(IneligibilityReason.ARCHIVED)
    if payload.get("disabled", False):
        reasons.append(IneligibilityReason.DISABLED)

    summary = RepositorySummary(
        node_id=payload["node_id"],
        owner=owner.get("login", ""),
        name=payload["name"],
        full_name=payload["full_name"],
        html_url=payload["html_url"],
        default_branch=payload.get("default_branch", "main"),
        license_spdx=spdx,
        open_issues_count=payload.get("open_issues_count", 0),
    )
    return EligibilityResult(eligible=not reasons, reasons=reasons, repository=summary)

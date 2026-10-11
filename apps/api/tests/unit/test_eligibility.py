from typing import Any

import pytest

from feedback_hub.config import Settings
from feedback_hub.github.eligibility import IneligibilityReason, evaluate_eligibility

ALLOWED = Settings().allowed_licenses


def test_appwrite_is_eligible(appwrite_repo_payload: dict[str, Any]) -> None:
    result = evaluate_eligibility(appwrite_repo_payload, ALLOWED)

    assert result.eligible
    assert result.reasons == []
    assert result.repository.node_id == appwrite_repo_payload["node_id"]
    assert result.repository.license_spdx == "BSD-3-Clause"


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"private": True}, IneligibilityReason.NOT_PUBLIC),
        ({"visibility": "internal"}, IneligibilityReason.NOT_PUBLIC),
        (
            {"owner": {"login": "someone", "type": "User"}},
            IneligibilityReason.NOT_ORGANIZATION_OWNED,
        ),
        ({"license": None}, IneligibilityReason.LICENSE_MISSING),
        ({"license": {"spdx_id": "NOASSERTION"}}, IneligibilityReason.LICENSE_MISSING),
        ({"license": {"spdx_id": "BUSL-1.1"}}, IneligibilityReason.LICENSE_NOT_ALLOWED),
        ({"has_issues": False}, IneligibilityReason.ISSUES_DISABLED),
        ({"archived": True}, IneligibilityReason.ARCHIVED),
        ({"disabled": True}, IneligibilityReason.DISABLED),
    ],
)
def test_single_rule_failures(
    appwrite_repo_payload: dict[str, Any], patch: dict[str, Any], reason: IneligibilityReason
) -> None:
    result = evaluate_eligibility({**appwrite_repo_payload, **patch}, ALLOWED)

    assert not result.eligible
    assert result.reasons == [reason]


def test_reports_every_failed_rule(appwrite_repo_payload: dict[str, Any]) -> None:
    payload = {**appwrite_repo_payload, "archived": True, "has_issues": False, "license": None}

    result = evaluate_eligibility(payload, ALLOWED)

    assert set(result.reasons) == {
        IneligibilityReason.ARCHIVED,
        IneligibilityReason.ISSUES_DISABLED,
        IneligibilityReason.LICENSE_MISSING,
    }
    assert result.repository.license_spdx is None


def test_missing_privacy_flag_fails_closed(appwrite_repo_payload: dict[str, Any]) -> None:
    payload = {k: v for k, v in appwrite_repo_payload.items() if k != "private"}

    assert IneligibilityReason.NOT_PUBLIC in evaluate_eligibility(payload, ALLOWED).reasons

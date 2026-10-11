"""Validate the committed seed fixtures. Usage: python -m feedback_hub.seed.validate <seed-dir>"""

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

from feedback_hub.config import Settings
from feedback_hub.feedback.csv_schema import parse_feedback_csv
from feedback_hub.github.refs import InvalidRepositoryReferenceError, parse_repository_reference

SOURCE_FILE = "appwrite-github-source.json"

APPWRITE_PRODUCT_AREAS = frozenset(
    {
        "Auth",
        "Databases",
        "Storage",
        "Functions",
        "Realtime",
        "Messaging",
        "Sites",
        "SDKs",
        "Console",
        "Deployment",
    }
)
SEED_ID_PREFIX = "AW-SYN-"


class GitHubSeedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
    repository: str
    repository_url: HttpUrl
    issues_url: HttpUrl
    visibility: Literal["public"]
    expected_license_spdx: str
    issue_states: list[Literal["open", "closed"]] = Field(min_length=1)
    include_pull_requests: Literal[False]
    include_comments: bool
    order_by: Literal["created", "updated", "comments"]
    direction: Literal["asc", "desc"]
    maximum_issues: int = Field(gt=0, le=5000)


class SeedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str
    product: str
    github: GitHubSeedSource
    csv_fixture: str = Field(pattern=r"^[A-Za-z0-9._-]+\.csv$")
    disclaimer: str = Field(min_length=20)


def validate_seed_directory(seed_dir: Path, settings: Settings) -> list[str]:
    problems: list[str] = []

    try:
        source = SeedSource.model_validate(
            json.loads((seed_dir / SOURCE_FILE).read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        return [f"{SOURCE_FILE}: {exc}"]

    github = source.github
    try:
        ref = parse_repository_reference(f"{github.owner}/{github.repository}")
    except InvalidRepositoryReferenceError as exc:
        problems.append(f"{SOURCE_FILE}: {exc}")
    else:
        if str(github.repository_url).rstrip("/") != f"https://github.com/{ref.full_name}":
            problems.append(f"{SOURCE_FILE}: repository_url does not match owner/repository.")
    if github.expected_license_spdx not in settings.allowed_licenses:
        problems.append(f"{SOURCE_FILE}: license {github.expected_license_spdx} not allowed.")
    if "synthetic" not in source.disclaimer.lower():
        problems.append(f"{SOURCE_FILE}: disclaimer must state the CSV is synthetic.")

    csv_path = seed_dir / source.csv_fixture
    try:
        text = csv_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [*problems, f"{source.csv_fixture}: {exc}"]

    report = parse_feedback_csv(
        text, max_rows=settings.csv_max_rows, max_feedback_chars=settings.csv_max_feedback_chars
    )
    problems.extend(
        f"{source.csv_fixture}:{err.row} {err.column or ''} {err.message}".strip()
        for err in report.errors
    )
    problems.extend(f"{source.csv_fixture}: {warning}" for warning in report.warnings)

    for row in report.rows:
        where = f"{source.csv_fixture}: {row.feedback_id}"
        if not row.is_synthetic:
            problems.append(f"{where} must have is_synthetic=true.")
        if not row.feedback_id.startswith(SEED_ID_PREFIX):
            problems.append(f"{where} must use the {SEED_ID_PREFIX} prefix.")
        if row.product_area not in APPWRITE_PRODUCT_AREAS:
            problems.append(f"{where} has unknown product_area {row.product_area!r}.")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2

    problems = validate_seed_directory(Path(args[0]), Settings())
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("Seed data is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

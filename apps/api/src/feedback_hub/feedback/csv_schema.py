import csv
import io
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

REQUIRED_COLUMNS = ("feedback_id", "created_at", "feedback")
OPTIONAL_COLUMNS = (
    "source",
    "customer_segment",
    "product_area",
    "rating",
    "severity",
    "language",
    "is_synthetic",
)
KNOWN_COLUMNS = frozenset(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

ShortLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FeedbackRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    feedback_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9._:-]{1,128}$"),
    ]
    created_at: AwareDatetime
    feedback: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    source: ShortLabel | None = None
    customer_segment: ShortLabel | None = None
    product_area: ShortLabel | None = None
    rating: Annotated[int, Field(ge=1, le=5)] | None = None
    severity: Severity | None = None
    language: (
        Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")] | None
    ) = None
    is_synthetic: bool = False

    @field_validator("created_at")
    @classmethod
    def _not_in_future(cls, value: datetime) -> datetime:
        if value > datetime.now(value.tzinfo):
            raise ValueError("created_at cannot be in the future")
        return value


class RowError(BaseModel):
    row: int = Field(description="1-based line number in the file, including the header.")
    column: str | None
    message: str


class CsvValidationReport(BaseModel):
    rows: list[FeedbackRow]
    errors: list[RowError]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def parse_feedback_csv(text: str, *, max_rows: int, max_feedback_chars: int) -> CsvValidationReport:
    """Validate an uploaded feedback CSV, collecting every row error instead of failing fast."""
    reader = csv.DictReader(io.StringIO(text.removeprefix("\ufeff"), newline=""))
    header = [name.strip() for name in reader.fieldnames or []]
    reader.fieldnames = header

    errors: list[RowError] = []
    warnings: list[str] = []

    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        errors.append(RowError(row=1, column=None, message=f"Missing columns: {missing}"))
        return CsvValidationReport(rows=[], errors=errors, warnings=warnings)
    if len(set(header)) != len(header):
        errors.append(RowError(row=1, column=None, message="Duplicate column names."))
        return CsvValidationReport(rows=[], errors=errors, warnings=warnings)

    unknown = sorted(set(header) - KNOWN_COLUMNS)
    if unknown:
        warnings.append(f"Ignoring unknown columns: {unknown}")

    rows: list[FeedbackRow] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(reader):
        line = index + 2
        if index >= max_rows:
            errors.append(RowError(row=line, column=None, message=f"More than {max_rows} rows."))
            break
        if None in record:
            errors.append(RowError(row=line, column=None, message="Too many fields in row."))
            continue

        values = {
            key: value
            for key, value in record.items()
            if key in KNOWN_COLUMNS and value is not None and value.strip()
        }
        feedback = values.get("feedback") or ""
        if len(feedback) > max_feedback_chars:
            errors.append(
                RowError(
                    row=line,
                    column="feedback",
                    message=f"Feedback exceeds {max_feedback_chars} characters.",
                )
            )
            continue

        try:
            row = FeedbackRow.model_validate(values)
        except ValidationError as exc:
            errors.extend(
                RowError(
                    row=line, column=str(err["loc"][0]) if err["loc"] else None, message=err["msg"]
                )
                for err in exc.errors()
            )
            continue

        if row.feedback_id in seen_ids:
            errors.append(
                RowError(row=line, column="feedback_id", message="Duplicate feedback_id.")
            )
            continue
        seen_ids.add(row.feedback_id)
        rows.append(row)

    if not rows and not errors:
        errors.append(RowError(row=1, column=None, message="CSV contains no feedback rows."))
    return CsvValidationReport(rows=rows, errors=errors, warnings=warnings)


def neutralize_spreadsheet_formula(value: str) -> str:
    """Prefix cells that spreadsheet apps would evaluate as formulas when exporting."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value

import pytest

from feedback_hub.feedback.csv_schema import (
    CsvValidationReport,
    Severity,
    neutralize_spreadsheet_formula,
    parse_feedback_csv,
)

HEADER = "feedback_id,created_at,source,product_area,rating,severity,language,is_synthetic,feedback"


def parse(text: str, *, max_rows: int = 100, max_chars: int = 500) -> CsvValidationReport:
    return parse_feedback_csv(text, max_rows=max_rows, max_feedback_chars=max_chars)


def test_valid_rows_are_parsed() -> None:
    report = parse(
        f"{HEADER}\n"
        'F-1,2026-06-03T09:15:00Z,survey,Auth,4,low,en,true,"OAuth, please"\n'
        "F-2,2026-06-04T10:00:00+02:00,,,,,,,Realtime drops\n"
    )

    assert report.ok
    assert [row.feedback_id for row in report.rows] == ["F-1", "F-2"]
    first, second = report.rows
    assert first.severity is Severity.LOW
    assert first.rating == 4
    assert first.is_synthetic
    assert first.feedback == "OAuth, please"
    assert second.source is None
    assert second.rating is None
    assert not second.is_synthetic


def test_minimal_header_and_bom_are_accepted() -> None:
    report = parse("\ufefffeedback_id,created_at,feedback\nF-1,2026-01-01T00:00:00Z,hello\n")

    assert report.ok
    assert report.rows[0].feedback == "hello"


def test_missing_required_columns_rejects_file() -> None:
    report = parse("feedback_id,feedback\nF-1,hello\n")

    assert not report.ok
    assert "created_at" in report.errors[0].message
    assert report.rows == []


def test_duplicate_columns_reject_file() -> None:
    report = parse("feedback_id,created_at,feedback,feedback\nF-1,2026-01-01T00:00:00Z,a,b\n")

    assert report.errors[0].message == "Duplicate column names."


def test_unknown_columns_warn() -> None:
    report = parse("feedback_id,created_at,feedback,email\nF-1,2026-01-01T00:00:00Z,hi,a@b.c\n")

    assert report.ok
    assert report.warnings == ["Ignoring unknown columns: ['email']"]


@pytest.mark.parametrize(
    ("row", "column"),
    [
        ("F 1,2026-01-01T00:00:00Z,,,,,,,text", "feedback_id"),
        ("F-1,2026-01-01,,,,,,,text", "created_at"),
        ("F-1,2026-01-01T00:00:00,,,,,,,text", "created_at"),
        ("F-1,2999-01-01T00:00:00Z,,,,,,,text", "created_at"),
        ("F-1,2026-01-01T00:00:00Z,,,6,,,,text", "rating"),
        ("F-1,2026-01-01T00:00:00Z,,,,urgent,,,text", "severity"),
        ("F-1,2026-01-01T00:00:00Z,,,,,English,,text", "language"),
        ("F-1,2026-01-01T00:00:00Z,,,,,,maybe,text", "is_synthetic"),
        ("F-1,2026-01-01T00:00:00Z,,,,,,,   ", "feedback"),
    ],
)
def test_row_errors_identify_line_and_column(row: str, column: str) -> None:
    report = parse(f"{HEADER}\n{row}\n")

    assert not report.ok
    assert report.errors[0].row == 2
    assert report.errors[0].column == column


def test_errors_are_collected_across_rows() -> None:
    report = parse(
        f"{HEADER}\n"
        "F-1,2026-01-01T00:00:00Z,,,9,,,,a\n"
        "F-2,2026-01-01T00:00:00Z,,,,,,,ok\n"
        "F-3,bad-date,,,,,,,b\n"
    )

    assert [err.row for err in report.errors] == [2, 4]
    assert [row.feedback_id for row in report.rows] == ["F-2"]


def test_duplicate_ids_are_rejected() -> None:
    report = parse(
        "feedback_id,created_at,feedback\nF-1,2026-01-01T00:00:00Z,a\nF-1,2026-01-02T00:00:00Z,b\n"
    )

    assert report.errors[0].row == 3
    assert report.errors[0].message == "Duplicate feedback_id."


def test_extra_fields_in_row_are_rejected() -> None:
    report = parse("feedback_id,created_at,feedback\nF-1,2026-01-01T00:00:00Z,a,extra\n")

    assert report.errors[0].message == "Too many fields in row."


def test_row_and_length_limits() -> None:
    rows = "".join(f"F-{i},2026-01-01T00:00:00Z,text\n" for i in range(3))
    over_rows = parse(f"feedback_id,created_at,feedback\n{rows}", max_rows=2)
    too_long = parse(
        "feedback_id,created_at,feedback\nF-1,2026-01-01T00:00:00Z,abcdef\n", max_chars=5
    )

    assert over_rows.errors[0].message == "More than 2 rows."
    assert len(over_rows.rows) == 2
    assert too_long.errors[0].column == "feedback"


def test_empty_file_is_rejected() -> None:
    assert not parse("").ok
    assert parse("feedback_id,created_at,feedback\n").errors[0].message == (
        "CSV contains no feedback rows."
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('=HYPERLINK("http://x")', '\'=HYPERLINK("http://x")'),
        ("+1", "'+1"),
        ("-cmd", "'-cmd"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\tdata", "'\tdata"),
        ("plain text", "plain text"),
    ],
)
def test_neutralize_spreadsheet_formula(value: str, expected: str) -> None:
    assert neutralize_spreadsheet_formula(value) == expected

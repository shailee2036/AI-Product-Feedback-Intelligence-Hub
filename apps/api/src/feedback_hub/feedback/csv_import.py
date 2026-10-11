import re

from feedback_hub.feedback.csv_schema import FeedbackRow

_WHITESPACE = re.compile(r"\s+")
_MAX_TITLE = 300


class CsvTooLargeError(Exception):
    pass


class CsvEncodingError(Exception):
    pass


def decode_csv(data: bytes, *, max_bytes: int) -> str:
    if len(data) > max_bytes:
        raise CsvTooLargeError
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvEncodingError from exc


def csv_title(row: FeedbackRow) -> str:
    text = _WHITESPACE.sub(" ", row.feedback).strip()
    if row.product_area:
        text = f"{row.product_area}: {text}"
    return text[:_MAX_TITLE]


def normalized_feedback(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()

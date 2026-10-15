from feedback_hub.feedback.normalize import prepare_text
from feedback_hub.observability import (
    DUPLICATE_RATIO,
    GITHUB_RATE_LIMIT,
    IMPORT_RECORDS,
    PROVIDER_COST,
    REDACTIONS,
    observe_duplicate_rate,
    observe_github_quota,
    observe_import_records,
    observe_provider_call,
    provider_cost_usd,
)


def _counter(metric: object, *labels: str) -> float:
    return float(metric.labels(*labels)._value.get())  # type: ignore[attr-defined]


def test_cost_uses_the_configured_rate_and_ignores_a_zero_rate() -> None:
    assert provider_cost_usd(prompt_tokens=1_000_000, prompt_usd_per_million=0.05) == 0.05
    assert provider_cost_usd(texts=2_000_000, embedding_usd_per_million_texts=1.5) == 3
    before = _counter(PROVIDER_COST, "generation", "groq", "priced")
    observe_provider_call(
        operation="generation",
        provider="groq",
        model="priced",
        result="ok",
        seconds=0.1,
        cost_usd=0,
    )
    assert _counter(PROVIDER_COST, "generation", "groq", "priced") == before
    observe_provider_call(
        operation="generation",
        provider="groq",
        model="priced",
        result="error",
        seconds=0.1,
        cost_usd=1.25,
    )
    assert _counter(PROVIDER_COST, "generation", "groq", "priced") == before
    observe_provider_call(
        operation="generation",
        provider="groq",
        model="priced",
        result="ok",
        seconds=0.1,
        cost_usd=0.05,
    )
    assert _counter(PROVIDER_COST, "generation", "groq", "priced") == before + 0.05


def test_import_records_keep_a_small_result_set() -> None:
    before = _counter(IMPORT_RECORDS, "imported")
    failed = _counter(IMPORT_RECORDS, "failed")
    observe_import_records("imported", 3)
    observe_import_records("owner/name", 1)
    assert _counter(IMPORT_RECORDS, "imported") == before + 3
    assert _counter(IMPORT_RECORDS, "failed") == failed + 1


def test_duplicate_rate_is_edges_over_possible_pairs() -> None:
    observe_duplicate_rate("semantic", edges=1, items=3)
    observe_duplicate_rate("repository", edges=9, items=3)
    assert DUPLICATE_RATIO.labels("semantic")._value.get() == 1 / 3


def test_github_quota_ignores_a_non_numeric_header() -> None:
    observe_github_quota("40")
    assert GITHUB_RATE_LIMIT._value.get() == 40
    observe_github_quota("owner/name")
    assert GITHUB_RATE_LIMIT._value.get() == 40


def test_redaction_counts_the_category_and_not_the_address() -> None:
    before = _counter(REDACTIONS, "email")
    prepare_text("Please email ada@example.com about this checkout bug today.")
    assert _counter(REDACTIONS, "email") == before + 1

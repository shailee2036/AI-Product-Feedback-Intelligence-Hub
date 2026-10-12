from feedback_hub.feedback.normalize import prepare_text, source_text


def test_prepare_text_redacts_contacts_and_secrets() -> None:
    prepared = prepare_text(
        "Email me at ada@example.com or call 415-555-0199. Token hf_abcdefghijklmnopqrstuvwxyz"
    )

    assert "ada@example.com" not in prepared.text
    assert "415-555-0199" not in prepared.text
    assert "hf_abcdefghijklmnopqrstuvwxyz" not in prepared.text
    assert "[email]" in prepared.text
    assert "[phone]" in prepared.text
    assert "[secret]" in prepared.text
    assert prepared.redaction_count == 3
    assert prepared.skip_reason is None
    assert prepared.language == "en"
    assert len(prepared.content_hash) == 64


def test_redacted_hash_does_not_change_when_wording_is_unchanged() -> None:
    first = prepare_text("Please email ada@example.com about OAuth.")
    second = prepare_text("Please email ada@example.com about OAuth.")

    assert first.content_hash == second.content_hash


def test_declared_language_and_short_text() -> None:
    spanish = prepare_text("Necesitamos una guía más clara para copias.", declared_language="es")
    short = prepare_text("too short")

    assert spanish.language == "es"
    assert short.skip_reason == "too_short"


def test_markdown_links_keep_the_label() -> None:
    prepared = prepare_text("Read [the import guide](https://example.com/docs) before uploading.")
    brackets = prepare_text("[" * 20_000)
    unfinished = prepare_text("See [docs](https://example.com/docs before you upload the rows.")
    empty_url = prepare_text("See [docs]() before you upload the spreadsheet rows.")

    assert prepared.text == "Read the import guide before uploading."
    assert brackets.text == "[" * 2_000
    assert unfinished.text == "See [docs](https://example.com/docs before you upload the rows."
    assert empty_url.text == "See [docs]() before you upload the spreadsheet rows."


def test_csv_text_does_not_repeat_the_title() -> None:
    assert (
        source_text(source="csv", title="Auth: hello", body="hello there friend")
        == "hello there friend"
    )
    assert source_text(source="github_issue", title="Login", body="fails") == "Login\nfails"

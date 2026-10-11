import pytest

from feedback_hub.github.refs import (
    InvalidRepositoryReferenceError,
    RepositoryRef,
    parse_repository_reference,
)


@pytest.mark.parametrize(
    "value",
    [
        "appwrite/appwrite",
        " appwrite/appwrite ",
        "https://github.com/appwrite/appwrite",
        "https://github.com/appwrite/appwrite/",
        "https://github.com/appwrite/appwrite.git",
        "https://www.github.com/appwrite/appwrite",
    ],
)
def test_accepts_supported_forms(value: str) -> None:
    assert parse_repository_reference(value) == RepositoryRef("appwrite", "appwrite")


@pytest.mark.parametrize(
    "value",
    [
        "appwrite",
        "appwrite/appwrite/issues",
        "https://gitlab.com/appwrite/appwrite",
        "https://github.com.evil.example/appwrite/appwrite",
        "https://github.com/appwrite/appwrite?tab=readme",
        "../etc/passwd",
        "owner/..",
        "-owner/repo",
        "owner-/repo",
        "own--er/repo",
        "owner/re po",
        "owner/repo%2F..",
        f"{'a' * 40}/repo",
    ],
)
def test_rejects_invalid_references(value: str) -> None:
    with pytest.raises(InvalidRepositoryReferenceError):
        parse_repository_reference(value)


def test_full_name() -> None:
    assert RepositoryRef("appwrite", "sdk-for-web").full_name == "appwrite/sdk-for-web"

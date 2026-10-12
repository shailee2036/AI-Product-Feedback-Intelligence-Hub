from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from feedback_hub.auth import AuthenticatedUser
from feedback_hub.embedding.runner import run_embeddings
from feedback_hub.feedback.embeddings import EmbeddingProviderError
from feedback_hub.feedback.normalize import prepare_text


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Row:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping


class _Conn:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows
        self.statements: list[str] = []
        self.params: list[object] = []

    async def execute(self, statement: object, params: object = None) -> _Result:
        self.statements.append(str(statement))
        self.params.append(params)
        if "left join" in str(statement):
            return _Result(self.rows)
        return _Result([])


class _Client:
    def __init__(
        self, vectors: list[list[float]] | None = None, error: Exception | None = None
    ) -> None:
        self.vectors = vectors or []
        self.error = error
        self.batches: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(texts)
        if self.error is not None:
            raise self.error
        return self.vectors


class _Database:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    @asynccontextmanager
    async def user_transaction(self, user: object) -> Any:
        yield self.conn


def _item(body: str, embedded_hash: str | None = None) -> _Row:
    return _Row(
        {
            "id": uuid4(),
            "source": "csv",
            "title": "Feedback",
            "body": body,
            "language": "en",
            "content_hash": None,
            "embedded_hash": embedded_hash,
        }
    )


async def test_runner_skips_short_text_and_embeds_the_rest() -> None:
    current = prepare_text("The OAuth callback checklist is still confusing for new teams.")
    rows = [
        _item("hi"),
        _item(current.text, embedded_hash=current.content_hash),
        _item("The storage quota warning appears before the upload finishes."),
    ]
    conn = _Conn(rows)
    client = _Client(vectors=[[0.2, 0.8]])

    await run_embeddings(
        _Database(conn),  # type: ignore[arg-type]
        client,  # type: ignore[arg-type]
        AuthenticatedUser(id=uuid4(), email="pm@example.com", claims={}),
        uuid4(),
        tenant_id=uuid4(),
        product_id=uuid4(),
        provider="huggingface",
        model="test-model",
        model_version="1",
        dimensions=2,
        batch_size=16,
    )

    assert client.batches == [["The storage quota warning appears before the upload finishes."]]
    assert any(
        isinstance(params, dict) and params.get("status") == "succeeded" for params in conn.params
    )
    assert any(
        isinstance(params, dict) and params.get("action") == "embedding.completed"
        for params in conn.params
    )


async def test_runner_keeps_partial_work_when_the_provider_fails() -> None:
    conn = _Conn([_item("The storage quota warning appears before the upload finishes.")])
    client = _Client(error=EmbeddingProviderError(429))

    await run_embeddings(
        _Database(conn),  # type: ignore[arg-type]
        client,  # type: ignore[arg-type]
        AuthenticatedUser(id=uuid4(), email="pm@example.com", claims={}),
        uuid4(),
        tenant_id=uuid4(),
        product_id=uuid4(),
        provider="huggingface",
        model="test-model",
        model_version="1",
        dimensions=2,
        batch_size=16,
    )

    assert any(isinstance(params, dict) and params.get("error_message") for params in conn.params)
    completed = [
        params
        for params in conn.params
        if isinstance(params, dict) and params.get("action") == "embedding.completed"
    ]
    assert completed == []

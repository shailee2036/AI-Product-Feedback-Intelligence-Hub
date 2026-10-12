from datetime import UTC, datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncConnection

from feedback_hub.api.audit import AUDIT_LIMIT, audit_summary
from feedback_hub.db.audit import load_audit_events


class _Result:
    def __init__(self, rows: list["_Row"]) -> None:
        self._rows = rows

    def all(self) -> list["_Row"]:
        return self._rows


class _Row:
    def __init__(self, **kwargs: object) -> None:
        self._mapping = kwargs


class _Conn:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows
        self.sql = ""
        self.params: object = None

    async def execute(self, statement: object, params: object = None) -> _Result:
        self.sql = " ".join(str(statement).split())
        self.params = params
        return _Result(self.rows)


def test_known_actions_use_a_fixed_sentence() -> None:
    assert audit_summary("cluster.approved") == "Approved a theme."
    assert audit_summary("csv.imported") == "Imported a customer-feedback CSV."


def test_unknown_action_stays_unchanged() -> None:
    assert audit_summary("theme.reopened") == "theme.reopened"


async def test_load_reads_newest_events_without_metadata() -> None:
    moment = datetime(2026, 10, 12, tzinfo=UTC)
    conn = _Conn([_Row(id=4, action="cluster.approved", created_at=moment)])

    events = await load_audit_events(cast(AsyncConnection, conn), limit=AUDIT_LIMIT)

    assert "metadata" not in conn.sql
    assert "order by created_at desc, id desc" in conn.sql
    assert conn.params == {"limit": AUDIT_LIMIT}
    assert events[0].id == 4
    assert events[0].action == "cluster.approved"
    assert events[0].created_at == moment

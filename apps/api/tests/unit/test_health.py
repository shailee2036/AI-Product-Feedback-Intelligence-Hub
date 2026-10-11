import httpx

from feedback_hub import __version__


async def test_live_reports_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "checks": {}}


async def test_ready_reports_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_ready_reports_unavailable_database(client: httpx.AsyncClient) -> None:
    from feedback_hub.db.engine import Database

    class BrokenDatabase(Database):
        def __init__(self) -> None:
            pass

        async def ping(self) -> None:
            raise ConnectionError("down")

    transport = client._transport
    assert isinstance(transport, httpx.ASGITransport)
    transport.app.state.database = BrokenDatabase()  # type: ignore[attr-defined]

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "unavailable"}


async def test_metrics_use_route_templates(client: httpx.AsyncClient) -> None:
    await client.get("/health/live")
    await client.get("/does-not-exist")

    body = (await client.get("/metrics/")).text

    assert 'route="/health/live"' in body
    assert 'route="unmatched"' in body
    assert "/does-not-exist" not in body

import httpx

from feedback_hub import __version__


async def test_live_reports_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_ready_reports_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_metrics_use_route_templates(client: httpx.AsyncClient) -> None:
    await client.get("/health/live")
    await client.get("/does-not-exist")

    body = (await client.get("/metrics/")).text

    assert 'route="/health/live"' in body
    assert 'route="unmatched"' in body
    assert "/does-not-exist" not in body

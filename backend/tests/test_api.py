from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def mock_graph(small_graph):
    with patch("app.core.graph.get_graph", return_value=small_graph), \
         patch("app.api.routes.get_graph", return_value=small_graph), \
         patch("app.api.routes.snap_to_node", side_effect=lambda lat, lng: 0 if lat > 37.785 else 3):
        yield


@pytest.mark.asyncio
async def test_health(mock_graph):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_route_returns_coordinates(mock_graph):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/route", json={
            "origin_lat": 37.79, "origin_lng": -122.40,
            "dest_lat": 37.78, "dest_lng": -122.40,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["coordinates"]) > 0
    assert "duration_minutes" in data
    assert "distance_km" in data

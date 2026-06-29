import asyncio
import logging
from datetime import datetime, timezone

import osmnx as ox

from app.core.config import settings
from app.core.graph import get_graph
from app.etl.fetcher import fetch_traffic_events
from app.schemas.route import TrafficResponse, TrafficSegment

logger = logging.getLogger(__name__)

_traffic_data = TrafficResponse(segments=[], updated_at="")
_has_live_traffic = False

_SEVERITY_MULTIPLIER = {"Minor": 1.5, "Moderate": 2.0, "Major": 2.5}
_SEVERITY_LEVEL = {"Minor": 1, "Moderate": 2, "Major": 3}


def get_traffic_data():
    return _traffic_data


def has_live_traffic():
    return _has_live_traffic


async def start_etl_loop():
    while True:
        try:
            await run_etl()
        except Exception as e:
            logger.error(f"ETL pipeline error: {e}")
        await asyncio.sleep(settings.etl_interval_seconds)


async def run_etl():
    global _traffic_data
    logger.info("Running traffic ETL")

    G = get_graph()
    events = await fetch_traffic_events()
    segments = []

    for event in events:
        try:
            coords = event.get("geography", {}).get("coordinates", [])
            if len(coords) < 2:
                continue
            lng, lat = float(coords[0]), float(coords[1])
            severity = event.get("severity", "Minor")
            level = _SEVERITY_LEVEL.get(severity, 1)
            segments.append(TrafficSegment(lat=lat, lng=lng, congestion_level=level))
            _penalize_nearby_edges(G, lat, lng, _SEVERITY_MULTIPLIER.get(severity, 1.5))
        except Exception:
            continue

    global _has_live_traffic
    _traffic_data = TrafficResponse(
        segments=segments,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    if segments:
        _has_live_traffic = True
    logger.info(f"ETL complete: {len(segments)} traffic segments")


def _penalize_nearby_edges(G, lat, lng, multiplier):
    try:
        node = ox.nearest_nodes(G, lng, lat)
        for _, _, data in G.edges(node, data=True):
            length = data.get("length", 100)
            speed_ms = data.get("speed_kph", 50) / 3.6
            data["travel_time"] = (length / max(speed_ms, 1)) * multiplier
    except Exception:
        pass

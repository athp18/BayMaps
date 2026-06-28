import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_511_EVENTS_URL = "https://api.511.org/traffic/events"


async def fetch_traffic_events():
    if not settings.api_511_key:
        logger.debug("No 511 API key configured, skipping traffic fetch")
        return []

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                _511_EVENTS_URL,
                params={"api_key": settings.api_511_key, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
            # 511 API returns either a bare list or {"events": {"events": [...]}}
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                inner = data.get("events", data)
                return inner.get("events", inner) if isinstance(inner, dict) else inner
            return []
        except Exception as e:
            logger.error(f"Failed to fetch 511 traffic events: {e}")
            return []

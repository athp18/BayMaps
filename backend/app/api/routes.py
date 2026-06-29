from datetime import datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException

from app.core.dijkstra import dijkstra
from app.core.directions import build_directions, duration_bounds
from app.core.graph import get_graph, snap_to_node
from app.core.speed_lookup import get_coverage, get_overrides
from app.etl.pipeline import get_traffic_data
from app.models.xgb_inference import get_multipliers, _HOUR_TO_BUCKET
from app.models.inference import predict_route
from app.schemas.route import Coordinate, Direction, RouteRequest, RouteResponse, TrafficResponse

router = APIRouter()

_ROUTE_CACHE_TTL = 300
_redis: aioredis.Redis | None = None


def init_redis(url: str):
    global _redis
    _redis = aioredis.from_url(url, decode_responses=True)


def _current_hour_of_week():
    now = datetime.now()
    return now.weekday() * 24 + now.hour


@router.get("/health")
async def health():
    G = get_graph()
    return {"status": "ok", "graph_nodes": len(G.nodes), "graph_edges": len(G.edges), **get_coverage()}


@router.post("/route", response_model=RouteResponse)
async def get_route(req: RouteRequest):
    G = get_graph()

    try:
        origin_node = snap_to_node(req.origin_lat, req.origin_lng)
        dest_node = snap_to_node(req.dest_lat, req.dest_lng)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not snap coordinates to road graph: {e}")

    hour = _current_hour_of_week()
    bucket = _HOUR_TO_BUCKET.get(hour, "weekday_midday")
    cache_key = f"route:{origin_node}:{dest_node}:{hour}"

    if _redis is not None:
        try:
            cached = await _redis.get(cache_key)
            if cached:
                return RouteResponse.model_validate_json(cached)
        except Exception:
            pass

    try:
        pems = get_overrides()
        xgb = get_multipliers(G)
        path, cost = dijkstra(G, origin_node, dest_node, pems_overrides=pems, gnn_multipliers=xgb)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    coords = [Coordinate(lat=G.nodes[n]["y"], lng=G.nodes[n]["x"]) for n in path]
    distance_m = sum(G[u][v][0].get("length", 0) for u, v in zip(path[:-1], path[1:]))
    score, traffic_adjusted = predict_route(G, path, cost)

    dur_min, dur_max = duration_bounds(cost, bucket)
    raw_directions = build_directions(G, path)
    directions = [Direction(**d) for d in raw_directions]

    response = RouteResponse(
        coordinates=coords,
        distance_km=round(distance_m / 1000, 2),
        duration_minutes=round(cost / 60, 1),
        duration_min_minutes=dur_min,
        duration_max_minutes=dur_max,
        traffic_adjusted=traffic_adjusted,
        score=round(score, 3),
        directions=directions,
    )

    if _redis is not None:
        try:
            await _redis.setex(cache_key, _ROUTE_CACHE_TTL, response.model_dump_json())
        except Exception:
            pass

    return response


@router.get("/traffic", response_model=TrafficResponse)
async def get_traffic():
    return get_traffic_data()

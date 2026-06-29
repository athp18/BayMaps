from fastapi import APIRouter, HTTPException

from app.core.dijkstra import dijkstra
from app.core.graph import get_graph, snap_to_node
from app.core.speed_lookup import get_coverage, get_overrides
from app.etl.pipeline import get_traffic_data
from app.models.xgb_inference import get_multipliers
from app.models.inference import predict_route
from app.schemas.route import Coordinate, RouteRequest, RouteResponse, TrafficResponse

router = APIRouter()


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

    try:
        pems = get_overrides()
        xgb = get_multipliers(G)
        path, cost = dijkstra(G, origin_node, dest_node, pems_overrides=pems, gnn_multipliers=xgb)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    coords = [Coordinate(lat=G.nodes[n]["y"], lng=G.nodes[n]["x"]) for n in path]

    distance_m = sum(
        G[u][v][0].get("length", 0) for u, v in zip(path[:-1], path[1:])
    )

    score, traffic_adjusted = predict_route(G, path, cost)

    return RouteResponse(
        coordinates=coords,
        distance_km=round(distance_m / 1000, 2),
        duration_minutes=round(cost / 60, 1),
        traffic_adjusted=traffic_adjusted,
        score=round(score, 3),
    )


@router.get("/traffic", response_model=TrafficResponse)
async def get_traffic():
    return get_traffic_data()

import networkx as nx

from app.etl.pipeline import has_live_traffic
from app.models.gnn import predict_edge_multipliers
from app.models.scorer import RouteScorer, extract_route_features

_scorer = RouteScorer()


def apply_gnn_weights(G: nx.MultiDiGraph) -> None:
    """Updates every edge's travel_time using GNN predictions (or numpy fallback)."""
    multipliers = predict_edge_multipliers(G)
    for (u, v), mult in multipliers.items():
        for key in G[u][v]:
            length = G[u][v][key].get("length", 100)
            speed_ms = G[u][v][key].get("speed_kph", 50) / 3.6
            G[u][v][key]["travel_time"] = (length / max(speed_ms, 1)) * mult


def predict_route(G: nx.MultiDiGraph, path: list[int], cost: float) -> tuple[float, bool]:
    features = extract_route_features(G, path)
    score = _scorer.score(features)
    return score, has_live_traffic()

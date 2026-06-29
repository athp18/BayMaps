"""
XGBoost route scorer.
Scores a route 0-1 based on 7 features. Higher = better route.
Falls back to a heuristic when no trained weights file is present.
"""

from pathlib import Path

import numpy as np

try:
    import xgboost as xgb
    _XGBOOST_AVAILABLE = True
except ImportError:
    _XGBOOST_AVAILABLE = False


def extract_route_features(G, path):
    if len(path) < 2:
        return np.zeros((1, 7), dtype=np.float32)

    edges = list(zip(path[:-1], path[1:]))
    lengths = [G[u][v][0].get("length", 0.0) for u, v in edges]
    speeds = [G[u][v][0].get("speed_kph", 50.0) for u, v in edges]
    travel_times = [G[u][v][0].get("travel_time", l / 13.9) for l, (u, v) in zip(lengths, edges)]
    highway_types = [str(G[u][v][0].get("highway", "")) for u, v in edges]

    total_dist_km = sum(lengths) / 1000
    total_time_min = sum(travel_times) / 60
    avg_speed = float(np.mean(speeds))
    num_nodes = len(path)
    highway_frac = sum(1 for h in highway_types if "motorway" in h or "trunk" in h) / max(len(edges), 1)
    speed_std = float(np.std(speeds)) if len(speeds) > 1 else 0.0
    congestion_ratio = sum(travel_times) / max(sum(lengths), 1) * 1000

    return np.array([[
        total_dist_km,
        total_time_min,
        avg_speed,
        num_nodes,
        highway_frac,
        speed_std,
        congestion_ratio,
    ]], dtype=np.float32)


class RouteScorer:
    def __init__(self, weights_path: str = "weights/scorer.json"):
        self._model = None
        if _XGBOOST_AVAILABLE and Path(weights_path).exists():
            try:
                self._model = xgb.XGBRegressor()
                self._model.load_model(weights_path)
            except Exception:
                pass

    def score(self, features):
        if self._model is not None:
            return float(self._model.predict(features)[0])

        # Heuristic fallback: reward high speed + highway usage, penalise congestion
        avg_speed = features[0, 2]
        highway_frac = features[0, 4]
        congestion_ratio = features[0, 6]
        raw = (avg_speed / 130) * 0.5 + highway_frac * 0.3 - congestion_ratio * 0.02
        return float(np.clip(raw, 0.0, 1.0))

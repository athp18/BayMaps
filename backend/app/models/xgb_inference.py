"""
XGBoost inference: loads per-bucket models and returns edge congestion multipliers.
"""

import logging
from datetime import datetime
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

WEIGHTS_DIR = Path("weights")

TIME_BUCKETS = {
    "weekday_am_peak":  [h + d * 24 for d in range(5) for h in range(7, 10)],
    "weekday_midday":   [h + d * 24 for d in range(5) for h in range(10, 16)],
    "weekday_pm_peak":  [h + d * 24 for d in range(5) for h in range(16, 20)],
    "weekday_night":    [h + d * 24 for d in range(5) for h in list(range(0, 7)) + list(range(20, 24))],
    "weekend_day":      [h + d * 24 for d in range(5, 7) for h in range(8, 21)],
    "weekend_night":    [h + d * 24 for d in range(5, 7) for h in list(range(0, 8)) + list(range(21, 24))],
}

BUCKET_LIST = list(TIME_BUCKETS.keys())

_HOUR_TO_BUCKET = {
    h: b for b, hours in TIME_BUCKETS.items() for h in hours
}

_models = {}
_multiplier_cache = {}
_sensor_tree = None
_sensor_coords = None
_bucket_sensor_ratios = {}  # bucket → per-sensor congestion ratio

ROAD_TYPE_RANK = {
    "motorway": 0, "motorway_link": 1, "trunk": 2, "trunk_link": 3,
    "primary": 4, "primary_link": 5, "secondary": 6, "secondary_link": 7,
    "tertiary": 8, "tertiary_link": 9, "residential": 10,
    "unclassified": 11, "living_street": 12, "service": 13,
}
K_NEIGHBORS = 5


def load_models():
    try:
        import xgboost as xgb
    except ImportError:
        logger.warning("xgboost not installed — ML multipliers disabled")
        return

    loaded = 0
    for i, bucket in enumerate(BUCKET_LIST):
        path = WEIGHTS_DIR / f"xgb_{bucket}.json"
        if path.exists():
            try:
                model = xgb.XGBRegressor()
                model.load_model(path)
                _models[bucket] = model
                loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load XGB weights for {bucket}: {e}")

    if loaded:
        logger.info(f"XGB: loaded {loaded}/{len(BUCKET_LIST)} bucket models")
    else:
        logger.info("XGB: no weights found — fallback to degree heuristic")


def load_sensor_data(G):
    """Build KDTree over sensor locations and precompute per-bucket congestion ratios."""
    global _sensor_tree, _sensor_coords, _bucket_sensor_ratios
    from scipy.spatial import cKDTree
    import pandas as pd

    meta_files = list(Path(".").glob("data/d04_text_meta_*.txt"))
    if not meta_files:
        logger.warning("No sensor metadata found — spatial features will be zeros")
        return

    chunks = []
    for f in meta_files:
        try:
            m = pd.read_csv(f, sep="\t", usecols=["ID", "Latitude", "Longitude"])
            chunks.append(m)
        except Exception:
            pass

    if not chunks:
        return

    meta = pd.concat(chunks).drop_duplicates("ID").dropna(subset=["Latitude", "Longitude"])
    _sensor_coords = meta[["Latitude", "Longitude"]].values
    _sensor_tree = cKDTree(_sensor_coords)
    logger.info(f"XGB: KDTree built over {len(_sensor_coords)} sensors")

    lookup_path = Path("data/pems/speed_lookup.parquet")
    if not lookup_path.exists():
        logger.warning("speed_lookup.parquet not found — sensor ratios will default to 1.0")
        return

    lookup = pd.read_parquet(lookup_path)

    # Precompute sensor congestion ratio for each time bucket
    covered_edges = list(set(zip(lookup["edge_u"], lookup["edge_v"])))
    covered_edges = [(eu, ev) for eu, ev in covered_edges if G.has_edge(eu, ev)]
    if not covered_edges:
        return

    edge_mids = np.array([
        [(G.nodes[eu].get("y", 0) + G.nodes[ev].get("y", 0)) / 2,
         (G.nodes[eu].get("x", 0) + G.nodes[ev].get("x", 0)) / 2]
        for eu, ev in covered_edges
    ])
    edge_tree = cKDTree(edge_mids)
    _, nearest_edge_idx = edge_tree.query(_sensor_coords, k=1)

    for bucket, hours in TIME_BUCKETS.items():
        subset = lookup[lookup["hour_of_week"].isin(hours)]
        bucket_speeds = subset.groupby(["edge_u", "edge_v"])["speed_kph"].median().to_dict()

        ratios = np.ones(len(_sensor_coords))
        for i, ei in enumerate(nearest_edge_idx):
            eu, ev = covered_edges[ei]
            pems_spd = bucket_speeds.get((eu, ev))
            osm_spd = G[eu][ev][0].get("speed_kph", 50.0) if G.has_edge(eu, ev) else 50.0
            if pems_spd and osm_spd > 0:
                ratios[i] = pems_spd / osm_spd
        _bucket_sensor_ratios[bucket] = ratios

    logger.info(f"XGB: sensor congestion ratios precomputed for {len(_bucket_sensor_ratios)} buckets")


def _build_features(G, bucket_idx, bucket):
    from scipy.spatial import cKDTree
    n_sensors = len(_sensor_tree.data) if _sensor_tree else 0
    rows, edge_keys = [], []

    for u, v, data in G.edges(data=True):
        lat_u = G.nodes[u].get("y", 0.0)
        lng_u = G.nodes[u].get("x", 0.0)
        lat_v = G.nodes[v].get("y", 0.0)
        lng_v = G.nodes[v].get("x", 0.0)
        lat_mid = (lat_u + lat_v) / 2
        lng_mid = (lng_u + lng_v) / 2

        osm_spd = data.get("speed_kph", 50.0)
        length_m = data.get("length", 100.0)
        highway = data.get("highway", "unclassified")
        if isinstance(highway, list):
            highway = highway[0]
        road_rank = ROAD_TYPE_RANK.get(highway, 11)

        feat = [
            lat_mid, lng_mid,
            osm_spd / 130.0,
            np.log1p(length_m),
            road_rank / 13.0,
            G.degree(u) / 10.0,
            G.degree(v) / 10.0,
            bucket_idx / 5.0,
        ]

        if _sensor_tree is not None:
            dists, idxs = _sensor_tree.query([lat_mid, lng_mid], k=K_NEIGHBORS)
            sensor_ratios = _bucket_sensor_ratios.get(bucket, np.ones(len(_sensor_coords)))
            for dist, idx in zip(dists, idxs):
                feat.append(np.log1p(dist * 111000))
                feat.append(float(sensor_ratios[idx]))
        else:
            feat.extend([0.0, 1.0] * K_NEIGHBORS)

        rows.append(feat)
        edge_keys.append((u, v))

    return np.array(rows, dtype=np.float32), edge_keys


def get_multipliers(G, hour_of_week=None):
    if hour_of_week is None:
        now = datetime.now()
        hour_of_week = now.weekday() * 24 + now.hour

    bucket = _HOUR_TO_BUCKET.get(hour_of_week, "weekday_midday")

    if bucket in _multiplier_cache:
        return _multiplier_cache[bucket]

    model = _models.get(bucket)
    if model is not None:
        try:
            bucket_idx = BUCKET_LIST.index(bucket)
            X, edge_keys = _build_features(G, bucket_idx, bucket)
            preds = np.clip(model.predict(X), 1.0, 4.0)
            result = {(u, v): float(p) for (u, v), p in zip(edge_keys, preds)}
            _multiplier_cache[bucket] = result
            logger.info(f"XGB: computed multipliers for bucket '{bucket}'")
            return result
        except Exception as e:
            logger.warning(f"XGB inference failed for {bucket}: {e}")

    if "fallback" not in _multiplier_cache:
        _multiplier_cache["fallback"] = _degree_fallback(G)
    return _multiplier_cache["fallback"]


def _degree_fallback(G):
    degree = dict(G.degree())
    max_degree = max(degree.values(), default=1)
    result = {}
    for u, v, data in G.edges(data=True):
        load = (degree.get(u, 1) / max_degree) * 0.4
        speed = data.get("speed_kph", 50)
        speed_factor = max(0.0, (60 - speed) / 60) * 0.3
        result[(u, v)] = float(np.clip(1.0 + load + speed_factor, 1.0, 4.0))
    return result

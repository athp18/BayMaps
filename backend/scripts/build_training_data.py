"""
Builds XGBoost training data from the Bay Area graph + PEMS speed lookup.

For each edge, engineers spatial + road features using the nearest PEMS sensors.
Outputs one feature matrix per time bucket.

Output: data/pems/training_data.pkl
    Dict keyed by bucket name, each value is:
        X_labeled   (n_labeled, n_features) — features for PEMS-covered edges
        y_labeled   (n_labeled,)            — congestion multipliers
        X_all       (n_edges, n_features)   — features for all edges (for inference)
        edge_keys   list of (u, v)          — OSM node ID pairs, aligned with X_all

Usage:
    cd backend/
    docker compose run --rm --no-deps backend python -m scripts.build_training_data
"""

import logging
import pickle
from pathlib import Path

import numpy as np
import osmnx as ox
import pandas as pd
from scipy.spatial import cKDTree

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GRAPH_PATH = Path("data/bay_area.graphml")
LOOKUP_PATH = Path("data/pems/speed_lookup.parquet")
META_GLOB = "data/d04_text_meta_*.txt"
OUT_PATH = Path("data/pems/training_data.pkl")
K_NEIGHBORS = 5

ROAD_TYPE_RANK = {
    "motorway": 0, "motorway_link": 1, "trunk": 2, "trunk_link": 3,
    "primary": 4, "primary_link": 5, "secondary": 6, "secondary_link": 7,
    "tertiary": 8, "tertiary_link": 9, "residential": 10,
    "unclassified": 11, "living_street": 12, "service": 13,
}

TIME_BUCKETS = {
    "weekday_am_peak":  [h + d * 24 for d in range(5) for h in range(7, 10)],
    "weekday_midday":   [h + d * 24 for d in range(5) for h in range(10, 16)],
    "weekday_pm_peak":  [h + d * 24 for d in range(5) for h in range(16, 20)],
    "weekday_night":    [h + d * 24 for d in range(5) for h in list(range(0, 7)) + list(range(20, 24))],
    "weekend_day":      [h + d * 24 for d in range(5, 7) for h in range(8, 21)],
    "weekend_night":    [h + d * 24 for d in range(5, 7) for h in list(range(0, 8)) + list(range(21, 24))],
}


def load_sensor_locations():
    """Load station lat/lon from PEMS metadata files."""
    from pathlib import Path
    meta_files = list(Path(".").glob(META_GLOB))
    if not meta_files:
        raise FileNotFoundError(f"No metadata files found matching {META_GLOB}")
    chunks = []
    for f in meta_files:
        try:
            m = pd.read_csv(f, sep="\t", usecols=["ID", "Latitude", "Longitude"])
            chunks.append(m)
        except Exception as e:
            logger.warning(f"Could not read {f}: {e}")
    meta = pd.concat(chunks).drop_duplicates("ID")
    meta = meta.dropna(subset=["Latitude", "Longitude"])
    logger.info(f"Loaded {len(meta)} sensor locations")
    return meta


def build_edge_features(G, lookup, meta,
                        bucket_hours, bucket_idx):
    """
    Returns (X_all, y_labeled, labeled_mask, edge_keys).
    X_all: (n_edges, n_features) for all edges.
    """
    # Build KDTree over sensor locations
    sensor_lats = meta["Latitude"].values
    sensor_lngs = meta["Longitude"].values
    sensor_coords = np.stack([sensor_lats, sensor_lngs], axis=1)
    tree = cKDTree(sensor_coords)

    # Bucket speed per sensor station → map to edge via station ID
    subset = lookup[lookup["hour_of_week"].isin(bucket_hours)]
    bucket_speeds = subset.groupby(["edge_u", "edge_v"])["speed_kph"].median().to_dict()

    # Compute per-sensor congestion ratio by snapping each sensor to its nearest covered edge
    sensor_ratio = np.ones(len(sensor_coords))  # default: free flow

    if bucket_speeds:
        covered_edges = [(eu, ev) for (eu, ev) in bucket_speeds if G.has_edge(eu, ev)]
        if covered_edges:
            edge_mids = np.array([
                [(G.nodes[eu].get("y", 0) + G.nodes[ev].get("y", 0)) / 2,
                 (G.nodes[eu].get("x", 0) + G.nodes[ev].get("x", 0)) / 2]
                for eu, ev in covered_edges
            ])
            edge_tree = cKDTree(edge_mids)
            _, nearest_edge_idx = edge_tree.query(sensor_coords, k=1)
            for i, ei in enumerate(nearest_edge_idx):
                eu, ev = covered_edges[ei]
                pems_spd = bucket_speeds[(eu, ev)]
                osm_spd = G[eu][ev][0].get("speed_kph", 50.0)
                if osm_spd > 0:
                    sensor_ratio[i] = pems_spd / osm_spd  # <1 = congested, >1 = faster than limit

    rows = []
    edge_keys = []
    labeled_mask = []
    y_labels = []

    for u, v, data in G.edges(data=True):
        # Edge midpoint
        lat_u = G.nodes[u].get("y", 0.0)
        lng_u = G.nodes[u].get("x", 0.0)
        lat_v = G.nodes[v].get("y", 0.0)
        lng_v = G.nodes[v].get("x", 0.0)
        lat_mid = (lat_u + lat_v) / 2
        lng_mid = (lng_u + lng_v) / 2

        # K nearest sensors
        dists, idxs = tree.query([lat_mid, lng_mid], k=K_NEIGHBORS)

        osm_spd = data.get("speed_kph", 50.0)
        length_m = data.get("length", 100.0)
        highway = data.get("highway", "unclassified")
        if isinstance(highway, list):
            highway = highway[0]
        road_rank = ROAD_TYPE_RANK.get(highway, 11)
        degree_u = G.degree(u)
        degree_v = G.degree(v)

        feat = [
            lat_mid, lng_mid,
            osm_spd / 130.0,
            np.log1p(length_m),
            road_rank / 13.0,
            degree_u / 10.0,
            degree_v / 10.0,
            float(bucket_idx) / 5.0,
        ]
        for dist, idx in zip(dists, idxs):
            feat.append(np.log1p(dist * 111000))   # approx meters
            feat.append(sensor_ratio[idx])          # congestion at that sensor

        rows.append(feat)
        edge_keys.append((u, v))

        pems_spd = bucket_speeds.get((u, v))
        if pems_spd and pems_spd > 0 and osm_spd > 0:
            multiplier = float(np.clip(osm_spd / pems_spd, 1.0, 4.0))
            y_labels.append(multiplier)
            labeled_mask.append(True)
        else:
            y_labels.append(0.0)
            labeled_mask.append(False)

    X_all = np.array(rows, dtype=np.float32)
    labeled_mask = np.array(labeled_mask, dtype=bool)
    y_labeled = np.array(y_labels, dtype=np.float32)[labeled_mask]

    return X_all, y_labeled, labeled_mask, edge_keys


def build_training_data():
    if not GRAPH_PATH.exists():
        raise FileNotFoundError(f"Graph not found: {GRAPH_PATH}")
    if not LOOKUP_PATH.exists():
        raise FileNotFoundError(f"Speed lookup not found: {LOOKUP_PATH}")

    logger.info("Loading graph...")
    G = ox.load_graphml(GRAPH_PATH)
    ox.add_edge_speeds(G)
    ox.add_edge_travel_times(G)
    logger.info(f"Graph: {len(G.nodes)} nodes, {len(G.edges)} edges")

    lookup = pd.read_parquet(LOOKUP_PATH)
    meta = load_sensor_locations()

    dataset = {}
    for i, (bucket_name, hours) in enumerate(TIME_BUCKETS.items()):
        logger.info(f"Building features for: {bucket_name}")
        X_all, y_labeled, labeled_mask, edge_keys = build_edge_features(
            G, lookup, meta, hours, i
        )
        covered = labeled_mask.sum()
        logger.info(f"  Labeled edges: {covered}/{len(edge_keys)} — X_all: {X_all.shape}")
        dataset[bucket_name] = {
            "X_labeled": X_all[labeled_mask],
            "y_labeled": y_labeled,
            "X_all": X_all,
            "edge_keys": edge_keys,
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "wb") as f:
        pickle.dump(dataset, f)
    logger.info(f"Saved training data to {OUT_PATH}")


if __name__ == "__main__":
    build_training_data()

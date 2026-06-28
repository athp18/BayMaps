"""
ETL pipeline: PEMS raw + metadata → training dataset for the GNN.

Steps:
1. Load station metadata → lat/lng per station
2. Snap each station to nearest graph edge
3. For each 5-min raw file, extract (station_id, timestamp, avg_speed)
4. Compute congestion multiplier = free_flow_speed / observed_speed
5. Aggregate per (station, hour_of_week) → stable label per edge
6. Save to data/pems/training_labels.parquet

Run from backend/:
    python -m scripts.build_training_data
"""

import gzip
import logging
from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = Path("data/pems/raw")
META_DIR = Path("data/pems/metadata")
GRAPH_PATH = Path("data/bay_area.graphml")
OUTPUT_PATH = Path("data/pems/training_labels.parquet")

# Raw file column layout (no header)
RAW_COLS = [
    "timestamp", "station_id", "district", "freeway", "direction",
    "lane_type", "station_length", "samples", "pct_observed",
    "total_flow", "avg_occupancy", "avg_speed",
]


def load_metadata() -> pd.DataFrame:
    files = sorted(META_DIR.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No metadata files in {META_DIR}")
    # Use the most recent metadata file
    meta = pd.read_csv(files[-1], sep="\t", usecols=["ID", "Latitude", "Longitude", "Type"])
    meta = meta.rename(columns={"ID": "station_id", "Latitude": "lat", "Longitude": "lng"})
    # Only mainline detectors — freeway shoulder/ramp detectors aren't useful for routing
    meta = meta[meta["Type"] == "ML"].drop(columns="Type")
    meta = meta.dropna(subset=["lat", "lng"])
    logger.info(f"Loaded {len(meta)} mainline stations from metadata")
    return meta


def load_graph() -> nx.MultiDiGraph:
    if not GRAPH_PATH.exists():
        raise FileNotFoundError(f"Graph not found at {GRAPH_PATH} — run download_graph.py first")
    logger.info("Loading graph...")
    G = ox.load_graphml(GRAPH_PATH)
    ox.add_edge_speeds(G)
    ox.add_edge_travel_times(G)
    logger.info(f"Graph: {len(G.nodes)} nodes, {len(G.edges)} edges")
    return G


def snap_stations_to_edges(meta: pd.DataFrame, G: nx.MultiDiGraph) -> pd.DataFrame:
    """Find the nearest graph node for each station, then the nearest edge."""
    logger.info("Snapping stations to graph edges...")
    lngs = meta["lng"].tolist()
    lats = meta["lat"].tolist()

    nearest_nodes = ox.nearest_nodes(G, lngs, lats)
    meta = meta.copy()
    meta["node_u"] = nearest_nodes

    # For each snapped node, pick the outgoing edge with minimum length as the representative edge
    edge_u, edge_v = [], []
    for node in meta["node_u"]:
        edges = list(G.edges(node, data=True))
        if edges:
            best = min(edges, key=lambda e: e[2].get("length", float("inf")))
            edge_u.append(best[0])
            edge_v.append(best[1])
        else:
            edge_u.append(node)
            edge_v.append(node)

    meta["edge_u"] = edge_u
    meta["edge_v"] = edge_v
    return meta


def get_free_flow_speed(G: nx.MultiDiGraph, u: int, v: int) -> float:
    """Speed limit in kph for edge (u, v), falling back to 88 kph (55 mph)."""
    if G.has_edge(u, v):
        return G[u][v][0].get("speed_kph", 88.0)
    return 88.0


def load_raw_file(path: Path) -> pd.DataFrame:
    with gzip.open(path, "rt") as f:
        df = pd.read_csv(
            f,
            header=None,
            names=RAW_COLS,
            usecols=["timestamp", "station_id", "avg_speed"],
        )
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%m/%d/%Y %H:%M:%S")
    df["avg_speed"] = pd.to_numeric(df["avg_speed"], errors="coerce")
    df = df.dropna(subset=["avg_speed"])
    df = df[df["avg_speed"] > 0]
    return df


def build_labels(meta: pd.DataFrame, G: nx.MultiDiGraph) -> pd.DataFrame:
    """
    For each raw file, extract speed readings and compute multiplier per station per 5-min slot.
    Aggregates to median per (edge_u, edge_v, hour_of_week) for a stable training label.
    """
    station_to_edge = meta.set_index("station_id")[["edge_u", "edge_v"]].to_dict("index")
    station_free_flow = {
        row["station_id"]: get_free_flow_speed(G, row["edge_u"], row["edge_v"])
        for _, row in meta.iterrows()
    }

    raw_files = sorted(RAW_DIR.glob("*.txt.gz"))
    logger.info(f"Processing {len(raw_files)} raw files...")

    records = []
    for i, path in enumerate(raw_files):
        if i % 20 == 0:
            logger.info(f"  {i}/{len(raw_files)} files processed")
        try:
            df = load_raw_file(path)
        except Exception as e:
            logger.warning(f"  Skipping {path.name}: {e}")
            continue

        df = df[df["station_id"].isin(station_to_edge)]
        if df.empty:
            continue

        df["edge_u"] = df["station_id"].map(lambda s: station_to_edge[s]["edge_u"])
        df["edge_v"] = df["station_id"].map(lambda s: station_to_edge[s]["edge_v"])
        df["free_flow"] = df["station_id"].map(station_free_flow)
        df["multiplier"] = df["free_flow"] / df["avg_speed"].clip(lower=5)
        df["multiplier"] = df["multiplier"].clip(1.0, 4.0)
        df["hour_of_week"] = df["timestamp"].dt.dayofweek * 24 + df["timestamp"].dt.hour

        records.append(df[["edge_u", "edge_v", "hour_of_week", "multiplier"]])

    if not records:
        raise RuntimeError("No usable records found — check raw files and metadata")

    combined = pd.concat(records, ignore_index=True)
    logger.info(f"Total records before aggregation: {len(combined):,}")

    # Aggregate to median per (edge, hour_of_week) — robust to outliers
    labels = (
        combined.groupby(["edge_u", "edge_v", "hour_of_week"])["multiplier"]
        .median()
        .reset_index()
    )
    logger.info(f"Training labels: {len(labels):,} (edge, hour_of_week) pairs")
    return labels


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    meta = load_metadata()
    G = load_graph()
    meta = snap_stations_to_edges(meta, G)
    labels = build_labels(meta, G)
    labels.to_parquet(OUTPUT_PATH, index=False)
    logger.info(f"Saved training labels to {OUTPUT_PATH}")

    # Quick sanity check
    logger.info(f"Multiplier stats:\n{labels['multiplier'].describe().round(3)}")
    logger.info(f"Unique edges covered: {labels[['edge_u','edge_v']].drop_duplicates().shape[0]}")


if __name__ == "__main__":
    main()

"""
Processes PEMS Station 5-Minute files from data/pems/raw/ into a speed lookup table.

Output: data/pems/speed_lookup.parquet
Schema: edge_u (int), edge_v (int), hour_of_week (int 0-167), speed_kph (float), sample_count (int)

Usage:
    python -m scripts.build_speed_lookup
"""

import logging
from pathlib import Path

import numpy as np
import osmnx as ox
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = Path("data")
OUT_PATH = Path("data/pems/speed_lookup.parquet")
GRAPH_PATH = Path("data/bay_area.graphml")

PEMS_COLS = [
    "timestamp", "station_id", "district", "freeway", "direction",
    "lane_type", "station_length", "samples", "pct_observed",
    "total_flow", "avg_occupancy", "avg_speed",
]


def load_graph():
    if not GRAPH_PATH.exists():
        raise FileNotFoundError(f"Graph not found at {GRAPH_PATH}. Run download_graph.py first.")
    logger.info("Loading graph...")
    G = ox.load_graphml(GRAPH_PATH)
    ox.add_edge_speeds(G)
    ox.add_edge_travel_times(G)
    return G


def build_station_node_map(G):
    """Map PEMS station coords to nearest OSMnx node."""
    nodes_gdf, _ = ox.graph_to_gdfs(G)
    return nodes_gdf


def read_pems_file(path: Path) -> pd.DataFrame:
    try:
        compression = "gzip" if str(path).endswith(".gz") else "infer"
        df = pd.read_csv(
            path, header=None, usecols=[0, 1, 11],
            names=["timestamp", "station_id", "avg_speed"],
            low_memory=False, compression=compression,
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["avg_speed"] = pd.to_numeric(df["avg_speed"], errors="coerce")
        df = df.dropna(subset=["timestamp", "avg_speed", "station_id"])
        df["hour_of_week"] = df["timestamp"].dt.dayofweek * 24 + df["timestamp"].dt.hour
        df["speed_kph"] = df["avg_speed"] * 1.60934  # mph → kph
        return df[["station_id", "hour_of_week", "speed_kph"]]
    except Exception as e:
        logger.warning(f"Failed to read {path}: {e}")
        return pd.DataFrame()


def build_speed_lookup():
    raw_files = (
        sorted(RAW_DIR.glob("d04_text_station_*.txt.gz"))
        + sorted(RAW_DIR.glob("d04_text_station_*.txt"))
        + sorted(RAW_DIR.glob("*.csv.gz"))
        + sorted(RAW_DIR.glob("*.csv"))
    )
    if not raw_files:
        raise FileNotFoundError(f"No PEMS files found in {RAW_DIR}")
    logger.info(f"Found {len(raw_files)} PEMS files")

    G = load_graph()

    chunks = []
    for i, f in enumerate(raw_files):
        logger.info(f"[{i+1}/{len(raw_files)}] Reading {f.name}")
        chunk = read_pems_file(f)
        if not chunk.empty:
            chunks.append(chunk)

    if not chunks:
        raise ValueError("No valid data loaded from PEMS files")

    all_data = pd.concat(chunks, ignore_index=True)
    logger.info(f"Total records: {len(all_data):,}")

    station_hourly = (
        all_data.groupby(["station_id", "hour_of_week"])["speed_kph"]
        .agg(speed_kph="median", sample_count="count")
        .reset_index()
    )
    logger.info(f"Station-hour records: {len(station_hourly):,}")

    # Load station metadata to get lat/lon
    meta_files = (
        list(Path("data/pems/metadata").glob("*.csv"))
        + list(Path("data/pems/metadata").glob("*.txt"))
        + list(Path("data").glob("d04_text_meta_*.txt"))
    )
    if not meta_files:
        logger.warning("No metadata files found — cannot map stations to graph edges")
        return

    meta_chunks = []
    for mf in meta_files:
        try:
            m = pd.read_csv(mf, sep="\t", low_memory=False)
            logger.info(f"Loaded metadata {mf.name}: {len(m)} stations, cols={m.columns.tolist()[:6]}")
            meta_chunks.append(m)
        except Exception as e:
            logger.warning(f"Could not read metadata {mf}: {e}")

    if not meta_chunks:
        logger.warning("No usable metadata — cannot map stations to edges")
        return

    meta = pd.concat(meta_chunks, ignore_index=True)
    meta.columns = [c.strip().lower().replace(" ", "_") for c in meta.columns]

    lat_col = next((c for c in meta.columns if "lat" in c), None)
    lon_col = next((c for c in meta.columns if "lon" in c), None)
    id_col = next((c for c in meta.columns if c in ("id", "station_id", "freeway_id")), None)

    if not all([lat_col, lon_col, id_col]):
        logger.error(f"Could not find lat/lon/id columns in metadata. Found: {meta.columns.tolist()}")
        return

    meta = meta[[id_col, lat_col, lon_col]].rename(columns={id_col: "station_id"})
    meta["station_id"] = pd.to_numeric(meta["station_id"], errors="coerce")
    meta[lat_col] = pd.to_numeric(meta[lat_col], errors="coerce")
    meta[lon_col] = pd.to_numeric(meta[lon_col], errors="coerce")
    meta = meta.dropna()

    merged = station_hourly.merge(meta, on="station_id", how="inner")
    logger.info(f"Stations with metadata: {merged['station_id'].nunique()}")

    logger.info("Snapping stations to nearest graph nodes...")
    lats = merged[lat_col].values
    lons = merged[lon_col].values
    nearest_nodes = ox.distance.nearest_nodes(G, lons, lats)
    merged["node"] = nearest_nodes

    node_to_edges: dict[int, list[tuple[int, int]]] = {}
    for u, v in G.edges():
        node_to_edges.setdefault(u, []).append((u, v))

    records = []
    for _, row in merged.iterrows():
        node = row["node"]
        for edge_u, edge_v in node_to_edges.get(node, []):
            records.append({
                "edge_u": edge_u,
                "edge_v": edge_v,
                "hour_of_week": int(row["hour_of_week"]),
                "speed_kph": row["speed_kph"],
                "sample_count": int(row["sample_count"]),
            })

    if not records:
        logger.error("No edge records generated — check station coords vs graph bounds")
        return

    result = pd.DataFrame(records)
    result = (
        result.groupby(["edge_u", "edge_v", "hour_of_week"])
        .agg(speed_kph=("speed_kph", "mean"), sample_count=("sample_count", "sum"))
        .reset_index()
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(OUT_PATH, index=False)
    logger.info(f"Saved {len(result):,} edge-hour records to {OUT_PATH}")
    logger.info(f"Coverage: {result[['edge_u','edge_v']].drop_duplicates().shape[0]} unique edges")


if __name__ == "__main__":
    build_speed_lookup()

"""
Exports the loaded graph to two small CSVs for use outside Docker.

Output:
    data/graph_nodes.csv  — node_id, lat, lng
    data/graph_edges.csv  — u, v, speed_kph, length_m

Usage (inside Docker):
    docker compose run --rm --no-deps backend python -m scripts.export_graph_csv
"""

import logging
from pathlib import Path

import osmnx as ox
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GRAPH_PATH = Path("data/bay_area.graphml")


def main():
    logger.info("Loading graph...")
    G = ox.load_graphml(GRAPH_PATH)
    ox.add_edge_speeds(G)
    ox.add_edge_travel_times(G)
    logger.info(f"Graph: {len(G.nodes)} nodes, {len(G.edges)} edges")

    nodes = [
        {"node_id": n, "lat": G.nodes[n].get("y", 0.0), "lng": G.nodes[n].get("x", 0.0)}
        for n in G.nodes()
    ]
    pd.DataFrame(nodes).to_csv("data/graph_nodes.csv", index=False)
    logger.info(f"Saved data/graph_nodes.csv ({len(nodes)} rows)")

    edges = []
    for u, v, data in G.edges(data=True):
        edges.append({
            "u": u,
            "v": v,
            "speed_kph": data.get("speed_kph", 50.0),
            "length_m": data.get("length", 100.0),
        })
    pd.DataFrame(edges).to_csv("data/graph_edges.csv", index=False)
    logger.info(f"Saved data/graph_edges.csv ({len(edges)} rows)")


if __name__ == "__main__":
    main()

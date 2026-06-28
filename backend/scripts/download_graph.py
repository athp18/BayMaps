"""
One-time script to download the Bay Area road network from OpenStreetMap.
Saves to backend/data/bay_area.graphml (~200MB).

Run from the backend/ directory:
    python -m scripts.download_graph
"""

from pathlib import Path

import osmnx as ox

OUTPUT_PATH = Path("data/bay_area.graphml")


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Downloading Bay Area road network from OpenStreetMap...")
    print("This takes 5-10 minutes and uses ~200MB of disk space.")

    G = ox.graph_from_place("San Francisco Bay Area, California", network_type="drive")

    print(f"Downloaded: {len(G.nodes)} nodes, {len(G.edges)} edges")
    print("Adding speed and travel time attributes...")

    ox.add_edge_speeds(G)
    ox.add_edge_travel_times(G)

    print(f"Saving to {OUTPUT_PATH}...")
    ox.save_graphml(G, OUTPUT_PATH)
    print("Done.")


if __name__ == "__main__":
    main()

import logging
from pathlib import Path
import networkx as nx
import osmnx as ox
from app.core.config import settings

logger = logging.getLogger(__name__)

_graph: nx.MultiDiGraph | None = None


def get_graph():
    if _graph is None:
        raise RuntimeError("Graph not loaded — call load_graph() at startup")
    return _graph


async def load_graph():
    global _graph
    path = Path(settings.graph_path)

    if path.exists():
        logger.info(f"Loading graph from {path}")
        G = ox.load_graphml(path)
        ox.add_edge_speeds(G)
        ox.add_edge_travel_times(G)
    else:
        logger.warning("Graph file not found, downloading Bay Area demo graph (takes 2-3 min)")
        # Centered between SF and San Jose — covers SF, Oakland, Peninsula, SFO, Palo Alto
        G = ox.graph_from_point((37.55, -122.28), dist=35000, network_type="drive")
        ox.add_edge_speeds(G)
        ox.add_edge_travel_times(G)
        path.parent.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(G, path)
        logger.info(f"Graph saved to {path} — next startup will load instantly")
    _graph = G
    logger.info(f"Graph ready: {len(G.nodes)} nodes, {len(G.edges)} edges")


def snap_to_node(lat: float, lng: float) -> int:
    # osmnx nearest_nodes takes (X=lng, Y=lat)
    return ox.nearest_nodes(get_graph(), lng, lat)

"""
Train the TrafficGAT model on synthetic congestion labels derived from graph structure.

Synthetic label rationale:
    Real congestion correlates with intersection degree (busy junctions),
    slow speed limits (residential areas), and road type. We use these
    signals to generate plausible multiplier targets, then train the GAT
    to recover them from raw graph topology — proving the model can learn
    structure-to-congestion mappings before real PEMS data is wired in.

Real data path (when available):
    Replace `_synthetic_labels()` with a loader for Caltrans PEMS or
    Uber Movement data matched to graph edges, then retrain.

Run from backend/:
    python -m scripts.train_gnn
"""

import logging
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox
import torch
import torch.nn as nn
from torch_geometric.data import Data

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.models.gnn import TrafficGAT, graph_to_pyg

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

GRAPH_PATH = Path("data/bay_area.graphml")
WEIGHTS_PATH = Path("weights/gnn.pt")
EPOCHS = 150
LR = 1e-3


def load_graph() -> nx.MultiDiGraph:
    if GRAPH_PATH.exists():
        logger.info(f"Loading graph from {GRAPH_PATH}")
        G = ox.load_graphml(GRAPH_PATH)
    else:
        logger.info("Graph not found, downloading demo graph for training...")
        G = ox.graph_from_point((37.55, -122.28), dist=35000, network_type="drive")
    ox.add_edge_speeds(G)
    ox.add_edge_travel_times(G)
    return G


def _synthetic_labels(G: nx.MultiDiGraph, edge_keys: list[tuple]) -> torch.Tensor:
    """
    Generate synthetic congestion multipliers [1.0, 4.0] per edge.

    Label = f(degree, speed_limit, road_type) + noise
    This teaches the GAT to infer congestion from topology before real data is available.
    """
    degree = dict(G.degree())
    max_degree = max(degree.values(), default=1)

    labels = []
    for u, v, k in edge_keys:
        data = G[u][v][k]
        deg_factor = degree.get(u, 1) / max_degree
        speed = data.get("speed_kph", 50.0)
        speed_factor = max(0.0, (70.0 - speed) / 70.0)
        highway = str(data.get("highway", ""))
        road_penalty = 0.3 if any(t in highway for t in ("motorway", "trunk")) else 0.0

        base = 1.0 + deg_factor * 1.2 + speed_factor * 0.8 - road_penalty
        noise = np.random.normal(0, 0.1)
        labels.append(float(np.clip(base + noise, 1.0, 4.0)))

    return torch.tensor(labels, dtype=torch.float)


def train() -> None:
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    G = load_graph()
    logger.info(f"Graph: {len(G.nodes)} nodes, {len(G.edges)} edges")

    logger.info("Converting graph to PyG format...")
    data, edge_keys = graph_to_pyg(G)
    labels = _synthetic_labels(G, edge_keys)
    logger.info(f"Training on {len(edge_keys)} edges")

    model = TrafficGAT()
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    loss_fn = nn.MSELoss()

    logger.info(f"Training for {EPOCHS} epochs...")
    model.train()
    for epoch in range(1, EPOCHS + 1):
        optimizer.zero_grad()
        preds = model(data.x, data.edge_index)
        loss = loss_fn(preds, labels)
        loss.backward()
        optimizer.step()

        if epoch % 25 == 0 or epoch == 1:
            logger.info(f"  Epoch {epoch:3d}/{EPOCHS}  loss={loss.item():.4f}")

    torch.save(model.state_dict(), WEIGHTS_PATH)
    logger.info(f"Saved weights to {WEIGHTS_PATH}")

    model.eval()
    with torch.no_grad():
        final_preds = model(data.x, data.edge_index).numpy()
    logger.info(f"Prediction range: [{final_preds.min():.2f}, {final_preds.max():.2f}]")


if __name__ == "__main__":
    train()

"""
Graph Attention Network (GAT) for predicting per-edge travel time multipliers.

Architecture:
    GATConv(4 → 64, heads=4) → ReLU
    GATConv(256 → 64, heads=1) → ReLU
    Edge head: Linear(128 → 1) on concat(h_src, h_dst) → sigmoid → [1.0, 4.0]

Node input features (4):
    lat_norm, lng_norm, degree_norm, avg_speed_norm

Output: one multiplier per directed edge — applied to free-flow travel_time.
"""

import logging
from pathlib import Path

import networkx as nx
import numpy as np
import torch
import torch.nn as nn
from torch_geometric.data import Data
from torch_geometric.nn import GATConv

logger = logging.getLogger(__name__)

WEIGHTS_PATH = Path("weights/gnn.pt")


class TrafficGAT(nn.Module):
    def __init__(self, in_channels: int = 4, hidden: int = 64, heads: int = 4):
        super().__init__()
        self.gat1 = GATConv(in_channels, hidden, heads=heads, dropout=0.1)
        self.gat2 = GATConv(hidden * heads, hidden, heads=1, concat=False)
        self.edge_head = nn.Linear(hidden * 2, 1)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        x = torch.relu(self.gat1(x, edge_index))
        x = torch.relu(self.gat2(x, edge_index))
        src, dst = edge_index
        edge_feats = torch.cat([x[src], x[dst]], dim=-1)
        # Output range [1.0, 4.0]: 1x = free flow, 4x = standstill
        return torch.sigmoid(self.edge_head(edge_feats)).squeeze(-1) * 3.0 + 1.0


def graph_to_pyg(G: nx.MultiDiGraph) -> tuple[Data, list[tuple[int, int, int]]]:
    """
    Converts a NetworkX MultiDiGraph to a PyG Data object.
    Returns (Data, edge_keys) where edge_keys maps PyG edge indices back to (u, v, key).
    """
    nodes = list(G.nodes())
    node_idx = {n: i for i, n in enumerate(nodes)}

    lats = np.array([G.nodes[n].get("y", 0.0) for n in nodes])
    lngs = np.array([G.nodes[n].get("x", 0.0) for n in nodes])
    degrees = np.array([G.degree(n) for n in nodes], dtype=float)

    def _norm(arr: np.ndarray) -> np.ndarray:
        r = arr.max() - arr.min()
        return (arr - arr.min()) / (r + 1e-8)

    lats_n = _norm(lats)
    lngs_n = _norm(lngs)
    degrees_n = degrees / (degrees.max() + 1e-8)

    avg_speeds = []
    for n in nodes:
        speeds = [
            G[n][v][k].get("speed_kph", 50.0)
            for v in G[n]
            for k in G[n][v]
        ]
        avg_speeds.append(np.mean(speeds) / 130.0 if speeds else 0.38)

    x = torch.tensor(
        np.stack([lats_n, lngs_n, degrees_n, avg_speeds], axis=1),
        dtype=torch.float,
    )

    edge_list: list[list[int]] = []
    edge_keys: list[tuple[int, int, int]] = []
    for u, v, k in G.edges(keys=True):
        edge_list.append([node_idx[u], node_idx[v]])
        edge_keys.append((u, v, k))

    edge_index = (
        torch.tensor(edge_list, dtype=torch.long).t().contiguous()
        if edge_list
        else torch.zeros((2, 0), dtype=torch.long)
    )

    return Data(x=x, edge_index=edge_index), edge_keys


def load_model() -> TrafficGAT | None:
    if not WEIGHTS_PATH.exists():
        return None
    try:
        model = TrafficGAT()
        model.load_state_dict(torch.load(WEIGHTS_PATH, map_location="cpu", weights_only=True))
        model.eval()
        logger.info("Loaded GNN weights from %s", WEIGHTS_PATH)
        return model
    except Exception as e:
        logger.warning("Failed to load GNN weights: %s", e)
        return None


def predict_edge_multipliers(G: nx.MultiDiGraph) -> dict[tuple[int, int], float]:
    """
    Returns {(u, v): multiplier} for all edges.
    Uses trained GNN if weights exist, otherwise falls back to degree+speed heuristic.
    """
    model = load_model()

    if model is not None:
        return _gnn_predict(G, model)

    logger.debug("No GNN weights found, using numpy heuristic")
    return _numpy_fallback(G)


def _gnn_predict(G: nx.MultiDiGraph, model: TrafficGAT) -> dict[tuple[int, int], float]:
    data, edge_keys = graph_to_pyg(G)
    with torch.no_grad():
        multipliers = model(data.x, data.edge_index).numpy()

    result: dict[tuple[int, int], float] = {}
    for (u, v, _), mult in zip(edge_keys, multipliers):
        # Keep the max multiplier if multiple edges connect the same (u, v)
        result[(u, v)] = max(result.get((u, v), 1.0), float(mult))
    return result


def _numpy_fallback(G: nx.MultiDiGraph) -> dict[tuple[int, int], float]:
    degree = dict(G.degree())
    max_degree = max(degree.values(), default=1)
    result: dict[tuple[int, int], float] = {}
    for u, v, data in G.edges(data=True):
        intersection_load = (degree.get(u, 1) / max_degree) * 0.4
        speed = data.get("speed_kph", 50)
        speed_factor = max(0.0, (60 - speed) / 60) * 0.3
        result[(u, v)] = float(np.clip(1.0 + intersection_load + speed_factor, 1.0, 4.0))
    return result

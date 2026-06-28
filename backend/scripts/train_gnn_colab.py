"""
GNN training script for Google Colab (GPU).

Before running:
1. Upload to Colab:
   - this file
   - data/bay_area.graphml
   - data/pems/training_labels.parquet

2. Set runtime to T4 GPU

3. Run all cells

After training, download gnn.pt and place at:
    bay-area-pathfinder/backend/weights/gnn.pt

Then restart the backend:
    docker compose restart backend
"""

# ── Install ───────────────────────────────────────────────────────────────────
import subprocess
subprocess.run(["pip", "install", "-q", "osmnx", "torch-geometric", "pandas", "pyarrow"], check=True)

# ── Imports ───────────────────────────────────────────────────────────────────
import logging
import numpy as np
import osmnx as ox
import pandas as pd
import torch
import torch.nn as nn
from torch_geometric.data import Data
from torch_geometric.nn import GATConv

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
EPOCHS = 200
LR = 1e-3
GRAPH_PATH = "bay_area.graphml"
LABELS_PATH = "training_labels.parquet"

logger.info(f"Training on: {DEVICE}")

# ── Model (must match app/models/gnn.py exactly) ─────────────────────────────
class TrafficGAT(nn.Module):
    def __init__(self, in_channels=4, hidden=64, heads=4):
        super().__init__()
        self.gat1 = GATConv(in_channels, hidden, heads=heads, dropout=0.1)
        self.gat2 = GATConv(hidden * heads, hidden, heads=1, concat=False)
        self.edge_head = nn.Linear(hidden * 2, 1)

    def forward(self, x, edge_index):
        x = torch.relu(self.gat1(x, edge_index))
        x = torch.relu(self.gat2(x, edge_index))
        src, dst = edge_index
        edge_feats = torch.cat([x[src], x[dst]], dim=-1)
        return torch.sigmoid(self.edge_head(edge_feats)).squeeze(-1) * 3.0 + 1.0


# ── Graph → PyG ───────────────────────────────────────────────────────────────
def graph_to_pyg(G):
    nodes = list(G.nodes())
    node_idx = {n: i for i, n in enumerate(nodes)}

    lats = np.array([G.nodes[n].get("y", 0.0) for n in nodes])
    lngs = np.array([G.nodes[n].get("x", 0.0) for n in nodes])
    degrees = np.array([G.degree(n) for n in nodes], dtype=float)

    def norm(arr):
        return (arr - arr.min()) / (arr.max() - arr.min() + 1e-8)

    avg_speeds = []
    for n in nodes:
        speeds = [G[n][v][k].get("speed_kph", 50.0) for v in G[n] for k in G[n][v]]
        avg_speeds.append(np.mean(speeds) / 130.0 if speeds else 0.38)

    x = torch.tensor(
        np.stack([norm(lats), norm(lngs), norm(degrees), avg_speeds], axis=1),
        dtype=torch.float,
    )

    edge_list, edge_keys = [], []
    for u, v, k in G.edges(keys=True):
        edge_list.append([node_idx[u], node_idx[v]])
        edge_keys.append((u, v, k))

    edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
    return Data(x=x, edge_index=edge_index), edge_keys, node_idx


# ── Load graph ────────────────────────────────────────────────────────────────
logger.info("Loading graph...")
G = ox.load_graphml(GRAPH_PATH)
ox.add_edge_speeds(G)
ox.add_edge_travel_times(G)
logger.info(f"Graph: {len(G.nodes)} nodes, {len(G.edges)} edges")

data, edge_keys, node_idx = graph_to_pyg(G)
data = data.to(DEVICE)

# ── Load PEMS labels ──────────────────────────────────────────────────────────
logger.info("Loading PEMS training labels...")
labels_df = pd.read_parquet(LABELS_PATH)

# Average multiplier per (edge_u, edge_v) across all hours — global congestion profile
edge_labels = labels_df.groupby(["edge_u", "edge_v"])["multiplier"].median().to_dict()
logger.info(f"Labels cover {len(edge_labels)} edges")

# Build label tensor aligned to PyG edge order
label_values = []
covered = 0
for u, v, _ in edge_keys:
    mult = edge_labels.get((u, v))
    if mult is not None:
        label_values.append(mult)
        covered += 1
    else:
        # Edges without PEMS coverage (surface streets) get free-flow = 1.0
        label_values.append(1.0)

labels = torch.tensor(label_values, dtype=torch.float).to(DEVICE)
logger.info(f"PEMS coverage: {covered}/{len(edge_keys)} edges ({100*covered/len(edge_keys):.1f}%)")

# ── Train ─────────────────────────────────────────────────────────────────────
model = TrafficGAT().to(DEVICE)
optimizer = torch.optim.Adam(model.parameters(), lr=LR)

# Weighted loss: PEMS-covered edges matter more than uncovered surface streets
weights = torch.tensor(
    [2.0 if edge_labels.get((u, v)) is not None else 0.5 for u, v, _ in edge_keys],
    dtype=torch.float,
).to(DEVICE)

logger.info(f"Training for {EPOCHS} epochs...")
model.train()
for epoch in range(1, EPOCHS + 1):
    optimizer.zero_grad()
    preds = model(data.x, data.edge_index)
    loss = (weights * (preds - labels) ** 2).mean()
    loss.backward()
    optimizer.step()
    if epoch % 25 == 0 or epoch == 1:
        logger.info(f"  Epoch {epoch:3d}/{EPOCHS}  loss={loss.item():.4f}")

# Save CPU weights
model_cpu = model.to("cpu")
torch.save(model_cpu.state_dict(), "gnn.pt")
logger.info("Saved gnn.pt")

# Evaluation
model_cpu.eval()
with torch.no_grad():
    preds_cpu = model_cpu(data.cpu().x, data.cpu().edge_index).numpy()

covered_mask = [edge_labels.get((u, v)) is not None for u, v, _ in edge_keys]
covered_labels = np.array([edge_labels.get((u, v), 1.0) for u, v, _ in edge_keys])[covered_mask]
covered_preds = preds_cpu[covered_mask]
mae = np.abs(covered_preds - covered_labels).mean()
logger.info(f"MAE on PEMS-covered edges: {mae:.4f} (in multiplier units, lower is better)")
logger.info(f"Pred range: [{preds_cpu.min():.2f}, {preds_cpu.max():.2f}]")

# Auto-download in Colab
try:
    from google.colab import files
    files.download("gnn.pt")
except ImportError:
    pass

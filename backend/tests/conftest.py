import networkx as nx
import pytest


@pytest.fixture
def small_graph():
    """
    4-node directed graph representing a tiny road network:
        0 → 1 (length=100, travel_time=10)
        1 → 2 (length=200, travel_time=20)
        2 → 3 (length=150, travel_time=15)
        0 → 3 (length=600, travel_time=60)  ← longer direct path
    Shortest path 0→3 should go 0→1→2→3 (cost=45), not 0→3 (cost=60).
    """
    G = nx.MultiDiGraph()

    for node_id, (y, x) in enumerate([(37.79, -122.40), (37.79, -122.39), (37.78, -122.39), (37.78, -122.40)]):
        G.add_node(node_id, y=y, x=x)

    edges = [
        (0, 1, {"length": 100, "travel_time": 10, "speed_kph": 50}),
        (1, 2, {"length": 200, "travel_time": 20, "speed_kph": 50}),
        (2, 3, {"length": 150, "travel_time": 15, "speed_kph": 50}),
        (0, 3, {"length": 600, "travel_time": 60, "speed_kph": 50}),
    ]
    for u, v, data in edges:
        G.add_edge(u, v, **data)

    return G

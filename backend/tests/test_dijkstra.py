import pytest

from app.core.dijkstra import dijkstra


def test_finds_shortest_path(small_graph):
    path, cost = dijkstra(small_graph, source=0, target=3)
    assert path == [0, 1, 2, 3]
    assert cost == pytest.approx(45.0)


def test_direct_path_when_shorter(small_graph):
    # 0→1 direct, cost=10 — shorter than any multi-hop alternative
    path, cost = dijkstra(small_graph, source=0, target=1)
    assert path == [0, 1]
    assert cost == pytest.approx(10.0)


def test_no_path_raises(small_graph):
    # No edges point back to 0 in this graph
    with pytest.raises(ValueError, match="No path found"):
        dijkstra(small_graph, source=3, target=0)


def test_source_equals_target(small_graph):
    path, cost = dijkstra(small_graph, source=2, target=2)
    assert path == [2]
    assert cost == pytest.approx(0.0)

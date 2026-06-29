import heapq


def _dijkstra(G, source, target, weight="travel_time",
              pems_overrides=None,
              gnn_multipliers=None):
    dist = {source: 0.0}
    prev = {source: None}
    heap = [(0.0, source)]
    visited = set()

    while heap:
        cost, u = heapq.heappop(heap)

        if u in visited:
            continue
        visited.add(u)

        if u == target:
            break

        for _, v, data in G.edges(u, data=True):
            if v in visited:
                continue

            length_m = data.get("length", 100.0)

            if pems_overrides and (u, v) in pems_overrides:
                # Real sensor speed — most accurate
                w = length_m / (pems_overrides[(u, v)] / 3.6)
            else:
                base_tt = data.get(weight) or (length_m / max(data.get("speed_kph", 50) / 3.6, 1))
                if gnn_multipliers and (u, v) in gnn_multipliers:
                    # GNN-predicted congestion on uncovered edges
                    w = base_tt * gnn_multipliers[(u, v)]
                else:
                    w = base_tt

            new_cost = cost + w
            if new_cost < dist.get(v, float("inf")):
                dist[v] = new_cost
                prev[v] = u
                heapq.heappush(heap, (new_cost, v))

    if target not in dist:
        raise ValueError(f"No path found between nodes {source} and {target}")

    return dist, prev


def dijkstra(G, source, target, weight="travel_time",
             pems_overrides=None,
             gnn_multipliers=None):
    dist, prev = _dijkstra(G, source, target, weight, pems_overrides, gnn_multipliers)

    path = []
    node = target
    while node is not None:
        path.append(node)
        node = prev[node]

    path.reverse()
    return path, dist[target]

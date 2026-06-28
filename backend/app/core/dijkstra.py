import heapq


def _dijkstra(G, source, target, weight="travel_time", overrides: dict | None = None):
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

            if overrides and (u, v) in overrides:
                length_m = data.get("length", 100.0)
                w = length_m / (overrides[(u, v)] / 3.6)
            else:
                w = data.get(weight) or data.get("length", 1.0)

            new_cost = cost + w
            if new_cost < dist.get(v, float("inf")):
                dist[v] = new_cost
                prev[v] = u
                heapq.heappush(heap, (new_cost, v))

    if target not in dist:
        raise ValueError(f"No path found between nodes {source} and {target}")

    return dist, prev


def dijkstra(G, source, target, weight="travel_time", overrides: dict | None = None):
    dist, prev = _dijkstra(G, source, target, weight, overrides)

    path = []
    node = target
    while node is not None:
        path.append(node)
        node = prev[node]

    path.reverse()
    return path, dist[target]

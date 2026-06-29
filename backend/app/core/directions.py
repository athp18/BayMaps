import math


_BUCKET_UNCERTAINTY = {
    "weekday_am_peak":  (0.80, 1.25),
    "weekday_midday":   (0.85, 1.18),
    "weekday_pm_peak":  (0.85, 1.18),
    "weekday_night":    (0.70, 1.35),
    "weekend_day":      (0.90, 1.12),
    "weekend_night":    (0.70, 1.35),
}


def duration_bounds(cost_seconds, bucket):
    lo, hi = _BUCKET_UNCERTAINTY.get(bucket, (0.80, 1.25))
    return round(cost_seconds * lo / 60, 1), round(cost_seconds * hi / 60, 1)


def _bearing(lat1, lng1, lat2, lng2):
    dlng = math.radians(lng2 - lng1)
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlng) * math.cos(lat2r)
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlng)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _turn_word(b1, b2):
    delta = (b2 - b1 + 360) % 360
    if delta > 180:
        delta -= 360
    if abs(delta) < 15:
        return "Continue"
    elif delta > 0:
        if delta < 45:
            return "Turn slight right"
        elif delta < 120:
            return "Turn right"
        else:
            return "Turn sharp right"
    else:
        if delta > -45:
            return "Turn slight left"
        elif delta > -120:
            return "Turn left"
        else:
            return "Turn sharp left"


def build_directions(G, path):
    """
    Returns list of dicts with keys: instruction, distance_m, street.
    Consecutive edges on the same named street are merged into one step.
    """
    if len(path) < 2:
        return []

    steps = []
    cur_street = None
    cur_dist = 0.0
    cur_bearing = None
    prev_bearing = None

    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        data = G[u][v][0]

        lat_u = G.nodes[u].get("y", 0.0)
        lng_u = G.nodes[u].get("x", 0.0)
        lat_v = G.nodes[v].get("y", 0.0)
        lng_v = G.nodes[v].get("x", 0.0)

        b = _bearing(lat_u, lng_u, lat_v, lng_v)
        length = data.get("length", 0.0)

        name = data.get("name", "")
        if isinstance(name, list):
            name = name[0] if name else ""
        name = name or ""

        if cur_street is None:
            cur_street = name
            cur_dist = length
            cur_bearing = b
            prev_bearing = b
        elif name == cur_street or not name:
            cur_dist += length
            prev_bearing = b
        else:
            turn = _turn_word(cur_bearing, b) if cur_bearing is not None else "Continue"
            label = f"{turn} onto {cur_street}" if cur_street else turn
            steps.append({"instruction": label, "distance_m": round(cur_dist, 1), "street": cur_street})
            cur_street = name
            cur_dist = length
            cur_bearing = b
            prev_bearing = b

    if cur_street is not None:
        label = f"Arrive at destination" if not cur_street else f"Continue on {cur_street} to destination"
        steps.append({"instruction": label, "distance_m": round(cur_dist, 1), "street": cur_street or ""})

    return steps

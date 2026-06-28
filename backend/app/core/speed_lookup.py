import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

LOOKUP_PATH = Path("data/pems/speed_lookup.parquet")

# hour_of_week (0-167) -> {(u, v): speed_kph}
_hour_cache: dict[int, dict[tuple[int, int], float]] = {}
_coverage: dict = {"covered_edges": 0, "total_edges": 0}


def load_speed_lookup() -> None:
    if not LOOKUP_PATH.exists():
        logger.warning("speed_lookup.parquet not found — PEMS layer disabled")
        return

    df = pd.read_parquet(LOOKUP_PATH)
    logger.info(f"Speed lookup loaded: {len(df)} records, building hour cache...")

    for hour, group in df.groupby("hour_of_week"):
        _hour_cache[int(hour)] = {
            (int(r.edge_u), int(r.edge_v)): float(r.speed_kph)
            for r in group.itertuples()
            if r.speed_kph > 0
        }

    sample = next(iter(_hour_cache.values())) if _hour_cache else {}
    logger.info(f"Hour cache ready: {len(_hour_cache)} hours, ~{len(sample)} edges/hour")


def get_overrides(hour_of_week: int | None = None) -> dict[tuple[int, int], float]:
    """Return {(u, v): speed_kph} for the given hour (defaults to current local time)."""
    if hour_of_week is None:
        now = datetime.now()
        hour_of_week = now.weekday() * 24 + now.hour
    return _hour_cache.get(hour_of_week, {})


def apply_speed_lookup(G, hour_of_week: int | None = None) -> int:
    """Bake current-hour speeds into graph edge travel_time (startup baseline only)."""
    overrides = get_overrides(hour_of_week)
    if not overrides:
        return 0

    updated = 0
    for u, v, data in G.edges(data=True):
        speed_kph = overrides.get((u, v))
        if speed_kph is not None:
            length_m = data.get("length", 100.0)
            osm_speed = data.get("speed_kph", 50.0)
            old_tt = data.get("travel_time", length_m / (osm_speed / 3.6))
            new_tt = length_m / (speed_kph / 3.6)
            logger.debug(
                f"edge ({u},{v}): length={length_m:.0f}m  "
                f"osm={osm_speed:.1f}→pems={speed_kph:.1f} kph  "
                f"tt={old_tt:.1f} -> {new_tt:.1f}s  factor={new_tt/old_tt:.3f}"
            )
            data["travel_time"] = new_tt
            updated += 1

    global _coverage
    _coverage = {"covered_edges": updated, "total_edges": G.number_of_edges()}
    logger.info(f"PEMS: baked {updated}/{G.number_of_edges()} edges for hour {hour_of_week}")
    return updated


def get_coverage() -> dict:
    return _coverage

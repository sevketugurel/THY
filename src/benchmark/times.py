"""Benchmark pipeline time maps: baseline times plus seed-delta overlay."""

import json
from pathlib import Path


def epoch_min(ts, anchor) -> int:
    return int((ts - anchor).total_seconds() // 60)


def build_baseline_times(tk, anchor) -> dict:
    """Return (role, flno, gun) -> epoch minute for each TK leg.

    A leg can appear in multiple itinerary rows. Keep the first occurrence,
    matching the independent validator's existing match.iloc[0] convention.
    """
    times = {}
    for row in tk.itertuples():
        arr_key = ("IB", int(row.flno1), int(row.gun))
        if arr_key not in times:
            times[arr_key] = epoch_min(row.arr_time, anchor)
        dep_key = ("OB", int(row.flno2), int(row.gun))
        if dep_key not in times:
            times[dep_key] = epoch_min(row.dep_time, anchor)
    return times


def load_seed_deltas(path) -> tuple:
    """Return (deltas, note); malformed seeds degrade to an empty overlay."""
    p = Path(path)
    if not p.exists():
        return [], f"seed file not found: {p}"
    try:
        data = json.loads(p.read_text())
        deltas = data["deltas"]
        for delta in deltas:
            if not all(k in delta for k in ("role", "flno", "gun", "delta_min")):
                return [], "seed file malformed: delta entry missing keys"
        return deltas, "ok"
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return [], f"seed file unreadable: {exc}"


def apply_seed_deltas(baseline_times: dict, deltas: list, adjustable_window_min: int) -> tuple:
    """Apply portable baseline deltas with missing-flight and window guards."""
    times = dict(baseline_times)
    stats = {"applied": 0, "skipped_missing_flight": 0, "fallback_window_exceeded": 0}
    for delta in deltas:
        key = (delta["role"], int(delta["flno"]), int(delta["gun"]))
        if key not in baseline_times:
            stats["skipped_missing_flight"] += 1
            continue
        delta_min = int(delta["delta_min"])
        if abs(delta_min) > adjustable_window_min:
            stats["fallback_window_exceeded"] += 1
            continue
        times[key] = baseline_times[key] + delta_min
        stats["applied"] += 1
    return times, stats

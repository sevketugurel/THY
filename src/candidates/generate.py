"""Candidate connection generation: TK inbound x outbound cross-product per (o,d,gun),
filtered by an ACHIEVABLE-RANGE feasibility gate (Modül-3 kapı 1, plan §4).

Correctness argument: a candidate pi=(r1,r2) belongs in the model iff there exists
SOME (t_arr,t_dep) within each flight's legal window such that gap=t_dep-t_arr is in
[L,U]. Since r1,r2 move independently in M1 (no A/G coupling yet), the achievable gap
range is [dep_lo-arr_hi, dep_hi-arr_lo] (interval subtraction of two independent
bounded intervals). If this range doesn't intersect [L,U], no time assignment can ever
validate the candidate -- safe to prune before the solver ever sees it. This reduces
exactly to M0's baseline-only check when adjustable_window_min=0 (a single-point
interval), so M0's existing tests remain valid as a special case.
"""
from dataclasses import dataclass
from itertools import product

import pandas as pd


@dataclass(frozen=True)
class Candidate:
    od: str
    o: str
    d: str
    gun: int
    flno1: int
    flno2: int
    r1_id: tuple
    r2_id: tuple
    arr_time: pd.Timestamp
    dep_time: pd.Timestamp
    gap_min: int
    arr_lo: int
    arr_hi: int
    dep_lo: int
    dep_hi: int
    gap_lo: int
    gap_hi: int


def _window(baseline_min: int, adjustable: bool, w: int) -> tuple:
    if not adjustable:
        return baseline_min, baseline_min
    return baseline_min - w, baseline_min + w


def compute_epoch_anchor(tk_rows: pd.DataFrame) -> pd.Timestamp:
    """Global epoch anchor: MIDNIGHT of the earliest calendar date across the whole
    dataset. Using a single global anchor (not a per-row/per-day reset) is required
    for correctness across midnight-crossing connections -- a per-day reset would
    silently discard which calendar date a timestamp falls on and corrupt
    cross-midnight gaps. Anchoring at midnight (rather than the exact earliest
    timestamp) keeps epoch-minutes hand-verifiable as "minutes since midnight of
    day 1" for anything on the first day, instead of shifting by an arbitrary offset."""
    return min(tk_rows["arr_time"].min(), tk_rows["dep_time"].min()).normalize()


def generate_candidates(
    tk_rows: pd.DataFrame, L: int, U: int, gun: int,
    adjustable_window_min: int = 0, adjustable_set: str = "none",
    epoch_anchor: pd.Timestamp = None,
) -> list[Candidate]:
    if adjustable_set not in ("none", "all"):
        raise NotImplementedError(f"adjustable_set={adjustable_set!r} not supported yet (only 'none'/'all')")
    is_adjustable = adjustable_set == "all"

    if epoch_anchor is None:
        epoch_anchor = compute_epoch_anchor(tk_rows)

    gun = int(gun)
    day_rows = tk_rows[tk_rows["gun"] == gun]

    inbound = day_rows[["dep1", "flno1", "arr_time"]].drop_duplicates(subset=["dep1", "flno1"])
    outbound = day_rows[["arr2", "flno2", "dep_time"]].drop_duplicates(subset=["arr2", "flno2"])

    def epoch_min(ts: pd.Timestamp) -> int:
        return int((ts - epoch_anchor).total_seconds() // 60)

    candidates = []
    for (_, ib), (_, ob) in product(inbound.iterrows(), outbound.iterrows()):
        o, d = ib["dep1"], ob["arr2"]
        if o == d:
            continue

        arr_baseline = epoch_min(ib["arr_time"])
        dep_baseline = epoch_min(ob["dep_time"])
        arr_lo, arr_hi = _window(arr_baseline, is_adjustable, adjustable_window_min)
        dep_lo, dep_hi = _window(dep_baseline, is_adjustable, adjustable_window_min)

        gap_lo = dep_lo - arr_hi
        gap_hi = dep_hi - arr_lo
        if not (gap_hi >= L and gap_lo <= U):
            continue

        gap_baseline = dep_baseline - arr_baseline
        candidates.append(Candidate(
            od=f"{o}-{d}", o=o, d=d, gun=gun,
            flno1=int(ib["flno1"]), flno2=int(ob["flno2"]),
            r1_id=("IB", int(ib["flno1"]), gun), r2_id=("OB", int(ob["flno2"]), gun),
            arr_time=ib["arr_time"], dep_time=ob["dep_time"],
            gap_min=gap_baseline,
            arr_lo=arr_lo, arr_hi=arr_hi, dep_lo=dep_lo, dep_hi=dep_hi,
            gap_lo=gap_lo, gap_hi=gap_hi,
        ))
    return candidates

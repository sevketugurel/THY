"""M5 solve-ladder step 2: adjustable-subset mode. Top-K markets (by rho)
keep their free (adjustable) flight-time window; every other candidate's
legs collapse to their raw baseline time (Rfix), folding the rest of the
schedule out of the MIP's variable scope while still counting toward F's
hub-capacity accounting via compute_out_of_scope_baselines (build.py wires
these together).

Doğruluk argümanı: bkz. tests/unit/test_subset_adjustable.py docstring.
"""
from dataclasses import replace

from src.candidates.generate import Candidate


def apply_adjustable_subset(candidates: list[Candidate], adjustable_markets: set, L: int, U: int) -> list[Candidate]:
    adjustable_arr = set()
    adjustable_dep = set()
    for c in candidates:
        if (c.o, c.d) in adjustable_markets:
            adjustable_arr.add(c.r1_id)
            adjustable_dep.add(c.r2_id)

    result = []
    for c in candidates:
        if c.r1_id in adjustable_arr:
            arr_lo, arr_hi = c.arr_lo, c.arr_hi
        else:
            arr_lo = arr_hi = _baseline_epoch(c.arr_lo, c.arr_hi)

        if c.r2_id in adjustable_dep:
            dep_lo, dep_hi = c.dep_lo, c.dep_hi
        else:
            dep_lo = dep_hi = _baseline_epoch(c.dep_lo, c.dep_hi)

        gap_lo = dep_lo - arr_hi
        gap_hi = dep_hi - arr_lo
        if not (gap_hi >= L and gap_lo <= U):
            continue

        result.append(replace(
            c, arr_lo=arr_lo, arr_hi=arr_hi, dep_lo=dep_lo, dep_hi=dep_hi,
            gap_lo=gap_lo, gap_hi=gap_hi,
        ))
    return result


def _baseline_epoch(lo, hi):
    """Recovers the original (pre-window) baseline epoch-minute for a leg
    from its symmetric [baseline-w,baseline+w] window (src.candidates.generate::_window
    always constructs it this way) -- the midpoint is exact, no need for the
    original epoch_anchor or arr_time/dep_time timestamps. Already-Rfix
    (lo==hi) legs are already their own baseline."""
    return lo + (hi - lo) // 2

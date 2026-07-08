"""W(r) monotonicity check + b_od (baseline rank) derivation.

Doğruluk argümanları için bkz. tests/unit/test_ranking.py docstring.
"""
import pandas as pd

from src.data.competitors import derive_rival_best_times


def is_ranking_monotonic(df: pd.DataFrame) -> bool:
    """True iff, for every fixed (n,b), weight is non-increasing as r increases."""
    for _, group in df.groupby(["n", "b"]):
        weights = group.sort_values("r")["weight"].tolist()
        if any(weights[i + 1] > weights[i] for i in range(len(weights) - 1)):
            return False
    return True


def compute_baseline_best_journey(od_table: pd.DataFrame, o: str, d: str, gun: int, L: int, U: int):
    """TK's best (min gate_to_gate_min) CURRENT itinerary for (o,d,gun) among
    valid-gap ([L,U]) rows. Returns None if no valid-gap TK row exists for
    this market (e.g. gun not present, or every row is placeholder/invalid)."""
    tk = od_table[od_table.cr1 == "TK"]
    market = tk[(tk.dep1 == o) & (tk.arr2 == d) & (tk.gun == gun)]
    if market.empty:
        return None
    gap_min = (market["dep_time"] - market["arr_time"]).dt.total_seconds() / 60
    valid = market[(gap_min >= L) & (gap_min <= U)]
    if valid.empty:
        return None
    return int(valid["gate_to_gate_min"].min())


def derive_b_od(od_table: pd.DataFrame, o: str, d: str, gun: int, baseline_journey_min: int) -> int:
    """b_od = N_{od,gun} - (rivals beaten by TK's baseline itinerary), using
    the SAME <= rule as D (Jpi <= Tcomp beats/ties the rival). This is r's own
    formula applied to the pre-optimization baseline, not a separate rule."""
    rivals = derive_rival_best_times(od_table, o, d, gun)
    n = len(rivals)
    beaten = sum(1 for t_comp in rivals.values() if baseline_journey_min <= t_comp)
    return n - beaten

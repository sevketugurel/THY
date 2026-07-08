"""N_od,h / T_comp_{od,h,k} derivation from the O&D table's non-TK rows.

Doğruluk argümanı: bir "rakip" (rival) TEK BİR TAŞIYICI (Cr1) -- o taşıyıcının
o (o,d,h) pazarındaki TÜM itineraryleri o rakibin PARÇASI, ayrı rakipler
değil. TK bir rakibi yenmek için rakibin EN İYİ alternatifinden daha hızlı
olmalı (aksi halde yolcu hala rakibin daha hızlı seçeneğini tercih eder).
Bkz. tests/unit/test_competitors.py docstring.
"""
import pandas as pd


def derive_rival_best_times(od_table: pd.DataFrame, o: str, d: str, gun: int) -> dict:
    """Returns {carrier: min_gate_to_gate_minutes} for all non-TK carriers
    with at least one row on (o,d,gun). len(result) == N_{od,gun}."""
    market = od_table[
        (od_table.cr1 != "TK") & (od_table.dep1 == o) & (od_table.arr2 == d) & (od_table.gun == gun)
    ]
    if market.empty:
        return {}
    return market.groupby("cr1")["gate_to_gate_min"].min().to_dict()

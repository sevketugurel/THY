#!/usr/bin/env python3
"""M5 diagnostic: isolate which constraint group makes the real full-data
model infeasible. Not a permanent artifact -- ad-hoc bisection script.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi
from src.data.ranking import compute_baseline_best_journey, derive_b_od, is_ranking_monotonic
from src.model.build import build_model_with_competition
from src.solve.runner import solve

L, U = 60, 300


def main():
    od_table = load_od_table("data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx")
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi("data_raw/Yolcu Verisi_masked.xlsx", strict=False)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    ranking_table = load_change_ranking("data_raw/change_ranking_input.xlsx")
    anchor = compute_epoch_anchor(tk)

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=180, adjustable_set="all", epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    provider = BlockTimeProvider(tk, L=L, U=U)
    journey_constants = {}
    dropped = set()
    for c in candidates:
        m = (c.o, c.d)
        if m in journey_constants or m in dropped:
            continue
        try:
            journey_constants[m] = provider.get_journey_constant(c.o, c.d)
        except KeyError:
            try:
                journey_constants[m] = provider.get_journey_constant_estimate(c.o, c.d)
            except KeyError:
                dropped.add(m)
    candidates = [c for c in candidates if (c.o, c.d) not in dropped]

    rival_data, b_od_data = {}, {}
    for c in candidates:
        mk = (c.o, c.d, c.gun)
        if mk not in rival_data:
            rival_data[mk] = derive_rival_best_times(od_table, c.o, c.d, c.gun)
        if (c.o, c.d) not in b_od_data:
            bj = compute_baseline_best_journey(od_table, c.o, c.d, c.gun, L=L, U=U)
            b_od_data[(c.o, c.d)] = derive_b_od(od_table, c.o, c.d, c.gun, bj) if bj is not None else 0

    monotonic = is_ranking_monotonic(ranking_table)
    print("monotonic=", monotonic, "candidates=", len(candidates), flush=True)

    print("=== TEST: B+C+D only (no A, no G) ===", flush=True)
    t0 = time.time()
    model = build_model_with_competition(
        candidates, rho, journey_constants, rival_data, b_od_data, ranking_table,
        L=L, U=U, monotonic=monotonic,
    )
    print("build time:", round(time.time() - t0, 1), flush=True)
    t1 = time.time()
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    print("solve time:", round(time.time() - t1, 1), "status=", result.status, "obj=", result.objective_value, flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""M5d Adım 2 diagnostic (before committing to another 720s local-branching
solve): k=200 local branching (Big-M/moved-indicator form) came back
watchdog_killed with Nodes=0 (runs/local_branching_20260710T214039Z.log.json)
-- the raw HiGHS log shows presolve/probing only got through 3765/278163
binaries before giving up, so the "moved=0 implies t=reference" deduction
never materialized as an actual size reduction. This script asks a cheaper,
prior question with NO large solve at all: re-solve A+G+F for a reference
point, then in pure Python (same gap/x/Jbest logic as
src.model.warm_start.derive_and_set_warm_start) compute exactly which E1/E2
market-pairs are violated at that reference, and how many DISTINCT flight
instances (t_arr/t_dep) would need to be freed (not fixed) to give those
markets any chance of a hard-feasible correction. If that count is itself a
large fraction of all instances, a surgical (hard-fix-based) local branching
has no realistic chance either, independent of any solve attempt.

Kullanım: .venv/bin/python3 -u scripts/analyze_violation_footprint.py
"""
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.model.build import build_core_feasibility_model
from src.model.deviation_objective import add_min_deviation_objective
from src.solve.subprocess_watchdog import solve_step_with_watchdog

from src.config.paths import FULL_OD, FULL_YV, FULL_FP
CORE_WORKER = Path(__file__).resolve().parent / "_core_feasibility_step_worker.py"


def main():
    t0 = time.time()
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]
    alpha, gamma = config["alpha"], config["gamma"]

    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FULL_YV, strict=False)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    pairs_df = load_flight_pairs(FULL_FP)
    anchor = compute_epoch_anchor(tk)

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=config["adjustable_window_min"],
            adjustable_set=config["adjustable_set"], epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    provider = BlockTimeProvider(tk, L=L, U=U)
    journey_constants, dropped_markets = {}, set()
    for c in candidates:
        market = (c.o, c.d)
        if market in journey_constants or market in dropped_markets:
            continue
        try:
            journey_constants[market] = provider.get_journey_constant(c.o, c.d)
        except KeyError:
            try:
                journey_constants[market] = provider.get_journey_constant_estimate(c.o, c.d)
            except KeyError:
                dropped_markets.add(market)
    candidates = [c for c in candidates if (c.o, c.d) not in dropped_markets]

    rotation_stations = set(row["dest"] for row in pairs_df.to_dict("records") if row["orig"] == "IST")
    r_o_lookup = {}
    for station in rotation_stations:
        try:
            r_o_lookup[station] = provider.get_rotation_constant(station)
        except KeyError:
            continue

    print(f"[analyze] preprocessing done in {time.time()-t0:.1f}s, n_candidates={len(candidates)}", flush=True)

    core_build_kwargs = dict(
        candidates=candidates, pairs_df=pairs_df, r_o_lookup=r_o_lookup,
        tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor, tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"],
    )
    core_solve_kwargs = dict(solver="highs", time_limit_sec=600.0, seed=config["seed"],
                              mip_gap=0.08, mip_heuristic_effort=0.3)
    print("[analyze] re-solving A+G+F for the reference point...", flush=True)
    t1 = time.time()
    core_result, _ = solve_step_with_watchdog(
        core_build_kwargs, core_solve_kwargs, time_limit_sec=600.0, watchdog_margin_sec=120.0,
        step_name="core_feasibility_for_footprint", worker_script=CORE_WORKER,
    )
    print(f"[analyze] A+G+F solve finished in {time.time()-t1:.1f}s status={core_result.status}", flush=True)
    if core_result.status not in ("optimal", "time_limit") or not core_result.arr_times:
        print("[analyze] ABORT -- no usable A+G+F reference point", flush=True)
        return

    arr_times, dep_times = core_result.arr_times, core_result.dep_times

    groups = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[(c.o, c.d, c.gun)].append(i)

    gap_of, x_of = {}, {}
    for i, c in enumerate(candidates):
        gap = dep_times[c.r2_id] - arr_times[c.r1_id]
        gap_of[i] = gap
        x_of[i] = 1 if L <= gap <= U else 0

    # E1: |n_fwd - n_bwd| <= alpha*(n_fwd+n_bwd) per (o,d,gun) pair.
    e1_pairs = {(c.o, c.d, c.gun) for c in candidates}
    e1_violations = []
    for (o, d, gun) in e1_pairs:
        if o > d:
            continue  # each unordered pair considered once
        n_fwd = sum(x_of[i] for i in groups.get((o, d, gun), []))
        n_bwd = sum(x_of[i] for i in groups.get((d, o, gun), []))
        if abs(n_fwd - n_bwd) > alpha * (n_fwd + n_bwd) + 1e-9:
            e1_violations.append((o, d, gun, n_fwd, n_bwd))

    # E2: |Jbest_fwd - Jbest_bwd| <= gamma, only when BOTH directions have >=1 offered candidate.
    jbest_of = {}
    for (o, d, gun), idxs in groups.items():
        offered = [i for i in idxs if x_of[i] == 1]
        if offered:
            jbest_of[(o, d, gun)] = min(journey_constants[(o, d)] + gap_of[i] for i in offered)

    e2_violations = []
    seen_pairs = set()
    for (o, d, gun) in list(jbest_of):
        if (d, o, gun) not in jbest_of:
            continue
        pair_key = tuple(sorted([(o, d, gun), (d, o, gun)]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        j_fwd, j_bwd = jbest_of[(o, d, gun)], jbest_of[(d, o, gun)]
        if abs(j_fwd - j_bwd) > gamma + 1e-9:
            e2_violations.append((o, d, gun, j_fwd, j_bwd))

    print(f"[analyze] E1 violations: {len(e1_violations)} / {len(e1_pairs)//2} pairs", flush=True)
    print(f"[analyze] E2 violations: {len(e2_violations)} / {len(seen_pairs)} pairs with both sides offered", flush=True)

    violating_markets = set()
    for (o, d, gun, *_ ) in e1_violations:
        violating_markets.add((o, d, gun))
        violating_markets.add((d, o, gun))
    for (o, d, gun, *_) in e2_violations:
        violating_markets.add((o, d, gun))
        violating_markets.add((d, o, gun))

    free_arr, free_dep = set(), set()
    for (o, d, gun) in violating_markets:
        for i in groups.get((o, d, gun), []):
            c = candidates[i]
            free_arr.add(c.r1_id)
            free_dep.add(c.r2_id)

    total_arr = len({c.r1_id for c in candidates})
    total_dep = len({c.r2_id for c in candidates})
    print(f"[analyze] violating markets (both directions): {len(violating_markets)}", flush=True)
    print(f"[analyze] free instances needed: arr={len(free_arr)}/{total_arr} "
          f"({100*len(free_arr)/total_arr:.1f}%), dep={len(free_dep)}/{total_dep} "
          f"({100*len(free_dep)/total_dep:.1f}%), total_free={len(free_arr)+len(free_dep)}", flush=True)


if __name__ == "__main__":
    main()

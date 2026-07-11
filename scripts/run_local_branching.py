#!/usr/bin/env python3
"""M5d Adım 2 (docs/decisions.md 2026-07-10, plan
.claude/plans/g-rev-i-lk-do-rulanm-wobbly-acorn.md): full-data local-branching
solve. Adım 1 (scripts/run_full_data.py, cold build_model_m4 rerun with the
Jbest fix, no scaffolding) came back watchdog_killed with zero incumbent
(runs/full_data_run_20260710T211554Z.log.json, 1019.3s) -- the Jbest fix
alone does not unstick HiGHS's root-node stall. This script re-solves A+G+F
for a reference point (same as scripts/warm_start_elastic.py's Step A), then
builds the REAL reward model (build_model_m4, hard E1/E2 -- not the elastic/
slack model) with a local-branching trust-region constraint
(src.model.local_branching.add_local_branching) restricting at most k time
instances to differ from the reference. The reference point is known
infeasible for hard E1/E2 (1879 violations, see decisions.md) -- it is used
as a NEIGHBORHOOD anchor, not a forced warm start, so HiGHS is free to move
up to k instances to find its own feasible correction.

Kullanım: .venv/bin/python3 -u scripts/run_local_branching.py --k 200
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi
from src.data.ranking import compute_baseline_best_journey, derive_b_od, is_ranking_monotonic
from src.output.writer import write_output
from src.solve.subprocess_watchdog import solve_step_with_watchdog
from src.validate.independent_validator import finalize_reported_objective, recompute_objective, validate_output

from src.config.paths import FULL_OD, FULL_YV, FULL_CR, FULL_FP
CORE_WORKER = Path(__file__).resolve().parent / "_core_feasibility_step_worker.py"
LOCAL_BRANCH_WORKER = Path(__file__).resolve().parent / "_local_branching_step_worker.py"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=200,
                         help="max number of t_arr/t_dep instances allowed to differ from the reference point")
    parser.add_argument("--core-time-limit-sec", type=float, default=600.0)
    parser.add_argument("--time-limit-sec", type=float, default=600.0)
    parser.add_argument("--watchdog-margin-sec", type=float, default=120.0)
    parser.add_argument("--mip-gap", type=float, default=0.05)
    parser.add_argument("--mip-heuristic-effort", type=float, default=0.3)
    parser.add_argument("--output", default="runs/local_branching_output.json")
    args = parser.parse_args(argv)

    t0 = time.time()
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]

    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FULL_YV, strict=False)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    ranking_table = load_change_ranking(FULL_CR)
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
    journey_constants, k_od_sources, dropped_markets = {}, {}, set()
    for c in candidates:
        market = (c.o, c.d)
        if market in journey_constants or market in dropped_markets:
            continue
        try:
            journey_constants[market] = provider.get_journey_constant(c.o, c.d)
            k_od_sources[market] = "direct"
        except KeyError:
            try:
                journey_constants[market] = provider.get_journey_constant_estimate(c.o, c.d)
                k_od_sources[market] = "estimated"
            except KeyError:
                dropped_markets.add(market)
    candidates = [c for c in candidates if (c.o, c.d) not in dropped_markets]

    rival_data, b_od_data = {}, {}
    for c in candidates:
        market = (c.o, c.d, c.gun)
        if market not in rival_data:
            rival_data[market] = derive_rival_best_times(od_table, c.o, c.d, c.gun)
        if (c.o, c.d) not in b_od_data:
            baseline_j = compute_baseline_best_journey(od_table, c.o, c.d, c.gun, L=L, U=U)
            b_od_data[(c.o, c.d)] = (
                derive_b_od(od_table, c.o, c.d, c.gun, baseline_j) if baseline_j is not None else 0
            )

    monotonic = is_ranking_monotonic(ranking_table)
    rotation_stations = set(row["dest"] for row in pairs_df.to_dict("records") if row["orig"] == "IST")
    r_o_lookup = {}
    for station in rotation_stations:
        try:
            r_o_lookup[station] = provider.get_rotation_constant(station)
        except KeyError:
            continue

    print(f"[run_local_branching] preprocessing done in {time.time()-t0:.1f}s, "
          f"n_candidates={len(candidates)}, k={args.k}", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    highs_log_dir = Path("runs") / f"local_branching_run_{stamp}_highs_logs"
    highs_log_dir.mkdir(parents=True, exist_ok=True)

    # --- Step A: re-solve A+G+F to get the reference point ---
    core_build_kwargs = dict(
        candidates=candidates, pairs_df=pairs_df, r_o_lookup=r_o_lookup,
        tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor, tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"],
    )
    core_solve_kwargs = dict(solver="highs", time_limit_sec=args.core_time_limit_sec, seed=config["seed"],
                              mip_gap=0.08, mip_heuristic_effort=0.3)
    print("[run_local_branching] re-solving A+G+F for the reference point...", flush=True)
    t1 = time.time()
    core_result, _ = solve_step_with_watchdog(
        core_build_kwargs, core_solve_kwargs, time_limit_sec=args.core_time_limit_sec,
        watchdog_margin_sec=120.0, step_name="core_feasibility_for_local_branching", worker_script=CORE_WORKER,
    )
    print(f"[run_local_branching] A+G+F solve finished in {time.time()-t1:.1f}s "
          f"status={core_result.status}", flush=True)
    if core_result.status not in ("optimal", "time_limit") or not core_result.arr_times:
        print("[run_local_branching] ABORT -- no usable A+G+F reference point", flush=True)
        return

    # --- Step B: watchdog-protected solve of build_model_m4 + local branching ---
    model_kwargs = dict(
        candidates=candidates, rho=rho, journey_constants=journey_constants,
        rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
        pairs_df=pairs_df, r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U, monotonic=monotonic,
    )
    local_branch_kwargs = dict(
        reference_arr=core_result.arr_times, reference_dep=core_result.dep_times, k=args.k,
    )
    solve_kwargs = dict(
        solver="highs", time_limit_sec=args.time_limit_sec, seed=config["seed"],
        mip_gap=args.mip_gap, mip_heuristic_effort=args.mip_heuristic_effort,
        log_file=highs_log_dir / "local_branching.highs.log",
    )
    print(f"[run_local_branching] solving build_model_m4+local_branching(k={args.k}) "
          f"(time_limit={args.time_limit_sec}s)...", flush=True)
    t2 = time.time()
    result, build_time_sec = solve_step_with_watchdog(
        {"model_kwargs": model_kwargs, "local_branch_kwargs": local_branch_kwargs},
        solve_kwargs, time_limit_sec=args.time_limit_sec,
        watchdog_margin_sec=args.watchdog_margin_sec, step_name="local_branching",
        worker_script=LOCAL_BRANCH_WORKER,
    )
    solve_wall_sec = time.time() - t2
    print(f"[run_local_branching] finished in {solve_wall_sec:.1f}s status={result.status} "
          f"objective={result.objective_value}", flush=True)

    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "k": args.k,
        "n_candidates": len(candidates), "build_time_sec": build_time_sec,
        "status": result.status, "objective_value": result.objective_value,
        "solve_wall_sec": round(solve_wall_sec, 1), "model_stats": result.model_stats,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if result.status in ("optimal", "time_limit") and result.objective_value is not None and result.selected:
        write_output(output_path, result, k_od_sources=k_od_sources)
        recompute_total, recompute_breakdown = recompute_objective(
            output_path, FULL_OD, FULL_YV, FULL_CR, L=L, U=U, strict=False,
            breakdown_path=output_path.with_suffix(".objective_breakdown.json"),
        )
        reconciliation_ok, reconciliation_msg = finalize_reported_objective(
            output_path, recompute_total, result.status, result.objective_value,
        )
        validation = validate_output(
            output_path, FULL_OD, L=L, U=U,
            adjustable_window_min=config["adjustable_window_min"], adjustable_set=config["adjustable_set"],
            flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
            alpha=config["alpha"], gamma=config["gamma"],
            bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
            capacity_arrival=config["capacity_arrival"],
        )
        n_offered = sum(1 for v in result.selected.values() if v == 1)
        log["n_offered"] = n_offered
        log["recompute_objective_value"] = recompute_total
        log["reconciliation_ok"] = reconciliation_ok
        log["validation_is_valid"] = validation.is_valid and reconciliation_ok
        log["n_violations"] = len(validation.violations)
        log["violations_by_family"] = {}
        for v in validation.violations:
            fam = v.split(" ", 1)[0]
            log["violations_by_family"][fam] = log["violations_by_family"].get(fam, 0) + 1
        if not reconciliation_ok:
            log["reconciliation_message"] = reconciliation_msg
        print(f"[run_local_branching] n_offered={n_offered} validation_is_valid={log['validation_is_valid']} "
              f"n_violations={log['n_violations']} reward_objective={recompute_total}", flush=True)
        print(f"[run_local_branching] violations_by_family={log['violations_by_family']}", flush=True)
    else:
        log["validation_is_valid"] = None
        log["validation_violations"] = [
            f"no accepted solution (status={result.status}) -- see solve log"
        ]

    log_path = Path("runs") / f"local_branching_{stamp}.log.json"
    log_path.write_text(json.dumps(log, indent=2, sort_keys=True, default=str))
    print(json.dumps(log, indent=2, sort_keys=True, default=str), flush=True)
    print(f"\nFull log: {log_path}", flush=True)
    return log


if __name__ == "__main__":
    main()

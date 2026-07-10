#!/usr/bin/env python3
"""M5c §5 Phase 1 (docs/decisions.md 2026-07-10): full-data min-deviation
feasibility attempt. Builds the FULL model (build_model_m4, all 18118
candidates, all A-G constraints -- same as step1) but replaces the reward
objective with min Σ|t-t_baseline| (src.model.deviation_objective). Watchdog-
protected (same mechanism as scripts/run_full_data.py). Goal: find ANY
feasible full-data schedule (the reward objective's LP looseness/symmetry
may be the reason step1 never found one) + report the standalone "minimum
cost to legalize baseline" metric.

Kullanım: .venv/bin/python3 -u scripts/run_min_deviation.py
"""
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

FULL_OD = "data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx"
FULL_YV = "data_raw/Yolcu Verisi_masked.xlsx"
FULL_CR = "data_raw/change_ranking_input.xlsx"
FULL_FP = "data_raw/Flight Pairs.xlsx"
DEVIATION_WORKER = Path(__file__).resolve().parent / "_deviation_step_worker.py"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="runs/min_deviation_output.json")
    parser.add_argument("--time-limit-sec", type=float, default=600.0)
    parser.add_argument("--watchdog-margin-sec", type=float, default=120.0)
    parser.add_argument("--mip-heuristic-effort", type=float, default=0.3)
    parser.add_argument("--mip-gap", type=float, default=0.08)
    args = parser.parse_args()

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
            b_od_data[(c.o, c.d)] = derive_b_od(od_table, c.o, c.d, c.gun, baseline_j) if baseline_j is not None else 0

    monotonic = is_ranking_monotonic(ranking_table)
    rotation_stations = set(row["dest"] for row in pairs_df.to_dict("records") if row["orig"] == "IST")
    r_o_lookup = {}
    for station in rotation_stations:
        try:
            r_o_lookup[station] = provider.get_rotation_constant(station)
        except KeyError:
            continue

    preprocessing_sec = time.time() - t0
    print(f"[min_deviation] preprocessing done in {preprocessing_sec:.1f}s, "
          f"n_candidates={len(candidates)}", flush=True)

    build_kwargs = dict(
        candidates=candidates, rho=rho, journey_constants=journey_constants,
        rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
        pairs_df=pairs_df, r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U, monotonic=monotonic,
    )
    stamp_pre = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    highs_log_dir = Path("runs") / f"min_deviation_run_{stamp_pre}_highs_logs"
    highs_log_dir.mkdir(parents=True, exist_ok=True)
    highs_log_file = highs_log_dir / "min_deviation.highs.log"

    solve_kwargs = dict(
        solver="highs", time_limit_sec=args.time_limit_sec, seed=config["seed"],
        mip_gap=args.mip_gap, mip_heuristic_effort=args.mip_heuristic_effort,
        log_file=highs_log_file,
    )

    print(f"[min_deviation] build+solve starting (time_limit={args.time_limit_sec}s, "
          f"watchdog_margin={args.watchdog_margin_sec}s, mip_heuristic_effort={args.mip_heuristic_effort}, "
          f"highs_log={highs_log_file})", flush=True)
    t1 = time.time()
    result, build_time_sec = solve_step_with_watchdog(
        build_kwargs, solve_kwargs, time_limit_sec=args.time_limit_sec,
        watchdog_margin_sec=args.watchdog_margin_sec, step_name="min_deviation",
        worker_script=DEVIATION_WORKER,
    )
    solve_wall_sec = time.time() - t1
    print(f"[min_deviation] finished in {solve_wall_sec:.1f}s status={result.status} "
          f"min_total_deviation_min={result.objective_value}", flush=True)

    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "n_candidates": len(candidates), "preprocessing_sec": round(preprocessing_sec, 1),
        "build_time_sec": build_time_sec, "solve_wall_sec": round(solve_wall_sec, 1),
        "status": result.status, "min_total_deviation_minutes": result.objective_value,
        "config": {**config, "phase1_time_limit_sec": args.time_limit_sec,
                   "phase1_mip_gap": args.mip_gap, "phase1_mip_heuristic_effort": args.mip_heuristic_effort},
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if result.status in ("optimal", "time_limit") and result.objective_value is not None:
        write_output(output_path, result, k_od_sources=k_od_sources)
        recompute_total, _ = recompute_objective(
            output_path, FULL_OD, FULL_YV, FULL_CR, L=L, U=U,
            breakdown_path=output_path.with_suffix(".objective_breakdown.json"),
        )
        # NOTE: this recompute is the REWARD objective's truth (connection +
        # ranking reward), NOT the min-deviation objective's own value --
        # both numbers are meaningful together: min_total_deviation_minutes
        # is Phase 1's own "cost to legalize baseline" metric, while
        # recompute_total is what that SAME feasible schedule would be
        # worth under the real scoring objective (useful context for
        # Phase 2's warm start, and for the closing report).
        log["reward_objective_at_this_schedule"] = recompute_total

        validation = validate_output(
            output_path, FULL_OD, L=L, U=U,
            adjustable_window_min=config["adjustable_window_min"],
            adjustable_set=config["adjustable_set"],
            flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
            alpha=config["alpha"], gamma=config["gamma"],
            bucket_size_min=config["bucket_size_min"],
            capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"],
        )
        log["validation_is_valid"] = validation.is_valid
        log["validation_violations"] = validation.violations
    else:
        log["validation_is_valid"] = None
        log["validation_violations"] = [f"no incumbent found (status={result.status})"]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = Path("runs") / f"min_deviation_run_{stamp}.log.json"
    log_path.write_text(json.dumps(log, indent=2, sort_keys=True, default=str))
    print(json.dumps(log, indent=2, sort_keys=True, default=str), flush=True)
    print(f"\nFull log: {log_path}", flush=True)
    return log


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""M5d step 2 (docs/decisions.md 2026-07-10, user protocol): warm-start
build_elastic_feasibility_model on full data using the point from
scripts/derive_warm_start.py (A+G+F-optimal times + B's deterministic
reification) -- proven feasible for THIS model (E1/E2 slack absorbs its
1882 E1 violations unconditionally). Derivation logic lives in
src/model/warm_start.py (shared with tests/solve/test_warm_start.py, which
already confirms the transfer works on the fixture). Watchdog-protected
(same mechanism as every other M5 full-data runner) since a warm-started
solve is not guaranteed to be fast at full scale.

Kullanım: .venv/bin/python3 -u scripts/warm_start_elastic.py
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
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.solve.subprocess_watchdog import solve_step_with_watchdog
from src.output.writer import write_output
from src.validate.independent_validator import recompute_objective, validate_output

FULL_OD = "data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx"
FULL_YV = "data_raw/Yolcu Verisi_masked.xlsx"
FULL_CR = "data_raw/change_ranking_input.xlsx"
FULL_FP = "data_raw/Flight Pairs.xlsx"
CORE_WORKER = Path(__file__).resolve().parent / "_core_feasibility_step_worker.py"
WARM_START_WORKER = Path(__file__).resolve().parent / "_warm_start_elastic_step_worker.py"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--time-limit-sec", type=float, default=600.0)
    parser.add_argument("--watchdog-margin-sec", type=float, default=120.0)
    parser.add_argument("--mip-heuristic-effort", type=float, default=0.3)
    parser.add_argument("--mip-gap", type=float, default=0.08)
    parser.add_argument("--max-improving-sols", type=int, default=None,
                         help="M5d (docs/decisions.md 2026-07-10): HiGHS's own time_limit does not "
                              "reliably interrupt root-node cutting -- when the goal is RECOVERING a "
                              "warm-started incumbent (not proving optimality), stopping after N "
                              "improving solutions (mip_max_improving_sols) lets HiGHS terminate itself "
                              "cleanly instead of relying on the external watchdog's SIGKILL.")
    args = parser.parse_args()

    t0 = time.time()
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]
    alpha, gamma, bucket_size_min = config["alpha"], config["gamma"], config["bucket_size_min"]

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

    print(f"[warm_start_elastic] preprocessing done in {time.time()-t0:.1f}s, "
          f"n_candidates={len(candidates)}", flush=True)

    # --- Step A: re-solve A+G+F to get the base point (§1, ~205s) ---
    core_build_kwargs = dict(
        candidates=candidates, pairs_df=pairs_df, r_o_lookup=r_o_lookup,
        tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor, tk_rows=tk,
        bucket_size_min=bucket_size_min, capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"],
    )
    core_solve_kwargs = dict(solver="highs", time_limit_sec=600.0, seed=config["seed"],
                              mip_gap=0.08, mip_heuristic_effort=0.3)
    print("[warm_start_elastic] re-solving A+G+F for the base point...", flush=True)
    t1 = time.time()
    core_result, _ = solve_step_with_watchdog(
        core_build_kwargs, core_solve_kwargs, time_limit_sec=600.0, watchdog_margin_sec=120.0,
        step_name="core_feasibility_for_warm_start", worker_script=CORE_WORKER,
    )
    print(f"[warm_start_elastic] A+G+F solve finished in {time.time()-t1:.1f}s "
          f"status={core_result.status}", flush=True)
    if core_result.status not in ("optimal", "time_limit") or not core_result.arr_times:
        print("[warm_start_elastic] ABORT -- no usable A+G+F point", flush=True)
        return

    # --- Step B: watchdog-protected elastic solve, warm-started from the point ---
    elastic_build_kwargs = dict(
        candidates=candidates, journey_constants=journey_constants, pairs_df=pairs_df,
        r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor,
        alpha=alpha, gamma=gamma, tk_rows=tk, bucket_size_min=bucket_size_min,
        capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"],
        L=L, U=U,
    )
    warm_start_kwargs = dict(
        candidates=candidates, journey_constants=journey_constants,
        arr_times=core_result.arr_times, dep_times=core_result.dep_times,
        L=L, U=U, alpha=alpha, gamma=gamma, bucket_size_min=bucket_size_min, epoch_anchor=anchor,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    highs_log_dir = Path("runs") / f"warm_start_elastic_run_{stamp}_highs_logs"
    highs_log_dir.mkdir(parents=True, exist_ok=True)
    highs_log_file = highs_log_dir / "warm_start_elastic.highs.log"
    elastic_solve_kwargs = dict(
        solver="highs", time_limit_sec=args.time_limit_sec, seed=config["seed"],
        mip_gap=args.mip_gap, mip_heuristic_effort=args.mip_heuristic_effort,
        log_file=highs_log_file,
    )
    if args.max_improving_sols is not None:
        elastic_solve_kwargs["extra_highs_options"] = {"mip_max_improving_sols": args.max_improving_sols}

    print(f"[warm_start_elastic] solving WITH warmstart=True (time_limit={args.time_limit_sec}s, "
          f"highs_log={highs_log_file})...", flush=True)
    t2 = time.time()
    result, build_time_sec = solve_step_with_watchdog(
        {"model_kwargs": elastic_build_kwargs, "warm_start_kwargs": warm_start_kwargs},
        elastic_solve_kwargs, time_limit_sec=args.time_limit_sec,
        watchdog_margin_sec=args.watchdog_margin_sec, step_name="warm_start_elastic",
        worker_script=WARM_START_WORKER,
    )
    solve_wall_sec = time.time() - t2
    print(f"[warm_start_elastic] finished in {solve_wall_sec:.1f}s status={result.status} "
          f"objective={result.objective_value}", flush=True)

    log_text = highs_log_file.read_text() if highs_log_file.exists() else ""
    warm_start_confirmed = "MIP start solution is feasible" in log_text
    print(f"[warm_start_elastic] warm_start_confirmed_in_log={warm_start_confirmed}", flush=True)

    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "n_candidates": len(candidates), "build_time_sec": build_time_sec,
        "status": result.status, "objective_value": result.objective_value,
        "solve_wall_sec": round(solve_wall_sec, 1),
        "warm_start_confirmed_in_log": warm_start_confirmed,
        "model_stats": result.model_stats,
    }

    # M5d step 4 (docs/decisions.md 2026-07-10, user protocol): whatever
    # incumbent we get, close the loop -- write it out, validate against
    # the FULL strict A-G validator (this is the elastic model's own
    # solution, so E1/E2 violations up to whatever slack was accepted are
    # EXPECTED, not a bug -- the interesting number is the reward value and
    # the violation breakdown for the closing report / Phase-2 seed).
    if result.status in ("optimal", "time_limit") and result.objective_value is not None and result.selected:
        output_path = Path("runs/warm_start_elastic_output.json")
        write_output(output_path, result)
        validation = validate_output(
            output_path, FULL_OD, L=L, U=U,
            adjustable_window_min=config["adjustable_window_min"], adjustable_set=config["adjustable_set"],
            flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
            alpha=config["alpha"], gamma=config["gamma"],
            bucket_size_min=bucket_size_min, capacity_departure=config["capacity_departure"],
            capacity_arrival=config["capacity_arrival"],
        )
        recompute_total, _ = recompute_objective(
            output_path, FULL_OD, FULL_YV, FULL_CR, L=L, U=U, strict=False,
            breakdown_path=output_path.with_suffix(".objective_breakdown.json"),
        )
        n_offered = sum(1 for v in result.selected.values() if v == 1)
        log["n_offered"] = n_offered
        log["validation_is_valid"] = validation.is_valid
        log["n_violations"] = len(validation.violations)
        log["violations_by_family"] = {}
        for v in validation.violations:
            fam = v.split(" ", 1)[0]
            log["violations_by_family"][fam] = log["violations_by_family"].get(fam, 0) + 1
        log["reward_objective_value"] = recompute_total
        print(f"[warm_start_elastic] n_offered={n_offered} validation_is_valid={validation.is_valid} "
              f"n_violations={len(validation.violations)} reward_objective={recompute_total}", flush=True)
        print(f"[warm_start_elastic] violations_by_family={log['violations_by_family']}", flush=True)
    log_path = Path("runs") / f"warm_start_elastic_{stamp}.log.json"
    log_path.write_text(json.dumps(log, indent=2, sort_keys=True, default=str))
    print(json.dumps(log, indent=2, sort_keys=True, default=str), flush=True)
    print(f"\nFull log: {log_path}\nHiGHS log: {highs_log_file}", flush=True)
    return log


if __name__ == "__main__":
    main()

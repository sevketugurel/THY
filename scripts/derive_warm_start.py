#!/usr/bin/env python3
"""M5d §2 continuation, step 1 (docs/decisions.md 2026-07-10, user protocol):
derive a feasible full-data point PURELY from §1's already-solved A+G+F
times, via B's deterministic reification (gap=t_dep-t_arr, x=1 iff
gap in [L,U] -- no new solve, no guessing). Validate it through the SAME
independent validator used everywhere else (zero violations required
before anything is trusted), then recompute its reward value -- if it
passes, THIS IS THE FIRST INDEPENDENTLY-VERIFIED FULL-DATA OBJECTIVE VALUE
of the whole M5 investigation, regardless of whether the warm-start
transfer (next step) works.

Kullanım: .venv/bin/python3 -u scripts/derive_warm_start.py
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
from src.output.writer import write_output
from src.solve.runner import SolveResult
from src.solve.subprocess_watchdog import solve_step_with_watchdog
from src.validate.independent_validator import recompute_objective, validate_output

FULL_OD = "data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx"
FULL_YV = "data_raw/Yolcu Verisi_masked.xlsx"
FULL_CR = "data_raw/change_ranking_input.xlsx"
FULL_FP = "data_raw/Flight Pairs.xlsx"
CORE_WORKER = Path(__file__).resolve().parent / "_core_feasibility_step_worker.py"


def main():
    t0 = time.time()
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]

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
    rotation_stations = set(row["dest"] for row in pairs_df.to_dict("records") if row["orig"] == "IST")
    r_o_lookup = {}
    for station in rotation_stations:
        try:
            r_o_lookup[station] = provider.get_rotation_constant(station)
        except KeyError:
            continue

    preprocessing_sec = time.time() - t0
    print(f"[derive_warm_start] preprocessing done in {preprocessing_sec:.1f}s, "
          f"n_candidates={len(candidates)}", flush=True)

    build_kwargs = dict(
        candidates=candidates, pairs_df=pairs_df, r_o_lookup=r_o_lookup,
        tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor, tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"],
    )
    solve_kwargs = dict(solver="highs", time_limit_sec=600.0, seed=config["seed"], mip_gap=0.08,
                         mip_heuristic_effort=0.3)

    print("[derive_warm_start] re-solving A+G+F (§1, ~205s expected)...", flush=True)
    t1 = time.time()
    core_result, _ = solve_step_with_watchdog(
        build_kwargs, solve_kwargs, time_limit_sec=600.0, watchdog_margin_sec=120.0,
        step_name="core_feasibility_for_warm_start", worker_script=CORE_WORKER,
    )
    print(f"[derive_warm_start] A+G+F solve finished in {time.time()-t1:.1f}s "
          f"status={core_result.status}", flush=True)

    if core_result.status not in ("optimal", "time_limit") or not core_result.arr_times:
        print("[derive_warm_start] ABORT -- A+G+F did not produce usable times "
              f"(status={core_result.status})", flush=True)
        return

    arr_times, dep_times = core_result.arr_times, core_result.dep_times

    # B's deterministic reification: gap = t_dep[r2] - t_arr[r1], x=1 iff
    # gap in [L,U] -- no choice involved, purely computed from the A+G+F point.
    selected, gap_values = {}, {}
    for c in candidates:
        gap = dep_times[c.r2_id] - arr_times[c.r1_id]
        gap_values[c] = gap
        selected[c] = 1 if L <= gap <= U else 0
    n_offered = sum(selected.values())
    print(f"[derive_warm_start] derived x/gap for {len(candidates)} candidates, "
          f"{n_offered} offered ({100*n_offered/len(candidates):.1f}%)", flush=True)

    result = SolveResult(
        status="optimal", objective_value=0.0, selected=selected, solve_time_sec=0.0,
        gap_values=gap_values, arr_times=arr_times, dep_times=dep_times,
    )
    output_path = Path("runs/warm_start_point.json")
    write_output(output_path, result)

    print("[derive_warm_start] validating derived point (full A/E1/E2/F/G/rotation/x_dev)...", flush=True)
    validation = validate_output(
        output_path, FULL_OD, L=L, U=U,
        adjustable_window_min=config["adjustable_window_min"], adjustable_set=config["adjustable_set"],
        flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
        alpha=config["alpha"], gamma=config["gamma"],
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"],
    )
    print(f"[derive_warm_start] validation.is_valid={validation.is_valid} "
          f"violations={len(validation.violations)}", flush=True)

    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "n_candidates": len(candidates), "n_offered": n_offered,
        "validation_is_valid": validation.is_valid,
        "validation_violations": validation.violations[:100],
        "n_violations": len(validation.violations),
    }

    if validation.is_valid:
        recompute_total, breakdown_path = recompute_objective(
            output_path, FULL_OD, FULL_YV, FULL_CR, L=L, U=U, strict=False,
            breakdown_path=output_path.with_suffix(".objective_breakdown.json"),
        )
        log["reward_objective_value"] = recompute_total
        print(f"[derive_warm_start] SUCCESS -- FIRST VERIFIED FULL-DATA VALUE: "
              f"reward_objective={recompute_total}", flush=True)
    else:
        print("[derive_warm_start] STOPPED -- derived point has violations, dumping:", flush=True)
        for v in validation.violations[:60]:
            print(f"  VIOLATION: {v}", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = Path("runs") / f"derive_warm_start_{stamp}.log.json"
    log_path.write_text(json.dumps(log, indent=2, sort_keys=True, default=str))
    print(f"\nFull log: {log_path}\nWarm-start point: {output_path}", flush=True)
    return log


if __name__ == "__main__":
    main()

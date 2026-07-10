#!/usr/bin/env python3
"""M5d §1 (docs/decisions.md 2026-07-10): full-data run of
build_core_feasibility_model (reification-free floor -- only t_arr/t_dep +
A/G/F, no B/C/D/E1/E2 at all). Goal: isolate whether A+G+F ALONE (the
absolute minimum physically-grounded constraint set) is already the
root-node bottleneck, independent of any connection-selection logic. Uses
the min-deviation objective (the only sensible objective here -- there's no
reward without B/x). Watchdog-protected, same mechanism as the other M5
full-data runners.

Kullanım: .venv/bin/python3 -u scripts/run_core_feasibility.py
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

FULL_OD = "data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx"
FULL_YV = "data_raw/Yolcu Verisi_masked.xlsx"
FULL_FP = "data_raw/Flight Pairs.xlsx"
CORE_WORKER = Path(__file__).resolve().parent / "_core_feasibility_step_worker.py"


def main():
    import argparse
    parser = argparse.ArgumentParser()
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
    print(f"[core_feasibility] preprocessing done in {preprocessing_sec:.1f}s, "
          f"n_candidates={len(candidates)}", flush=True)

    build_kwargs = dict(
        candidates=candidates, pairs_df=pairs_df, r_o_lookup=r_o_lookup,
        tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor, tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"],
    )
    stamp_pre = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    highs_log_dir = Path("runs") / f"core_feasibility_run_{stamp_pre}_highs_logs"
    highs_log_dir.mkdir(parents=True, exist_ok=True)
    highs_log_file = highs_log_dir / "core_feasibility.highs.log"

    solve_kwargs = dict(
        solver="highs", time_limit_sec=args.time_limit_sec, seed=config["seed"],
        mip_gap=args.mip_gap, mip_heuristic_effort=args.mip_heuristic_effort,
        log_file=highs_log_file,
    )

    print(f"[core_feasibility] build+solve starting (time_limit={args.time_limit_sec}s, "
          f"watchdog_margin={args.watchdog_margin_sec}s, highs_log={highs_log_file})", flush=True)
    t1 = time.time()
    result, build_time_sec = solve_step_with_watchdog(
        build_kwargs, solve_kwargs, time_limit_sec=args.time_limit_sec,
        watchdog_margin_sec=args.watchdog_margin_sec, step_name="core_feasibility",
        worker_script=CORE_WORKER,
    )
    solve_wall_sec = time.time() - t1
    print(f"[core_feasibility] finished in {solve_wall_sec:.1f}s status={result.status} "
          f"min_total_deviation_min={result.objective_value}", flush=True)

    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "n_candidates": len(candidates), "preprocessing_sec": round(preprocessing_sec, 1),
        "build_time_sec": build_time_sec, "solve_wall_sec": round(solve_wall_sec, 1),
        "status": result.status, "min_total_deviation_minutes": result.objective_value,
        "model_stats": result.model_stats,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = Path("runs") / f"core_feasibility_run_{stamp}.log.json"
    log_path.write_text(json.dumps(log, indent=2, sort_keys=True, default=str))
    print(json.dumps(log, indent=2, sort_keys=True, default=str), flush=True)
    print(f"\nFull log: {log_path}", flush=True)
    return log


if __name__ == "__main__":
    main()

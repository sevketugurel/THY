#!/usr/bin/env python3
"""M5: full-data solve run via the 3-step ladder. NOT a pytest test (the
60-second rule is for tests only) -- a separate command with a timestamped
log, per the M5 protocol.

Kullanım: .venv/bin/python3 scripts/run_full_data.py [--output PATH]
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
from src.solve.ladder import solve_with_ladder
from src.validate.independent_validator import validate_output

FULL_OD = "data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx"
FULL_YV = "data_raw/Yolcu Verisi_masked.xlsx"
FULL_CR = "data_raw/change_ranking_input.xlsx"
FULL_FP = "data_raw/Flight Pairs.xlsx"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="src/config/standard.yaml")
    parser.add_argument("--output", default="runs/full_data_output.json")
    parser.add_argument("--step1-time-limit", type=float, default=None,
                         help="override config's time_limit_sec for step1 (exploratory runs)")
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text())
    if args.step1_time_limit is not None:
        config["time_limit_sec"] = args.step1_time_limit
    L, U = config["L"], config["U"]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = Path("runs") / f"full_data_run_{stamp}.log.json"
    log = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "config": config}

    t0 = time.time()
    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    # VARSAYIM-2 (ASSUMPTIONS.md): drop the 3 known missing-dest rows, logged.
    yolcu = load_yolcu_verisi(FULL_YV, strict=False)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    ranking_table = load_change_ranking(FULL_CR)
    pairs_df = load_flight_pairs(FULL_FP)
    log["data_load_time_sec"] = round(time.time() - t0, 1)

    anchor = compute_epoch_anchor(tk)
    t1 = time.time()
    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun,
            adjustable_window_min=config["adjustable_window_min"],
            adjustable_set=config["adjustable_set"], epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]
    log["candidate_gen_time_sec"] = round(time.time() - t1, 1)
    log["candidate_count"] = len(candidates)

    provider = BlockTimeProvider(tk, L=L, U=U)
    # VARSAYIM-8 (ASSUMPTIONS.md): direct median K_od -> LS-estimate fallback
    # -> drop market if neither works.
    journey_constants = {}
    dropped_markets = set()
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
    log["dropped_markets_no_k_od"] = sorted(f"{o}-{d}" for o, d in dropped_markets)
    candidates = [c for c in candidates if (c.o, c.d) not in dropped_markets]
    log["candidate_count_after_k_od_drop"] = len(candidates)

    t2 = time.time()
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
    log["rival_b_od_time_sec"] = round(time.time() - t2, 1)

    monotonic = is_ranking_monotonic(ranking_table)
    rotation_stations = set(row["dest"] for row in pairs_df.to_dict("records") if row["orig"] == "IST")
    r_o_lookup = {}
    for station in rotation_stations:
        try:
            r_o_lookup[station] = provider.get_rotation_constant(station)
        except KeyError:
            continue
    log["monotonic"] = monotonic
    log["r_o_lookup_size"] = len(r_o_lookup)

    log["preprocessing_total_time_sec"] = round(time.time() - t0, 1)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, indent=2, sort_keys=True, default=str))
    print(f"Preprocessing done in {log['preprocessing_total_time_sec']}s. Starting solve ladder...")
    print(f"Interim log: {log_path}")

    t3 = time.time()
    model, result, ladder_log = solve_with_ladder(
        candidates_full=candidates, rho=rho, journey_constants=journey_constants,
        rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
        pairs_df=pairs_df, r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U, monotonic=monotonic,
        step1_time_limit_sec=config["time_limit_sec"], seed=config["seed"], solver=config["solver"],
    )
    log["ladder_log"] = ladder_log
    log["ladder_total_time_sec"] = round(time.time() - t3, 1)
    log["final_status"] = result.status
    log["final_objective_value"] = result.objective_value

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if result.status in ("optimal", "time_limit") and result.objective_value is not None:
        write_output(output_path, result)
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
        log["validation_violations"] = ["STEP3: no accepted solution at any ladder step -- see ladder_log"]

    log_path.write_text(json.dumps(log, indent=2, sort_keys=True, default=str))
    print(json.dumps({k: v for k, v in log.items() if k not in ("config",)}, indent=2, sort_keys=True, default=str))
    print(f"\nFull log: {log_path}")
    return log


if __name__ == "__main__":
    main()

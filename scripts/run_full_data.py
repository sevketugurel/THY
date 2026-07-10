#!/usr/bin/env python3
"""M5: full-data solve run via the 3-step ladder. NOT a pytest test (the
60-second rule is for tests only) -- a separate command with a timestamped
log, per the M5 protocol.

Kullanım: .venv/bin/python3 -u scripts/run_full_data.py [--output PATH]
(the `-u` flag matters -- without it, prints below can sit in a buffer for
minutes on a background/redirected run, making a live solve look hung; every
print in this file and in src/solve/ladder.py also passes flush=True as a
second line of defense against that exact failure mode, observed firsthand
in M5's first 4 full-data attempts today.)
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
from src.validate.independent_validator import finalize_reported_objective, recompute_objective, validate_output

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
    parser.add_argument("--step2-time-limit", type=float, default=None,
                         help="override the ladder's default step2 per-K time limit (300s)")
    parser.add_argument("--mip-gap", type=float, default=None,
                         help="HiGHS mip_rel_gap for all ladder steps; exploratory runs: 0.05-0.10, "
                              "omit for production (HiGHS default ~1e-4)")
    parser.add_argument("--budget-sec", type=float, default=3600.0,
                         help="total wall-clock budget for preprocessing+ladder; a ladder step is "
                              "SKIPPED (not started) once this is exceeded, and a diagnostic "
                              "summary is written instead of hanging silently")
    parser.add_argument("--mip-heuristic-effort", type=float, default=None,
                         help="HiGHS mip_heuristic_effort (0-1, default ~0.05); raise for "
                              "incumbent-priority exploratory runs (0.2-0.5) -- see "
                              "docs/decisions.md 2026-07-09 (root-node cuts alone found zero "
                              "incumbent after 1280s+ on the full-data model)")
    parser.add_argument("--no-subprocess-watchdog", action="store_true",
                         help="disable the external SIGTERM/SIGKILL watchdog and rely on "
                              "appsi_highs's own (unreliable at this scale, see docs/decisions.md) "
                              "in-process time_limit -- default is watchdog ON")
    parser.add_argument("--watchdog-margin-sec", type=float, default=60.0,
                         help="grace period beyond time_limit_sec before the external watchdog "
                              "sends SIGTERM to a step's subprocess")
    parser.add_argument("--enable-step2-ladder", action="store_true",
                         help="M5c (docs/decisions.md 2026-07-10): step2's K-subset ladder is "
                              "DEPRECATED by default -- apply_adjustable_subset freezes by MARKET, "
                              "but candidate generation's full inbound x outbound cross-product "
                              "means a physical leg touches 4.4 markets on average (max 183), so "
                              "leg-sharing propagates 'adjustable' status transitively until ~0%% "
                              "of candidates are ever fully frozen even at K=50 -- the mechanism "
                              "does not meaningfully shrink the model's true degrees of freedom. "
                              "Kept for reference/comparison only; the leg-level freezing idea now "
                              "lives in the proximity-search incumbent engine instead. Default: "
                              "step1 only, straight to step3 diagnosis if it fails.")
    args = parser.parse_args(argv)

    script_t0 = time.time()
    deadline_ts = script_t0 + args.budget_sec

    config = yaml.safe_load(Path(args.config).read_text())
    if args.step1_time_limit is not None:
        config["time_limit_sec"] = args.step1_time_limit
    L, U = config["L"], config["U"]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = Path("runs") / f"full_data_run_{stamp}.log.json"
    highs_log_dir = Path("runs") / f"full_data_run_{stamp}_highs_logs"
    highs_log_dir.mkdir(parents=True, exist_ok=True)
    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "config": config,
        "budget_sec": args.budget_sec, "mip_gap": args.mip_gap,
        "mip_heuristic_effort": args.mip_heuristic_effort,
        "subprocess_watchdog": not args.no_subprocess_watchdog,
        "watchdog_margin_sec": args.watchdog_margin_sec,
    }
    print(f"[run_full_data] budget={args.budget_sec}s mip_gap={args.mip_gap} "
          f"mip_heuristic_effort={args.mip_heuristic_effort} "
          f"subprocess_watchdog={not args.no_subprocess_watchdog} "
          f"highs_logs={highs_log_dir}", flush=True)

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
    k_od_sources = {}
    dropped_markets = set()
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
    log["dropped_markets_no_k_od"] = sorted(f"{o}-{d}" for o, d in dropped_markets)
    candidates = [c for c in candidates if (c.o, c.d) not in dropped_markets]
    log["candidate_count_after_k_od_drop"] = len(candidates)
    log["k_od_source_counts"] = {
        "direct": sum(1 for s in k_od_sources.values() if s == "direct"),
        "estimated": sum(1 for s in k_od_sources.values() if s == "estimated"),
    }

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
    print(f"Preprocessing done in {log['preprocessing_total_time_sec']}s. Starting solve ladder...", flush=True)
    print(f"Interim log: {log_path}", flush=True)
    remaining_budget = deadline_ts - time.time()
    print(f"[run_full_data] {remaining_budget:.0f}s of budget remaining for the ladder", flush=True)

    ladder_kwargs = dict(
        candidates_full=candidates, rho=rho, journey_constants=journey_constants,
        rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
        pairs_df=pairs_df, r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U, monotonic=monotonic,
        step1_time_limit_sec=config["time_limit_sec"], seed=config["seed"], solver=config["solver"],
        mip_gap=args.mip_gap, log_dir=highs_log_dir, deadline_ts=deadline_ts,
        mip_heuristic_effort=args.mip_heuristic_effort,
        use_subprocess_watchdog=not args.no_subprocess_watchdog,
        watchdog_margin_sec=args.watchdog_margin_sec,
    )
    if args.step2_time_limit is not None:
        ladder_kwargs["step2_time_limit_sec"] = args.step2_time_limit
    if not args.enable_step2_ladder:
        ladder_kwargs["step2_k_schedule"] = ()  # M5c: deprecated by default, see --enable-step2-ladder help

    t3 = time.time()
    model, result, ladder_log = solve_with_ladder(**ladder_kwargs)
    log["ladder_log"] = ladder_log
    log["ladder_total_time_sec"] = round(time.time() - t3, 1)
    log["final_status"] = result.status
    log["final_objective_value"] = result.objective_value
    log["script_total_time_sec"] = round(time.time() - script_t0, 1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if result.status in ("optimal", "time_limit") and result.objective_value is not None:
        write_output(output_path, result, k_od_sources=k_od_sources)

        # M5c §2 (docs/decisions.md 2026-07-10): the OFFICIAL reported
        # objective_value is always the independently-recomputed one, never
        # the solver's raw internal claim -- overwrites output.json in place,
        # BEFORE validate_output runs (so validation checks the same number
        # that gets reported).
        recompute_total, recompute_breakdown = recompute_objective(
            output_path, FULL_OD, FULL_YV, FULL_CR, L=L, U=U, strict=False,
            breakdown_path=output_path.with_suffix(".objective_breakdown.json"),
        )
        reconciliation_ok, reconciliation_msg = finalize_reported_objective(
            output_path, recompute_total, result.status, result.objective_value,
        )
        log["recompute_objective_value"] = recompute_total
        log["reconciliation_ok"] = reconciliation_ok
        if not reconciliation_ok:
            log["reconciliation_message"] = reconciliation_msg
            print(f"[run_full_data] RECONCILIATION FAILURE: {reconciliation_msg}", flush=True)

        validation = validate_output(
            output_path, FULL_OD, L=L, U=U,
            adjustable_window_min=config["adjustable_window_min"],
            adjustable_set=config["adjustable_set"],
            flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
            alpha=config["alpha"], gamma=config["gamma"],
            bucket_size_min=config["bucket_size_min"],
            capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"],
        )
        log["validation_is_valid"] = validation.is_valid and reconciliation_ok
        log["validation_violations"] = validation.violations + ([] if reconciliation_ok else [reconciliation_msg])
    else:
        log["validation_is_valid"] = None
        reason = ("STEP0: wall-clock budget exceeded before any ladder step could complete "
                  "-- see ladder_log and re-run with a larger --budget-sec"
                  if result.status == "budget_exceeded" else
                  "STEP3: no accepted solution at any ladder step -- see ladder_log")
        log["validation_violations"] = [reason]

    log_path.write_text(json.dumps(log, indent=2, sort_keys=True, default=str))
    print(json.dumps({k: v for k, v in log.items() if k not in ("config",)}, indent=2, sort_keys=True, default=str),
          flush=True)
    print(f"\nFull log: {log_path}", flush=True)
    return log


if __name__ == "__main__":
    main()

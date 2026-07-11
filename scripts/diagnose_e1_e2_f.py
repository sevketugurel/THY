#!/usr/bin/env python3
"""M5 DAL C diagnostic (NOT a permanent pipeline stage, NOT a code change to
the model): the full-data solve ladder exhausted step1 (watchdog-killed, no
incumbent) and step2's entire K-schedule (50/100/200/400, all four cleanly
INFEASIBLE per HiGHS, not timeouts -- see runs/full_data_run_20260709T161927Z.log.json).
Per the user's DAL C protocol: first suspect E1, binary-search it off, then
E2, then F, on the SAME step2_subset_k400 candidate set (already proven
infeasible with all constraints on, and fast to solve: ~24s). Whichever
family's removal flips the model to feasible is reported back -- this
script does NOT change src/model/*.py; it composes the SAME tested
constraint-adding primitives build_model_m4 already uses, just toggling
which ones get called, so removing a constraint here is a diagnostic
question ("is this family the blocker"), not a production decision.

Every variant is solved through the SAME external subprocess watchdog the
main pipeline uses (docs/decisions.md 2026-07-09: appsi_highs's own
time_limit cannot reliably interrupt root-node cut generation) -- a bonus
"remove all three at once" attempt run as a raw in-process solve() call
(bypassing the watchdog) hung for 13:44 wall-clock with zero result and had
to be killed by hand; every variant here is now capped at
time_limit_sec+watchdog_margin_sec regardless of what HiGHS does internally.

Kullanım: .venv/bin/python3 -u scripts/diagnose_e1_e2_f.py
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyomo.environ as pyo
import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.candidates.subset import apply_adjustable_subset
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi
from src.data.ranking import compute_baseline_best_journey, derive_b_od, is_ranking_monotonic
from src.model.constraints_balance import add_e1_constraints, add_e2_constraints
from src.model.constraints_capacity import add_f_constraints, compute_out_of_scope_baselines, compute_residual_capacity
from src.model.constraints_competition import add_d_constraints, add_rank_onehot
from src.model.constraints_operations import add_a_constraints, add_g_constraints
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.model.objective import add_connection_reward_objective, add_ranking_reward_objective
from src.solve.subprocess_watchdog import solve_step_with_watchdog

from src.config.paths import FULL_OD, FULL_YV, FULL_CR, FULL_FP
DIAGNOSE_WORKER = Path(__file__).resolve().parent / "_diagnose_step_worker.py"
STEP_TIME_LIMIT_SEC = 180
WATCHDOG_MARGIN_SEC = 60
K_SUBSET = 400  # same as the ladder's step2_subset_k400, already proven infeasible with everything on


def _build_variant(
    candidates, rho, journey_constants, rival_data, b_od_data, ranking_table,
    pairs_df, r_o_lookup, tau, x_dev, epoch_anchor, alpha, gamma, tk_rows,
    bucket_size_min, capacity_departure, capacity_arrival, L, U, monotonic,
    include_e1: bool, include_e2: bool, include_f: bool,
    include_a: bool = True, include_g: bool = True,
):
    """Line-for-line the same sequence as src.model.build.build_model_m4,
    with include_a/e1/e2/f/g as the ONLY deviation (each family's
    add_*_constraints call is skipped, not modified). A and G already carry
    their own per-pair/per-cluster VARSAYIM-9/11 exemptions internally --
    include_a=False/include_g=False strips the WHOLE family, a strictly
    stronger relaxation than what those exemptions already allow."""
    model = pyo.ConcreteModel()
    model._candidates = candidates

    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_connection_reward_objective(model, rho)

    n_by_market = add_d_constraints(model, candidates, journey_constants, rival_data, monotonic=monotonic)
    add_rank_onehot(model, n_by_market)
    add_ranking_reward_objective(model, rho, b_od_data, ranking_table, n_by_market)

    out_of_scope_baselines = compute_out_of_scope_baselines(tk_rows, model, epoch_anchor)
    if include_a:
        add_a_constraints(model, candidates, pairs_df, r_o_lookup, tau, out_of_scope_baselines)
    if include_g:
        add_g_constraints(model, candidates, epoch_anchor, x_dev)

    if include_e1:
        add_e1_constraints(model, candidates, alpha)
    if include_e2:
        add_e2_constraints(model, candidates, journey_constants, gamma)

    if include_f:
        residual_dep, residual_arr = compute_residual_capacity(
            out_of_scope_baselines, bucket_size_min, capacity_departure, capacity_arrival,
        )
        add_f_constraints(model, bucket_size_min, capacity_departure, capacity_arrival, residual_dep, residual_arr)

    return model


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default=None,
                         help="run only this variant name (e.g. E1_E2_F_all_off) instead of the full sequence")
    parser.add_argument("--full", action="store_true",
                         help="use the FULL 18118-candidate set (nothing fixed to baseline) instead of the "
                              "K=400 adjustable-subset -- all 5 families came back clean-infeasible when "
                              "removed individually on K=400, so the next hypothesis is that the subset's "
                              "15742 baseline-fixed flights (themselves violation-riddled, see the baseline "
                              "feasibility witness) are the actual source, not any one constraint family")
    parser.add_argument("--time-limit-sec", type=float, default=None,
                         help="override STEP_TIME_LIMIT_SEC (180s default; --full needs more, e.g. 600s "
                              "to match step1's original budget)")
    parser.add_argument("--mip-heuristic-effort", type=float, default=None,
                         help="HiGHS mip_heuristic_effort passthrough, same rationale as scripts/run_full_data.py")
    args = parser.parse_args()

    time_limit_sec = args.time_limit_sec if args.time_limit_sec is not None else STEP_TIME_LIMIT_SEC

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

    if args.full:
        subset_candidates = candidates
        print(f"[diagnose] --full: using all {len(candidates)} candidates, nothing fixed to baseline", flush=True)
    else:
        # Same top-K-by-rho adjustable subset the ladder's step2_subset_k400 used.
        markets_by_rho = sorted({(c.o, c.d) for c in candidates}, key=lambda m: -rho.get(m, 0))
        adjustable_markets = set(markets_by_rho[:K_SUBSET])
        subset_candidates = apply_adjustable_subset(candidates, adjustable_markets, L=L, U=U)

    common_kwargs = dict(
        candidates=subset_candidates, rho=rho, journey_constants=journey_constants,
        rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
        pairs_df=pairs_df, r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U, monotonic=monotonic,
    )

    variants = [
        ("all_on_A-G", dict(include_e1=True, include_e2=True, include_f=True)),
        ("E1_off", dict(include_e1=False, include_e2=True, include_f=True)),
        ("E2_off", dict(include_e1=True, include_e2=False, include_f=True)),
        ("F_off", dict(include_e1=True, include_e2=True, include_f=False)),
        # 2026-07-09: none of the three above alone flipped the model to
        # feasible (each independently still infeasible) -- next question is
        # whether it's a COMPOUNDING effect across all three together.
        ("E1_E2_F_all_off", dict(include_e1=False, include_e2=False, include_f=False)),
        # 2026-07-09: E1/E2/F-all-off was inconclusive (watchdog_killed at
        # 240s, neither proven feasible nor infeasible) -- baseline witness
        # showed A (~144 genuine, non-exempt) and G (53) ALSO have real
        # violations even after their own VARSAYIM-9/11 exemptions, so
        # they're the next single-culprit candidates to rule in/out.
        ("A_off", dict(include_e1=True, include_e2=True, include_f=True, include_a=False, include_g=True)),
        ("G_off", dict(include_e1=True, include_e2=True, include_f=True, include_a=True, include_g=False)),
    ]
    if args.only:
        variants = [(n, f) for n, f in variants if n == args.only]
        if not variants:
            parser.error(f"--only {args.only!r} does not match any variant name")

    results = []
    for name, flags in variants:
        build_kwargs = {**common_kwargs, **flags}
        solve_kwargs = dict(
            solver="highs", time_limit_sec=time_limit_sec, seed=42, mip_gap=0.08,
            mip_heuristic_effort=args.mip_heuristic_effort,
        )
        print(f"[diagnose] {name}: build+solve starting (watchdog-protected, "
              f"n_candidates={len(subset_candidates)}, time_limit={time_limit_sec}s)", flush=True)
        result, build_time_sec = solve_step_with_watchdog(
            build_kwargs, solve_kwargs, time_limit_sec=time_limit_sec,
            watchdog_margin_sec=WATCHDOG_MARGIN_SEC, step_name=name, worker_script=DIAGNOSE_WORKER,
        )
        n_selected = sum(result.selected.values()) if result.selected else 0
        build_str = f"{build_time_sec:.1f}s" if build_time_sec is not None else "unknown (killed before reporting)"
        print(f"[diagnose] {name}: build={build_str} solve={result.solve_time_sec:.1f}s "
              f"status={result.status} obj={result.objective_value} selected={n_selected}", flush=True)
        results.append({
            "variant": name,
            "build_time_sec": round(build_time_sec, 1) if build_time_sec is not None else None,
            "solve_time_sec": round(result.solve_time_sec, 1), "status": result.status,
            "objective_value": result.objective_value, "n_selected": n_selected,
        })
        # Stop as soon as we find the culprit -- E1/E2/F is checked in that
        # order per the user's protocol, and once one variant is feasible
        # while all_on_A-G was infeasible, that family (or combination) is a
        # genuine suspect; no need to burn more solver time confirming rest.
        if name != "all_on_A-G" and result.status in ("optimal", "time_limit") and result.objective_value is not None:
            print(f"[diagnose] {name}: FEASIBLE after removing this family -- stopping search early", flush=True)
            break

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = Path("runs") / f"diagnose_e1_e2_f_{stamp}.json"
    log_path.write_text(json.dumps({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "full": args.full, "time_limit_sec": time_limit_sec,
        "mip_heuristic_effort": args.mip_heuristic_effort,
        "k_subset": None if args.full else K_SUBSET, "n_candidates_in_subset": len(subset_candidates),
        "results": results,
    }, indent=2, sort_keys=True))
    print(f"\nFull log: {log_path}", flush=True)
    return results


if __name__ == "__main__":
    main()

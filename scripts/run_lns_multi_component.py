#!/usr/bin/env python3
"""M5f Kapı-3 adım (c) (docs/CLOSING_PLAN.md): ÇOKLU-BİLEŞEN LNS, TEK deneme
hakkı. Adım (b)'nin (`scripts/run_lns.py --builder folded --selection
component`) tek-bileşen-at-a-time yaklaşımı, "en inatçı" (stubborn)
bileşenlerde 20 iterasyon platoya girdi -- M5d'nin daha önce bulduğu "yerel
düzeltme alanı boş" semptomunun component-bazlı bir tekrarı: bir bileşenin
KENDİ içinde serbest bıraktığımız örnekler E1/E2'sini düzeltmeye yetmiyor,
çünkü gerçek çözüm KOMŞU bir bileşenin de aynı anda hareket etmesini
gerektiriyor olabilir (paylaşılan uçuş örnekleri üzerinden). Bu script TEK
bir denemede (600s, ≤45dk toplam duvar) en kötü Σslack'e sahip 2-3 bağlantılı
bileşeni AYNI ANDA serbest bırakıp TEK bir birleşik alt-problem çözer --
adım (b)'nin plato noktasından (en son `runs/lns_best_partial_*.json`)
devam eder, sıfırdan başlamaz.

Kullanım: .venv/bin/python3 -u scripts/run_lns_multi_component.py [--k 3]
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
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.model.constraints_capacity import compute_out_of_scope_baselines_from_keys
from src.model.lns import (
    build_pair_adjacency, compute_gamma_infeasible_pairs, compute_pair_slack,
    connected_components, free_instances_for_pairs,
)
from src.output.writer import write_output
from src.solve.subprocess_watchdog import solve_step_with_watchdog
from src.validate.independent_validator import finalize_reported_objective, recompute_objective, validate_output

from src.config.paths import FULL_CR, FULL_FP, FULL_OD, FULL_YV
from src.data.provenance import file_provenance

LNS_WORKER_FOLDED = Path(__file__).resolve().parent / "_lns_step_worker_folded.py"
SLACK_EPS = 1e-6


def _latest_partial_output() -> Path:
    candidates = sorted(Path("runs").glob("lns_best_partial_*.json"))
    if not candidates:
        raise FileNotFoundError(
            "no runs/lns_best_partial_*.json found -- run scripts/run_lns.py "
            "(adım b) first, this script continues from its plateau point"
        )
    return candidates[-1]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=3, help="number of worst-slack components to free simultaneously")
    parser.add_argument("--iter-time-limit-sec", type=float, default=600.0)
    parser.add_argument("--watchdog-margin-sec", type=float, default=120.0)
    parser.add_argument("--mip-gap", type=float, default=0.05)
    parser.add_argument("--mip-heuristic-effort", type=float, default=0.3)
    parser.add_argument("--max-improving-sols", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epsilon", type=float, default=0.0)
    parser.add_argument("--input", default=None, help="starting point (default: latest runs/lns_best_partial_*.json)")
    parser.add_argument("--output", default="runs/lns_multi_component_output.json")
    args = parser.parse_args(argv)

    t0 = time.time()
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U, alpha, gamma = config["L"], config["U"], config["alpha"], config["gamma"]

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

    rotation_stations = set(row["dest"] for row in pairs_df.to_dict("records") if row["orig"] == "IST")
    r_o_lookup = {}
    for station in rotation_stations:
        try:
            r_o_lookup[station] = provider.get_rotation_constant(station)
        except KeyError:
            continue

    full_arr_keys = {c.r1_id for c in candidates}
    full_dep_keys = {c.r2_id for c in candidates}
    true_out_of_scope_baselines = compute_out_of_scope_baselines_from_keys(tk, full_arr_keys, full_dep_keys, anchor)

    input_path = Path(args.input) if args.input else _latest_partial_output()
    print(f"[multi_component] continuing from {input_path}", flush=True)
    data = json.loads(input_path.read_text())
    reference_arr, reference_dep = {}, {}
    for e in data["adjusted_flight_times"]:
        key = (e["role"], e["flno"], e["gun"])
        if e["role"] == "IB":
            reference_arr[key] = e["time_min"]
        else:
            reference_dep[key] = e["time_min"]

    print(f"[multi_component] preprocessing done in {time.time()-t0:.1f}s, n_candidates={len(candidates)}", flush=True)

    gamma_infeasible = compute_gamma_infeasible_pairs(candidates, journey_constants, L, U, gamma)
    pair_slack = compute_pair_slack(
        candidates, journey_constants, reference_arr, reference_dep, L, U, alpha, gamma,
        gamma_infeasible_pairs=gamma_infeasible,
    )
    before_total = sum(v["total"] for v in pair_slack.values())
    print(f"[multi_component] starting Sigma-slack={before_total:.2f}", flush=True)

    violated_fixable = [p for p, s in pair_slack.items() if s["total"] > 0 and p not in gamma_infeasible]
    adjacency = build_pair_adjacency(candidates, violated_fixable)
    components = connected_components(adjacency)
    if not components:
        print("[multi_component] ABORT -- no violating fixable components remain", flush=True)
        return

    ranked = sorted(
        components, key=lambda c: -sum(pair_slack.get(p, {"total": 0.0})["total"] for p in c),
    )
    chosen = ranked[: args.k]
    chosen_pairs = [p for comp in chosen for p in comp]
    for i, comp in enumerate(chosen):
        comp_slack = sum(pair_slack.get(p, {"total": 0.0})["total"] for p in comp)
        print(f"[multi_component] component {i+1}/{len(chosen)}: {len(comp)} pairs, slack={comp_slack:.2f}",
              flush=True)

    free_arr, free_dep = free_instances_for_pairs(candidates, chosen_pairs)
    n_free = len(free_arr) + len(free_dep)
    print(f"[multi_component] combined free instances: {n_free} (arr={len(free_arr)}, dep={len(free_dep)})",
          flush=True)

    model_kwargs_base = dict(
        candidates=candidates, journey_constants=journey_constants, pairs_df=pairs_df,
        r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor,
        alpha=alpha, gamma=gamma, tk_rows=tk, bucket_size_min=config["bucket_size_min"],
        capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"], L=L, U=U,
    )
    build_kwargs = {
        "model_kwargs": model_kwargs_base,
        "epsilon": args.epsilon,
        "true_out_of_scope_baselines": true_out_of_scope_baselines,
        "partition_kwargs": {
            "reference_arr": reference_arr, "reference_dep": reference_dep,
            "free_arr": free_arr, "free_dep": free_dep,
        },
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    highs_log_dir = Path("runs") / f"lns_multi_component_{stamp}_highs_logs"
    highs_log_dir.mkdir(parents=True, exist_ok=True)
    solve_kwargs = dict(
        solver="highs", time_limit_sec=args.iter_time_limit_sec, seed=args.seed,
        mip_gap=args.mip_gap, mip_heuristic_effort=args.mip_heuristic_effort,
        log_file=highs_log_dir / "solve.highs.log",
    )
    if args.max_improving_sols is not None:
        solve_kwargs["extra_highs_options"] = {"mip_max_improving_sols": args.max_improving_sols}

    print(f"[multi_component] solving combined subproblem (time_limit={args.iter_time_limit_sec}s)...", flush=True)
    t_solve = time.time()
    result, build_time_sec = solve_step_with_watchdog(
        build_kwargs, solve_kwargs, time_limit_sec=args.iter_time_limit_sec,
        watchdog_margin_sec=args.watchdog_margin_sec, step_name="lns_multi_component",
        worker_script=LNS_WORKER_FOLDED,
    )
    solve_sec = time.time() - t_solve
    print(f"[multi_component] solve finished in {solve_sec:.1f}s status={result.status}", flush=True)

    summary = {
        "data_provenance": {"FULL_OD": file_provenance(FULL_OD)},
        "input_path": str(input_path),
        "k_components": args.k,
        "n_free_instances": n_free,
        "before_total_slack": before_total,
        "status": result.status,
        "solve_sec": round(solve_sec, 1),
    }

    if result.status not in ("optimal", "time_limit") or not result.arr_times:
        summary["outcome"] = "no_usable_result"
        print(f"[multi_component] NO USABLE RESULT (status={result.status}) -- single attempt exhausted", flush=True)
    else:
        merged_arr = {**reference_arr, **result.arr_times}
        merged_dep = {**reference_dep, **result.dep_times}
        after_slack = compute_pair_slack(
            candidates, journey_constants, merged_arr, merged_dep, L, U, alpha, gamma,
            gamma_infeasible_pairs=gamma_infeasible,
        )
        after_total = sum(v["total"] for v in after_slack.values())
        summary["after_total_slack"] = after_total
        summary["improved_by"] = before_total - after_total
        print(f"[multi_component] before={before_total:.2f} after={after_total:.2f} "
              f"improved_by={before_total-after_total:.2f}", flush=True)

        selected_full, gap_full = {}, {}
        for c in candidates:
            gap = merged_dep[c.r2_id] - merged_arr[c.r1_id]
            selected_full[c] = 1 if L <= gap <= U else 0
            gap_full[c] = gap
        import dataclasses
        merged_result = dataclasses.replace(
            result, selected=selected_full, gap_values=gap_full, arr_times=merged_arr, dep_times=merged_dep,
        )

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_output(output_path, merged_result, k_od_sources=k_od_sources)

        if after_total <= SLACK_EPS:
            recompute_total, _ = recompute_objective(
                output_path, FULL_OD, FULL_YV, FULL_CR, L=L, U=U, strict=False,
                breakdown_path=output_path.with_suffix(".objective_breakdown.json"),
            )
            reconciliation_ok, reconciliation_msg = finalize_reported_objective(
                output_path, recompute_total, merged_result.status, merged_result.objective_value,
            )
            validation = validate_output(
                output_path, FULL_OD, L=L, U=U,
                adjustable_window_min=config["adjustable_window_min"], adjustable_set=config["adjustable_set"],
                flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
                alpha=config["alpha"], gamma=config["gamma"],
                bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
                capacity_arrival=config["capacity_arrival"],
            )
            is_valid = validation.is_valid and reconciliation_ok
            summary["outcome"] = "slack_zero_reached"
            summary["validation_is_valid"] = is_valid
            summary["n_violations"] = len(validation.violations)
            summary["recompute_objective_value"] = recompute_total
            print(f"[multi_component] SLACK~0 REACHED -- validation_is_valid={is_valid} "
                  f"n_violations={len(validation.violations)} recompute_objective={recompute_total}", flush=True)
        else:
            summary["outcome"] = "plateau_not_broken" if after_total >= before_total - 1e-9 else "partial_improvement"
            final_slack = after_slack
            n_e1_final = sum(1 for v in final_slack.values() if v["e1"] > 0)
            n_e2_final = sum(1 for v in final_slack.values() if v["e2"] > 0)
            summary["n_e1_pairs_violated_at_stop"] = n_e1_final
            summary["n_e2_pairs_violated_at_stop"] = n_e2_final

    log_path = Path("runs") / f"lns_multi_component_summary_{stamp}.json"
    log_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str))
    print(json.dumps(summary, indent=2, sort_keys=True, default=str), flush=True)
    print(f"\nSummary: {log_path}", flush=True)
    return summary


if __name__ == "__main__":
    main()

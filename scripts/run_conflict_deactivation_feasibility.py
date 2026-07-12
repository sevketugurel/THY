#!/usr/bin/env python3
"""K2/K3 (bu oturum, E2-conflict kırma + KONTROLLÜ MARKET-DIRECTION KAPATMA):
full-data'da validator'dan geçen İLK feasible output.json arayışı.

Mekanizma (mimari kararlar D1-D8, önceden verildi -- bkz. session brief):
  D1: bir (o,d,gun) YÖNÜ tamamen kapatılır -- build_feasibility_model
      (A/B/E1c/E2/F/G, HARD kısıtlar) SONRASI o yöne ait TÜM adayların
      model.x[i]'si .fix(0). B'nin backward reifikasyonu gap'i [L,U]
      DIŞINA zorlar -- "uygun olan sunulmak zorunda" kuralı BÜKÜLMEZ.
  D2: bir yön ancak İÇİNDEKİ HER ADAY için achievable range'i TAMAMEN
      [L,U] içinde değilse kapatılabilir (src.model.deactivation.is_direction_killable).
  D3: "conflict edge" -- referans noktada (bir LNS/warm-start partial'ı)
      E1/E2 slack'i pozitif olan her (o,d,gun) pair'i, iki yönünü
      birbirine bağlayan bir kenar. VARSAYIM-17 muaf çiftler kenar DEĞİL.
  D4: cost(dir)=rho*max(1,n_candidates); greedy ağırlıklı-vertex-cover
      (src.model.deactivation.greedy_cover) kalan kenarları en ucuza kapatır.
  D5: kapatma seviyeleri (violated edge'lerin %40/%70/%100'ünü kapsayan
      greedy önekleri), her seviye için TEK watchdog'lu solve denemesi.
  D6: bir seviye kök-düğümde donarsa (watchdog_killed, sıfır incumbent) --
      AYNI kapatma setini elastik yola (scripts/warm_start_elastic.py +
      scripts/run_lns.py, ikisi de --deactivation-file destekler) manuel
      olarak takmak BU script'in DIŞINDA bir sonraki adımdır (STATUS.md'ye
      loglanır) -- otomatik zincirleme YAPILMAZ, çünkü elastik yol kendi
      çok-adımlı (Adım A + warm-start + LNS) protokolüne sahip.
  D7: feasible incumbent bulununca -- güvenlik assert'i (kapatılan
      yönlerin TÜM adaylarının raporlanan gap'i [L,U] DIŞINDA), post-hoc
      ranking sentezi, write_output, validate_output (SIFIR ihlal ŞART),
      recompute_objective + finalize_reported_objective. Validator
      geçmezse: ihlalli pazarların yönlerini kapatma listesine ekleyip
      (killable olanları) --max-extra-iterations kadar AYNI seviyede
      tekrar dene.

Kullanım: .venv/bin/python3 -u scripts/run_conflict_deactivation_feasibility.py [--dry-run]
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.config.paths import FULL_CR, FULL_FP, FULL_OD, FULL_YV
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.data.provenance import file_provenance
from src.model.deactivation import (
    apply_deactivation, build_conflict_edges, direction_cost, greedy_cover,
    is_direction_killable, market_direction_index,
)
from src.model.lns import compute_gamma_infeasible_pairs, compute_pair_slack
from src.model.ranking_derive import derive_ranking_results
from src.output.writer import write_output
from src.solve.subprocess_watchdog import solve_step_with_watchdog
from src.validate.independent_validator import finalize_reported_objective, recompute_objective, validate_output

CONFLICT_WORKER = Path(__file__).resolve().parent / "_conflict_deactivation_step_worker.py"
DEFAULT_REFERENCE = "runs/lns_best_partial_20260711T194301Z.json"

_VIOLATION_MARKET_RE = re.compile(r"^(?:E1|E2) ([A-Z]{3})-([A-Z]{3}) Gün=(\d+):")


def _load_reference(reference_path, candidates):
    data = json.loads(Path(reference_path).read_text())
    arr_times, dep_times = {}, {}
    for e in data["adjusted_flight_times"]:
        key = (e["role"], e["flno"], e["gun"])
        if e["role"] == "IB":
            arr_times[key] = e["time_min"]
        else:
            dep_times[key] = e["time_min"]
    arr_ids = {c.r1_id for c in candidates}
    dep_ids = {c.r2_id for c in candidates}
    missing_arr = arr_ids - set(arr_times)
    missing_dep = dep_ids - set(dep_times)
    assert not missing_arr, f"reference partial missing arr instances: {sorted(missing_arr)[:5]}"
    assert not missing_dep, f"reference partial missing dep instances: {sorted(missing_dep)[:5]}"
    return arr_times, dep_times


def _violating_markets_from_report(violations):
    markets = set()
    for v in violations:
        m = _VIOLATION_MARKET_RE.match(v)
        if m:
            o, d, gun = m.group(1), m.group(2), int(m.group(3))
            markets.add((o, d, gun))
    return markets


def _level_prefixes(edges, deactivated_order, thresholds):
    """D5: prefixes of the greedy kill order whose CUMULATIVE covered-edge
    count reaches >= threshold * len(edges). 1.0 lands on the full
    deactivated_order (== greedy_cover's own natural stopping point --
    everything coverable, per build_conflict_edges/greedy_cover)."""
    total = len(edges)
    covered = set()
    running = []
    checkpoints = []
    for direction, cost in deactivated_order:
        running = running + [direction]
        for e in edges:
            if e in covered:
                continue
            if direction in e:
                covered.add(e)
        checkpoints.append((list(running), len(covered)))

    result = {}
    for t in thresholds:
        target = t * total if total else 0
        chosen = None
        for directions, n_covered in checkpoints:
            if n_covered >= target - 1e-9:
                chosen = (directions, n_covered)
                break
        if chosen is None:
            chosen = checkpoints[-1] if checkpoints else ([], 0)
        result[t] = chosen
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-partial", default=DEFAULT_REFERENCE)
    parser.add_argument("--levels", default="0.4,0.7,1.0")
    parser.add_argument("--time-limit-sec", type=float, default=900.0)
    parser.add_argument("--watchdog-margin-sec", type=float, default=120.0)
    parser.add_argument("--mip-heuristic-effort", type=float, default=0.5)
    parser.add_argument("--max-improving-sols", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-extra-iterations", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true",
                         help="Stop after computing conflict edges + the greedy level plan -- no solve "
                              "budget spent. Use this to sanity-check numbers before committing the "
                              "campaign's solver-hour budget.")
    args = parser.parse_args()
    thresholds = [float(x) for x in args.levels.split(",")]

    script_t0 = time.time()
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

    print(f"[conflict_deactivation] preprocessing done in {time.time()-script_t0:.1f}s, "
          f"n_candidates={len(candidates)}", flush=True)

    reference_arr, reference_dep = _load_reference(args.reference_partial, candidates)

    gamma_infeasible_pairs = compute_gamma_infeasible_pairs(candidates, journey_constants, L, U, gamma)
    pair_slack = compute_pair_slack(
        candidates, journey_constants, reference_arr, reference_dep, L, U, alpha, gamma,
        e1_activation=config["e1_activation"], gamma_infeasible_pairs=gamma_infeasible_pairs,
    )
    n_e2_violated = sum(1 for v in pair_slack.values() if v["e2"] > 0)
    sigma_e2 = sum(v["e2"] for v in pair_slack.values())
    print(f"[conflict_deactivation] reference point: n_e2_violated_pairs={n_e2_violated} "
          f"sigma_e2={sigma_e2:.2f} (D3 expected ~1094 pairs, Sigma~=56540.6)", flush=True)
    if not (900 <= n_e2_violated <= 1300 and 45000 <= sigma_e2 <= 68000):
        print("[conflict_deactivation] WARNING: reference-point E2 numbers deviate meaningfully from "
              "D3's expectation -- inspect before trusting the campaign below.", flush=True)

    direction_index = market_direction_index(candidates)
    killable = {
        d for d, idxs in direction_index.items()
        if is_direction_killable([candidates[i] for i in idxs], L, U)
    }
    selected_count = {}
    for c in candidates:
        gap = reference_dep[c.r2_id] - reference_arr[c.r1_id]
        if L <= gap <= U:
            key = (c.o, c.d, c.gun)
            selected_count[key] = selected_count.get(key, 0) + 1

    edges = build_conflict_edges(pair_slack, gamma_infeasible_pairs)
    direction_costs = {}
    for a, b in edges:
        direction_costs.setdefault(a, direction_cost(a, direction_index, rho))
        direction_costs.setdefault(b, direction_cost(b, direction_index, rho))

    deactivated_order, uncovered_unkillable = greedy_cover(edges, direction_costs, killable, selected_count)
    print(f"[conflict_deactivation] n_conflict_edges={len(edges)} "
          f"n_killable_directions_in_cover={len(deactivated_order)} "
          f"n_uncovered_unkillable_edges={len(uncovered_unkillable)}", flush=True)

    level_plan = _level_prefixes(edges, deactivated_order, thresholds)
    for t in thresholds:
        directions, n_covered = level_plan[t]
        rho_lost = sum(direction_costs[d] for d in directions)
        print(f"[conflict_deactivation] level {t}: n_directions={len(directions)} "
              f"edges_covered={n_covered}/{len(edges)} rho_lost={rho_lost}", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    plan_log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "data_provenance": {"FULL_OD": file_provenance(FULL_OD)},
        "reference_partial": args.reference_partial,
        "n_candidates": len(candidates),
        "n_e2_violated_pairs_at_reference": n_e2_violated,
        "sigma_e2_at_reference": sigma_e2,
        "n_conflict_edges": len(edges),
        "n_uncovered_unkillable_edges": len(uncovered_unkillable),
        "uncovered_unkillable_edges": [[list(a), list(b)] for a, b in uncovered_unkillable],
        "levels": {
            str(t): {
                "n_directions": len(level_plan[t][0]),
                "edges_covered": level_plan[t][1],
                "rho_lost": sum(direction_costs[d] for d in level_plan[t][0]),
                "directions": [list(d) for d in level_plan[t][0]],
            }
            for t in thresholds
        },
    }
    plan_path = Path("runs") / f"conflict_deactivation_plan_{stamp}.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan_log, indent=2, sort_keys=True, default=str))
    print(f"[conflict_deactivation] plan written to {plan_path}", flush=True)

    if args.dry_run:
        print("[conflict_deactivation] --dry-run: stopping before any solve.", flush=True)
        return plan_log

    rival_data = {}
    for c in candidates:
        market = (c.o, c.d, c.gun)
        if market not in rival_data:
            rival_data[market] = derive_rival_best_times(od_table, c.o, c.d, c.gun)

    model_kwargs_base = dict(
        candidates=candidates, journey_constants=journey_constants, pairs_df=pairs_df,
        r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor,
        alpha=alpha, gamma=gamma, tk_rows=tk, bucket_size_min=config["bucket_size_min"],
        capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"],
        L=L, U=U, e1_activation=config["e1_activation"],
    )
    solve_kwargs_base = dict(
        solver="highs", time_limit_sec=args.time_limit_sec, seed=args.seed,
        mip_heuristic_effort=args.mip_heuristic_effort,
        extra_highs_options={"mip_max_improving_sols": args.max_improving_sols},
    )

    attempts_log = []
    for t in thresholds:
        directions_to_kill = list(level_plan[t][0])
        extra_iter = 0
        while True:
            label = f"level{t}" + (f"_extra{extra_iter}" if extra_iter else "")
            highs_log_dir = Path("runs") / f"conflict_deactivation_{stamp}_highs_logs"
            highs_log_dir.mkdir(parents=True, exist_ok=True)
            solve_kwargs = dict(solve_kwargs_base, log_file=highs_log_dir / f"{label}.highs.log")
            build_kwargs = {"model_kwargs": model_kwargs_base, "directions_to_kill": directions_to_kill}

            print(f"[conflict_deactivation] {label}: solving with {len(directions_to_kill)} "
                  f"deactivated direction(s) (time_limit={args.time_limit_sec}s)...", flush=True)
            t_solve = time.time()
            result, build_time_sec = solve_step_with_watchdog(
                build_kwargs, solve_kwargs, time_limit_sec=args.time_limit_sec,
                watchdog_margin_sec=args.watchdog_margin_sec, step_name=label,
                worker_script=CONFLICT_WORKER,
            )
            solve_sec = time.time() - t_solve
            print(f"[conflict_deactivation] {label}: status={result.status} solve_sec={solve_sec:.1f}", flush=True)
            attempt_record = {
                "label": label, "status": result.status, "solve_sec": round(solve_sec, 1),
                "n_directions_killed": len(directions_to_kill),
            }

            if result.status not in ("optimal", "time_limit") or not result.arr_times:
                attempt_record["outcome"] = "no_incumbent"
                attempts_log.append(attempt_record)
                print(f"[conflict_deactivation] {label}: NO INCUMBENT -- Plan B (elastic, D6) needed "
                      f"if this level is to be recovered.", flush=True)
                break

            # D7 (1): safety assert -- every killed direction's candidates must
            # report a gap OUTSIDE [L,U] (B's backward reification is what
            # guarantees this; a violation here would mean a real modeling bug).
            for direction in directions_to_kill:
                for i in direction_index.get(direction, []):
                    c = candidates[i]
                    gap = result.gap_values[c]
                    assert not (L <= gap <= U), (
                        f"SAFETY ASSERT FAILED: killed direction {direction} candidate "
                        f"FlNo1={c.flno1} FlNo2={c.flno2} still reports gap={gap} in [{L},{U}]"
                    )

            rank_values, beaten_rivals = derive_ranking_results(
                candidates, rival_data, journey_constants, result.selected, result.gap_values,
            )
            result.rank_values, result.beaten_rivals = rank_values, beaten_rivals

            output_path = Path("runs") / f"conflict_deactivation_{stamp}_{label}_output.json"
            write_output(output_path, result, k_od_sources=k_od_sources)

            validation = validate_output(
                output_path, FULL_OD, L=L, U=U,
                adjustable_window_min=config["adjustable_window_min"], adjustable_set=config["adjustable_set"],
                flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
                alpha=config["alpha"], gamma=config["gamma"],
                bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
                capacity_arrival=config["capacity_arrival"], e1_activation=config["e1_activation"],
            )
            attempt_record["n_violations"] = len(validation.violations)
            attempt_record["output_path"] = str(output_path)

            if validation.is_valid:
                recompute_total, _ = recompute_objective(
                    output_path, FULL_OD, FULL_YV, FULL_CR, L=L, U=U, strict=False,
                    breakdown_path=output_path.with_suffix(".objective_breakdown.json"),
                )
                reconciliation_ok, reconciliation_msg = finalize_reported_objective(
                    output_path, recompute_total, result.status, result.objective_value,
                )
                attempt_record["outcome"] = "SUCCESS"
                attempt_record["recompute_objective_value"] = recompute_total
                attempt_record["reconciliation_ok"] = reconciliation_ok
                attempt_record["reconciliation_msg"] = reconciliation_msg
                attempts_log.append(attempt_record)
                print(f"[conflict_deactivation] {label}: SUCCESS -- validator PASSED, "
                      f"recompute_objective={recompute_total}, output={output_path}", flush=True)
                summary = {
                    "success": True, "attempts": attempts_log, "final_output_path": str(output_path),
                    "recompute_objective_value": recompute_total,
                    "n_directions_killed": len(directions_to_kill),
                    "rho_lost": sum(direction_costs.get(d, direction_cost(d, direction_index, rho))
                                     for d in directions_to_kill),
                }
                summary_path = Path("runs") / f"conflict_deactivation_summary_{stamp}.json"
                summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str))
                print(json.dumps(summary, indent=2, sort_keys=True, default=str), flush=True)
                return summary

            attempt_record["outcome"] = "validator_rejected"
            attempts_log.append(attempt_record)
            print(f"[conflict_deactivation] {label}: validator REJECTED ({len(validation.violations)} "
                  f"violations) -- {validation.violations[:5]}", flush=True)

            if extra_iter >= args.max_extra_iterations:
                print(f"[conflict_deactivation] {label}: remediation budget exhausted for this level, "
                      f"escalating to next level.", flush=True)
                break

            violating_markets = _violating_markets_from_report(validation.violations)
            added = False
            for (o, d, gun) in violating_markets:
                for direction in ((o, d, gun), (d, o, gun)):
                    if direction in killable and direction not in directions_to_kill:
                        directions_to_kill.append(direction)
                        added = True
            if not added:
                print(f"[conflict_deactivation] {label}: no additional killable directions found among "
                      f"violating markets -- escalating to next level.", flush=True)
                break
            extra_iter += 1

    print("[conflict_deactivation] all levels exhausted without a validated feasible point.", flush=True)
    summary = {"success": False, "attempts": attempts_log}
    summary_path = Path("runs") / f"conflict_deactivation_summary_{stamp}.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str))
    print(json.dumps(summary, indent=2, sort_keys=True, default=str), flush=True)
    return summary


if __name__ == "__main__":
    main()

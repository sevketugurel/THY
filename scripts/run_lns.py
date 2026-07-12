#!/usr/bin/env python3
"""M5d Fix-and-Optimize LNS (docs/decisions.md 2026-07-11, user redirect):
starts from the existing full-data elastic incumbent
(runs/warm_start_elastic_output.json, Sigma-slack~1879-violations-worth,
NOT yet validated) and iteratively:

  1. picks the m worst E1/E2 pairs by slack magnitude (src.model.lns),
  2. frees exactly the flight-time instances those pairs touch,
  3. REALLY fixes (.fix(), not a Big-M indicator) every other instance to
     the current incumbent,
  4. re-solves the (now mostly-fixed, much smaller after presolve) elastic
     model, watchdog-protected,
  5. adopts the result as the new incumbent if Sigma-slack improved.

Every subproblem is trivially feasible before HiGHS even starts (the fixed
portion IS the current incumbent, which is always a valid assignment) --
unlike the K-subset ladder (freezing chosen blind, before any solve) and
unlike local-branching's Big-M/moved-indicator form (mathematically
correct but never actually shrinks the presolved model -- HiGHS's own
probing couldn't get through it in time, see
runs/local_branching_20260710T214039Z.log.json).

Stops when: (a) Sigma-slack reaches ~0 -- the point is written out and run
through the SAME validation chain every other full-data script uses
(recompute_objective/finalize_reported_objective/validate_output); if it
passes, this is the session's first validated value; (b) a wall-clock or
iteration cap is hit; (c) a plateau (no meaningful improvement for
--plateau-iters iterations after both widening m and randomizing block
selection have been tried) -- in which case a summary (slack curve +
worst-offender map) is written and the script stops WITHOUT touching any
model code, exactly as instructed.

Per-iteration progress is appended to runs/lns_progress.log (one line each,
gitignored -- this can run for hours) and docs/STATUS.md's LNS section is
refreshed every --status-refresh-every iterations (a tracked doc file
should not be rewritten hundreds of times an hour).

Kullanım: .venv/bin/python3 -u scripts/run_lns.py
"""
import argparse
import dataclasses
import json
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.model.constraints_capacity import compute_out_of_scope_baselines_from_keys
from src.model.lns import (
    compute_gamma_infeasible_pairs, compute_pair_slack, free_instances_for_pairs, select_pairs_by_component,
    select_worst_pairs,
)
from src.output.writer import write_output
from src.solve.subprocess_watchdog import solve_step_with_watchdog
from src.validate.independent_validator import finalize_reported_objective, recompute_objective, validate_output

from src.config.paths import FULL_OD, FULL_YV, FULL_CR, FULL_FP
from src.data.provenance import file_provenance
LNS_WORKER = Path(__file__).resolve().parent / "_lns_step_worker.py"
LNS_WORKER_FOLDED = Path(__file__).resolve().parent / "_lns_step_worker_folded.py"
PROGRESS_LOG = Path("runs/lns_progress.log")
STATUS_MD = Path("docs/STATUS.md")
STARTING_INCUMBENT = Path("runs/warm_start_elastic_output.json")

SLACK_EPS = 1e-3


def _load_starting_reference(candidates):
    data = json.loads(STARTING_INCUMBENT.read_text())
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
    assert not missing_arr, f"starting incumbent missing arr instances: {sorted(missing_arr)[:5]}"
    assert not missing_dep, f"starting incumbent missing dep instances: {sorted(missing_dep)[:5]}"
    return arr_times, dep_times


def _tune_m(pair_slack, candidates, target_low, target_high, m_base, exclude, max_tries=12):
    """Grows/shrinks m so the resulting free-instance count lands in
    [target_low, target_high] if at all possible; otherwise returns the
    closest attempt (preferring <=target_high over exceeding it)."""
    m = max(1, m_base)
    best = None
    for _ in range(max_tries):
        pairs = select_worst_pairs(pair_slack, m, exclude=exclude)
        if not pairs:
            return [], set(), set(), 0
        free_arr, free_dep = free_instances_for_pairs(candidates, pairs)
        total_free = len(free_arr) + len(free_dep)
        candidate_result = (pairs, free_arr, free_dep, total_free, m)
        if target_low <= total_free <= target_high:
            return pairs, free_arr, free_dep, total_free
        if best is None or (total_free <= target_high and total_free > best[3]) or (
            best[3] > target_high and total_free < best[3]
        ):
            best = candidate_result
        if total_free > target_high:
            if m <= 1:
                break
            m = max(1, m // 2)
        else:
            if len(pairs) < m:  # ran out of violating pairs -- can't grow further
                break
            m *= 2
    pairs, free_arr, free_dep, total_free, _ = best
    return pairs, free_arr, free_dep, total_free


def _log_progress(line: str):
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def _refresh_status_md(history, stamp):
    if not STATUS_MD.exists():
        return
    text = STATUS_MD.read_text()
    marker = "## LNS İlerleme (M5d)"
    recent = history[-15:]
    rows = "\n".join(
        f"| {h['iter']} | {h['status']} | {h['before_total']:.2f} | {h['after_total']:.2f} | "
        f"{h['n_free']} | {h['m']} | {h['solve_sec']:.1f}s |"
        for h in recent
    )
    section = (
        f"{marker}\n\n"
        f"Son güncelleme: {stamp}. Son {len(recent)} iterasyon (tam log: "
        f"`runs/lns_progress.log`, gitignored):\n\n"
        f"| iter | status | Σslack (önce) | Σslack (sonra) | serbest örnek | m | süre |\n"
        f"|---|---|---|---|---|---|---|\n{rows}\n"
    )
    if marker in text:
        head, _, tail_after_marker = text.partition(marker)
        # drop everything from the marker up to the next top-level '##' or EOF
        rest = tail_after_marker.split("\n## ", 1)
        tail = ("\n## " + rest[1]) if len(rest) > 1 else ""
        text = head + section + tail
    else:
        text = text.rstrip() + "\n\n" + section
    STATUS_MD.write_text(text)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--iter-time-limit-sec", type=float, default=120.0)
    parser.add_argument("--watchdog-margin-sec", type=float, default=60.0)
    parser.add_argument("--mip-gap", type=float, default=0.05)
    parser.add_argument("--mip-heuristic-effort", type=float, default=0.3)
    parser.add_argument("--m-base", type=int, default=20, help="starting worst-pair count for the m-tuning search")
    parser.add_argument("--target-low", type=int, default=400)
    parser.add_argument("--target-high", type=int, default=800)
    parser.add_argument("--max-iterations", type=int, default=200)
    parser.add_argument("--max-wall-sec", type=float, default=10800.0)
    parser.add_argument("--plateau-iters", type=int, default=20,
                         help="stop (report, don't error) after this many iterations without a new best")
    parser.add_argument("--selection", choices=["flat", "component"], default="flat",
                         help="M5d LNS redesign (plan a-evet-ama-iki-tingly-canyon.md, adım 2): 'flat' is the "
                              "original worst-slack-first/randomize targeting; 'component' targets one connected "
                              "component (via src.model.lns.select_pairs_by_component) at a time -- never splits "
                              "a connected violation-neighborhood across iterations, which flat targeting could.")
    parser.add_argument("--max-component-instances", type=int, default=800,
                         help="oversized-component split threshold for --selection component")
    parser.add_argument("--builder", choices=["fix", "folded"], default="fix",
                         help="M5d LNS redesign (plan a-evet-ama-iki-tingly-canyon.md, adım 3-9): 'fix' is the "
                              "original full-model + .fix() approach (~100+s/iteration presolve cost at full-data "
                              "scale); 'folded' builds real Var/rows ONLY for the free subset "
                              "(build_elastic_feasibility_model_folded, proven equivalent + genuinely smaller via "
                              "tests/solve/test_lns_fold_equivalence.py). 'fix' kept as a rollback/regression "
                              "baseline, not deleted.")
    parser.add_argument("--output", default="runs/lns_output.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epsilon", type=float, default=0.0,
                         help="deviation-tracking tie-breaker weight in add_elastic_feasibility_objective -- "
                              "smoke-tested finding (2026-07-11): epsilon=1e-6 (the original elastic-model "
                              "default) reproduced the familiar Nodes=0/no-incumbent stall even on a shrunk "
                              "(post-fix) LNS subproblem; epsilon=0 reached proven optimal on the same scale")
    parser.add_argument("--max-improving-sols", type=int, default=1,
                         help="HiGHS mip_max_improving_sols -- smoke-tested finding (2026-07-11): a warm-started "
                              "LNS subproblem DOES find improving incumbents (a feasibility-jump heuristic), but "
                              "HiGHS's own time_limit does not reliably stop cleanly afterwards (root-node cuts "
                              "keep running past the budget, same as every prior full-data attempt) -- this "
                              "forces a clean stop as soon as N improving solutions are found, per "
                              "docs/decisions.md 2026-07-10's mip_max_improving_sols=1 recovery trick")
    parser.add_argument("--adjustable-window-min", type=int, default=None,
                         help="M5e Bölüm 3d (VARSAYIM-3 override, ±180 our own choice, brief's Standard "
                              "tier states no limit): overrides config's adjustable_window_min for this "
                              "run only (candidate generation AND the validator's own window check). "
                              "Omit to use src/config/standard.yaml's value unchanged.")
    parser.add_argument("--deactivation-file", default=None,
                         help="D6 (Plan B, conflict-deactivation campaign, this session): path to a JSON "
                              "list of [o, d, gun] market-directions to fix x=0 for every LNS iteration "
                              "(src.model.deactivation). Only supported with --builder fix -- the folded "
                              "builder excludes frozen candidates from having a real x Var at all, so a "
                              "killed direction whose instances are frozen this iteration cannot be "
                              "re-fixed there (raises if combined with --builder folded).")
    args = parser.parse_args(argv)
    if args.deactivation_file and args.builder == "folded":
        raise ValueError("--deactivation-file is only supported with --builder fix (see help text)")
    random.seed(args.seed)

    script_t0 = time.time()
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    if args.adjustable_window_min is not None:
        config["adjustable_window_min"] = args.adjustable_window_min
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

    print(f"[run_lns] preprocessing done, n_candidates={len(candidates)}", flush=True)

    # Only needed for --builder folded (build_elastic_feasibility_model_folded
    # merges this with the CURRENT iteration's frozen instances) -- computed
    # once since it's schedule-independent (candidates' scope never changes
    # between iterations, only which subset is free/frozen does).
    true_out_of_scope_baselines = None
    if args.builder == "folded":
        full_arr_keys = {c.r1_id for c in candidates}
        full_dep_keys = {c.r2_id for c in candidates}
        true_out_of_scope_baselines = compute_out_of_scope_baselines_from_keys(
            tk, full_arr_keys, full_dep_keys, anchor,
        )
        print(f"[run_lns] true_out_of_scope_baselines: {len(true_out_of_scope_baselines)} instances", flush=True)

    reference_arr, reference_dep = _load_starting_reference(candidates)
    # M5d LNS redesign (adım 10 fix): --builder folded's result.selected/
    # gap_values only cover model.CANDIDATES for the CURRENT iteration's
    # free subset (unlike fix's, which always covers every candidate) --
    # maintain a running merged view, seeded from the starting reference's
    # own implied selection, so the final write_output call (whichever
    # iteration ends up "best") is never missing candidates that were
    # frozen the whole time or frozen in an earlier iteration.
    selected_full, gap_full = {}, {}
    for c in candidates:
        gap = reference_dep[c.r2_id] - reference_arr[c.r1_id]
        selected_full[c] = 1 if L <= gap <= U else 0
        gap_full[c] = gap

    pair_slack = compute_pair_slack(candidates, journey_constants, reference_arr, reference_dep, L, U, alpha, gamma)
    best_total = sum(v["total"] for v in pair_slack.values())
    n_e1_viol = sum(1 for v in pair_slack.values() if v["e1"] > 0)
    n_e2_viol = sum(1 for v in pair_slack.values() if v["e2"] > 0)
    print(f"[run_lns] starting Sigma-slack={best_total:.2f} (E1 pairs violated={n_e1_viol}, "
          f"E2 pairs violated={n_e2_viol})", flush=True)

    # M5d finding (docs/decisions.md 2026-07-11): "worst slack" selection
    # disproportionately picks pairs whose E2 violation is a journey_constant
    # ASYMMETRY that no schedule choice can ever close (best-case achievable
    # Jbest ranges are still >gamma apart) -- these are computed ONCE
    # (schedule-independent) and permanently excluded from targeting;
    # including even one stalled every sub-solve in smoke-testing.
    gamma_infeasible = compute_gamma_infeasible_pairs(candidates, journey_constants, L, U, gamma)
    print(f"[run_lns] gamma-infeasible pairs (excluded from targeting): {len(gamma_infeasible)}", flush=True)

    directions_to_kill = []
    if args.deactivation_file:
        directions_to_kill = [tuple(d) for d in json.loads(Path(args.deactivation_file).read_text())]
        print(f"[run_lns] Plan B: {len(directions_to_kill)} market-direction(s) deactivated "
              f"from {args.deactivation_file}", flush=True)

    model_kwargs_base = dict(
        candidates=candidates, journey_constants=journey_constants, pairs_df=pairs_df,
        r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor,
        alpha=alpha, gamma=gamma, tk_rows=tk, bucket_size_min=config["bucket_size_min"],
        capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"], L=L, U=U,
    )
    highs_log_dir = Path("runs") / f"lns_run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_highs_logs"
    highs_log_dir.mkdir(parents=True, exist_ok=True)
    solve_kwargs = dict(
        solver="highs", time_limit_sec=args.iter_time_limit_sec, seed=args.seed,
        mip_gap=args.mip_gap, mip_heuristic_effort=args.mip_heuristic_effort,
    )
    if args.max_improving_sols is not None:
        solve_kwargs["extra_highs_options"] = {"mip_max_improving_sols": args.max_improving_sols}

    history = []
    no_improve_streak = 0
    plateau_count = 0
    m_base = args.m_base
    randomize_mode = False
    best_result = None  # last SolveResult that achieved best_total
    last_improvement_iter = 0

    # --selection component driver state (owned here, select_pairs_by_component
    # itself is stateless -- mirrors m_base/randomize_mode above).
    stubborn = set()
    attempts_by_component = defaultdict(int)
    chunk_idx_by_component = defaultdict(int)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _log_progress(f"# LNS run started {stamp}, starting Sigma-slack={best_total:.2f}")

    for it in range(1, args.max_iterations + 1):
        if time.time() - script_t0 > args.max_wall_sec:
            _log_progress(f"iter={it} STOP wall-clock budget ({args.max_wall_sec}s) exceeded")
            break

        if best_total <= SLACK_EPS:
            break

        improved = False
        comp_id = None
        is_revisit = False
        if args.selection == "component":
            # comp_id is independent of chunk_index -- probe once with 0,
            # then re-call with the real stored chunk index for THAT
            # component if it's an oversized one we've visited before.
            pairs, free_arr, free_dep, comp_id, comp_size, is_revisit = select_pairs_by_component(
                pair_slack, candidates, gamma_infeasible, stubborn, attempts=attempts_by_component,
                max_instances=args.max_component_instances, seed=args.seed, chunk_index=0,
            )
            if comp_id is not None and chunk_idx_by_component[comp_id] != 0:
                pairs, free_arr, free_dep, comp_id, comp_size, is_revisit = select_pairs_by_component(
                    pair_slack, candidates, gamma_infeasible, stubborn, attempts=attempts_by_component,
                    max_instances=args.max_component_instances, seed=args.seed,
                    chunk_index=chunk_idx_by_component[comp_id],
                )
            n_free = len(free_arr) + len(free_dep)
            if pairs:
                chunk_idx_by_component[comp_id] += 1
                _log_progress(f"iter={it} PRE component comp_size={comp_size} n_pairs={len(pairs)} "
                              f"n_free={n_free} stubborn_revisit={is_revisit}")
        elif randomize_mode:
            positive = [p for p, s in pair_slack.items() if s["total"] > 0 and p not in gamma_infeasible]
            m = min(len(positive), max(m_base, args.m_base))
            pairs = random.sample(positive, m) if positive else []
            free_arr, free_dep = free_instances_for_pairs(candidates, pairs)
            n_free = len(free_arr) + len(free_dep)
        else:
            pairs, free_arr, free_dep, n_free = _tune_m(
                pair_slack, candidates, args.target_low, args.target_high, m_base, gamma_infeasible,
            )

        if not pairs:
            _log_progress(f"iter={it} STOP no violating pairs remain but Sigma-slack={best_total:.4f} > eps")
            break

        _log_progress(f"iter={it} PRE m~{len(pairs)} n_free={n_free} (before building) "
                       f"before_total={best_total:.2f} randomize={randomize_mode}")

        if args.builder == "folded":
            build_kwargs = {
                "model_kwargs": model_kwargs_base,
                "epsilon": args.epsilon,
                "true_out_of_scope_baselines": true_out_of_scope_baselines,
                "partition_kwargs": {
                    "reference_arr": reference_arr, "reference_dep": reference_dep,
                    "free_arr": free_arr, "free_dep": free_dep,
                },
            }
            worker_script = LNS_WORKER_FOLDED
        else:
            build_kwargs = {
                "model_kwargs": model_kwargs_base,
                "epsilon": args.epsilon,
                "fix_kwargs": {
                    "reference_arr": reference_arr, "reference_dep": reference_dep,
                    "free_arr": free_arr, "free_dep": free_dep,
                },
                "directions_to_kill": directions_to_kill,
            }
            worker_script = LNS_WORKER
        iter_solve_kwargs = dict(solve_kwargs, log_file=highs_log_dir / f"iter{it}.highs.log")
        t_solve = time.time()
        result, build_time_sec = solve_step_with_watchdog(
            build_kwargs, iter_solve_kwargs, time_limit_sec=args.iter_time_limit_sec,
            watchdog_margin_sec=args.watchdog_margin_sec, step_name=f"lns_iter{it}",
            worker_script=worker_script,
        )
        solve_sec = time.time() - t_solve

        if result.status not in ("optimal", "time_limit") or not result.arr_times:
            _log_progress(f"iter={it} status={result.status} NO USABLE RESULT (build={build_time_sec}) -- "
                           f"keeping previous reference")
            history.append({"iter": it, "status": result.status, "before_total": best_total,
                             "after_total": best_total, "n_free": n_free, "m": len(pairs), "solve_sec": solve_sec})
            no_improve_streak += 1
            if comp_id is not None:
                attempts_by_component[comp_id] += 1
                if attempts_by_component[comp_id] >= 2:
                    stubborn.add(comp_id)
                    _log_progress(f"iter={it} component marked STUBBORN (no usable result twice)")
        else:
            # M5d LNS redesign (adım 10 fix): --builder folded's
            # result.arr_times/dep_times only cover the FREE subset (unlike
            # fix's, which always covers every instance) -- merge onto the
            # CURRENT reference before recomputing slack or adopting, or the
            # frozen 90%+ of the point would be silently lost.
            merged_arr = {**reference_arr, **result.arr_times}
            merged_dep = {**reference_dep, **result.dep_times}
            after_slack = compute_pair_slack(candidates, journey_constants, merged_arr, merged_dep, L, U, alpha, gamma)
            after_total = sum(v["total"] for v in after_slack.values())
            improved = after_total < best_total - 1e-9
            rel_improve = (best_total - after_total) / best_total if best_total > 0 else 0.0
            _log_progress(f"iter={it} status={result.status} n_free={n_free} m={len(pairs)} "
                          f"before={best_total:.2f} after={after_total:.2f} rel_improve={rel_improve:.4f} "
                          f"solve_sec={solve_sec:.1f}")
            history.append({"iter": it, "status": result.status, "before_total": best_total,
                             "after_total": after_total, "n_free": n_free, "m": len(pairs), "solve_sec": solve_sec})

            if after_total <= best_total + 1e-9:
                reference_arr, reference_dep = merged_arr, merged_dep
                selected_full.update(result.selected)
                gap_full.update(result.gap_values or {})
                pair_slack = after_slack
                best_result = result
                if improved:
                    last_improvement_iter = it
                best_total = after_total

            if rel_improve < 0.01:
                no_improve_streak += 1
            else:
                no_improve_streak = 0
                plateau_count = 0
                randomize_mode = False

            if comp_id is not None:
                if improved:
                    stubborn.discard(comp_id)
                    attempts_by_component[comp_id] = 0
                else:
                    attempts_by_component[comp_id] += 1
                    if attempts_by_component[comp_id] >= 2:
                        stubborn.add(comp_id)
                        _log_progress(f"iter={it} component marked STUBBORN (2 attempts, no improvement)")

        if args.selection != "component" and no_improve_streak >= 2 and not randomize_mode:
            m_base *= 2
            _log_progress(f"iter={it} widening m_base -> {m_base} (2 consecutive <1% improvements)")
            no_improve_streak = 0
            plateau_count += 1

        if args.selection != "component" and plateau_count >= 2 and not randomize_mode:
            randomize_mode = True
            _log_progress(f"iter={it} switching to RANDOMIZE block selection (cycle-breaker)")

        if it % 5 == 0 or improved:
            _refresh_status_md(history, datetime.now(timezone.utc).isoformat())

        if randomize_mode and (it - last_improvement_iter) >= args.plateau_iters:
            _log_progress(f"iter={it} PLATEAU: no improvement in {it - last_improvement_iter} iterations "
                          f"even after widening+randomizing -- stopping per protocol")
            break

        # Adım 13 kabul kriteri (b): component seçiminde "tüm bileşenler
        # denendi" sinyali is_revisit=True'dur (non_stubborn havuzu
        # tükendi) -- bu moddayken plateau_iters kadar iyileşme
        # görülmezse (her bileşene en az bir revizit şansı tanınmış
        # demektir), inatçı bileşen dökümüyle DUR.
        if args.selection == "component" and is_revisit and (it - last_improvement_iter) >= args.plateau_iters:
            _log_progress(f"iter={it} PLATEAU: tüm bileşenler denendi, {it - last_improvement_iter} "
                          f"iterasyondur iyileşme yok -- stopping per protocol")
            break

    _refresh_status_md(history, datetime.now(timezone.utc).isoformat())

    # M5d LNS redesign (adım 10 fix): reconstruct a COMPLETE result for
    # write_output -- best_result's own raw .selected/.gap_values/
    # .arr_times/.dep_times may only cover the LAST iteration's free subset
    # (--builder folded); selected_full/gap_full/reference_arr/reference_dep
    # are the running merged view across every candidate/instance ever seen.
    if best_result is not None:
        best_result = dataclasses.replace(
            best_result, selected=selected_full, gap_values=gap_full,
            arr_times=reference_arr, dep_times=reference_dep,
        )

    if best_total <= SLACK_EPS and best_result is not None:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_output(output_path, best_result, k_od_sources=k_od_sources)
        recompute_total, _ = recompute_objective(
            output_path, FULL_OD, FULL_YV, FULL_CR, L=L, U=U, strict=False,
            breakdown_path=output_path.with_suffix(".objective_breakdown.json"),
        )
        reconciliation_ok, reconciliation_msg = finalize_reported_objective(
            output_path, recompute_total, best_result.status, best_result.objective_value,
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
        _log_progress(f"SLACK~0 REACHED -- validation_is_valid={is_valid} "
                      f"n_violations={len(validation.violations)} recompute_objective={recompute_total}")
        summary = {
            "final_sigma_slack": best_total, "validation_is_valid": is_valid,
            "n_violations": len(validation.violations), "recompute_objective_value": recompute_total,
            "reconciliation_ok": reconciliation_ok, "n_iterations": len(history),
        }
    else:
        _log_progress(f"STOP without reaching slack~0 -- final Sigma-slack={best_total:.2f} "
                      f"after {len(history)} iterations")
        summary = {
            "final_sigma_slack": best_total, "validation_is_valid": None,
            "n_iterations": len(history),
        }
        # Persist the best-so-far point even on a plateau stop -- otherwise
        # all that real (if partial) progress is lost the moment the process
        # exits, and a future session has to re-derive it from scratch.
        if best_result is not None:
            partial_path = Path("runs") / f"lns_best_partial_{stamp}.json"
            write_output(partial_path, best_result, k_od_sources=k_od_sources)
            final_slack = compute_pair_slack(
                candidates, journey_constants, best_result.arr_times, best_result.dep_times, L, U, alpha, gamma,
            )
            n_e1_final = sum(1 for v in final_slack.values() if v["e1"] > 0)
            n_e2_final = sum(1 for v in final_slack.values() if v["e2"] > 0)
            worst_remaining = sorted(
                final_slack.items(), key=lambda kv: -kv[1]["total"],
            )[:20]
            summary["partial_output_path"] = str(partial_path)
            summary["n_e1_pairs_violated_at_stop"] = n_e1_final
            summary["n_e2_pairs_violated_at_stop"] = n_e2_final
            summary["n_gamma_infeasible_pairs_excluded"] = len(gamma_infeasible)
            summary["worst_remaining_pairs"] = [
                {"pair": list(p), "e1": s["e1"], "e2": s["e2"], "total": s["total"]}
                for p, s in worst_remaining
            ]
            summary["slack_trajectory"] = [
                {"iter": h["iter"], "before_total": h["before_total"], "after_total": h["after_total"]}
                for h in history
            ]
            _log_progress(f"partial best-so-far point saved to {partial_path} "
                          f"(E1 violated={n_e1_final}, E2 violated={n_e2_final})")

            # Adım 13 kabul kriteri (b): "tüm bileşenler 2'şer denendi, slack
            # kaldı" durumunda inatçı bileşen dökümü (id/boyut/kalan
            # slack/denenen bütçe) -- attempts_by_component her görülen
            # bileşeni tutar (yalnızca stubborn kümesini değil), o yüzden
            # burada TÜM denenen bileşenler raporlanır, en inatçı en üstte.
            if args.selection == "component" and attempts_by_component:
                component_breakdown = []
                for comp, n_attempts in attempts_by_component.items():
                    remaining = sum(final_slack.get(p, {}).get("total", 0.0) for p in comp)
                    component_breakdown.append({
                        "component_id": f"comp_{abs(hash(comp)) % 100000}",
                        "size_pairs": len(comp),
                        "attempts": n_attempts,
                        "is_stubborn": comp in stubborn,
                        "remaining_slack": remaining,
                    })
                component_breakdown.sort(key=lambda d: -d["remaining_slack"])
                summary["stubborn_component_breakdown"] = component_breakdown
                _log_progress(f"stubborn component breakdown: {len(component_breakdown)} components tried, "
                              f"{sum(1 for c in component_breakdown if c['is_stubborn'])} marked stubborn")

    summary["data_provenance"] = {"FULL_OD": file_provenance(FULL_OD)}
    log_path = Path("runs") / f"lns_summary_{stamp}.log.json"
    log_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str))
    print(json.dumps(summary, indent=2, sort_keys=True, default=str), flush=True)
    print(f"\nSummary: {log_path}\nProgress log: {PROGRESS_LOG}", flush=True)
    return summary


if __name__ == "__main__":
    main()

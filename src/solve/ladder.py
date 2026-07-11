"""M5 solve ladder: fully-adjustable -> [M5f Kapı-5: elastic single-shot
fallback] -> adjustable-subset (escalating K, deprecated by default) ->
stop+diagnose. Doğruluk argümanı için bkz. tests/unit/test_solve_ladder.py
docstring.

Step 1 ve step 2'nin (K-subset) "başarı" kriteri AYNI: status=="optimal"
VEYA (status=="time_limit" ve objective_value is not None -- yani en az
bir feasible incumbent bulunmuş). status=="infeasible" veya "time_limit"
ama incumbent'sız (objective_value is None) sonraki adıma geçirir.

M5f Kapı-5 (docs/CLOSING_PLAN.md, "gizli test dayanıklılığı"): bir adımın
MIP-incumbent'a sahip olması onu TEK BAŞINA "kabul edilebilir" yapmaz --
`validate_fn` verilmişse (main.py'nin production yolu HER ZAMAN verir),
sonuç AYRICA bağımsız validator'dan SIFIR ihlalle geçmek ZORUNDA, yoksa
ladder BİR SONRAKİ adıma geçer (üretim çıktısına asla sessizce ihlalli bir
tarife YAZILMAZ). `validate_fn=None` (varsayılan, geriye-uyumluluk --
scripts/run_full_data.py gibi teşhis amaçlı çağıranlar) eski davranışı
korur: yalnızca incumbent varlığı yeterli.

Elastic single-shot fallback adımı (step1 kabul edilmezse, K-subset
merdiveninden ÖNCE denenir): build_elastic_feasibility_model (A/B/E1/E2/F/G,
slack-relaxed, koşullu E1 varsayılan) TEK bir bekçili solve ile denenir --
Σslack<=eps ise bu nokta zaten strict-feasible'dır (C/D hiç kurulmadığından
rank/beaten_rivals `src.model.ranking_derive.derive_ranking_results` ile
saf Python'da post-hoc türetilir). Bu, `scripts/run_lns.py`'nin çok
iterasyonlu (dakikalarca süren) kampanyasının BİR YERİNE geçmez -- ayrı,
uzun-soluklu bir teşhis/kampanya aracı olarak kalıyor (bkz. docs/decisions.md);
bu adım yalnızca "veri yeterince küçük/kolaysa TEK solve'da Σslack=0'a
ulaşılabilir mi" sorusuna TEK bir denemeyle cevap arar, tek bir üretim
komutunun makul bir bütçe içinde kalmasını garanti eder.
"""
import time
from pathlib import Path

from src.candidates.subset import apply_adjustable_subset
from src.model.build import build_elastic_feasibility_model, build_model_m4
from src.model.constraints_elastic import add_elastic_feasibility_objective
from src.model.lns import compute_pair_slack
from src.model.ranking_derive import derive_ranking_results
from src.solve.runner import SolveResult, solve as default_solve
from src.solve.subprocess_watchdog import solve_step_with_watchdog

import dataclasses

ELASTIC_FALLBACK_WORKER = Path(__file__).resolve().parent.parent.parent / "scripts" / "_elastic_feasibility_step_worker.py"
SLACK_EPS = 1e-6


def _accepted(result, candidates=None, validate_fn=None) -> bool:
    has_incumbent = result.status == "optimal" or (result.status == "time_limit" and result.objective_value is not None)
    if not has_incumbent:
        return False
    if validate_fn is None:
        return True
    return validate_fn(candidates, result)


def solve_with_ladder(
    candidates_full, rho, journey_constants, rival_data, b_od_data, ranking_table,
    pairs_df, r_o_lookup, tau, x_dev, epoch_anchor, alpha, gamma, tk_rows,
    bucket_size_min, capacity_departure, capacity_arrival, L, U, monotonic,
    step1_time_limit_sec: float = 900, step2_time_limit_sec: float = 300,
    step2_k_schedule: tuple = (50, 100, 200, 400),
    seed: int = 42, solver: str = "highs", solve_fn=default_solve,
    mip_gap: float = None, log_dir=None, deadline_ts: float = None,
    mip_heuristic_effort: float = None,
    use_subprocess_watchdog: bool = True, watchdog_margin_sec: float = 60,
    validate_fn=None, e1_activation: str = "conditional",
    enable_elastic_fallback: bool = False, elastic_time_limit_sec: float = 600,
    elastic_watchdog_margin_sec: float = 120, elastic_solve_fn=default_solve,
):
    ladder_log = []

    def _elastic_fallback(candidates, step_name="step_elastic_fallback"):
        if deadline_ts is not None and time.time() >= deadline_ts:
            model, result = _budget_exceeded(step_name)
            return model, result, False
        print(f"[ladder] {step_name}: build started (n_candidates={len(candidates)})", flush=True)
        log_file = Path(log_dir) / f"{step_name}.highs.log" if log_dir is not None else None

        if use_subprocess_watchdog and elastic_solve_fn is default_solve:
            build_kwargs = dict(
                candidates=candidates, journey_constants=journey_constants, pairs_df=pairs_df,
                r_o_lookup=r_o_lookup, tau=tau, x_dev=x_dev, epoch_anchor=epoch_anchor,
                alpha=alpha, gamma=gamma, tk_rows=tk_rows, bucket_size_min=bucket_size_min,
                capacity_departure=capacity_departure, capacity_arrival=capacity_arrival,
                L=L, U=U, e1_activation=e1_activation,
            )
            solve_kwargs = dict(
                solver=solver, time_limit_sec=elastic_time_limit_sec, seed=seed,
                mip_gap=mip_gap, log_file=log_file, mip_heuristic_effort=mip_heuristic_effort,
            )
            result, build_time_sec = solve_step_with_watchdog(
                build_kwargs, solve_kwargs, time_limit_sec=elastic_time_limit_sec,
                watchdog_margin_sec=elastic_watchdog_margin_sec, step_name=step_name,
                worker_script=ELASTIC_FALLBACK_WORKER,
            )
            print(f"[ladder] {step_name}: subprocess finished "
                  f"status={result.status} obj={result.objective_value}", flush=True)
        else:
            t0 = time.time()
            model = build_elastic_feasibility_model(
                candidates, journey_constants, pairs_df, r_o_lookup, tau=tau, x_dev=x_dev,
                epoch_anchor=epoch_anchor, alpha=alpha, gamma=gamma, tk_rows=tk_rows,
                bucket_size_min=bucket_size_min, capacity_departure=capacity_departure,
                capacity_arrival=capacity_arrival, L=L, U=U, e1_activation=e1_activation,
            )
            add_elastic_feasibility_objective(model)
            build_time_sec = time.time() - t0
            result = elastic_solve_fn(
                model, solver=solver, time_limit_sec=elastic_time_limit_sec, seed=seed,
                mip_gap=mip_gap, log_file=log_file,
            )
            print(f"[ladder] {step_name}: solve finished status={result.status} "
                  f"obj={result.objective_value}", flush=True)

        ladder_log.append({
            "step": step_name, "n_candidates": len(candidates),
            "build_time_sec": round(build_time_sec, 1) if build_time_sec is not None else None,
            "status": result.status, "objective_value": result.objective_value,
            "solve_time_sec": round(result.solve_time_sec, 1),
        })

        if result.status not in ("optimal", "time_limit") or not result.arr_times:
            print(f"[ladder] {step_name}: no usable elastic solution", flush=True)
            return None, result, False

        pair_slack = compute_pair_slack(
            candidates, journey_constants, result.arr_times, result.dep_times, L, U, alpha, gamma,
            e1_activation=e1_activation,
        )
        total_slack = sum(v["total"] for v in pair_slack.values())
        print(f"[ladder] {step_name}: Sigma-slack={total_slack:.2f}", flush=True)
        ladder_log[-1]["sigma_slack"] = total_slack
        if total_slack > SLACK_EPS:
            return None, result, False  # not strict-feasible -- elastic-only signal, not a candidate answer

        # Sigma-slack~0 -- this point already satisfies A/B/E1/E2/F/G. C/D
        # were never built (elastic model is A/B/E1/E2/F/G-only) -- their
        # reporting fields (rank/beaten_rivals) are derived post-hoc from
        # the now-FIXED (x,gap) assignment (src.model.ranking_derive),
        # mathematically identical to what add_d_constraints would have
        # forced for this exact point (see that module's docstring).
        rank_values, beaten_rivals = derive_ranking_results(
            candidates, rival_data, journey_constants, result.selected, result.gap_values,
        )
        result = dataclasses.replace(result, rank_values=rank_values, beaten_rivals=beaten_rivals)
        return None, result, True

    def _budget_exceeded(step_name):
        print(f"[ladder] {step_name}: SKIPPED -- wall-clock budget exceeded before this step could start", flush=True)
        ladder_log.append({
            "step": step_name, "status": "budget_exceeded",
            "reason": "wall-clock budget exceeded before this step could start",
        })
        return None, SolveResult(status="budget_exceeded", objective_value=None, selected={}, solve_time_sec=0.0)

    def _build_and_solve(candidates, time_limit_sec, step_name):
        if deadline_ts is not None and time.time() >= deadline_ts:
            return _budget_exceeded(step_name)
        print(f"[ladder] {step_name}: build started (n_candidates={len(candidates)})", flush=True)
        log_file = Path(log_dir) / f"{step_name}.highs.log" if log_dir is not None else None

        # M5 finding (docs/decisions.md 2026-07-09): appsi_highs's own
        # time_limit cannot reliably interrupt root-node cut generation on
        # large models -- a real solve can only be trusted to respect its
        # budget if something OUTSIDE the process enforces it. Tests inject
        # their own solve_fn (never default_solve) specifically to avoid a
        # real HiGHS call, so they're routed around the subprocess path
        # unconditionally -- only genuine production solves pay the
        # subprocess/pickle overhead.
        if use_subprocess_watchdog and solve_fn is default_solve:
            build_kwargs = dict(
                candidates=candidates, rho=rho, journey_constants=journey_constants,
                rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
                pairs_df=pairs_df, r_o_lookup=r_o_lookup, tau=tau, x_dev=x_dev,
                epoch_anchor=epoch_anchor, alpha=alpha, gamma=gamma, tk_rows=tk_rows,
                bucket_size_min=bucket_size_min, capacity_departure=capacity_departure,
                capacity_arrival=capacity_arrival, L=L, U=U, monotonic=monotonic,
            )
            solve_kwargs = dict(
                solver=solver, time_limit_sec=time_limit_sec, seed=seed,
                mip_gap=mip_gap, log_file=log_file, mip_heuristic_effort=mip_heuristic_effort,
            )
            result, build_time_sec = solve_step_with_watchdog(
                build_kwargs, solve_kwargs, time_limit_sec=time_limit_sec,
                watchdog_margin_sec=watchdog_margin_sec, step_name=step_name,
            )
            model = None  # owned by the (possibly-killed) subprocess, never available here
            print(f"[ladder] {step_name}: subprocess finished "
                  f"status={result.status} obj={result.objective_value}", flush=True)
        else:
            t0 = time.time()
            model = build_model_m4(
                candidates, rho, journey_constants, rival_data, b_od_data, ranking_table,
                pairs_df, r_o_lookup, tau=tau, x_dev=x_dev, epoch_anchor=epoch_anchor,
                alpha=alpha, gamma=gamma, tk_rows=tk_rows, bucket_size_min=bucket_size_min,
                capacity_departure=capacity_departure, capacity_arrival=capacity_arrival,
                L=L, U=U, monotonic=monotonic,
            )
            build_time_sec = time.time() - t0
            print(f"[ladder] {step_name}: build finished in {build_time_sec:.1f}s, "
                  f"solve started (time_limit={time_limit_sec}s, mip_gap={mip_gap})", flush=True)
            t1 = time.time()
            result = solve_fn(
                model, solver=solver, time_limit_sec=time_limit_sec, seed=seed,
                mip_gap=mip_gap, log_file=log_file,
            )
            solve_time_sec = time.time() - t1
            print(f"[ladder] {step_name}: solve finished in {solve_time_sec:.1f}s "
                  f"status={result.status} obj={result.objective_value}", flush=True)

        ladder_log.append({
            "step": step_name,
            "n_candidates": len(candidates),
            "build_time_sec": round(build_time_sec, 1) if build_time_sec is not None else None,
            "status": result.status,
            "objective_value": result.objective_value,
            "solve_time_sec": round(result.solve_time_sec, 1),
            "model_stats": result.model_stats,
        })
        return model, result

    model, result = _build_and_solve(candidates_full, step1_time_limit_sec, "step1_full_adjustable")
    if _accepted(result, candidates_full, validate_fn):
        return model, result, ladder_log

    if enable_elastic_fallback:
        model, result, is_candidate = _elastic_fallback(candidates_full)
        if is_candidate and (validate_fn is None or validate_fn(candidates_full, result)):
            return model, result, ladder_log

    markets_by_rho = sorted({(c.o, c.d) for c in candidates_full}, key=lambda m: -rho.get(m, 0))
    for k in step2_k_schedule:
        print(f"[ladder] step2: trying K={k}", flush=True)
        adjustable_markets = set(markets_by_rho[:k])
        subset_candidates = apply_adjustable_subset(candidates_full, adjustable_markets, L=L, U=U)
        model, result = _build_and_solve(subset_candidates, step2_time_limit_sec, f"step2_subset_k{k}")
        if _accepted(result, subset_candidates, validate_fn):
            return model, result, ladder_log

    print("[ladder] step3: no accepted solution at any step -- stopping (diagnostic)", flush=True)
    ladder_log.append({
        "step": "step3_stop_diagnose",
        "reason": "no accepted solution at step1 or any step2_k_schedule value -- stopping per M5 protocol, not proceeding silently",
    })
    # M5f Kapı-5: the last-attempted result's OWN status can still read
    # "optimal" (e.g. the elastic fallback solved ITS OWN relaxed problem
    # to optimality even though Sigma-slack>0, or a validate_fn rejection)
    # -- a caller checking status/objective_value alone (the established
    # pattern, see scripts/run_full_data.py) must not mistake this for an
    # accepted answer. Normalized here so "reached step3" is unambiguous
    # from the return value alone, without changing the tuple arity every
    # existing caller already unpacks. "budget_exceeded" is left AS-IS --
    # it is already unambiguous and scripts/run_full_data.py distinguishes
    # it (STEP0 vs STEP3 diagnostic messages) from a genuine solve failure.
    if result.status != "budget_exceeded":
        result = SolveResult(status="no_feasible_solution_found", objective_value=None, selected={}, solve_time_sec=0.0)
    return model, result, ladder_log

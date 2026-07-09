"""M5 solve ladder: fully-adjustable -> adjustable-subset (escalating K) ->
stop+diagnose. Doğruluk argümanı için bkz. tests/unit/test_solve_ladder.py
docstring.

Step 1 ve step 2'nin "başarı" kriteri AYNI: status=="optimal" VEYA
(status=="time_limit" ve objective_value is not None -- yani en az bir
feasible incumbent bulunmuş). status=="infeasible" veya "time_limit" ama
incumbent'sız (objective_value is None, bkz. src.solve.runner'ın
maxTimeLimit-no-incumbent savunma dalı) sonraki adıma geçirir.
"""
import time
from pathlib import Path

from src.candidates.subset import apply_adjustable_subset
from src.model.build import build_model_m4
from src.solve.runner import SolveResult, solve as default_solve
from src.solve.subprocess_watchdog import solve_step_with_watchdog


def _accepted(result) -> bool:
    return result.status == "optimal" or (result.status == "time_limit" and result.objective_value is not None)


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
):
    ladder_log = []

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
    if _accepted(result):
        return model, result, ladder_log

    markets_by_rho = sorted({(c.o, c.d) for c in candidates_full}, key=lambda m: -rho.get(m, 0))
    for k in step2_k_schedule:
        print(f"[ladder] step2: trying K={k}", flush=True)
        adjustable_markets = set(markets_by_rho[:k])
        subset_candidates = apply_adjustable_subset(candidates_full, adjustable_markets, L=L, U=U)
        model, result = _build_and_solve(subset_candidates, step2_time_limit_sec, f"step2_subset_k{k}")
        if _accepted(result):
            return model, result, ladder_log

    print("[ladder] step3: no accepted solution at any step -- stopping (diagnostic)", flush=True)
    ladder_log.append({
        "step": "step3_stop_diagnose",
        "reason": "no accepted solution at step1 or any step2_k_schedule value -- stopping per M5 protocol, not proceeding silently",
    })
    return model, result, ladder_log

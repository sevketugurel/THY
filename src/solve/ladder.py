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

from src.candidates.subset import apply_adjustable_subset
from src.model.build import build_model_m4
from src.solve.runner import solve as default_solve


def _accepted(result) -> bool:
    return result.status == "optimal" or (result.status == "time_limit" and result.objective_value is not None)


def solve_with_ladder(
    candidates_full, rho, journey_constants, rival_data, b_od_data, ranking_table,
    pairs_df, r_o_lookup, tau, x_dev, epoch_anchor, alpha, gamma, tk_rows,
    bucket_size_min, capacity_departure, capacity_arrival, L, U, monotonic,
    step1_time_limit_sec: float = 900, step2_time_limit_sec: float = 300,
    step2_k_schedule: tuple = (50, 100, 200, 400),
    seed: int = 42, solver: str = "highs", solve_fn=default_solve,
):
    ladder_log = []

    def _build_and_solve(candidates, time_limit_sec, step_name):
        t0 = time.time()
        model = build_model_m4(
            candidates, rho, journey_constants, rival_data, b_od_data, ranking_table,
            pairs_df, r_o_lookup, tau=tau, x_dev=x_dev, epoch_anchor=epoch_anchor,
            alpha=alpha, gamma=gamma, tk_rows=tk_rows, bucket_size_min=bucket_size_min,
            capacity_departure=capacity_departure, capacity_arrival=capacity_arrival,
            L=L, U=U, monotonic=monotonic,
        )
        build_time_sec = time.time() - t0
        result = solve_fn(model, solver=solver, time_limit_sec=time_limit_sec, seed=seed)
        ladder_log.append({
            "step": step_name,
            "n_candidates": len(candidates),
            "build_time_sec": round(build_time_sec, 1),
            "status": result.status,
            "objective_value": result.objective_value,
            "solve_time_sec": round(result.solve_time_sec, 1),
        })
        return model, result

    model, result = _build_and_solve(candidates_full, step1_time_limit_sec, "step1_full_adjustable")
    if _accepted(result):
        return model, result, ladder_log

    markets_by_rho = sorted({(c.o, c.d) for c in candidates_full}, key=lambda m: -rho.get(m, 0))
    for k in step2_k_schedule:
        adjustable_markets = set(markets_by_rho[:k])
        subset_candidates = apply_adjustable_subset(candidates_full, adjustable_markets, L=L, U=U)
        model, result = _build_and_solve(subset_candidates, step2_time_limit_sec, f"step2_subset_k{k}")
        if _accepted(result):
            return model, result, ladder_log

    ladder_log.append({
        "step": "step3_stop_diagnose",
        "reason": "no accepted solution at step1 or any step2_k_schedule value -- stopping per M5 protocol, not proceeding silently",
    })
    return model, result, ladder_log

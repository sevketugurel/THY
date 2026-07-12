"""Full-data warm-start solve pipeline (M5d): A+G+F -> elastic -> reward model."""
from pathlib import Path

from src.solve.runner import SolveResult
from src.solve.subprocess_watchdog import solve_step_with_watchdog

_CORE_WORKER = Path(__file__).resolve().parent.parent.parent / "scripts" / "_core_feasibility_step_worker.py"
_ELASTIC_WORKER = Path(__file__).resolve().parent.parent.parent / "scripts" / "_warm_start_elastic_step_worker.py"
_REWARD_WORKER = Path(__file__).resolve().parent.parent.parent / "scripts" / "_warm_start_reward_step_worker.py"


def _accepted(result: SolveResult) -> bool:
    return result.status == "optimal" or (
        result.status == "time_limit" and result.objective_value is not None
    )


def solve_full_data_warm(
    *,
    candidates,
    rho,
    journey_constants,
    rival_data,
    b_od_data,
    ranking_table,
    pairs_df,
    r_o_lookup,
    tk_rows,
    anchor,
    config,
    core_time_limit_sec: float = 600.0,
    elastic_time_limit_sec: float = 120.0,
    reward_time_limit_sec: float = 120.0,
    watchdog_margin_sec: float = 60.0,
    reward_watchdog_margin_sec: float = 300.0,
    log_dir: Path = None,
) -> tuple[SolveResult, list]:
    """Three-step warm pipeline. Returns (best_result, step_log)."""
    L, U = config["L"], config["U"]
    alpha, gamma = config["alpha"], config["gamma"]
    bucket_size_min = config["bucket_size_min"]
    seed = config["seed"]
    step_log = []

    core_build = dict(
        candidates=candidates, pairs_df=pairs_df, r_o_lookup=r_o_lookup,
        tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor, tk_rows=tk_rows,
        bucket_size_min=bucket_size_min, capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"],
    )
    core_solve = dict(
        solver="highs", time_limit_sec=core_time_limit_sec, seed=seed,
        mip_gap=0.08, mip_heuristic_effort=0.3,
    )
    print(f"[warm_pipeline] step1: A+G+F core (limit={core_time_limit_sec}s)...", flush=True)
    core_result, core_build_sec = solve_step_with_watchdog(
        core_build, core_solve, time_limit_sec=core_time_limit_sec,
        watchdog_margin_sec=watchdog_margin_sec, step_name="warm_core_agf",
        worker_script=_CORE_WORKER,
    )
    step_log.append({
        "step": "warm_core_agf", "status": core_result.status,
        "objective_value": core_result.objective_value, "build_time_sec": core_build_sec,
    })
    if not _accepted(core_result) or not core_result.arr_times:
        print("[warm_pipeline] ABORT: A+G+F failed", flush=True)
        return core_result, step_log

    elastic_build = {
        "model_kwargs": dict(
            candidates=candidates, journey_constants=journey_constants, pairs_df=pairs_df,
            r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"], epoch_anchor=anchor,
            alpha=alpha, gamma=gamma, tk_rows=tk_rows, bucket_size_min=bucket_size_min,
            capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"],
            L=L, U=U,
        ),
        "warm_start_kwargs": dict(
            candidates=candidates, journey_constants=journey_constants,
            arr_times=core_result.arr_times, dep_times=core_result.dep_times,
            L=L, U=U, alpha=alpha, gamma=gamma, bucket_size_min=bucket_size_min, epoch_anchor=anchor,
        ),
    }
    elastic_log = Path(log_dir) / "warm_elastic.highs.log" if log_dir else None
    elastic_solve = dict(
        solver="highs", time_limit_sec=elastic_time_limit_sec, seed=seed,
        mip_gap=0.08, mip_heuristic_effort=0.3,
        extra_highs_options={"mip_max_improving_sols": 1},
        log_file=elastic_log,
    )
    print(f"[warm_pipeline] step2: elastic warm-start (limit={elastic_time_limit_sec}s)...", flush=True)
    elastic_result, elastic_build_sec = solve_step_with_watchdog(
        elastic_build, elastic_solve, time_limit_sec=elastic_time_limit_sec,
        watchdog_margin_sec=watchdog_margin_sec, step_name="warm_elastic",
        worker_script=_ELASTIC_WORKER,
    )
    step_log.append({
        "step": "warm_elastic", "status": elastic_result.status,
        "objective_value": elastic_result.objective_value, "build_time_sec": elastic_build_sec,
    })

    arr_times = elastic_result.arr_times or core_result.arr_times
    dep_times = elastic_result.dep_times or core_result.dep_times
    warm_from = "elastic" if elastic_result.arr_times else "core"

    reward_build = {
        "model_kwargs": dict(
            candidates=candidates, rho=rho, journey_constants=journey_constants,
            rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
            pairs_df=pairs_df, r_o_lookup=r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
            epoch_anchor=anchor, alpha=alpha, gamma=gamma, tk_rows=tk_rows,
            bucket_size_min=bucket_size_min, capacity_departure=config["capacity_departure"],
            capacity_arrival=config["capacity_arrival"], L=L, U=U, monotonic=True,
        ),
        "warm_start_kwargs": dict(
            candidates=candidates, journey_constants=journey_constants, rival_data=rival_data,
            arr_times=arr_times, dep_times=dep_times, L=L, U=U, gamma=gamma,
            bucket_size_min=bucket_size_min, epoch_anchor=anchor, alpha=alpha,
        ),
    }
    reward_log = Path(log_dir) / "warm_reward.highs.log" if log_dir else None
    reward_solve = dict(
        solver="highs", time_limit_sec=reward_time_limit_sec, seed=seed,
        mip_gap=config.get("mip_gap", 0.01), mip_heuristic_effort=0.3,
        extra_highs_options={"mip_max_improving_sols": 1},
        log_file=reward_log,
    )
    print(f"[warm_pipeline] step3: full reward warm-start from {warm_from} "
          f"(limit={reward_time_limit_sec}s)...", flush=True)
    reward_result, reward_build_sec = solve_step_with_watchdog(
        reward_build, reward_solve, time_limit_sec=reward_time_limit_sec,
        watchdog_margin_sec=reward_watchdog_margin_sec, step_name="warm_reward",
        worker_script=_REWARD_WORKER,
    )
    step_log.append({
        "step": "warm_reward", "status": reward_result.status,
        "objective_value": reward_result.objective_value, "build_time_sec": reward_build_sec,
        "warm_from": warm_from,
    })

    if _accepted(reward_result):
        return reward_result, step_log
    if _accepted(elastic_result):
        return elastic_result, step_log
    return core_result, step_log

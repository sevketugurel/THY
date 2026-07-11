#!/usr/bin/env python3
"""Internal worker for scripts/run_lns.py's subprocess watchdog (--builder
folded) -- NOT meant to be invoked directly. Builds
build_elastic_feasibility_model_folded (real Var/row only for the current
iteration's free instances -- see src/model/build.py, plan
.claude/plans/a-evet-ama-iki-tingly-canyon.md adım 8/9) and solves cold (no
warm-start -- src/model/warm_start.py's module docstring explains why: the
folded model's free subproblem is small enough to not need one, and
model.Jbest is a pyo.Expression there, not a settable Var).

Usage: python -u scripts/_lns_step_worker_folded.py <input.pkl> <output.pkl>

NOTE: result.arr_times/dep_times returned here cover ONLY the free subset
(model.ARR_INSTANCES/DEP_INSTANCES in the folded model) -- the caller MUST
merge with its own reference dict to reconstruct the full point, unlike the
fix-based worker where arr_times/dep_times always cover every instance.
"""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyomo.environ as pyo

from src.model.build import build_elastic_feasibility_model_folded
from src.model.constraints_elastic import add_elastic_feasibility_objective
from src.model.partition import partition_by_freedom
from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    t0 = time.time()
    model_kwargs = spec["build_kwargs"]["model_kwargs"]
    partition_kwargs = spec["build_kwargs"]["partition_kwargs"]
    partition = partition_by_freedom(
        model_kwargs["candidates"], partition_kwargs["free_arr"], partition_kwargs["free_dep"],
        partition_kwargs["reference_arr"], partition_kwargs["reference_dep"],
        model_kwargs["L"], model_kwargs["U"],
    )
    model = build_elastic_feasibility_model_folded(
        partition=partition,
        true_out_of_scope_baselines=spec["build_kwargs"].get("true_out_of_scope_baselines"),
        **model_kwargs,
    )
    epsilon = spec["build_kwargs"].get("epsilon", 0.0)
    add_elastic_feasibility_objective(model, epsilon=epsilon)
    build_time_sec = time.time() - t0
    n_rows = sum(1 for _ in model.component_data_objects(pyo.Constraint, active=True))
    print(f"[_lns_step_worker_folded] model built in {build_time_sec:.1f}s (rows={n_rows})", flush=True)

    result = solve(model, **spec["solve_kwargs"])
    print(f"[_lns_step_worker_folded] solve finished status={result.status}", flush=True)

    with open(output_path, "wb") as f:
        pickle.dump({
            "status": result.status, "objective_value": result.objective_value,
            "selected": result.selected, "solve_time_sec": result.solve_time_sec,
            "gap_values": result.gap_values, "arr_times": result.arr_times,
            "dep_times": result.dep_times, "rank_values": result.rank_values,
            "beaten_rivals": result.beaten_rivals, "model_stats": result.model_stats,
            "build_time_sec": build_time_sec, "n_rows": n_rows,
        }, f)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Internal worker for scripts/run_local_branching.py's subprocess watchdog --
NOT meant to be invoked directly. Builds build_model_m4 (the real hard-
constrained reward model, Jbest-fix included), adds a local-branching
trust-region constraint (src.model.local_branching.add_local_branching)
around a reference (arr_times, dep_times) point, then solves normally (no
warm-start -- the reference point is known infeasible for hard E1/E2, see
docs/decisions.md 2026-07-10; local branching lets HiGHS find its OWN
feasible correction within a bounded neighborhood instead).

Usage: python -u scripts/_local_branching_step_worker.py <input.pkl> <output.pkl>
"""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model.build import build_model_m4
from src.model.local_branching import add_local_branching
from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    t0 = time.time()
    model = build_model_m4(**spec["build_kwargs"]["model_kwargs"])
    lb_kwargs = spec["build_kwargs"]["local_branch_kwargs"]
    add_local_branching(
        model, lb_kwargs["reference_arr"], lb_kwargs["reference_dep"], lb_kwargs["k"],
    )
    build_time_sec = time.time() - t0

    result = solve(model, **spec["solve_kwargs"])

    with open(output_path, "wb") as f:
        pickle.dump({
            "status": result.status, "objective_value": result.objective_value,
            "selected": result.selected, "solve_time_sec": result.solve_time_sec,
            "gap_values": result.gap_values, "arr_times": result.arr_times,
            "dep_times": result.dep_times, "rank_values": result.rank_values,
            "beaten_rivals": result.beaten_rivals, "model_stats": result.model_stats,
            "build_time_sec": build_time_sec,
        }, f)


if __name__ == "__main__":
    main()

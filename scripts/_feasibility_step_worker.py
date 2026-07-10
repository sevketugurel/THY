#!/usr/bin/env python3
"""Internal worker for scripts/run_feasibility_only.py's subprocess watchdog --
NOT meant to be invoked directly. Same purpose as scripts/_deviation_step_worker.py
but builds with build_feasibility_model (A/B/E1/E2/F/G only -- no C, no D,
no reward objective) instead of build_model_m4, then adds the min-deviation
objective (M5c §3, docs/decisions.md 2026-07-10 -- "Plan B" while the
reward+full-constraint model's root node stays stuck).

Usage: python -u scripts/_feasibility_step_worker.py <input.pkl> <output.pkl>
"""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model.build import build_feasibility_model
from src.model.deviation_objective import add_min_deviation_objective
from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    t0 = time.time()
    model = build_feasibility_model(**spec["build_kwargs"])
    add_min_deviation_objective(model)
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

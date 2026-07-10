#!/usr/bin/env python3
"""Internal worker for scripts/run_core_feasibility.py's subprocess watchdog
-- NOT meant to be invoked directly. Builds with build_core_feasibility_model
(A/G/F only, no B/C/D/E1/E2) then adds the min-deviation objective.

Usage: python -u scripts/_core_feasibility_step_worker.py <input.pkl> <output.pkl>
"""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model.build import build_core_feasibility_model
from src.model.deviation_objective import add_min_deviation_objective
from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    t0 = time.time()
    model = build_core_feasibility_model(**spec["build_kwargs"])
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

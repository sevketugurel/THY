#!/usr/bin/env python3
"""Internal worker for scripts/run_conflict_deactivation_feasibility.py's
subprocess watchdog -- NOT meant to be invoked directly. Builds
build_feasibility_model (A/B/E1c/E2/F/G, all HARD constraints, no C/D --
src/model/build.py), applies src.model.deactivation.apply_deactivation for
the given market-directions (D1: model.x[i].fix(0) for every candidate in
each killed direction, applied AFTER build so B's own reification stays
intact), then adds the min-deviation objective and solves. A feasible
incumbent here is ALREADY strictly A/B/E1/E2/F/G-valid by construction (no
slack variables exist in this model) -- see build_feasibility_model's own
docstring for why C/D's absence doesn't change the (t,x,gap) feasible set.

Usage: python -u scripts/_conflict_deactivation_step_worker.py <input.pkl> <output.pkl>
"""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model.build import build_feasibility_model
from src.model.deactivation import apply_deactivation, market_direction_index
from src.model.deviation_objective import add_min_deviation_objective
from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    t0 = time.time()
    model_kwargs = spec["build_kwargs"]["model_kwargs"]
    model = build_feasibility_model(**model_kwargs)

    directions_to_kill = spec["build_kwargs"].get("directions_to_kill") or []
    direction_index = market_direction_index(model_kwargs["candidates"])
    n_fixed = apply_deactivation(model, direction_index, directions_to_kill)

    add_min_deviation_objective(model)
    build_time_sec = time.time() - t0
    print(f"[_conflict_deactivation_step_worker] model built in {build_time_sec:.1f}s, "
          f"{len(directions_to_kill)} direction(s) deactivated ({n_fixed} candidates fixed)", flush=True)

    result = solve(model, **spec["solve_kwargs"])
    print(f"[_conflict_deactivation_step_worker] solve finished status={result.status}", flush=True)

    with open(output_path, "wb") as f:
        pickle.dump({
            "status": result.status, "objective_value": result.objective_value,
            "selected": result.selected, "solve_time_sec": result.solve_time_sec,
            "gap_values": result.gap_values, "arr_times": result.arr_times,
            "dep_times": result.dep_times, "rank_values": result.rank_values,
            "beaten_rivals": result.beaten_rivals, "model_stats": result.model_stats,
            "build_time_sec": build_time_sec, "n_candidates_fixed": n_fixed,
        }, f)


if __name__ == "__main__":
    main()

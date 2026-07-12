#!/usr/bin/env python3
"""Internal worker for scripts/warm_start_elastic.py's subprocess watchdog --
NOT meant to be invoked directly. Builds build_elastic_feasibility_model,
derives+sets a full warm-start assignment from a raw (arr_times, dep_times)
point (src.model.warm_start.derive_and_set_warm_start), then solves with
warmstart=True.

Usage: python -u scripts/_warm_start_elastic_step_worker.py <input.pkl> <output.pkl>
"""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model.build import build_elastic_feasibility_model
from src.model.constraints_elastic import add_elastic_feasibility_objective
from src.model.deactivation import apply_deactivation, market_direction_index
from src.model.warm_start import derive_and_set_warm_start
from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    # solve_step_with_watchdog always pickles {"build_kwargs":...,
    # "solve_kwargs":...} -- this worker needs TWO distinct kwarg sets
    # (model construction + warm-start derivation), so they travel nested
    # inside build_kwargs as model_kwargs/warm_start_kwargs.
    t0 = time.time()
    model_kwargs = spec["build_kwargs"]["model_kwargs"]
    model = build_elastic_feasibility_model(**model_kwargs)
    # Order matters: the objective creates the deviation-tracking vars that
    # derive_and_set_warm_start also needs to set -- must run first.
    add_elastic_feasibility_objective(model)
    summary = derive_and_set_warm_start(model, **spec["build_kwargs"]["warm_start_kwargs"])
    # D6 (Plan B, conflict-deactivation campaign): optional -- apply the SAME
    # market-direction kill set a build_feasibility_model attempt used. Runs
    # LAST, AFTER derive_and_set_warm_start: that function sets model.x[i]
    # .value from the PRE-deactivation reference point, which may say x=1
    # for a candidate this kill set wants at 0 -- .fix(0) here must be the
    # final word (Pyomo's .fix() both marks fixed=True and pins .value, so
    # running it after warm-start guarantees the deactivated candidates are
    # genuinely fixed regardless of what the stale warm-start hint said).
    # Absent/empty directions_to_kill is a no-op, identical to before this.
    directions_to_kill = spec["build_kwargs"].get("directions_to_kill") or []
    if directions_to_kill:
        direction_index = market_direction_index(model_kwargs["candidates"])
        apply_deactivation(model, direction_index, directions_to_kill)
    build_time_sec = time.time() - t0

    result = solve(model, warmstart=True, **spec["solve_kwargs"])

    with open(output_path, "wb") as f:
        pickle.dump({
            "status": result.status, "objective_value": result.objective_value,
            "selected": result.selected, "solve_time_sec": result.solve_time_sec,
            "gap_values": result.gap_values, "arr_times": result.arr_times,
            "dep_times": result.dep_times, "rank_values": result.rank_values,
            "beaten_rivals": result.beaten_rivals, "model_stats": result.model_stats,
            "build_time_sec": build_time_sec, "warm_start_summary": summary,
        }, f)


if __name__ == "__main__":
    main()

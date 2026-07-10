#!/usr/bin/env python3
"""Internal worker for scripts/run_elastic_feasibility.py's subprocess
watchdog -- NOT meant to be invoked directly. Builds with
build_elastic_feasibility_model (A/B/F/G + slack-relaxed E1/E2, no C/D)
then adds add_elastic_feasibility_objective.

The slack breakdown (which pairs, how much) is NOT carried by the pickled
SolveResult -- subprocess_watchdog.py's payload schema is fixed and this
worker doesn't control it. Instead it's written to its OWN JSON file,
derived deterministically from solve_kwargs['log_file'] (same directory,
'.slack.json' suffix) so the parent process can read it back without any
change to the shared watchdog module.

Usage: python -u scripts/_elastic_feasibility_step_worker.py <input.pkl> <output.pkl>
"""
import json
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyomo.environ as pyo

from src.model.build import build_elastic_feasibility_model
from src.model.constraints_elastic import add_elastic_feasibility_objective
from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    t0 = time.time()
    model = build_elastic_feasibility_model(**spec["build_kwargs"])
    add_elastic_feasibility_objective(model)
    build_time_sec = time.time() - t0

    result = solve(model, **spec["solve_kwargs"])

    if result.status in ("optimal", "time_limit") and result.objective_value is not None:
        slack_by_pair = {"e1": {}, "e2": {}}
        if hasattr(model, "s_e1"):
            for k in model.s_e1:
                v = pyo.value(model.s_e1[k])
                if v > 1e-6:
                    slack_by_pair["e1"][str(k)] = v
        if hasattr(model, "s_e2"):
            for k in model.s_e2:
                v = pyo.value(model.s_e2[k])
                if v > 1e-6:
                    slack_by_pair["e2"][str(k)] = v
        log_file = spec["solve_kwargs"].get("log_file")
        if log_file is not None:
            slack_path = Path(log_file).with_suffix(".slack.json")
            slack_path.write_text(json.dumps(slack_by_pair, indent=2, sort_keys=True))

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

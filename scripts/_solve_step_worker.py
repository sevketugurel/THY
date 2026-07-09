#!/usr/bin/env python3
"""Internal worker for src.solve.subprocess_watchdog -- NOT meant to be
invoked directly by a human. Builds+solves exactly ONE ladder step in its
own OS process so the caller can enforce a HARD wall-clock limit via
SIGTERM/SIGKILL from outside, because appsi_highs's own time_limit cannot
reliably interrupt root-node cut generation on large models (see
docs/decisions.md 2026-07-09 "appsi_highs time_limit kok-dugum cut
turlarini KESEMIYOR" -- a single cut round on a 605K-row presolved model
overran a configured 600s time_limit by more than 2x with zero incumbent).

Usage: python -u scripts/_solve_step_worker.py <input.pkl> <output.pkl>
Reads a pickled {"build_kwargs":..., "solve_kwargs":...} dict from
input.pkl, writes a pickled result-fields dict to output.pkl. If this
process is killed before finishing, output.pkl simply never appears -- the
caller (src.solve.subprocess_watchdog.solve_step_with_watchdog) treats a
missing output file as "no incumbent, watchdog killed".
"""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model.build import build_model_m4
from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    t0 = time.time()
    model = build_model_m4(**spec["build_kwargs"])
    build_time_sec = time.time() - t0

    result = solve(model, **spec["solve_kwargs"])

    with open(output_path, "wb") as f:
        pickle.dump({
            "status": result.status,
            "objective_value": result.objective_value,
            "selected": result.selected,
            "solve_time_sec": result.solve_time_sec,
            "gap_values": result.gap_values,
            "arr_times": result.arr_times,
            "dep_times": result.dep_times,
            "rank_values": result.rank_values,
            "beaten_rivals": result.beaten_rivals,
            "model_stats": result.model_stats,
            "build_time_sec": build_time_sec,
        }, f)


if __name__ == "__main__":
    main()

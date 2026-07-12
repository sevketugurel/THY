#!/usr/bin/env python3
"""Worker: build_model_m4 + warm-start from A+G+F/elastic point + reward solve."""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model.build import build_model_m4
from src.model.warm_start import derive_and_set_warm_start_full
from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    t0 = time.time()
    model = build_model_m4(**spec["build_kwargs"]["model_kwargs"])
    derive_and_set_warm_start_full(model, **spec["build_kwargs"]["warm_start_kwargs"])
    build_time_sec = time.time() - t0

    result = solve(model, warmstart=True, **spec["solve_kwargs"])

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

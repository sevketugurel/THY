#!/usr/bin/env python3
"""Internal worker for scripts/diagnose_e1_e2_f.py's subprocess watchdog --
NOT meant to be invoked directly. Same purpose as scripts/_solve_step_worker.py
(build+solve in an isolated OS process so a hard wall-clock kill is possible
from outside -- see docs/decisions.md 2026-07-09) but calls the DIAGNOSTIC
model variant (diagnose_e1_e2_f.py's _build_variant, which selectively omits
E1/E2/F) instead of the production build_model_m4. Kept as a SEPARATE script
so the production worker (scripts/_solve_step_worker.py) never imports
diagnostic-only code.

Usage: python -u scripts/_diagnose_step_worker.py <input.pkl> <output.pkl>
"""
import importlib.util
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "diagnose_e1_e2_f", Path(__file__).resolve().parent / "diagnose_e1_e2_f.py",
)
_diag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_diag)

from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    t0 = time.time()
    model = _diag._build_variant(**spec["build_kwargs"])
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

"""Deterministic JSON output writer.

Output schema (VARSAYIM -- brief does not specify an exact format, see plan §7
"Açık Sorular"): objective_value, selected_connections[], adjusted_flight_times[],
solver_metrics. Connections are sorted by (od, flno1, flno2), adjusted times by
(role, flno, gun), for stable, byte-identical output across runs with the same
input and seed (plan §6 determinism requirement).

M1: selected_connections' gap_min now reports the ACTUAL solved gap (via
result.gap_values), not the static baseline -- falls back to the candidate's
baseline gap_min when gap_values is empty (M0's trivial model, no B/gap
variables exist there).
"""
import json
from pathlib import Path

from src.solve.runner import SolveResult


def write_output(path: Path, result: SolveResult) -> None:
    selected = sorted(
        (c for c, x in result.selected.items() if x == 1),
        key=lambda c: (c.od, c.flno1, c.flno2),
    )
    gap_values = result.gap_values or {}

    adjusted_times = []
    for r_id, time_min in {**(result.arr_times or {}), **(result.dep_times or {})}.items():
        role, flno, gun = r_id
        adjusted_times.append({"role": role, "flno": flno, "gun": gun, "time_min": time_min})
    adjusted_times.sort(key=lambda e: (e["role"], e["flno"], e["gun"]))

    data = {
        "objective_value": result.objective_value,
        "selected_connections": [
            {
                "od": c.od, "flno1": c.flno1, "flno2": c.flno2,
                "gun": c.gun, "gap_min": gap_values.get(c, c.gap_min),
            }
            for c in selected
        ],
        "adjusted_flight_times": adjusted_times,
        "solver_metrics": {
            "status": result.status,
            "solve_time_sec": result.solve_time_sec,
        },
    }

    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

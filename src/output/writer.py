"""Deterministic JSON output writer.

Output schema (VARSAYIM -- brief does not specify an exact format, see plan §7
"Açık Sorular"): objective_value, selected_connections[], solver_metrics.
Connections are sorted by (od, flno1, flno2) for stable, byte-identical output
across runs with the same input and seed (plan §6 determinism requirement).
"""
import json
from pathlib import Path

from src.solve.runner import SolveResult


def write_output(path: Path, result: SolveResult) -> None:
    selected = sorted(
        (c for c, x in result.selected.items() if x == 1),
        key=lambda c: (c.od, c.flno1, c.flno2),
    )

    data = {
        "objective_value": result.objective_value,
        "selected_connections": [
            {
                "od": c.od, "flno1": c.flno1, "flno2": c.flno2,
                "gun": c.gun, "gap_min": c.gap_min,
            }
            for c in selected
        ],
        "solver_metrics": {
            "status": result.status,
            "solve_time_sec": result.solve_time_sec,
        },
    }

    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

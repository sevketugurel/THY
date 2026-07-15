"""Deterministic benchmark output writer with diagnostics."""

import json
from pathlib import Path


def write_benchmark_output(
    path,
    times: dict,
    connections: list,
    ranking_results: list,
    k_od_sources: dict,
    status: str,
    solve_time_sec: float,
    diagnostics: dict,
) -> None:
    adjusted = [
        {"role": role, "flno": flno, "gun": gun, "time_min": time_min}
        for (role, flno, gun), time_min in times.items()
    ]
    adjusted.sort(key=lambda e: (e["role"], e["flno"], e["gun"]))

    k_od_source_list = [
        {"o": o, "d": d, "source": source}
        for (o, d), source in (k_od_sources or {}).items()
    ]
    k_od_source_list.sort(key=lambda e: (e["o"], e["d"]))

    data = {
        "objective_value": None,
        "selected_connections": connections,
        "adjusted_flight_times": adjusted,
        "ranking_results": ranking_results,
        "k_od_sources": k_od_source_list,
        "solver_metrics": {"status": status, "solve_time_sec": solve_time_sec},
        "diagnostics": diagnostics,
    }
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def stamp_recomputed_objective(path, total: float) -> None:
    patch_json_field(path, ["objective_value"], total)


def patch_json_field(path, keys: list, value) -> None:
    data = json.loads(Path(path).read_text())
    node = data
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

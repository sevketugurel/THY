"""Deterministic JSON output writer.

Output schema (VARSAYIM -- brief does not specify an exact format, see plan §7
"Açık Sorular"): objective_value, selected_connections[], adjusted_flight_times[],
ranking_results[], solver_metrics. Lists are sorted by their natural key for
stable, byte-identical output across runs with the same input and seed (plan
§6 determinism requirement).

M1: selected_connections' gap_min reports the ACTUAL solved gap (via
result.gap_values), not the static baseline -- falls back to the candidate's
baseline gap_min when gap_values is empty (M0's trivial model, no B/gap
variables exist there).

M2: ranking_results[] reports per-market rank + beaten rivals (brief §5
"O–D bazında yenilen rakipler" deliverable requirement) -- empty when the
model has no D constraints (M0/M1).

M5: k_od_sources[] reports, per (o,d) market, whether its journey constant
came from a direct row-median (VARSAYIM-8 "direct") or the bipartite
least-squares fallback ("estimated") -- lets a reviewer see which markets'
numbers rest on thinner data. Optional (callers that don't pass
k_od_sources, e.g. the M0-M4 test suite, get an empty list).
"""
import json
from pathlib import Path

from src.solve.runner import SolveResult


def write_output(path: Path, result: SolveResult, k_od_sources: dict = None) -> None:
    selected = sorted(
        (c for c, x in result.selected.items() if x == 1),
        key=lambda c: (c.od, c.flno1, c.flno2),
    )
    gap_values = result.gap_values or {}

    adjusted_times = []
    for r_id, time_min in {**(result.arr_times or {}), **(result.dep_times or {})}.items():
        role, flno, gun = r_id
        adjusted_times.append({
            "role": role, "flno": flno, "gun": gun, "time_min": time_min,
            "time_hhmm": f"{(time_min % 1440) // 60:02d}:{time_min % 60:02d}",
        })
    adjusted_times.sort(key=lambda e: (e["role"], e["flno"], e["gun"]))

    ranking_results = []
    for market, rank in (result.rank_values or {}).items():
        o, d, gun = market
        beaten = sorted((result.beaten_rivals or {}).get(market, []))
        ranking_results.append({"o": o, "d": d, "gun": gun, "rank": rank, "beaten_rivals": beaten})
    ranking_results.sort(key=lambda e: (e["o"], e["d"], e["gun"]))

    k_od_source_list = [
        {"o": o, "d": d, "source": source} for (o, d), source in (k_od_sources or {}).items()
    ]
    k_od_source_list.sort(key=lambda e: (e["o"], e["d"]))

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
        "ranking_results": ranking_results,
        "k_od_sources": k_od_source_list,
        "solver_metrics": {
            "status": result.status,
            "solve_time_sec": result.solve_time_sec,
        },
    }

    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

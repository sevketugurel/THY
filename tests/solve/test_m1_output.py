"""M1: solver result must expose actual solved gap/flight-times (not just x),
output writer must report them, and the independent validator must check
against the OUTPUT's own reported times (not just static baseline data) --
now that M1 introduces genuine time adjustment, re-deriving from raw baseline
data alone would both false-flag legitimately shifted flights and fail to
catch a corrupted claim of an out-of-window time.

marker: solve (small HiGHS solve, <60s).
"""
import json
from pathlib import Path

import pytest

from src.candidates.generate import generate_candidates
from src.data.loaders import load_od_table, load_yolcu_verisi
from src.model.build import build_model
from src.output.writer import write_output
from src.solve.runner import solve
from src.validate.independent_validator import validate_output

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.solve

L, U = 60, 300


@pytest.fixture
def solved_result():
    od_table = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXDIR / "synthetic_yolcu_verisi.xlsx")
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=0, adjustable_set="none",
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    model = build_model(candidates, rho, L=L, U=U)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    return result, candidates


def test_solve_result_exposes_actual_gap_and_flight_times(solved_result):
    result, candidates = solved_result
    selected_candidate = next(c for c, x in result.selected.items() if x == 1)

    assert selected_candidate in result.gap_values
    assert result.gap_values[selected_candidate] == selected_candidate.gap_min  # Rfix -> matches baseline

    assert selected_candidate.r1_id in result.arr_times
    assert selected_candidate.r2_id in result.dep_times


def test_write_output_reports_adjusted_flight_times(tmp_path, solved_result):
    result, candidates = solved_result
    path = tmp_path / "output.json"
    write_output(path, result)

    data = json.loads(path.read_text())
    assert "adjusted_flight_times" in data
    assert len(data["adjusted_flight_times"]) > 0
    entry = data["adjusted_flight_times"][0]
    assert set(entry.keys()) == {"role", "flno", "gun", "time_min", "time_hhmm"}

    # selected_connections must report the ACTUAL solved gap, not a stale field
    assert all("gap_min" in c for c in data["selected_connections"])


def test_validator_passes_output_with_genuinely_valid_adjusted_times(tmp_path, solved_result):
    result, candidates = solved_result
    path = tmp_path / "output.json"
    write_output(path, result)

    validation = validate_output(
        path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U,
        adjustable_window_min=0, adjustable_set="none",
    )
    assert validation.is_valid
    assert validation.violations == []


def test_validator_catches_reported_time_outside_legal_window(tmp_path, solved_result):
    result, candidates = solved_result
    path = tmp_path / "output.json"
    write_output(path, result)

    data = json.loads(path.read_text())
    # Corrupt one adjusted time to fall outside its (degenerate, Rfix) window.
    data["adjusted_flight_times"][0]["time_min"] += 500
    path.write_text(json.dumps(data))

    validation = validate_output(
        path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U,
        adjustable_window_min=0, adjustable_set="none",
    )
    assert not validation.is_valid
    assert any("window" in v.lower() for v in validation.violations)

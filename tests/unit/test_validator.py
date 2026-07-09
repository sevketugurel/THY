"""Unit tests for src.validate.independent_validator.

This module must be independently verifiable of src.model.* / src.candidates.* --
it re-derives gap validity from the OUTPUT's own reported adjusted_flight_times
(never a connection's claimed gap_min display field) and checks those reported
times against a legal window independently re-derived from raw data. See plan
§1 "validate/ modelin Pyomo kodundan hiç import almayan ayrı bir mantık yolu"
(diskalifiye sigortası).

marker: unit (solver-free, pure logic).
"""
import json
from pathlib import Path

import pytest

from src.validate.independent_validator import recompute_objective, validate_output

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.unit

L, U = 60, 300


def _write_output(tmp_path, connections, adjusted_times):
    data = {
        "objective_value": 0.0,
        "selected_connections": connections,
        "adjusted_flight_times": adjusted_times,
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }
    path = tmp_path / "output.json"
    path.write_text(json.dumps(data))
    return path


def test_validate_passes_for_hand_verified_valid_connections(tmp_path):
    # MI1xMO2 (baseline gap=60) and NI1xNO2 (baseline gap=205) from
    # fixtures/README.md, reported at their exact baseline (Rfix) times.
    output_path = _write_output(
        tmp_path,
        connections=[
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
        ],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 795},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
        ],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert result.is_valid
    assert result.violations == []


def test_validate_catches_gap_below_l(tmp_path):
    # MI1xMO1 has baseline gap=-360 (deliberately invalid per fixtures/README.md).
    output_path = _write_output(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9111, "gun": 1, "gap_min": -360}],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9111, "gun": 1, "time_min": 480},
        ],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("gap" in v.lower() for v in result.violations)


def test_validate_ignores_claimed_gap_min_and_recomputes_from_adjusted_times(tmp_path):
    # Output CLAIMS gap_min=60 (valid) via the display field, but the reported
    # adjusted_flight_times actually give gap=-360 (MI1xMO1's real gap) --
    # validator must use the TIMES, not the claimed display value.
    output_path = _write_output(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9111, "gun": 1, "gap_min": 60}],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9111, "gun": 1, "time_min": 480},
        ],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid


def test_validate_accepts_synthesized_pairing_of_two_real_legs(tmp_path):
    # RB2(9401, inbound leg of ZZB-ZZA) and NO2(9212, outbound leg of ZZB-ZZA)
    # each individually exist as real TK flights on Gün=1, but the raw O&D
    # table never lists them PAIRED TOGETHER in one row (confirmed by
    # inspection). The model's candidate generation is a full inbound x
    # outbound cross-product (plan §4) -- a synthesized pairing of two real
    # legs is a legitimate candidate, not a fabrication. Baseline: RB2 arr=555,
    # NO2 dep=1000 -> gap=445 (invalid at baseline, but a real pairing).
    output_path = _write_output(
        tmp_path,
        connections=[{"od": "ZZB-ZZA", "flno1": 9401, "flno2": 9212, "gun": 1, "gap_min": 445}],
        adjusted_times=[
            {"role": "IB", "flno": 9401, "gun": 1, "time_min": 555},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
        ],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not any("not found" in v.lower() for v in result.violations), result.violations
    # (still correctly flagged for gap=445 > U=300, just NOT as "not found")
    assert any("gap" in v.lower() for v in result.violations)


def test_validate_catches_nonexistent_flight_reference(tmp_path):
    output_path = _write_output(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 99999, "flno2": 88888, "gun": 1, "gap_min": 100}],
        adjusted_times=[],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("not found" in v.lower() for v in result.violations)


def test_validate_catches_reported_time_outside_legal_window(tmp_path):
    # Rfix (adjustable_set defaults to "none") -- reported time must equal
    # baseline EXACTLY; a claimed deviation must be flagged.
    output_path = _write_output(
        tmp_path,
        connections=[],
        adjusted_times=[{"role": "IB", "flno": 9101, "gun": 1, "time_min": 840 + 500}],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("window" in v.lower() for v in result.violations)


def _write_output_with_ranking(tmp_path, connections, adjusted_times, ranking_results):
    data = {
        "objective_value": 0.0,
        "selected_connections": connections,
        "adjusted_flight_times": adjusted_times,
        "ranking_results": ranking_results,
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }
    path = tmp_path / "output.json"
    path.write_text(json.dumps(data))
    return path


def test_validate_passes_correctly_reported_beaten_rivals_and_rank(tmp_path):
    # MI1xMO2, J=280, correctly beats R1(300) not R2(250) -- matches
    # fixtures/README.md hand calc: N=2, beaten=[R1], rank=1.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60}],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
        ],
        ranking_results=[{"o": "ZZA", "d": "ZZB", "gun": 1, "rank": 1, "beaten_rivals": ["R1"]}],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert result.is_valid, result.violations


def test_validate_catches_fabricated_beaten_rival(tmp_path):
    # Same offered connection (only beats R1), but output FALSELY claims R2
    # (250) was also beaten -- J=280 does not beat T_comp=250.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60}],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
        ],
        ranking_results=[{"o": "ZZA", "d": "ZZB", "gun": 1, "rank": 0, "beaten_rivals": ["R1", "R2"]}],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("R2" in v and "beaten" in v.lower() for v in result.violations)


def test_validate_allows_under_claimed_beaten_rivals(tmp_path):
    # Forward-only D forcing (monotonic W(r)) can legitimately leave a
    # genuinely-beatable rival unclaimed in a flat-reward-tie scenario (e.g.
    # beating N-1 vs N rivals both land on the same clamped r=1) -- this is
    # NOT a violation (claimed subset of actual is always reward-safe, never
    # inflated). NI1xNO2 reported at arr=700,dep=820 (within each leg's
    # +-180min window of baseline 795/1000) -> gap=120, J=K_od(240)+120=360,
    # which genuinely beats ALL THREE rivals (R3=500,R4=400,R5=445) -- but
    # only R3,R5 are claimed, R4 deliberately left out.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[{"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 120}],
        adjusted_times=[
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 700},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 820},
        ],
        ranking_results=[{"o": "ZZB", "d": "ZZA", "gun": 1, "rank": 1, "beaten_rivals": ["R3", "R5"]}],
    )
    result = validate_output(
        output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U,
        adjustable_window_min=180, adjustable_set="all",
    )
    assert result.is_valid, result.violations


def test_validate_catches_rank_inconsistent_with_beaten_count(tmp_path):
    # beaten_rivals correctly lists just R1, but claimed rank doesn't match
    # N(2) - len(beaten)(1) = 1.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60}],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
        ],
        ranking_results=[{"o": "ZZA", "d": "ZZB", "gun": 1, "rank": 99, "beaten_rivals": ["R1"]}],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("rank" in v.lower() for v in result.violations)


def test_recompute_objective_matches_m2_hand_calc(tmp_path):
    # adjustable_set:none baseline scenario (fixtures/README.md M2 eki):
    # connection_reward=400.0 (200x2 days), ranking_reward=100.0 (Gün1 only,
    # Gün2 has no rival data), total=500.0.
    data = {
        "objective_value": 500.0,
        "selected_connections": [
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
            {"od": "ZZA-ZZB", "flno1": 9102, "flno2": 9112, "gun": 1, "gap_min": 300},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 2, "gap_min": 85},
            {"od": "ZZA-ZZB", "flno1": 9102, "flno2": 9112, "gun": 2, "gap_min": 300},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 2, "gap_min": 200},
        ],
        "adjusted_flight_times": [
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "IB", "flno": 9102, "gun": 1, "time_min": 600},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 795},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
            {"role": "IB", "flno": 9101, "gun": 2, "time_min": 1440 + 815},
            {"role": "IB", "flno": 9102, "gun": 2, "time_min": 1440 + 600},
            {"role": "OB", "flno": 9112, "gun": 2, "time_min": 1440 + 900},
            {"role": "IB", "flno": 9201, "gun": 2, "time_min": 1440 + 800},
            {"role": "OB", "flno": 9212, "gun": 2, "time_min": 1440 + 1000},
        ],
        "ranking_results": [],
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps(data))
    breakdown_path = tmp_path / "breakdown.json"

    total, breakdown = recompute_objective(
        output_path, FIXDIR / "synthetic_od_table.xlsx",
        FIXDIR / "synthetic_yolcu_verisi.xlsx", FIXDIR / "synthetic_change_ranking_input.xlsx",
        L=L, U=U, breakdown_path=breakdown_path,
    )

    assert total == pytest.approx(500.0)
    assert breakdown["connection_reward"] == pytest.approx(400.0)
    assert breakdown["ranking_reward"] == pytest.approx(100.0)
    assert breakdown_path.exists()
    written = json.loads(breakdown_path.read_text())
    assert written["total"] == pytest.approx(500.0)

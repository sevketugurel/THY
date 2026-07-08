"""Unit tests for src.validate.independent_validator.

This module must be independently verifiable of src.model.* / src.candidates.* --
it re-derives gap validity from raw arr_time/dep_time itself rather than trusting
any value the model already computed. See plan §1 "validate/ modelin Pyomo
kodundan hiç import almayan ayrı bir mantık yolu" (diskalifiye sigortası).

marker: unit (solver-free, pure logic).
"""
import json
from pathlib import Path

import pytest

from src.validate.independent_validator import validate_output

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.unit

L, U = 60, 300


def _write_output(tmp_path, connections):
    data = {
        "objective_value": 0.0,
        "selected_connections": connections,
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }
    path = tmp_path / "output.json"
    path.write_text(json.dumps(data))
    return path


def test_validate_passes_for_hand_verified_valid_connections(tmp_path):
    # MI1xMO2 (gap=60) and NI1xNO2 (gap=205) from fixtures/README.md.
    output_path = _write_output(tmp_path, [
        {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
        {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
    ])
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert result.is_valid
    assert result.violations == []


def test_validate_catches_gap_below_l(tmp_path):
    # MI1xMO1 has gap=-360 (deliberately invalid per fixtures/README.md).
    output_path = _write_output(tmp_path, [
        {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9111, "gun": 1, "gap_min": -360},
    ])
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert len(result.violations) == 1
    assert "gap" in result.violations[0].lower()


def test_validate_recomputes_gap_independently_ignoring_claimed_value(tmp_path):
    # Output CLAIMS gap_min=60 (valid) but the real flights (9101 x 9111) actually
    # have gap=-360 -- validator must recompute from raw data, not trust the claim.
    output_path = _write_output(tmp_path, [
        {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9111, "gun": 1, "gap_min": 60},
    ])
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid


def test_validate_catches_nonexistent_flight_reference(tmp_path):
    output_path = _write_output(tmp_path, [
        {"od": "ZZA-ZZB", "flno1": 99999, "flno2": 88888, "gun": 1, "gap_min": 100},
    ])
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("not found" in v.lower() for v in result.violations)

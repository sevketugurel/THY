"""Unit tests for scripts.validate_output.check_schema.

marker: unit (no solver, no data files).
"""
import pytest

from scripts.validate_output import check_schema

pytestmark = pytest.mark.unit


def _minimal_valid() -> dict:
    return {
        "objective_value": 668.75,
        "selected_connections": [
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 80}
        ],
        "adjusted_flight_times": [
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 670},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 750},
        ],
        "ranking_results": [
            {"o": "ZZA", "d": "ZZB", "gun": 1, "rank": 1, "beaten_rivals": ["R1"]}
        ],
        "k_od_sources": [],
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.18},
    }


def test_schema_valid_minimal():
    assert check_schema(_minimal_valid()) == []


def test_schema_missing_top_level_field():
    data = _minimal_valid()
    del data["selected_connections"]
    errors = check_schema(data)
    assert any("selected_connections" in e for e in errors)


def test_schema_extra_top_level_field():
    data = _minimal_valid()
    data["unknown_field"] = "surprise"
    errors = check_schema(data)
    assert any("spec dışı" in e and "unknown_field" in e for e in errors)


def test_schema_diagnostics_not_flagged_as_extra():
    data = _minimal_valid()
    data["diagnostics"] = {"mode": "benchmark_full_claim"}
    assert check_schema(data) == []


def test_schema_objective_null_allowed():
    data = _minimal_valid()
    data["objective_value"] = None
    assert check_schema(data) == []


def test_schema_duplicate_connection():
    data = _minimal_valid()
    data["selected_connections"].append(
        {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 80}
    )
    errors = check_schema(data)
    assert any("yinelenen bağlantı" in e for e in errors)


def test_schema_duplicate_adjusted_time():
    data = _minimal_valid()
    data["adjusted_flight_times"].append(
        {"role": "IB", "flno": 9101, "gun": 1, "time_min": 671}
    )
    errors = check_schema(data)
    assert any("yinelenen adjusted_flight_times" in e for e in errors)


def test_schema_invalid_role():
    data = _minimal_valid()
    data["adjusted_flight_times"][0]["role"] = "XX"
    errors = check_schema(data)
    assert any("role" in e and "geçersiz" in e for e in errors)


def test_schema_missing_connection_field():
    data = _minimal_valid()
    del data["selected_connections"][0]["gap_min"]
    errors = check_schema(data)
    assert any("gap_min" in e for e in errors)


def test_schema_null_connection_field():
    data = _minimal_valid()
    data["selected_connections"][0]["od"] = None
    errors = check_schema(data)
    assert any("od" in e and "null" in e for e in errors)


def test_schema_missing_ranking_field():
    data = _minimal_valid()
    del data["ranking_results"][0]["beaten_rivals"]
    errors = check_schema(data)
    assert any("beaten_rivals" in e for e in errors)


def test_schema_rank_zero_allowed_no_rivals():
    # rank=0 rivalsiz pazarda geçerli (validator expected_rank=0 döndürür)
    data = _minimal_valid()
    data["ranking_results"][0]["rank"] = 0
    assert check_schema(data) == []


def test_schema_rank_negative_rejected():
    data = _minimal_valid()
    data["ranking_results"][0]["rank"] = -1
    errors = check_schema(data)
    assert any("rank" in e for e in errors)


def test_schema_solver_metrics_missing_status():
    data = _minimal_valid()
    del data["solver_metrics"]["status"]
    errors = check_schema(data)
    assert any("status" in e for e in errors)

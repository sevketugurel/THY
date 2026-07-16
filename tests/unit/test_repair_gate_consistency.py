"""Repair full-gate diagnostics consistency tests."""

import pytest

from scripts.repair_e1_e2_local import _assert_gate_consistency, _build_gate_diagnostics
from src.validate.independent_validator import ValidationResult, summarize_violation_families

pytestmark = pytest.mark.unit


def _claim(*, complete=True, missing=0, extra=0):
    return {
        "claim_complete": complete,
        "missing_claims": missing,
        "extra_claims": extra,
    }


def test_stale_clean_diagnostics_are_rejected():
    claim = _claim()
    validation = ValidationResult(
        is_valid=False,
        violations=["E1 AAA-BBB Gün=1: |n_fwd(2)-n_bwd(0)| exceeds alpha"],
    )
    data = {
        "objective_value": 10.0,
        "diagnostics": {
            "claim_complete": True,
            "missing_claims": 0,
            "extra_claims": 0,
            "claim_check": {"missing_claims": 0, "extra_claims": 0},
            "strict_feasible": True,
            "strict_violations": {"total": 0, "total_pairs": 0, "by_family": {}},
        },
    }

    with pytest.raises(RuntimeError, match="diagnostics.strict_feasible"):
        _assert_gate_consistency(data, claim, validation, 10.0)


def test_gate_diagnostics_overwrite_stale_clean_state():
    claim = _claim()
    validation = ValidationResult(
        is_valid=False,
        violations=["E2 AAA-BBB Gün=1: |Jbest_fwd(500)-Jbest_bwd(400)| exceeds Gamma(30)"],
    )
    families = summarize_violation_families(validation.violations)
    data = {
        "objective_value": 999.0,
        "diagnostics": {
            "strict_feasible": True,
            "strict_violations": {"total": 0, "total_pairs": 0, "by_family": {}},
        },
    }

    data["objective_value"] = 123.456
    data["diagnostics"] = _build_gate_diagnostics(
        families=families,
        claim=claim,
        strict_feasible=validation.is_valid,
        moves=(),
        objective=123.456,
        dropped_markets=0,
    )

    _assert_gate_consistency(data, claim, validation, 123.456, families)
    assert data["diagnostics"]["strict_feasible"] is False
    assert data["diagnostics"]["strict_violations"]["by_family"] == {"E2": 1}


def test_objective_value_must_match_recompute_total():
    claim = _claim()
    validation = ValidationResult(is_valid=True, violations=[])
    families = summarize_violation_families(validation.violations)
    data = {
        "objective_value": 100.0,
        "diagnostics": _build_gate_diagnostics(
            families=families,
            claim=claim,
            strict_feasible=True,
            moves=(),
            objective=100.0,
            dropped_markets=0,
        ),
    }

    _assert_gate_consistency(data, claim, validation, 100.0, families)
    with pytest.raises(RuntimeError, match="objective_value"):
        _assert_gate_consistency(data, claim, validation, 101.0, families)


def test_claim_counts_are_reflected_in_diagnostics():
    claim = _claim(complete=False, missing=2, extra=1)
    validation = ValidationResult(is_valid=False, violations=["connection AAA-BBB FlNo1=1 FlNo2=2 Gün=1: gap=30min outside [60,300]"])
    families = summarize_violation_families(validation.violations)
    data = {
        "objective_value": 50.0,
        "diagnostics": _build_gate_diagnostics(
            families=families,
            claim=claim,
            strict_feasible=validation.is_valid,
            moves=(),
            objective=50.0,
            dropped_markets=0,
        ),
    }

    _assert_gate_consistency(data, claim, validation, 50.0, families)
    assert data["diagnostics"]["claim_complete"] is False
    assert data["diagnostics"]["missing_claims"] == 2
    assert data["diagnostics"]["extra_claims"] == 1
    assert data["diagnostics"]["claim_check"] == {"missing_claims": 2, "extra_claims": 1}

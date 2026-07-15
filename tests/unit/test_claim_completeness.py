"""Claim-completeness equality tests for the independent validator."""

import json
from pathlib import Path

import pytest

from src.validate.independent_validator import summarize_violation_families, validate_claim_completeness

pytestmark = pytest.mark.unit

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_OUTPUT = "outputs/fixture_output.json"


def _load_fixture_output():
    return json.loads(Path(FIXTURE_OUTPUT).read_text())


def test_untampered_fixture_output_is_claim_complete(tmp_path):
    p = tmp_path / "out.json"
    p.write_text(json.dumps(_load_fixture_output()))
    res = validate_claim_completeness(p, FIXTURE_OD, FIXTURE_YV, L=60, U=300)
    assert res["claim_complete"] is True
    assert res["missing_claims"] == 0
    assert res["extra_claims"] == 0


def test_missing_claim_detected(tmp_path):
    data = _load_fixture_output()
    data["selected_connections"].pop(0)
    p = tmp_path / "out.json"
    p.write_text(json.dumps(data))
    res = validate_claim_completeness(p, FIXTURE_OD, FIXTURE_YV, L=60, U=300)
    assert res["missing_claims"] == 1
    assert res["claim_complete"] is False


def test_extra_claim_detected(tmp_path):
    data = _load_fixture_output()
    fake = dict(data["selected_connections"][0])
    fake["flno2"] = 99999
    data["selected_connections"].append(fake)
    p = tmp_path / "out.json"
    p.write_text(json.dumps(data))
    res = validate_claim_completeness(p, FIXTURE_OD, FIXTURE_YV, L=60, U=300)
    assert res["extra_claims"] == 1
    assert res["claim_complete"] is False


def test_summarize_violation_families_prefix_classifier():
    violations = [
        "E1 AAA-BBB Gün=1: |n_fwd(2)-n_bwd(0)| exceeds alpha(0.2)*(n_fwd+n_bwd)",
        "E2 AAA-BBB Gün=1: |Jbest_fwd(500)-Jbest_bwd(400)| exceeds Gamma(30)",
        "E2 CCC-DDD Gün=2: |Jbest_fwd(700)-Jbest_bwd(500)| exceeds Gamma(30)",
        "rotation FlNo(OB)=5 Gün=1 FlNo(IB)=6 Gün=1: IST arrival 100 < required minimum 200",
        "F kova(departure) bucket=12: 11 uçuş, kalan kapasite 10",
        "regularity (x_dev) role=IB FlNo=7 küme=[1, 2]: gün-içi spread=40min exceeds X_dev=15",
        "connection AAA-BBB FlNo1=1 FlNo2=2 Gün=1: gap=30min outside [60,300]",
        "bilinmeyen bir mesaj",
    ]
    fam = summarize_violation_families(violations)
    assert fam["counts"] == {"E1": 1, "E2": 2, "A": 1, "F": 1, "G": 1, "B": 1, "other": 1}
    assert fam["examples"]["E2"][0].startswith("E2 AAA-BBB")
    assert len(fam["examples"]["E2"]) == 2

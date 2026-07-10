"""M5d (docs/decisions.md 2026-07-10): solve tests for the slack-relaxed
E1/E2 constraints (src/model/constraints_elastic.py). Doğruluk argümanı:
strict E1/E2'nin AYNI kısıt yapısı, sağ tarafa NonNegativeReals bir slack
eklenmiş hali -- s=0 iken kısıt strict versiyonla TAMAMEN özdeş olmalı
(kontrol testleri), s>0 gerektiğinde slack GERÇEKTEN o miktarı absorbe
etmeli (adversarial: minimize slack, tam beklenen değere iner mi).

marker: solve (small HiGHS solve, <60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_elastic import (
    add_elastic_e1_constraints, add_elastic_e2_constraints, add_elastic_feasibility_objective,
)
from src.model.constraints_selection import add_b_constraints, add_flight_time_variables
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300
ALPHA = 0.20
GAMMA = 30
JOURNEY_CONST = {("ZZG", "ZZH"): 100, ("ZZH", "ZZG"): 100}


def _fixed_candidate(o, d, flno1, flno2, gap, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=gap, arr_lo=0, arr_hi=0, dep_lo=gap, dep_hi=gap,
        gap_lo=gap, gap_hi=gap,
    )


def _build_e1(candidates):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_elastic_e1_constraints(model, candidates, ALPHA)
    add_elastic_feasibility_objective(model)
    model._candidates = candidates
    return model


def _build_e2(candidates, gamma=GAMMA):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_elastic_e2_constraints(model, candidates, JOURNEY_CONST, gamma)
    add_elastic_feasibility_objective(model)
    model._candidates = candidates
    return model


def test_elastic_e1_slack_is_zero_when_balanced():
    # fwd=1, bwd=1 (both fixed, forced offered) -- |1-1|=0 <= alpha*2, no
    # slack needed.
    c_fwd = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=100)
    c_bwd = _fixed_candidate("ZZH", "ZZG", 202, 302, gap=100)
    model = _build_e1([c_fwd, c_bwd])
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.s_e1["ZZG", "ZZH", 1]) == pytest.approx(0.0, abs=1e-6)


def test_elastic_e1_slack_absorbs_forced_imbalance():
    # fwd=1 (forced offered, gap=100 in [L,U]), bwd=1 candidate but forced
    # OFF (gap=1000, outside [L,U]) -- n_fwd=1, n_bwd=0 UNCONDITIONALLY.
    # |1-0|=1 > alpha*(1)=0.2 -- minimum slack to satisfy is EXACTLY 0.8.
    c_fwd = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=100)
    c_bwd = _fixed_candidate("ZZH", "ZZG", 202, 302, gap=1000)
    model = _build_e1([c_fwd, c_bwd])
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.s_e1["ZZG", "ZZH", 1]) == pytest.approx(0.8, abs=1e-6)


def test_elastic_e2_slack_is_zero_when_within_gamma():
    c_fwd = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=100)  # J=200
    c_bwd = _fixed_candidate("ZZH", "ZZG", 202, 302, gap=100)  # J=200
    model = _build_e2([c_fwd, c_bwd])
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.s_e2["ZZG", "ZZH", 1]) == pytest.approx(0.0, abs=1e-6)


def test_elastic_e2_slack_absorbs_forced_gamma_violation():
    # fwd forced J=200 (gap=100), bwd forced J=300 (gap=200) -- |300-200|=100
    # > Gamma=30 -- minimum slack EXACTLY 70, both a_dir forced to 1 (single
    # candidate per direction, both offered).
    c_fwd = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=100)
    c_bwd = _fixed_candidate("ZZH", "ZZG", 202, 302, gap=200)
    model = _build_e2([c_fwd, c_bwd])
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.s_e2["ZZG", "ZZH", 1]) == pytest.approx(70.0, abs=1e-6)


def test_elastic_objective_is_feasible_by_construction():
    # A market pair with NO way to avoid violating -- the model must still
    # solve to OPTIMAL (never infeasible/no-incumbent), proving the "feasible
    # by construction" claim itself, not just the slack value.
    c_fwd = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=100)
    c_bwd = _fixed_candidate("ZZH", "ZZG", 202, 302, gap=1000)
    model = _build_e1([c_fwd, c_bwd])
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value is not None

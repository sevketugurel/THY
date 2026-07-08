"""Adversarial solve tests for B's bidirectional reification.

E1/E2 (M4) will give the solver a real incentive to hide a genuinely-valid
connection to dodge a balance penalty -- these tests prove that incentive is
already structurally blocked in M1, before E1/E2 exist to create it. Each test
crafts an objective that WOULD exploit an incomplete reification if one
existed, then asserts the solver is forced into the correct answer anyway
(infeasible to do otherwise), not just that it happens to prefer it.

marker: solve (small HiGHS solve, single-candidate models).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_selection import add_b_constraints, add_flight_time_variables
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300


def _fixed_candidate(gap):
    # Both legs Rfix (single-point window) -> gap is a known constant.
    return Candidate(
        od="ZZA-ZZB", o="ZZA", d="ZZB", gun=1, flno1=9101, flno2=9112,
        r1_id=("IB", 9101, 1), r2_id=("OB", 9112, 1), arr_time=None, dep_time=None,
        gap_min=gap, arr_lo=0, arr_hi=0, dep_lo=gap, dep_hi=gap, gap_lo=gap, gap_hi=gap,
    )


def _straddling_candidate():
    # arr free in [0,10], dep free in [55,65] -> gap achievable in [45,65],
    # straddling L=60 (the model itself, not just a fixed data point, must
    # respect the integer boundary).
    return Candidate(
        od="ZZA-ZZB", o="ZZA", d="ZZB", gun=1, flno1=9101, flno2=9112,
        r1_id=("IB", 9101, 1), r2_id=("OB", 9112, 1), arr_time=None, dep_time=None,
        gap_min=60, arr_lo=0, arr_hi=10, dep_lo=55, dep_hi=65, gap_lo=45, gap_hi=65,
    )


def _build_and_solve(candidates, sense, weight_x):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    model.objective = pyo.Objective(
        expr=sum(weight_x * model.x[i] for i in model.CANDIDATES), sense=sense,
    )
    model._candidates = candidates
    return solve(model, solver="highs", time_limit_sec=60, seed=42)


def test_x_cannot_be_zero_when_gap_is_genuinely_valid():
    # gap=100 (comfortably in [60,300]); objective REWARDS x=0 (wants to hide
    # the connection). If backward forcing were missing, solver would exploit
    # this and report x=0 despite a valid connection.
    c = _fixed_candidate(gap=100)
    result = _build_and_solve([c], sense=pyo.minimize, weight_x=1)
    assert result.status == "optimal"
    assert result.selected[c] == 1, "x=0 was chosen despite gap being genuinely valid -- backward forcing broken"


def test_x_cannot_be_one_when_gap_is_genuinely_invalid():
    # gap=400 (invalid, >U); objective REWARDS x=1 (wants to falsely claim the
    # connection). If forward forcing were missing, solver would exploit this.
    c = _fixed_candidate(gap=400)
    result = _build_and_solve([c], sense=pyo.maximize, weight_x=1)
    assert result.status == "optimal"
    assert result.selected[c] == 0, "x=1 was chosen despite gap being genuinely invalid -- forward forcing broken"


def test_integer_boundary_x_one_reachable_at_gap_exactly_l():
    c = _straddling_candidate()
    result = _build_and_solve([c], sense=pyo.maximize, weight_x=1)
    assert result.status == "optimal"
    assert result.selected[c] == 1


def test_integer_boundary_x_zero_reachable_at_gap_just_below_l():
    # Forcing x=0 in a range that straddles L must NOT be infeasible (a
    # continuous-time model with an epsilon=1 relaxation would wrongly forbid
    # the entire (L-1,L) zone -- with integer domain there is no such zone).
    c = _straddling_candidate()
    result = _build_and_solve([c], sense=pyo.minimize, weight_x=1)
    assert result.status == "optimal"
    assert result.selected[c] == 0

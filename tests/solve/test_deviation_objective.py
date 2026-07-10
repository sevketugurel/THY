"""Solve tests for M5c §5 Phase 1's min-deviation objective
(src.model.deviation_objective.add_min_deviation_objective).

Doğruluk argümanı: dev_plus-dev_minus == t-baseline (linked equality, both
>=0), objective = min Sum(dev_plus+dev_minus) -- standard absolute-value
linearization. Unconstrained, the optimal is always dev=0 (t=baseline is
always achievable and trivially minimal). When something ELSE forces t away
from baseline (e.g. a fixed lower bound above baseline), the objective must
report EXACTLY that forced distance, not more (no slack/looseness) and not
less (the equality can't be gamed).

marker: solve (small HiGHS solve, <60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_selection import add_flight_time_variables
from src.model.deviation_objective import add_min_deviation_objective
from src.solve.runner import solve

pytestmark = pytest.mark.solve


def _candidate(arr_lo, arr_hi, dep_lo, dep_hi):
    return Candidate(
        od="ZZA-ZZB", o="ZZA", d="ZZB", gun=1, flno1=9101, flno2=9112,
        r1_id=("IB", 9101, 1), r2_id=("OB", 9112, 1), arr_time=None, dep_time=None,
        gap_min=dep_lo - arr_hi, arr_lo=arr_lo, arr_hi=arr_hi, dep_lo=dep_lo, dep_hi=dep_hi,
        gap_lo=dep_lo - arr_hi, gap_hi=dep_hi - arr_lo,
    )


def test_unconstrained_optimal_deviation_is_zero():
    # Baseline (midpoint of [700,900]=800) is always achievable when
    # nothing else constrains t_arr -- optimal deviation must be exactly 0.
    c = _candidate(arr_lo=700, arr_hi=900, dep_lo=1000, dep_hi=1000)
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, [c])
    add_min_deviation_objective(model)
    model._candidates = [c]
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(0.0)
    assert pyo.value(model.t_arr["IB", 9101, 1]) == pytest.approx(800.0)


def test_forced_deviation_is_measured_exactly():
    # Force t_arr's lower bound (via an extra constraint) above baseline
    # (800) -- the ONLY way to satisfy it is a genuine deviation, and the
    # objective must report EXACTLY that forced distance (850-800=50), not
    # more (no artificial slack in the dev_plus/dev_minus linking) and not
    # less (can't be gamed since dev_plus-dev_minus is an EQUALITY, not an
    # inequality that could be left slack).
    c = _candidate(arr_lo=700, arr_hi=900, dep_lo=1000, dep_hi=1000)
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, [c])
    add_min_deviation_objective(model)
    model._candidates = [c]
    model.force_above_baseline = pyo.Constraint(expr=model.t_arr["IB", 9101, 1] >= 850)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(50.0)
    assert pyo.value(model.t_arr["IB", 9101, 1]) == pytest.approx(850.0)


def test_rfix_instance_contributes_zero_deviation():
    # Both legs Rfix (single-point window) -- already AT baseline by
    # construction (lo==hi means baseline==lo==hi), zero freedom, must
    # contribute exactly 0 to the objective.
    c = _candidate(arr_lo=500, arr_hi=500, dep_lo=700, dep_hi=700)
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, [c])
    add_min_deviation_objective(model)
    model._candidates = [c]
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(0.0)


def test_deviation_can_go_either_direction():
    # Force t_arr's UPPER bound below baseline (800) this time -- deviation
    # must be measured correctly regardless of direction (dev_minus, not
    # dev_plus, absorbs it).
    c = _candidate(arr_lo=700, arr_hi=900, dep_lo=1000, dep_hi=1000)
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, [c])
    add_min_deviation_objective(model)
    model._candidates = [c]
    model.force_below_baseline = pyo.Constraint(expr=model.t_arr["IB", 9101, 1] <= 750)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(50.0)
    assert pyo.value(model.t_arr["IB", 9101, 1]) == pytest.approx(750.0)

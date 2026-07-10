"""M5d Adım 2 (docs/decisions.md 2026-07-10): add_local_branching'in
doğruluk testleri -- referans noktadan en fazla k örneğin sapmasına izin
veren trust-region kısıtı.

marker: solve (small HiGHS solve, <60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.model.local_branching import add_local_branching
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300


def _adjustable_candidate(o, d, flno1, flno2, arr_lo, arr_hi, dep_lo, dep_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=dep_lo - arr_hi, arr_lo=arr_lo, arr_hi=arr_hi, dep_lo=dep_lo, dep_hi=dep_hi,
        gap_lo=dep_lo - arr_hi, gap_hi=dep_hi - arr_lo,
    )


def _build(candidates):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    model._candidates = candidates
    return model


def test_zero_k_forces_reference_exactly():
    # Three independently-adjustable legs, each with room to move. An
    # adversarial objective wants every t as large as possible; with k=0 the
    # local-branching constraint must pin ALL of them to the reference
    # regardless of what the objective wants.
    candidates = [
        _adjustable_candidate("ZZG", "ZZH", 201, 301, arr_lo=0, arr_hi=100, dep_lo=150, dep_hi=250),
        _adjustable_candidate("ZZG", "ZZI", 202, 302, arr_lo=0, arr_hi=100, dep_lo=150, dep_hi=250),
        _adjustable_candidate("ZZG", "ZZJ", 203, 303, arr_lo=0, arr_hi=100, dep_lo=150, dep_hi=250),
    ]
    model = _build(candidates)
    reference_arr = {c.r1_id: 20 for c in candidates}
    reference_dep = {c.r2_id: 180 for c in candidates}
    add_local_branching(model, reference_arr, reference_dep, k=0)
    model.objective = pyo.Objective(
        expr=sum(model.t_arr[c.r1_id] + model.t_dep[c.r2_id] for c in candidates),
        sense=pyo.maximize,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    for c in candidates:
        assert pyo.value(model.t_arr[c.r1_id]) == pytest.approx(20.0)
        assert pyo.value(model.t_dep[c.r2_id]) == pytest.approx(180.0)


def test_k_bounds_number_of_moved_instances():
    # Same 3 legs, k=1 -- adversarial objective wants ALL three t_dep at
    # their max (250), but only ONE instance total (arr+dep combined) may
    # differ from the reference. Reference already has arr at its own max
    # (100) so arr never needs to move; only ONE dep can move to 250, the
    # other two must stay pinned at the reference (180).
    candidates = [
        _adjustable_candidate("ZZG", "ZZH", 201, 301, arr_lo=0, arr_hi=100, dep_lo=150, dep_hi=250),
        _adjustable_candidate("ZZG", "ZZI", 202, 302, arr_lo=0, arr_hi=100, dep_lo=150, dep_hi=250),
        _adjustable_candidate("ZZG", "ZZJ", 203, 303, arr_lo=0, arr_hi=100, dep_lo=150, dep_hi=250),
    ]
    model = _build(candidates)
    reference_arr = {c.r1_id: 100 for c in candidates}
    reference_dep = {c.r2_id: 180 for c in candidates}
    add_local_branching(model, reference_arr, reference_dep, k=1)
    model.objective = pyo.Objective(
        expr=sum(model.t_dep[c.r2_id] for c in candidates), sense=pyo.maximize,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    dep_values = [pyo.value(model.t_dep[c.r2_id]) for c in candidates]
    n_moved = sum(1 for v in dep_values if abs(v - 180.0) > 1e-6)
    assert n_moved == 1, f"expected exactly 1 moved dep instance, got {n_moved} ({dep_values})"
    assert max(dep_values) == pytest.approx(250.0)
    assert sum(dep_values) == pytest.approx(180.0 + 180.0 + 250.0)


def test_large_k_matches_unconstrained_optimum():
    # k >= total instance count -> non-binding, must reproduce the same
    # optimum as solving without the local-branching constraint at all.
    candidates = [
        _adjustable_candidate("ZZG", "ZZH", 201, 301, arr_lo=0, arr_hi=100, dep_lo=150, dep_hi=250),
        _adjustable_candidate("ZZG", "ZZI", 202, 302, arr_lo=0, arr_hi=100, dep_lo=150, dep_hi=250),
    ]

    unconstrained = _build(candidates)
    unconstrained.objective = pyo.Objective(
        expr=sum(unconstrained.t_arr[c.r1_id] + unconstrained.t_dep[c.r2_id] for c in candidates),
        sense=pyo.maximize,
    )
    baseline_result = solve(unconstrained, solver="highs", time_limit_sec=60, seed=42)
    assert baseline_result.status == "optimal"

    branched = _build(candidates)
    reference_arr = {c.r1_id: 0 for c in candidates}
    reference_dep = {c.r2_id: 150 for c in candidates}
    add_local_branching(branched, reference_arr, reference_dep, k=4)  # 2 arr + 2 dep instances total
    branched.objective = pyo.Objective(
        expr=sum(branched.t_arr[c.r1_id] + branched.t_dep[c.r2_id] for c in candidates),
        sense=pyo.maximize,
    )
    branched_result = solve(branched, solver="highs", time_limit_sec=60, seed=42)
    assert branched_result.status == "optimal"
    assert branched_result.objective_value == pytest.approx(baseline_result.objective_value)


def test_missing_reference_instance_raises():
    candidates = [
        _adjustable_candidate("ZZG", "ZZH", 201, 301, arr_lo=0, arr_hi=100, dep_lo=150, dep_hi=250),
    ]
    model = _build(candidates)
    with pytest.raises(AssertionError):
        add_local_branching(model, reference_arr={}, reference_dep={}, k=0)

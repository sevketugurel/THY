"""M5d LNS fold-redesign (plan: .claude/plans/a-evet-ama-iki-tingly-canyon.md,
adim 3): add_flight_time_variables_folded / add_b_constraints_folded.

marker: solve (small HiGHS solve, <60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_selection import (
    add_b_constraints, add_b_constraints_folded, add_c_constraints,
    add_flight_time_variables, add_flight_time_variables_folded,
)
from src.model.lns import fix_reference_except_free
from src.model.partition import partition_by_freedom
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300


def _candidate(o, d, flno1, flno2, arr_lo, arr_hi, dep_lo, dep_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=dep_lo - arr_hi, arr_lo=arr_lo, arr_hi=arr_hi, dep_lo=dep_lo, dep_hi=dep_hi,
        gap_lo=dep_lo - arr_hi, gap_hi=dep_hi - arr_lo,
    )


def _four_candidates():
    # c1 (idx0): fully free.
    c1 = _candidate("A", "B", 1, 11, arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500)
    # c2 (idx1): fully frozen (neither end free) -- must get ZERO Vars/rows.
    c2 = _candidate("A", "B", 2, 12, arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500)
    # c3 (idx2): mixed -- r1 free, r2 frozen.
    c3 = _candidate("A", "B", 3, 13, arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500)
    # c4 (idx3): mixed -- r1 frozen, r2 free.
    c4 = _candidate("A", "B", 4, 14, arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500)
    return [c1, c2, c3, c4]


def _partition_for_four_candidates(candidates):
    c1, c2, c3, c4 = candidates
    free_arr = {c1.r1_id, c3.r1_id}
    free_dep = {c1.r2_id, c4.r2_id}
    reference_arr = {c1.r1_id: 0, c2.r1_id: 0, c3.r1_id: 0, c4.r1_id: 10}
    reference_dep = {c1.r2_id: 0, c2.r2_id: 200, c3.r2_id: 250, c4.r2_id: 0}
    return partition_by_freedom(candidates, free_arr, free_dep, reference_arr, reference_dep, L, U)


def test_add_b_constraints_folded_excludes_fully_frozen_candidates():
    candidates = _four_candidates()
    partition = _partition_for_four_candidates(candidates)

    model = pyo.ConcreteModel()
    add_flight_time_variables_folded(model, candidates, partition)
    add_b_constraints_folded(model, candidates, L, U, partition)

    assert set(model.CANDIDATES) == {0, 2, 3}, "fully-frozen candidate (idx1) must get zero Vars/rows"
    assert set(model.ARR_INSTANCES) == {("IB", 1, 1), ("IB", 3, 1)}
    assert set(model.DEP_INSTANCES) == {("OB", 11, 1), ("OB", 14, 1)}


def test_add_b_constraints_folded_gap_definition_folds_frozen_end_correctly():
    candidates = _four_candidates()
    partition = _partition_for_four_candidates(candidates)

    model = pyo.ConcreteModel()
    model._candidates = candidates
    add_flight_time_variables_folded(model, candidates, partition)
    add_b_constraints_folded(model, candidates, L, U, partition)

    # idx2 (c3): r1 free, r2 frozen at reference_dep=250 -- objective wants
    # t_arr[IB3] as LARGE as possible; B's own forward/backward reification
    # should still force gap in [L,U] given x is free to choose either.
    model.objective = pyo.Objective(expr=model.t_arr[("IB", 3, 1)], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=30, seed=42)
    assert result.status == "optimal"
    t_arr3 = pyo.value(model.t_arr[("IB", 3, 1)])
    gap2 = pyo.value(model.gap[2])
    assert gap2 == pytest.approx(250 - t_arr3), "gap must equal frozen dep constant minus the free arr Var"


def test_add_b_constraints_folded_matches_fix_based_for_same_split():
    candidates = _four_candidates()
    partition = _partition_for_four_candidates(candidates)

    # FIX-based (original functions + fix_reference_except_free).
    fixed_model = pyo.ConcreteModel()
    fixed_model._candidates = candidates
    add_flight_time_variables(fixed_model, candidates)
    add_b_constraints(fixed_model, candidates, L=L, U=U)
    fix_reference_except_free(
        fixed_model, partition.reference_arr, partition.reference_dep, partition.free_arr, partition.free_dep,
    )
    fixed_model.objective = pyo.Objective(
        expr=fixed_model.t_arr[("IB", 1, 1)] + fixed_model.t_dep[("OB", 14, 1)], sense=pyo.maximize,
    )
    fixed_result = solve(fixed_model, solver="highs", time_limit_sec=30, seed=42)
    assert fixed_result.status == "optimal"

    # FOLD-based (new functions).
    folded_model = pyo.ConcreteModel()
    folded_model._candidates = candidates
    add_flight_time_variables_folded(folded_model, candidates, partition)
    add_b_constraints_folded(folded_model, candidates, L, U, partition)
    folded_model.objective = pyo.Objective(
        expr=folded_model.t_arr[("IB", 1, 1)] + folded_model.t_dep[("OB", 14, 1)], sense=pyo.maximize,
    )
    folded_result = solve(folded_model, solver="highs", time_limit_sec=30, seed=42)
    assert folded_result.status == "optimal"

    assert folded_result.objective_value == pytest.approx(fixed_result.objective_value)
    for i in (0, 2, 3):
        assert pyo.value(folded_model.x[i]) == pytest.approx(pyo.value(fixed_model.x[i]))
        assert pyo.value(folded_model.gap[i]) == pytest.approx(pyo.value(fixed_model.gap[i]))

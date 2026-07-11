"""M5d LNS fold-redesign (plan: .claude/plans/a-evet-ama-iki-tingly-canyon.md,
adim 5): add_elastic_e1_constraints_folded.

marker: solve (small HiGHS solve, <60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_elastic import add_elastic_e1_constraints, add_elastic_e1_constraints_folded
from src.model.constraints_selection import (
    add_b_constraints, add_b_constraints_folded, add_flight_time_variables, add_flight_time_variables_folded,
)
from src.model.lns import compute_pair_slack, fix_reference_except_free
from src.model.partition import partition_by_freedom
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300
ALPHA = 0.2


def _candidate(o, d, flno1, flno2, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=0, arr_lo=0, arr_hi=300, dep_lo=0, dep_hi=600, gap_lo=-600, gap_hi=600,
    )


def test_fully_frozen_pair_no_violation_gets_no_row():
    # fwd: 1 frozen-offered candidate. bwd: 1 frozen-offered candidate.
    # n_fwd=n_bwd=1 -> balanced, no violation.
    c_fwd = _candidate("A", "B", 1, 11)
    c_bwd = _candidate("B", "A", 2, 22)
    candidates = [c_fwd, c_bwd]
    reference_arr = {c_fwd.r1_id: 0, c_bwd.r1_id: 0}
    reference_dep = {c_fwd.r2_id: 100, c_bwd.r2_id: 100}  # both gap=100, offered
    partition = partition_by_freedom(candidates, set(), set(), reference_arr, reference_dep, L, U)

    model = pyo.ConcreteModel()
    add_flight_time_variables_folded(model, candidates, partition)
    add_b_constraints_folded(model, candidates, L, U, partition)
    groups, real_pairs = add_elastic_e1_constraints_folded(model, candidates, ALPHA, partition)

    assert real_pairs == []
    assert not hasattr(model, "s_e1") or len(model.s_e1) == 0
    assert model._e1_frozen_slack_total == pytest.approx(0.0)


def test_fully_frozen_pair_with_violation_reports_constant_slack():
    # fwd: 2 frozen-offered candidates. bwd: 0 offered (both frozen, gap
    # outside [L,U]). n_fwd=2, n_bwd=0 -> |2-0| - 0.2*(2) = 1.6.
    c_fwd1 = _candidate("A", "B", 1, 11)
    c_fwd2 = _candidate("A", "B", 3, 33)
    c_bwd = _candidate("B", "A", 2, 22)
    candidates = [c_fwd1, c_fwd2, c_bwd]
    reference_arr = {c_fwd1.r1_id: 0, c_fwd2.r1_id: 0, c_bwd.r1_id: 0}
    reference_dep = {c_fwd1.r2_id: 100, c_fwd2.r2_id: 150, c_bwd.r2_id: 1000}  # bwd gap=1000, not offered
    partition = partition_by_freedom(candidates, set(), set(), reference_arr, reference_dep, L, U)

    model = pyo.ConcreteModel()
    add_flight_time_variables_folded(model, candidates, partition)
    add_b_constraints_folded(model, candidates, L, U, partition)
    groups, real_pairs = add_elastic_e1_constraints_folded(model, candidates, ALPHA, partition)

    assert real_pairs == []
    assert model._e1_frozen_slack_total == pytest.approx(1.6)


def test_mixed_pair_gets_real_row_and_folds_frozen_counts():
    # fwd: 1 free candidate + 1 frozen-offered candidate. bwd: 1 frozen-offered.
    c_fwd_free = _candidate("A", "B", 1, 11)
    c_fwd_frozen = _candidate("A", "B", 3, 33)
    c_bwd_frozen = _candidate("B", "A", 2, 22)
    candidates = [c_fwd_free, c_fwd_frozen, c_bwd_frozen]
    reference_arr = {c_fwd_free.r1_id: 0, c_fwd_frozen.r1_id: 0, c_bwd_frozen.r1_id: 0}
    reference_dep = {c_fwd_free.r2_id: 100, c_fwd_frozen.r2_id: 150, c_bwd_frozen.r2_id: 100}
    free_arr = {c_fwd_free.r1_id}
    free_dep = {c_fwd_free.r2_id}
    partition = partition_by_freedom(candidates, free_arr, free_dep, reference_arr, reference_dep, L, U)

    model = pyo.ConcreteModel()
    model._candidates = candidates
    add_flight_time_variables_folded(model, candidates, partition)
    add_b_constraints_folded(model, candidates, L, U, partition)
    groups, real_pairs = add_elastic_e1_constraints_folded(model, candidates, ALPHA, partition)

    assert real_pairs == [("A", "B", 1)]
    assert len(model.s_e1) == 1
    # Adversarial objective: push the free candidate's gap OUT of [60,300]
    # (x_free=0) so n_fwd drops to just the frozen-offered count (1),
    # n_bwd stays 1 (frozen-offered) -> balanced, s_e1 should be forced to 0.
    model.objective = pyo.Objective(expr=model.t_dep[c_fwd_free.r2_id], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=30, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.s_e1[("A", "B", 1)]) == pytest.approx(0.0)


def test_folded_matches_fix_based_recompute_for_mixed_scenario():
    # End-to-end cross-check against the independent compute_pair_slack
    # recompute (same one src.model.lns uses) AND against the original
    # fix-based build for the same free/frozen split.
    c1 = _candidate("A", "B", 1, 11)   # free
    c2 = _candidate("A", "B", 3, 33)   # frozen, offered
    c3 = _candidate("B", "A", 2, 22)   # frozen, offered
    candidates = [c1, c2, c3]
    journey_constants = {("A", "B"): 0.0, ("B", "A"): 0.0}
    reference_arr = {c1.r1_id: 0, c2.r1_id: 0, c3.r1_id: 0}
    reference_dep = {c1.r2_id: 100, c2.r2_id: 150, c3.r2_id: 100}
    free_arr, free_dep = {c1.r1_id}, {c1.r2_id}
    partition = partition_by_freedom(candidates, free_arr, free_dep, reference_arr, reference_dep, L, U)

    # FIX-based.
    fixed_model = pyo.ConcreteModel()
    fixed_model._candidates = candidates
    add_flight_time_variables(fixed_model, candidates)
    add_b_constraints(fixed_model, candidates, L=L, U=U)
    fix_reference_except_free(fixed_model, reference_arr, reference_dep, free_arr, free_dep)
    add_elastic_e1_constraints(fixed_model, candidates, ALPHA)
    fixed_model.objective = pyo.Objective(expr=sum(fixed_model.s_e1[p] for p in fixed_model.E1_PAIRS))
    fixed_result = solve(fixed_model, solver="highs", time_limit_sec=30, seed=42)
    assert fixed_result.status == "optimal"

    # FOLD-based.
    folded_model = pyo.ConcreteModel()
    folded_model._candidates = candidates
    add_flight_time_variables_folded(folded_model, candidates, partition)
    add_b_constraints_folded(folded_model, candidates, L, U, partition)
    add_elastic_e1_constraints_folded(folded_model, candidates, ALPHA, partition)
    if len(folded_model.E1_PAIRS) > 0:
        folded_model.objective = pyo.Objective(expr=sum(folded_model.s_e1[p] for p in folded_model.E1_PAIRS))
    else:
        folded_model.objective = pyo.Objective(expr=0)
    folded_result = solve(folded_model, solver="highs", time_limit_sec=30, seed=42)
    assert folded_result.status == "optimal"

    fixed_slack = compute_pair_slack(
        candidates, journey_constants, fixed_result.arr_times, fixed_result.dep_times, L, U, ALPHA, gamma=999999,
    )
    folded_full_arr = {**reference_arr, **folded_result.arr_times}
    folded_full_dep = {**reference_dep, **folded_result.dep_times}
    folded_slack = compute_pair_slack(
        candidates, journey_constants, folded_full_arr, folded_full_dep, L, U, ALPHA, gamma=999999,
    )
    fixed_total_e1 = sum(v["e1"] for v in fixed_slack.values())
    folded_total_e1 = sum(v["e1"] for v in folded_slack.values()) + folded_model._e1_frozen_slack_total
    assert folded_total_e1 == pytest.approx(fixed_total_e1)

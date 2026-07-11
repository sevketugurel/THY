"""M5d LNS fold-redesign (plan: .claude/plans/a-evet-ama-iki-tingly-canyon.md,
adim 7, EN ZOR TEK PARCA): add_elastic_e2_constraints_folded.

5 test, plandaki sirayla: tam-serbest (regresyon), tam-donuk-ihlalsiz,
tam-donuk-ihlalli, karisik+donuk-aday-gercek-argmin (adversarial -- jbest_ge
donuk-sunulmus adaylar icin ATLANIRSA bunu yakalar), karisik+serbest-aday-
argmin.

marker: solve (small HiGHS solve, <60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_elastic import add_elastic_e2_constraints, add_elastic_e2_constraints_folded
from src.model.constraints_selection import (
    add_b_constraints, add_b_constraints_folded, add_flight_time_variables, add_flight_time_variables_folded,
)
from src.model.lns import fix_reference_except_free
from src.model.partition import partition_by_freedom
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300
GAMMA = 30
JC = {("A", "B"): 100.0, ("B", "A"): 100.0}


def _candidate(o, d, flno1, flno2, arr_lo, arr_hi, dep_lo, dep_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=dep_lo - arr_hi, arr_lo=arr_lo, arr_hi=arr_hi, dep_lo=dep_lo, dep_hi=dep_hi,
        gap_lo=dep_lo - arr_hi, gap_hi=dep_hi - arr_lo,
    )


def _all_bounds(candidates):
    arr_bounds, dep_bounds = {}, {}
    for c in candidates:
        arr_bounds.setdefault(c.r1_id, (c.arr_lo, c.arr_hi))
        dep_bounds.setdefault(c.r2_id, (c.dep_lo, c.dep_hi))
    return arr_bounds, dep_bounds


def _partition(candidates, free_arr, free_dep, overrides_arr=None, overrides_dep=None):
    arr_bounds, dep_bounds = _all_bounds(candidates)
    reference_arr = {r: lo for r, (lo, hi) in arr_bounds.items()}
    reference_dep = {r: lo for r, (lo, hi) in dep_bounds.items()}
    reference_arr.update(overrides_arr or {})
    reference_dep.update(overrides_dep or {})
    return partition_by_freedom(candidates, free_arr, free_dep, reference_arr, reference_dep, L, U)


def _build_folded(candidates, partition):
    model = pyo.ConcreteModel()
    model._candidates = candidates
    add_flight_time_variables_folded(model, candidates, partition)
    add_b_constraints_folded(model, candidates, L, U, partition)
    add_elastic_e2_constraints_folded(model, candidates, JC, GAMMA, partition)
    return model


def _build_fixed(candidates, partition):
    model = pyo.ConcreteModel()
    model._candidates = candidates
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    fix_reference_except_free(
        model, partition.reference_arr, partition.reference_dep, partition.free_arr, partition.free_dep,
    )
    add_elastic_e2_constraints(model, candidates, JC, GAMMA)
    return model


def test_fully_free_matches_unfolded():
    c_fwd = _candidate("A", "B", 201, 301, arr_lo=0, arr_hi=0, dep_lo=0, dep_hi=250)
    c_bwd = _candidate("B", "A", 202, 302, arr_lo=0, arr_hi=0, dep_lo=0, dep_hi=250)
    candidates = [c_fwd, c_bwd]
    free_arr = {c_fwd.r1_id, c_bwd.r1_id}
    free_dep = {c_fwd.r2_id, c_bwd.r2_id}
    partition = _partition(candidates, free_arr, free_dep)

    fixed_model = _build_fixed(candidates, partition)
    fixed_model.objective = pyo.Objective(expr=fixed_model.Jbest[("A", "B", 1)], sense=pyo.maximize)
    fixed_result = solve(fixed_model, solver="highs", time_limit_sec=30, seed=42)
    assert fixed_result.status == "optimal"

    folded_model = _build_folded(candidates, partition)
    folded_model.objective = pyo.Objective(expr=folded_model.Jbest[("A", "B", 1)], sense=pyo.maximize)
    folded_result = solve(folded_model, solver="highs", time_limit_sec=30, seed=42)
    assert folded_result.status == "optimal"
    assert folded_result.objective_value == pytest.approx(fixed_result.objective_value)


def test_fully_frozen_no_violation_gets_no_rows():
    # fwd offered gap=100 (J=200), bwd offered gap=100 (J=200) -- diff=0, no violation.
    c_fwd = _candidate("A", "B", 201, 301, arr_lo=0, arr_hi=0, dep_lo=100, dep_hi=100)
    c_bwd = _candidate("B", "A", 202, 302, arr_lo=0, arr_hi=0, dep_lo=100, dep_hi=100)
    candidates = [c_fwd, c_bwd]
    partition = _partition(candidates, set(), set())
    model = _build_folded(candidates, partition)
    assert len(model.E2_PAIRS) == 0
    assert model._e2_frozen_slack_total == pytest.approx(0.0)


def test_fully_frozen_with_violation_reports_constant_slack():
    # fwd offered gap=100 (J=200), bwd offered gap=150 (J=250) -- diff=50>30 -> slack=20.
    c_fwd = _candidate("A", "B", 201, 301, arr_lo=0, arr_hi=0, dep_lo=100, dep_hi=100)
    c_bwd = _candidate("B", "A", 202, 302, arr_lo=0, arr_hi=0, dep_lo=150, dep_hi=150)
    candidates = [c_fwd, c_bwd]
    partition = _partition(candidates, set(), set())
    model = _build_folded(candidates, partition)
    assert len(model.E2_PAIRS) == 0
    assert model._e2_frozen_slack_total == pytest.approx(20.0)


def test_mixed_frozen_candidate_is_true_argmin_jbest_ge_not_dropped():
    # fwd market (A,B,1): c_frozen (FROZEN, offered, gap=100 -> J=200, the
    # TRUE argmin) + c_free (FREE, gap fixed at -500 -> x forced 0, NEVER
    # offered, J_if_offered=-400 -- a "trap" mirroring
    # test_m4_constraints_e2.py's own adversarial c3). bwd: c_bwd (frozen,
    # offered, gap=110 -> J=210, Gamma-compliant with 200, non-binding).
    # Minimizing Jbest[fwd]: if jbest_ge were dropped for the FROZEN
    # candidate, nothing would pin Jbest>=200 and it could sink to the
    # trap's -400 (market_j_bounds' own lower bound). Correct behavior
    # floors it at 200.
    c_frozen = _candidate("A", "B", 201, 301, arr_lo=0, arr_hi=0, dep_lo=100, dep_hi=100)
    c_free = _candidate("A", "B", 203, 303, arr_lo=0, arr_hi=0, dep_lo=-500, dep_hi=-500)
    c_bwd = _candidate("B", "A", 202, 302, arr_lo=0, arr_hi=0, dep_lo=110, dep_hi=110)
    candidates = [c_frozen, c_free, c_bwd]
    partition = _partition(candidates, free_arr={c_free.r1_id}, free_dep={c_free.r2_id})

    model = _build_folded(candidates, partition)
    assert c_free.r1_id in partition.free_arr
    model.objective = pyo.Objective(expr=model.Jbest[("A", "B", 1)], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=30, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.Jbest[("A", "B", 1)]) == pytest.approx(200.0), (
        "Jbest must floor at the frozen TRUE argmin's J (200), not the free trap candidate's -400"
    )


def test_mixed_free_candidate_is_true_argmin():
    # fwd market: c_frozen2 (FROZEN, offered, gap=150 -> J=250, NOT the
    # argmin) + c_free2 (FREE, gap fixed at 120 -> offered, J=220, the TRUE,
    # LOWER argmin). Minimizing Jbest must settle at 220 (via w on the free
    # candidate), not be dragged up by the frozen one.
    c_frozen2 = _candidate("A", "B", 201, 301, arr_lo=0, arr_hi=0, dep_lo=150, dep_hi=150)
    c_free2 = _candidate("A", "B", 203, 303, arr_lo=0, arr_hi=0, dep_lo=120, dep_hi=120)
    c_bwd = _candidate("B", "A", 202, 302, arr_lo=0, arr_hi=0, dep_lo=100, dep_hi=100)  # J=200, Gamma-compliant
    candidates = [c_frozen2, c_free2, c_bwd]
    partition = _partition(candidates, free_arr={c_free2.r1_id}, free_dep={c_free2.r2_id})

    model = _build_folded(candidates, partition)
    model.objective = pyo.Objective(expr=model.Jbest[("A", "B", 1)], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=30, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.Jbest[("A", "B", 1)]) == pytest.approx(220.0)

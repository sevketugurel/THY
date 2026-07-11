"""M5d LNS fold-redesign (plan: .claude/plans/a-evet-ama-iki-tingly-canyon.md,
adim 6, EN YUKSEK RISK): add_g_constraints_folded.

Uses the same tk_free fixture and MI1(9101, IB role) flight as
tests/solve/test_m3_constraints_g.py: Gün1 baseline arr=840 (raw epoch 840,
day_offset=120), Gün2 baseline arr=815 (raw epoch 1440+815=2255,
day_offset=1560) -- day-of-day diff=25 > X_DEV=15 (genuinely violates at
baseline, verified against the existing G test's own docstring numbers).

Finding during TDD (worth keeping in mind when reading the tests below):
cluster_flight_days's clustering itself always operates on baseline_tod
(the flight's OWN real time-of-day), NOT on whatever value a test freezes
it at -- freezing only affects half_width (0 for frozen) and which
raw/reference VALUE downstream rows compare against. So "freeze both days
at genuinely incompatible values" does NOT raise an assertion -- it makes
cluster_flight_days split them into separate singleton clusters instead
(exactly VARSAYIM-9's designed behavior), which then correctly get NO
T_ref at all (len(cluster)<2). An assertion firing would only be reachable
via a genuine bug in cluster_flight_days' own chaining logic, not from
"realistic" frozen-value choices -- so no test here exercises that path.

marker: solve (small HiGHS solve, <60s).
"""
from pathlib import Path

import pyomo.environ as pyo
import pytest

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.loaders import load_od_table
from src.model.constraints_operations import add_g_constraints_folded
from src.model.constraints_selection import add_flight_time_variables_folded
from src.model.partition import partition_by_freedom
from src.solve.runner import solve

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.solve

L, U = 60, 300
X_DEV = 15
MI1_G1_ARR = ("IB", 9101, 1)
MI1_G2_ARR = ("IB", 9101, 2)


@pytest.fixture
def tk_free():
    od_table = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    tk = od_table[od_table.cr1 == "TK"]
    anchor = compute_epoch_anchor(tk)
    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=180, adjustable_set="all",
            epoch_anchor=anchor,
        ))
    return candidates, anchor


def _bounds(candidates):
    arr_bounds, dep_bounds = {}, {}
    for c in candidates:
        arr_bounds.setdefault(c.r1_id, (c.arr_lo, c.arr_hi))
        dep_bounds.setdefault(c.r2_id, (c.dep_lo, c.dep_hi))
    return arr_bounds, dep_bounds


def _partition_freeze_arr(candidates, frozen_arr_overrides: dict):
    """Freezes only the given IB instances at the given raw epoch values;
    every other instance in the fixture (including MI1's other gun, when
    not explicitly frozen) stays free -- matches the natural non-folded
    case except for the specific instances under test."""
    arr_bounds, dep_bounds = _bounds(candidates)
    reference_arr = {r: (lo + hi) // 2 for r, (lo, hi) in arr_bounds.items()}
    reference_dep = {r: (lo + hi) // 2 for r, (lo, hi) in dep_bounds.items()}
    reference_arr.update(frozen_arr_overrides)
    free_arr = set(arr_bounds) - set(frozen_arr_overrides)
    free_dep = set(dep_bounds)
    return partition_by_freedom(candidates, free_arr, free_dep, reference_arr, reference_dep, L, U)


def _build(candidates, partition, anchor, x_dev):
    model = pyo.ConcreteModel()
    model._candidates = candidates
    add_flight_time_variables_folded(model, candidates, partition)
    add_g_constraints_folded(model, candidates, anchor, x_dev, partition)
    return model


def test_all_free_matches_unfolded_g_behavior(tk_free):
    # Regression: nothing frozen -> folded must reproduce the ORIGINAL
    # add_g_constraints test's exact result (test_m3_constraints_g.py's
    # test_g_binding_forces_mi1_within_x_dev_across_days).
    candidates, anchor = tk_free
    partition = _partition_freeze_arr(candidates, {})
    model = _build(candidates, partition, anchor, X_DEV)
    model.objective = pyo.Objective(expr=0, sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    t1 = pyo.value(model.t_arr[MI1_G1_ARR])
    t2 = pyo.value(model.t_arr[MI1_G2_ARR])
    assert abs(t2 - 1440 - t1) <= X_DEV


def test_fully_frozen_consistent_creates_no_rows(tk_free):
    candidates, anchor = tk_free
    # gun1 at baseline (840, normalized 720); gun2 at a value normalized to
    # 715 (raw 715+1560=2275) -- diff=5<=15, mutually consistent.
    partition = _partition_freeze_arr(candidates, {MI1_G1_ARR: 840, MI1_G2_ARR: 2275})
    model = _build(candidates, partition, anchor, X_DEV)
    assert ("IB", 9101) not in {(r, f) for (r, f, _) in model.G_FLIGHTS}, (
        "fully-frozen flight must get NO T_ref -- no genuine freedom to constrain"
    )
    assert len(model.G_FLIGHT_DAYS_PARTIAL) == 0 or all(
        (r, f) != ("IB", 9101) for (r, f, _, _) in model.G_FLIGHT_DAYS_PARTIAL
    )


def test_fully_frozen_genuinely_incompatible_splits_into_singleton_clusters(tk_free):
    # Both frozen at their OWN raw baseline (840, 1440+815=2255) -- the
    # exact scenario test_m3_constraints_g.py documents as genuinely
    # violating at baseline (day-of-day diff=25>15). With half_width=0 for
    # BOTH (frozen), cluster_flight_days does NOT raise -- it does exactly
    # what VARSAYIM-9 designed it to do: split into the minimum number of
    # mutually-compatible clusters (here, two SINGLETON clusters, since 2
    # occurrences 25min apart with zero tolerance can never share one
    # cluster). Neither singleton reaches the len>=2 threshold, so MI1
    # correctly gets NO T_ref/rows -- same OUTCOME as the consistent case,
    # reached via a genuinely different path (splitting, not single-cluster
    # consistency). This is the fold code correctly relying on
    # cluster_flight_days's OWN pre-existing safety net rather than needing
    # a redundant defensive check of its own.
    candidates, anchor = tk_free
    partition = _partition_freeze_arr(candidates, {MI1_G1_ARR: 840, MI1_G2_ARR: 1440 + 815})
    model = _build(candidates, partition, anchor, X_DEV)
    assert ("IB", 9101) not in {(r, f) for (r, f, _) in model.G_FLIGHTS}


def test_mixed_cluster_frozen_day_genuinely_constrains_free_day(tk_free):
    # gun1 FREE (window [660,1020], normalized [540,900]). gun2 FROZEN at
    # raw 2275 (normalized 715). T_ref must satisfy 715-15<=T_ref<=715 (from
    # the frozen constraint) -- adversarial objective maximizing gun1's
    # time must be capped at T_ref_max+X_DEV = 715+15=730 (raw 730+120=850),
    # NOT at gun1's own window max (1020) -- proves the frozen day GENUINELY
    # restricts the free day, not just "some feasible value".
    candidates, anchor = tk_free
    partition = _partition_freeze_arr(candidates, {MI1_G2_ARR: 2275})
    model = _build(candidates, partition, anchor, X_DEV)

    assert ("IB", 9101, 1) in model.G_FLIGHTS, "mixed cluster (gun1 free) must get a real T_ref"
    # T_ref's own bounds must include BOTH gun1's free envelope (540..900)
    # AND gun2's frozen point (715) -- the critical correctness point:
    # excluding the frozen point from T_ref's own domain would make the
    # model spuriously infeasible (G is hard even in the elastic model).
    lb, ub = pyo.value(model.T_ref[("IB", 9101, 1)].lb), pyo.value(model.T_ref[("IB", 9101, 1)].ub)
    assert lb <= 715 <= ub
    assert lb <= 540 and ub >= 900

    model.objective = pyo.Objective(expr=model.t_arr[MI1_G1_ARR], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    t1 = pyo.value(model.t_arr[MI1_G1_ARR])
    assert t1 == pytest.approx(850.0), (
        "frozen gun2 must cap gun1's max at T_ref_max(715)+X_DEV(15)+day_offset(120)=850, "
        "not gun1's own window max (1020)"
    )

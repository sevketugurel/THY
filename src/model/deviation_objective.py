"""M5c §5 Phase 1 (docs/decisions.md 2026-07-10): a min-deviation objective
that REPLACES the reward objective on an already-built model, leaving every
A-G constraint exactly as build_model_m4 constructed it. Purpose: find ANY
feasible full-data schedule first -- the reward objective's huge LP ceiling
and slot/argmin symmetry may be what's preventing HiGHS's root node from
finding an incumbent at all (see docs/lp_anatomy.md); minimizing deviation
from baseline is a much "flatter", less symmetric objective that gives
HiGHS's own feasibility heuristics something more direct to latch onto.
Also reports a standalone metric: the minimum total schedule deviation
(minutes) required to make the baseline tariff satisfy A-G at all.
"""
import pyomo.environ as pyo


def _baseline(lo, hi):
    return lo + (hi - lo) // 2


def add_min_deviation_objective(model):
    """Requires add_flight_time_variables to have already run (model.t_arr,
    model.t_dep, model.ARR_INSTANCES, model.DEP_INSTANCES). Replaces
    model.objective if one already exists (matches
    add_ranking_reward_objective's del_component pattern). Already-Rfix
    (lo==hi) instances naturally settle at zero deviation (t is already
    fixed to baseline) -- no special-casing needed, just slightly wasted
    (always-zero) variables for them."""
    if hasattr(model, "objective"):
        model.del_component(model.objective)

    model._arr_baseline = {r: _baseline(model.t_arr[r].lb, model.t_arr[r].ub) for r in model.ARR_INSTANCES}
    model._dep_baseline = {r: _baseline(model.t_dep[r].lb, model.t_dep[r].ub) for r in model.DEP_INSTANCES}

    model.arr_dev_plus = pyo.Var(model.ARR_INSTANCES, domain=pyo.NonNegativeIntegers)
    model.arr_dev_minus = pyo.Var(model.ARR_INSTANCES, domain=pyo.NonNegativeIntegers)
    model.dep_dev_plus = pyo.Var(model.DEP_INSTANCES, domain=pyo.NonNegativeIntegers)
    model.dep_dev_minus = pyo.Var(model.DEP_INSTANCES, domain=pyo.NonNegativeIntegers)

    def arr_dev_link_rule(m, role, flno, gun):
        r = (role, flno, gun)
        return m.t_arr[r] - m._arr_baseline[r] == m.arr_dev_plus[r] - m.arr_dev_minus[r]
    model.arr_dev_link = pyo.Constraint(model.ARR_INSTANCES, rule=arr_dev_link_rule)

    def dep_dev_link_rule(m, role, flno, gun):
        r = (role, flno, gun)
        return m.t_dep[r] - m._dep_baseline[r] == m.dep_dev_plus[r] - m.dep_dev_minus[r]
    model.dep_dev_link = pyo.Constraint(model.DEP_INSTANCES, rule=dep_dev_link_rule)

    model.total_deviation = pyo.Expression(
        expr=sum(model.arr_dev_plus[r] + model.arr_dev_minus[r] for r in model.ARR_INSTANCES)
        + sum(model.dep_dev_plus[r] + model.dep_dev_minus[r] for r in model.DEP_INSTANCES)
    )
    model.objective = pyo.Objective(expr=model.total_deviation, sense=pyo.minimize)

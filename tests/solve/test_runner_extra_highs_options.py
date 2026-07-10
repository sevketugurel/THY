"""M5c (docs/decisions.md 2026-07-10): solve() needs a generic escape hatch
for ad-hoc HiGHS options beyond the few already named (mip_gap, log_file,
mip_heuristic_effort) -- specifically to test the "is the root-node stall a
symmetry/cut-generation artifact, not a size artifact" hypothesis
(mip_detect_symmetry off) on the full-data Plan B model, without hardcoding
a one-off parameter into the function signature every time a new HiGHS knob
needs testing.

marker: solve (trivial fixed-point model, solves instantly).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.model.objective import add_connection_reward_objective
from src.solve.runner import solve

pytestmark = pytest.mark.solve


def _candidate():
    return Candidate(
        od="ZZA-ZZB", o="ZZA", d="ZZB", gun=1, flno1=1, flno2=2,
        r1_id=("IB", 1, 1), r2_id=("OB", 2, 1), arr_time=None, dep_time=None,
        gap_min=100, arr_lo=0, arr_hi=0, dep_lo=100, dep_hi=100,
        gap_lo=100, gap_hi=100,
    )


def _build():
    c = _candidate()
    model = pyo.ConcreteModel()
    model._candidates = [c]
    add_flight_time_variables(model, [c])
    add_b_constraints(model, [c], L=60, U=300)
    add_c_constraints(model, [c])
    add_connection_reward_objective(model, {("ZZA", "ZZB"): 100})
    return model


def test_extra_highs_options_pass_through_without_breaking_solve():
    model = _build()
    result = solve(
        model, solver="highs", time_limit_sec=60, seed=42,
        extra_highs_options={"mip_detect_symmetry": False, "presolve": "on"},
    )
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(100.0)


def test_extra_highs_options_default_none_is_a_noop():
    model = _build()
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(100.0)


def test_maxiterations_termination_is_treated_like_time_limit(monkeypatch):
    # M5d (docs/decisions.md 2026-07-10): appsi_highs maps HiGHS's "Solution
    # limit reached" (mip_max_improving_sols -- used to force a clean early
    # stop for a warm-started full-data run, since HiGHS's own time_limit
    # does not reliably interrupt root-node cutting) to Pyomo's
    # maxIterations termination condition, NOT maxTimeLimit -- before this
    # fix, runner.py's status mapping silently dropped a genuinely-found
    # feasible incumbent (status fell through to str(term)=="maxIterations",
    # which wasn't in the ("optimal","time_limit") extraction gate, so
    # objective_value/selected stayed empty even though HiGHS reported a
    # real incumbent). Forcing this deterministically via a real solve is
    # unreliable (trivial models often close the gap on their first/only
    # improving solution and report "optimal" instead) -- monkeypatch the
    # termination condition directly, matching the existing pattern in
    # test_runner_time_limit_no_incumbent.py.
    model = _build()
    import src.solve.runner as runner_mod
    real_factory = pyo.SolverFactory

    def fake_factory(name):
        opt = real_factory(name)
        real_opt_solve = opt.solve

        def fake_solve(*a, **kw):
            actual_result = real_opt_solve(*a, **kw)
            actual_result.solver.termination_condition = pyo.TerminationCondition.maxIterations
            return actual_result
        opt.solve = fake_solve
        return opt

    monkeypatch.setattr(runner_mod.pyo, "SolverFactory", fake_factory)
    result = runner_mod.solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "time_limit"
    assert result.objective_value == pytest.approx(100.0)
    assert result.selected != {}

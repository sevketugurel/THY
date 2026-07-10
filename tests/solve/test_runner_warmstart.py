"""M5d (docs/decisions.md 2026-07-10): solve()'s warmstart passthrough --
appsi_highs's legacy solve() interface accepts warmstart=True, which reads
every Var's CURRENT .value and hands them to HiGHS as a MIP start via
highspy's setSolution. Empirically confirmed (manual smoke test before
writing this): HiGHS's own log prints "MIP start solution is feasible,
objective value is X" when the transfer actually happens -- this test locks
that confirmation string in, so a future Pyomo/HiGHS version silently
breaking the transfer is caught immediately rather than discovered by a
confusing full-data run.

marker: solve (trivial small MIP, solves instantly either way -- this test
is about the LOG evidence of transfer, not about warmstart making a hard
problem easier).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.model.objective import add_connection_reward_objective
from src.solve.runner import solve

pytestmark = pytest.mark.solve


def _candidate():
    # arr fixed at 0, dep free in [0,400] -- x/gap/y stay real (unfixed)
    # binaries/integers, unlike a gap_lo==gap_hi candidate (which B.fix()es
    # trivially and would make this test degenerate).
    return Candidate(
        od="ZZA-ZZB", o="ZZA", d="ZZB", gun=1, flno1=1, flno2=2,
        r1_id=("IB", 1, 1), r2_id=("OB", 2, 1), arr_time=None, dep_time=None,
        gap_min=100, arr_lo=0, arr_hi=0, dep_lo=0, dep_hi=400,
        gap_lo=0, gap_hi=400,
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


def test_warmstart_transfer_is_visible_in_highs_log(tmp_path):
    model = _build()
    # a known-feasible point: x=1, gap=100 (in [L,U]=[60,300]), t_dep=100.
    model.x[0].value = 1
    model.gap[0].value = 100
    model.y[0].value = 0
    model.t_dep["OB", 2, 1].value = 100

    log_path = tmp_path / "warmstart.log"
    result = solve(model, solver="highs", time_limit_sec=30, seed=42, log_file=log_path, warmstart=True)

    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(100.0)
    log_text = log_path.read_text()
    assert "MIP start solution is feasible" in log_text, (
        "warm-start transfer not confirmed in HiGHS log -- appsi may have "
        "stopped forwarding .value to highspy's setSolution"
    )


def test_warmstart_false_does_not_claim_a_mip_start(tmp_path):
    model = _build()
    model.x[0].value = 1
    model.gap[0].value = 100
    model.y[0].value = 0
    model.t_dep["OB", 2, 1].value = 100

    log_path = tmp_path / "no_warmstart.log"
    result = solve(model, solver="highs", time_limit_sec=30, seed=42, log_file=log_path, warmstart=False)

    assert result.status == "optimal"
    log_text = log_path.read_text()
    assert "MIP start solution is feasible" not in log_text

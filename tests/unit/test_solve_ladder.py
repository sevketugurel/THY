"""Unit tests for src.solve.ladder -- M5's 3-step solve ladder, using a fake
solve_fn (dependency injection) so the control-flow logic is verified
without ever running a real (slow) HiGHS solve.

Doğruluk argümanı: adım 1 (tam ayarlanabilir) optimal VEYA time_limit+incumbent
verirse KABUL edilir, dur. İkisi de olmazsa (infeasible, ya da time_limit
incumbent'sız) adım 2'ye geçilir: K şemasındaki her K için top-K pazar
adjustable, gerisi baseline'a sabitlenir (residual capacity'ye katlanır),
tekrar dene. Adım 2'nin HİÇBİR K'sı başarılı olmazsa adım 3: DUR ve
diagnostic log'la (sessizce devam ETME).

marker: unit (solve_fn fake, gerçek HiGHS çağrısı yok -- <1sn).
"""
import time

import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.solve.ladder import solve_with_ladder
from src.solve.runner import SolveResult

pytestmark = pytest.mark.unit


def _candidate(o, d, flno1, flno2, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun),
        arr_time=None, dep_time=None, gap_min=100,
        arr_lo=0, arr_hi=0, dep_lo=100, dep_hi=100,
        gap_lo=100, gap_hi=100,
    )


def _ladder_kwargs(candidates):
    return dict(
        candidates_full=candidates, rho={("ZZA", "ZZB"): 100, ("ZZC", "ZZD"): 50},
        journey_constants={}, rival_data={}, b_od_data={}, ranking_table=None,
        pairs_df=None, r_o_lookup={}, tau=45, x_dev=15, epoch_anchor=None,
        alpha=0.2, gamma=30, tk_rows=None, bucket_size_min=10,
        capacity_departure=10, capacity_arrival=15, L=60, U=300, monotonic=True,
    )


def _result(status, obj=None):
    return SolveResult(status=status, objective_value=obj, selected={}, solve_time_sec=0.1)


def test_step1_success_stops_immediately(monkeypatch):
    calls = []

    def fake_build(*a, **kw):
        return object()

    def fake_solve(model, solver, time_limit_sec, seed, **kwargs):
        calls.append("solve")
        return _result("optimal", 100.0)

    monkeypatch.setattr("src.solve.ladder.build_model_m4", fake_build)
    candidates = [_candidate("ZZA", "ZZB", 1, 2)]
    model, result, log = solve_with_ladder(**_ladder_kwargs(candidates), solve_fn=fake_solve)
    assert result.status == "optimal"
    assert len(calls) == 1
    assert log[0]["step"] == "step1_full_adjustable"
    assert len(log) == 1


def test_step1_fails_escalates_to_step2_and_succeeds(monkeypatch):
    call_log = []

    def fake_build(*a, **kw):
        return object()

    def fake_solve(model, solver, time_limit_sec, seed, **kwargs):
        call_log.append(1)
        if len(call_log) == 1:
            return _result("infeasible")
        return _result("optimal", 42.0)

    monkeypatch.setattr("src.solve.ladder.build_model_m4", fake_build)
    candidates = [_candidate("ZZA", "ZZB", 1, 2), _candidate("ZZC", "ZZD", 3, 4)]
    model, result, log = solve_with_ladder(
        **_ladder_kwargs(candidates), solve_fn=fake_solve, step2_k_schedule=(1, 2),
    )
    assert result.status == "optimal"
    assert len(call_log) == 2
    assert log[0]["step"] == "step1_full_adjustable"
    assert log[1]["step"] == "step2_subset_k1"


def test_all_steps_fail_reaches_step3_diagnosis(monkeypatch):
    def fake_build(*a, **kw):
        return object()

    def fake_solve(model, solver, time_limit_sec, seed, **kwargs):
        return _result("infeasible")

    monkeypatch.setattr("src.solve.ladder.build_model_m4", fake_build)
    candidates = [_candidate("ZZA", "ZZB", 1, 2), _candidate("ZZC", "ZZD", 3, 4)]
    model, result, log = solve_with_ladder(
        **_ladder_kwargs(candidates), solve_fn=fake_solve, step2_k_schedule=(1, 2),
    )
    # M5f Kapı-5: step3 normalizes the terminal status so it's unambiguous
    # from the return value alone (the raw last-attempt status is still in
    # ladder_log for diagnostics).
    assert result.status == "no_feasible_solution_found"
    assert result.objective_value is None
    assert log[-1]["step"] == "step3_stop_diagnose"
    steps = [entry["step"] for entry in log]
    assert steps == [
        "step1_full_adjustable", "step2_subset_k1", "step2_subset_k2", "step3_stop_diagnose",
    ]


def test_time_limit_with_incumbent_is_accepted_at_step1(monkeypatch):
    def fake_build(*a, **kw):
        return object()

    def fake_solve(model, solver, time_limit_sec, seed, **kwargs):
        return _result("time_limit", 77.0)

    monkeypatch.setattr("src.solve.ladder.build_model_m4", fake_build)
    candidates = [_candidate("ZZA", "ZZB", 1, 2)]
    model, result, log = solve_with_ladder(**_ladder_kwargs(candidates), solve_fn=fake_solve)
    assert result.status == "time_limit"
    assert result.objective_value == 77.0
    assert len(log) == 1


def test_time_limit_without_incumbent_escalates(monkeypatch):
    call_log = []

    def fake_build(*a, **kw):
        return object()

    def fake_solve(model, solver, time_limit_sec, seed, **kwargs):
        call_log.append(1)
        if len(call_log) == 1:
            return _result("time_limit", None)  # no incumbent
        return _result("optimal", 10.0)

    monkeypatch.setattr("src.solve.ladder.build_model_m4", fake_build)
    candidates = [_candidate("ZZA", "ZZB", 1, 2), _candidate("ZZC", "ZZD", 3, 4)]
    model, result, log = solve_with_ladder(
        **_ladder_kwargs(candidates), solve_fn=fake_solve, step2_k_schedule=(1,),
    )
    assert result.status == "optimal"
    assert len(call_log) == 2


def test_deadline_in_the_past_skips_all_steps_without_solving(monkeypatch):
    def fake_build(*a, **kw):
        raise AssertionError("build should never be reached once the deadline has passed")

    def fake_solve(model, solver, time_limit_sec, seed, **kwargs):
        raise AssertionError("solve should never be reached once the deadline has passed")

    monkeypatch.setattr("src.solve.ladder.build_model_m4", fake_build)
    candidates = [_candidate("ZZA", "ZZB", 1, 2)]
    model, result, log = solve_with_ladder(
        **_ladder_kwargs(candidates), solve_fn=fake_solve, step2_k_schedule=(1,),
        deadline_ts=time.time() - 1,
    )
    assert result.status == "budget_exceeded"
    assert model is None
    assert log[0]["step"] == "step1_full_adjustable"
    assert log[0]["status"] == "budget_exceeded"
    assert log[1]["step"] == "step2_subset_k1"
    assert log[1]["status"] == "budget_exceeded"
    assert log[-1]["step"] == "step3_stop_diagnose"


# --- M5f Kapı-5: validate_fn gating + elastic single-shot fallback ---

def _elastic_result(status, arr, dep, selected=None, gap_values=None, obj=0.0):
    return SolveResult(
        status=status, objective_value=obj, selected=selected or {},
        gap_values=gap_values or {}, arr_times=arr, dep_times=dep, solve_time_sec=0.1,
    )


def test_step1_incumbent_rejected_by_validate_fn_falls_through_to_step2(monkeypatch):
    # M5f Kapı-5 core safety property: an incumbent is NOT enough on its
    # own when validate_fn is supplied -- a "valid MIP status" that fails
    # independent validation must NOT be returned as the ladder's answer,
    # it must escalate exactly like a genuine infeasible/no-incumbent case.
    monkeypatch.setattr("src.solve.ladder.build_model_m4", lambda *a, **kw: object())

    call_log = []

    def fake_solve(model, solver, time_limit_sec, seed, **kwargs):
        call_log.append(1)
        if len(call_log) == 1:
            return _result("optimal", 100.0)  # has an incumbent...
        return _result("optimal", 42.0)

    def reject_first_accept_rest(candidates, result):
        # step1's incumbent (obj=100.0) is rejected; step2's (obj=42.0) passes.
        return result.objective_value != 100.0

    candidates = [_candidate("ZZA", "ZZB", 1, 2), _candidate("ZZC", "ZZD", 3, 4)]
    model, result, log = solve_with_ladder(
        **_ladder_kwargs(candidates), solve_fn=fake_solve, step2_k_schedule=(1, 2),
        validate_fn=reject_first_accept_rest,
    )
    assert result.status == "optimal"
    assert result.objective_value == 42.0, "step1's rejected incumbent must NOT be the final answer"
    assert log[0]["step"] == "step1_full_adjustable"
    assert log[1]["step"] == "step2_subset_k1"


def test_elastic_fallback_accepted_when_slack_zero_and_validated(monkeypatch):
    # Single one-directional candidate -- no reverse market exists, so E1/E2
    # have no pairs to check at all -> Sigma-slack is trivially 0. Isolates
    # the test to the ladder's OWN accept/reject wiring, not E1/E2 arithmetic
    # (covered separately in test_m4_constraints_e1/e2.py).
    monkeypatch.setattr("src.solve.ladder.build_model_m4", lambda *a, **kw: object())
    monkeypatch.setattr("src.solve.ladder.build_elastic_feasibility_model", lambda *a, **kw: object())
    monkeypatch.setattr("src.solve.ladder.add_elastic_feasibility_objective", lambda *a, **kw: None)

    def fake_solve(model, solver, time_limit_sec, seed, **kwargs):
        return _result("infeasible")

    c1 = _candidate("ZZA", "ZZB", 1, 2)

    def fake_elastic_solve(model, solver, time_limit_sec, seed, **kwargs):
        return _elastic_result(
            "optimal", arr={("IB", 1, 1): 0}, dep={("OB", 2, 1): 100},
            selected={c1: 1}, gap_values={c1: 100},
        )

    kwargs = _ladder_kwargs([c1])
    kwargs["journey_constants"] = {("ZZA", "ZZB"): 0}
    model, result, log = solve_with_ladder(
        **kwargs, solve_fn=fake_solve, elastic_solve_fn=fake_elastic_solve,
        enable_elastic_fallback=True, step2_k_schedule=(),
        validate_fn=lambda candidates, result: True,
    )
    assert result.status == "optimal"
    assert result.rank_values == {}  # empty rival_data -> nothing to report, but no crash
    steps = [entry["step"] for entry in log]
    assert steps == ["step1_full_adjustable", "step_elastic_fallback"]
    assert log[1]["sigma_slack"] == 0.0


def test_elastic_fallback_skipped_when_slack_nonzero_falls_through(monkeypatch):
    monkeypatch.setattr("src.solve.ladder.build_model_m4", lambda *a, **kw: object())
    monkeypatch.setattr("src.solve.ladder.build_elastic_feasibility_model", lambda *a, **kw: object())
    monkeypatch.setattr("src.solve.ladder.add_elastic_feasibility_objective", lambda *a, **kw: None)

    def fake_solve(model, solver, time_limit_sec, seed, **kwargs):
        return _result("infeasible")

    c_fwd = _candidate("ZZA", "ZZB", 1, 2)
    c_bwd = _candidate("ZZB", "ZZA", 3, 4)

    def fake_elastic_solve(model, solver, time_limit_sec, seed, **kwargs):
        # fwd offered (gap=100 in [L,U]), bwd's gap pushed OUTSIDE [L,U] --
        # n_fwd=1, n_bwd=0 under UNCONDITIONAL semantics would need slack;
        # force unconditional via e1_activation override to get a
        # deterministic nonzero slack without depending on a_dir plumbing
        # this stub doesn't build.
        return _elastic_result(
            "optimal", arr={("IB", 1, 1): 0, ("IB", 3, 1): 0},
            dep={("OB", 2, 1): 100, ("OB", 4, 1): 1000},
        )

    kwargs = _ladder_kwargs([c_fwd, c_bwd])
    kwargs["journey_constants"] = {("ZZA", "ZZB"): 0, ("ZZB", "ZZA"): 0}
    model, result, log = solve_with_ladder(
        **kwargs, solve_fn=fake_solve, elastic_solve_fn=fake_elastic_solve,
        enable_elastic_fallback=True, step2_k_schedule=(), e1_activation="unconditional",
        validate_fn=lambda candidates, result: True,
    )
    # Both step1 (fake infeasible) and the elastic fallback (nonzero slack)
    # were rejected -- must reach step3, never silently accept the elastic
    # point (which is a slack-relaxed, NOT strict-feasible, point). The
    # elastic result's OWN status was "optimal" (for ITS relaxed problem) --
    # step3 must normalize this away, not let it masquerade as accepted.
    assert result.status == "no_feasible_solution_found"
    assert result.objective_value is None
    steps = [entry["step"] for entry in log]
    assert steps == ["step1_full_adjustable", "step_elastic_fallback", "step3_stop_diagnose"]
    assert log[1]["sigma_slack"] > 0

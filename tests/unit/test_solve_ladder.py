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

    def fake_solve(model, solver, time_limit_sec, seed):
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

    def fake_solve(model, solver, time_limit_sec, seed):
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

    def fake_solve(model, solver, time_limit_sec, seed):
        return _result("infeasible")

    monkeypatch.setattr("src.solve.ladder.build_model_m4", fake_build)
    candidates = [_candidate("ZZA", "ZZB", 1, 2), _candidate("ZZC", "ZZD", 3, 4)]
    model, result, log = solve_with_ladder(
        **_ladder_kwargs(candidates), solve_fn=fake_solve, step2_k_schedule=(1, 2),
    )
    assert result.status == "infeasible"
    assert log[-1]["step"] == "step3_stop_diagnose"
    steps = [entry["step"] for entry in log]
    assert steps == [
        "step1_full_adjustable", "step2_subset_k1", "step2_subset_k2", "step3_stop_diagnose",
    ]


def test_time_limit_with_incumbent_is_accepted_at_step1(monkeypatch):
    def fake_build(*a, **kw):
        return object()

    def fake_solve(model, solver, time_limit_sec, seed):
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

    def fake_solve(model, solver, time_limit_sec, seed):
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

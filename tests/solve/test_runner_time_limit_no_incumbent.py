"""Solve test for src.solve.runner's handling of a time-limit termination
with NO feasible incumbent found (distinct from the infeasible case already
covered by tests/solve/test_m3_constraints_g.py's genuine-violation test).

Doğruluk argümanı (M5 motivasyonu): 900sn zaman limitiyle çözülen full-data
modelinde HiGHS'in HİÇ feasible çözüm bulamadan zaman limitine ulaşması
gerçek bir olasılık (yoğun reifikasyonlu, dar feasible bölgeli bir model).
Bu durumda `opt.solve(model, load_solutions=False)`'un termination_condition'ı
`maxTimeLimit` olur ama `model.solutions.load_from(result)` çağrısı, tıpkı
infeasible durumda olduğu gibi, YÜKLENECEK bir çözüm olmadığından exception
fırlatır (appsi_highs'ın kendi hata mesajı bunu doğruluyor, bkz.
docs/decisions.md). Bu senaryoyu küçük bir MIP'le DETERMİNİSTİK olarak
tetiklemek pratikte zor (HiGHS'in presolve/heuristic'leri çoğu küçük/orta
problemde anında bir incumbent buluyor) -- bu yüzden `model.solutions.load_from`
monkeypatch'lenerek runner'ın KENDİ savunma dalı doğrudan test ediliyor (gerçek
solver davranışını mock'lamak değil, runner'ın BİR exception'a nasıl tepki
verdiğini test etmek).

marker: solve (uses a real solve() call + a real small model; only the
load_from step is monkeypatched).
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


def test_time_limit_with_no_incumbent_does_not_crash(monkeypatch):
    c = _candidate()
    model = pyo.ConcreteModel()
    model._candidates = [c]
    add_flight_time_variables(model, [c])
    add_b_constraints(model, [c], L=60, U=300)
    add_c_constraints(model, [c])
    add_connection_reward_objective(model, {("ZZA", "ZZB"): 100})

    # Monkeypatch model.solutions.load_from specifically (not the solver
    # itself) -- simulates the real appsi_highs failure mode for a
    # maxTimeLimit-with-no-incumbent result without needing to construct a
    # MIP hard enough to genuinely reproduce it in test time.
    def _patched_load_from(result, **kwargs):
        raise RuntimeError(
            "A feasible solution was not found, so no solution can be loaded. "
            "If using the appsi.solvers.Highs interface, you can set "
            "opt.config.load_solution=False."
        )
    monkeypatch.setattr(model.solutions, "load_from", _patched_load_from)

    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status in ("optimal", "time_limit")
    assert result.objective_value is None
    assert result.selected == {}

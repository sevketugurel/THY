"""Solve test for src.solve.runner's rank_values extraction -- a latent bug
found via the M4 CLI end-to-end run (E1's directional balancing pushed the
solver into beating ALL of a market's rivals for the first time, which had
never happened in any prior fixture run).

Doğruluk argümanı (ultrathink, kod öncesi bulundu): `model.rank[market]` bir
Expression, ham `N - beaten` değerini taşır -- N rakibin TÜMÜ yenilirse bu
0'a iner. Ama gerçek change_ranking_input.xlsx tablosu r=0 için HİÇBİR
zaman bir satır tanımlamıyor (min gözlemlenen r HER ZAMAN 1) -- bu yüzden
`add_rank_onehot`'un linking kısıtı ZATEN r>=1'e clamp'liyor (bkz.
constraints_competition.py::add_rank_onehot docstring, "kritik düzeltme").
Ancak `runner.py`'nin `rank_values` çıkarımı bu clamp'i YOK SAYIYORDU --
ham `model.rank[market]` değerini DOĞRUDAN output.json'a yazıyordu, r=0
gibi tabloda hiç var olmayan bir değeri raporlayarak validator'ın (ve
`add_rank_onehot`'un kendi objektif ödülünün) beklediği max(1,N-beaten)
semantiğiyle ÇELİŞİYORDU. N=0 (rakipsiz pazar) durumunda 0 DOĞRU bir
değerdir (clamp EDİLMEMELİ) -- bu yüzden clamp yalnızca N>0 iken uygulanır.

marker: solve (small HiGHS solve).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_competition import add_d_constraints, add_rank_onehot
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300


def _fixed_candidate(o, d, gun, gap, flno1, flno2):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=gap, arr_lo=0, arr_hi=0, dep_lo=gap, dep_hi=gap, gap_lo=gap, gap_hi=gap,
    )


def _build(candidates, journey_constants, rival_data):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    n_by_market = add_d_constraints(model, candidates, journey_constants, rival_data, monotonic=True)
    add_rank_onehot(model, n_by_market)
    model._candidates = candidates
    return model


def test_rank_values_clamped_to_one_when_all_rivals_beaten():
    # Single rival R1, easily beaten (J=280<=300) -- raw model.rank = 1-1 = 0,
    # but the real ranking table never has an r=0 row; the reported value
    # must be the clamped max(1,0)=1.
    c = _fixed_candidate("ZZA", "ZZB", 1, gap=60, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 300}})
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.rank["ZZA", "ZZB", 1]) == pytest.approx(0.0), \
        "test setup sanity: raw expression should be 0 (all rivals beaten)"
    assert result.rank_values[("ZZA", "ZZB", 1)] == 1


def test_rank_values_stays_zero_when_market_has_no_rivals():
    # No rivals at all (N=0) -- 0 IS the correct reported value, must NOT be
    # incorrectly clamped up to 1.
    c = _fixed_candidate("ZZA", "ZZB", 1, gap=60, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {})
    model.objective = pyo.Objective(expr=model.x[0], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.rank_values[("ZZA", "ZZB", 1)] == 0

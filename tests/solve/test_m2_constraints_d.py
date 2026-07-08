"""Adversarial solve tests for D's beat reification + OR-aggregation + rank linking.

Doğruluk argümanı (ultrathink, kod öncesi): beat_{pi,k}=1 anlamı "pi rakip
k'yı yeniyor" (J_pi <= T_comp_k). Gerçek change_ranking_input.xlsx tablosu
MONOTONIK (sabit N,b için r arttıkça W hiç artmıyor -- 820 grupta 0 ihlal,
bkz. tests/unit/test_ranking.py). Bu doğruysa tek-yönlü (forward) zorlama
yeterli:
    J_pi <= T_comp_k + M(1-beat)   [beat=1 => J<=T_comp, OVER-CLAIM engellenir]
Backward yön (J<=T_comp => beat=1) gerekmiyor çünkü optimal çözüm, W monoton
azalan olduğundan r'yi küçültmeye (daha çok rakip yenmeye) çalışır -- beat=0
bırakmak (under-claim) objektifi ASLA artıramaz, solver'ın bunu YAPMA
motivasyonu yok. Monotonluk BOZULURSA sistem otomatik çift-yönlü moda geçer
(bu dosyada her iki mod da test ediliyor).

OR-aggregation (beaten_k = OR_pi(beat_{pi,k})) HER ZAMAN iki yönlü -- bu
monotonluktan bağımsız yapısal bir gereklilik (iç tutarlılık: bir pi
gerçekten yeniyorsa beaten_k=1 OLMAK ZORUNDA, aksi halde model kendi içinde
tutarsız/yanlış rank hesaplar).

marker: solve (small HiGHS solve, single/few-candidate models).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_competition import add_d_constraints
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


def _build(candidates, journey_constants, rival_data, monotonic):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_d_constraints(model, candidates, journey_constants, rival_data, monotonic=monotonic)
    model._candidates = candidates
    return model


def test_beat_cannot_be_one_when_j_exceeds_tcomp_forward_mode():
    # gap=250 -> J=220+250=470. T_comp=300 -> J>T_comp, should NOT beat.
    # Objective REWARDS beat=1 (adversarial) -- forward forcing must block it.
    c = _fixed_candidate("ZZA", "ZZB", 1, gap=250, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=True)
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beat[0, "R1"]) == pytest.approx(0.0)


def test_beat_can_be_one_when_j_within_tcomp_forward_mode():
    # gap=60 -> J=220+60=280. T_comp=300 -> J<=T_comp, CAN beat (feasible).
    c = _fixed_candidate("ZZA", "ZZB", 1, gap=60, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=True)
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beat[0, "R1"]) == pytest.approx(1.0)


def test_forward_only_mode_allows_under_claim_when_adversarial():
    # Monotonic (forward-only) mode: J<=T_comp but objective REWARDS beat=0.
    # No backward forcing exists in this mode -- beat=0 is a legitimate
    # (if unhelpful) feasible point. This is exactly why the forward-only
    # optimization is safe ONLY when downstream reward is monotonic: the
    # solver never has incentive to pick it, but nothing stops it structurally.
    c = _fixed_candidate("ZZA", "ZZB", 1, gap=60, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=True)
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beat[0, "R1"]) == pytest.approx(0.0)


def test_bidirectional_fallback_forces_beat_one_when_j_within_tcomp():
    # monotonic=False -> full bidirectional forcing. Same adversarial setup as
    # the forward-only test above, but now beat=0 must be INFEASIBLE (not
    # just unrewarded) when J<=T_comp.
    c = _fixed_candidate("ZZA", "ZZB", 1, gap=60, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=False)
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beat[0, "R1"]) == pytest.approx(1.0), \
        "beat=0 was chosen despite J<=T_comp in bidirectional mode -- backward forcing broken"


def test_beat_requires_x_one_cannot_beat_unoffered_connection():
    # gap=400 (invalid, x forced to 0). Even though J might arithmetically be
    # <=T_comp, an unoffered connection cannot claim a win.
    c = _fixed_candidate("ZZA", "ZZB", 1, gap=400, flno1=1, flno2=2)  # J=620, way above T_comp anyway
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 9999}}, monotonic=True)
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beat[0, "R1"]) == pytest.approx(0.0)


def test_beaten_aggregation_forces_one_when_any_beat_is_one():
    # Two candidates both beating the same rival -- beaten_k must be forced to
    # 1 (structural OR consistency), even under an adversarial objective that
    # wants beaten_k=0.
    c1 = _fixed_candidate("ZZA", "ZZB", 1, gap=60, flno1=1, flno2=2)
    c2 = _fixed_candidate("ZZA", "ZZB", 1, gap=70, flno1=3, flno2=4)
    model = _build(
        [c1, c2], {("ZZA", "ZZB"): 220},
        {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=True,
    )
    # Force beat[0,"R1"]=1 directly (both legs already valid, J<=T_comp for both).
    model.x[0].fix(1)
    model.x[1].fix(1)
    model.beat[0, "R1"].fix(1)
    model.objective = pyo.Objective(
        expr=model.beaten["ZZA", "ZZB", 1, "R1"], sense=pyo.minimize,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beaten["ZZA", "ZZB", 1, "R1"]) == pytest.approx(1.0), \
        "beaten_k=0 was chosen despite beat[0,R1]=1 -- OR-aggregation lower bound broken"


def test_beaten_aggregation_forces_zero_when_no_beat_is_one():
    c = _fixed_candidate("ZZA", "ZZB", 1, gap=250, flno1=1, flno2=2)  # J=470 > T_comp=300
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=True)
    model.objective = pyo.Objective(
        expr=model.beaten["ZZA", "ZZB", 1, "R1"], sense=pyo.maximize,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beaten["ZZA", "ZZB", 1, "R1"]) == pytest.approx(0.0), \
        "beaten_k=1 was chosen despite no candidate beating it -- OR-aggregation upper bound broken"


def test_rank_expression_matches_hand_calc():
    # N=2 rivals (R1,R2). Only R1 beatable (J=280<=300) -- R2(250) is not.
    # Forward-only forcing NEVER makes beat=1 automatic; it must be rewarded
    # for the "under-claim never optimal" argument to actually kick in, so
    # this objective rewards beat directly (mirroring the real ranking
    # reward, which is exactly what makes forward-only forcing safe).
    c = _fixed_candidate("ZZA", "ZZB", 1, gap=60, flno1=1, flno2=2)
    model = _build(
        [c], {("ZZA", "ZZB"): 220},
        {("ZZA", "ZZB", 1): {"R1": 300, "R2": 250}}, monotonic=True,
    )
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.maximize)
    solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert pyo.value(model.rank["ZZA", "ZZB", 1]) == pytest.approx(1.0)

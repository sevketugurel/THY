"""Solve tests for E1 (yönsel sayı dengesi).

Doğruluk argümanı (ultrathink, kod öncesi): brief "iki yöndeki sunulan
bağlantı sayıları arasındaki bağıl dengesizlik alpha eşiğini aşmamalı"
diyor. VARSAYIM formülü (ASSUMPTIONS.md'ye işlendi, organizatör sorusu
eklendi): |n_fwd - n_bwd| <= alpha*(n_fwd+n_bwd), (o,d,h) vs (d,o,h) AYNI
gün. Big-M/reifikasyon GEREKMİYOR -- n_fwd,n_bwd zaten Sum(x_pi) (dogrudan
lineer ifadeler), iki yönlü mutlak-değer eşitsizliği yeterli:

    n_fwd - n_bwd <= alpha*(n_fwd+n_bwd)
    n_bwd - n_fwd <= alpha*(n_fwd+n_bwd)

İki yön de boş -> 0<=0 her ikisinde de, otomatik sağlanır (brief'in istediği).

KRİTİK dinamik (model.md'ye yazılacak): B'nin "gap in [L,U] ise x=1 ZORUNLU"
kuralı nedeniyle, E1'i sağlamanın YEGANE yolu bir bağlantıyı KISMEN
gizlemek DEĞİL (bu B tarafından yasaklı), zamanı KAYDIRIP bağlantının
GAP'ini [L,U] dışına iterek TAMAMEN ÖLDÜRMEKTİR. Bu, küçük/asimetrik
pazarlarda E1'i potansiyel bir "amaç bastırıcı" yapar -- tek bir fazla
bağlantıyı dengelemek yerine, solver TÜM pazarı sıfırlamayı (n_fwd=n_bwd=0,
kendiliğinden sağlanan durum) tercih edebilir eğer bu objektif açısından
ucuzsa. Diagnostik bu davranışı izler.

marker: solve (small HiGHS solve, <60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_balance import add_e1_constraints
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300
ALPHA = 0.20


def _candidate(o, d, flno1, flno2, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=100, arr_lo=0, arr_hi=0, dep_lo=0, dep_hi=400,
        gap_lo=0, gap_hi=400,
    )


def _build(candidates):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_e1_constraints(model, candidates, alpha=ALPHA)
    model._candidates = candidates
    return model


def test_e1_forces_connection_kill_to_restore_balance():
    # fwd market (ZZE,ZZF) has 2 candidates, bwd (ZZF,ZZE) has 1. Objective
    # rewards MAXIMIZING total offered connections (adversarial: wants
    # fwd=2,bwd=1, which VIOLATES E1: |2-1|=1 > 0.2*3=0.6). E1 must force
    # exactly one of the two fwd candidates to be pushed out of [L,U],
    # settling at fwd=1,bwd=1 (better for the objective than killing all 3).
    c1 = _candidate("ZZE", "ZZF", 201, 301)
    c2 = _candidate("ZZE", "ZZF", 202, 302)
    c3 = _candidate("ZZF", "ZZE", 203, 303)
    candidates = [c1, c2, c3]
    model = _build(candidates)
    model.objective = pyo.Objective(expr=sum(model.x[i] for i in model.CANDIDATES), sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    x1, x2, x3 = pyo.value(model.x[0]), pyo.value(model.x[1]), pyo.value(model.x[2])
    assert x1 + x2 == pytest.approx(1.0), "exactly one fwd candidate must be sacrificed"
    assert x3 == pytest.approx(1.0), "bwd candidate should survive (killing it helps nothing)"
    assert result.objective_value == pytest.approx(2.0)


def test_e1_non_binding_when_already_balanced():
    # 1 fwd, 1 bwd -- already balanced (|1-1|=0<=alpha*2). E1 must not
    # additionally restrict anything.
    c1 = _candidate("ZZE", "ZZF", 201, 301)
    c3 = _candidate("ZZF", "ZZE", 203, 303)
    candidates = [c1, c3]
    model = _build(candidates)
    model.objective = pyo.Objective(expr=sum(model.x[i] for i in model.CANDIDATES), sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(2.0)


def test_e1_skips_one_directional_markets():
    # Only fwd market has candidates at all (bwd doesn't exist as a market in
    # this scenario) -- E1 must NOT force fwd to 0 just because bwd is
    # structurally absent (a modeling-scope gap, not a real imbalance).
    c1 = _candidate("ZZE", "ZZF", 201, 301)
    c2 = _candidate("ZZE", "ZZF", 202, 302)
    candidates = [c1, c2]
    model = _build(candidates)
    model.objective = pyo.Objective(expr=sum(model.x[i] for i in model.CANDIDATES), sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(2.0)

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

KARAR-0 (docs/CLOSING_PLAN.md, VARSAYIM-16, M5f): varsayılan
`activation="conditional"` modda E1 yalnızca HER İKİ yön de AKTİFKEN (>=1
sunulan bağlantı) bağlayıcı -- yukarıdaki "amaç bastırıcı" patolojisinin
TEK-YÖN-SIFIR alt-vakası artık kendiliğinden sağlanır. `activation="unconditional"`
eski literal okumayı duyarlılık analizi için korur. Testler HER İKİ modu da
kapsar: davranış AYNI kaldığı yerde (her iki yön de aktif) tek bir test
yeterli, davranış AYRIŞTIĞI yerde (bir yön yapısal olarak pasif) her iki
mod için AYRI testler var.

marker: solve (small HiGHS solve, <60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_balance import add_e1_constraints, add_e2_constraints
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300
ALPHA = 0.20
HUGE_GAMMA = 1_000_000  # E2 must never bind in these E1-focused tests


def _candidate(o, d, flno1, flno2, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=100, arr_lo=0, arr_hi=0, dep_lo=0, dep_hi=400,
        gap_lo=0, gap_hi=400,
    )


def _frozen_candidate(o, d, flno1, flno2, gap, gun=1):
    # Both legs Rfix (single-point window, matching K-subset's frozen legs)
    # -- gap_lo==gap_hi means x is data-determined (M5c fold, add_b_constraints),
    # not a genuine decision.
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=gap, arr_lo=0, arr_hi=0, dep_lo=gap, dep_hi=gap, gap_lo=gap, gap_hi=gap,
    )


def _dead_candidate(o, d, flno1, flno2, gun=1):
    # Fixed gap far OUTSIDE [L,U] -- B forces x=0 unconditionally in EVERY
    # feasible solution, but the candidate is still a STRUCTURAL member of
    # its (o,d,gun) group (not absent -- see test_e1_skips_one_directional_markets
    # for the "absent entirely" case).
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=1000, arr_lo=0, arr_hi=0, dep_lo=1000, dep_hi=1000, gap_lo=1000, gap_hi=1000,
    )


def _build_unconditional(candidates, alpha=ALPHA):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_e1_constraints(model, candidates, alpha=alpha, activation="unconditional")
    model._candidates = candidates
    return model


def _build_conditional(candidates, alpha=ALPHA):
    # Conditional E1 reuses E2's a_dir -- E2 must run first. journey_constants
    # covers every (o,d) market appearing in candidates; gamma is huge so E2
    # itself never binds (isolates these tests to E1's own behavior).
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    journey_constants = {(c.o, c.d): 0 for c in candidates}
    add_e2_constraints(model, candidates, journey_constants, gamma=HUGE_GAMMA, L=L, U=U)
    add_e1_constraints(model, candidates, alpha=alpha, activation="conditional")
    model._candidates = candidates
    return model


# --- Behavior IDENTICAL in both modes (both directions active in the optimum) ---

@pytest.mark.parametrize("build", [_build_unconditional, _build_conditional])
def test_e1_forces_connection_kill_to_restore_balance(build):
    # fwd market (ZZE,ZZF) has 2 candidates, bwd (ZZF,ZZE) has 1. Objective
    # rewards MAXIMIZING total offered connections (adversarial: wants
    # fwd=2,bwd=1, which VIOLATES E1: |2-1|=1 > 0.2*3=0.6). E1 must force
    # exactly one of the two fwd candidates to be pushed out of [L,U],
    # settling at fwd=1,bwd=1 (better for the objective than killing all 3).
    # Both directions end up ACTIVE in the optimum, so conditional and
    # unconditional modes agree here (gate term is 0 either way).
    c1 = _candidate("ZZE", "ZZF", 201, 301)
    c2 = _candidate("ZZE", "ZZF", 202, 302)
    c3 = _candidate("ZZF", "ZZE", 203, 303)
    candidates = [c1, c2, c3]
    model = build(candidates)
    model.objective = pyo.Objective(expr=sum(model.x[i] for i in model.CANDIDATES), sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    x1, x2, x3 = pyo.value(model.x[0]), pyo.value(model.x[1]), pyo.value(model.x[2])
    assert x1 + x2 == pytest.approx(1.0), "exactly one fwd candidate must be sacrificed"
    assert x3 == pytest.approx(1.0), "bwd candidate should survive (killing it helps nothing)"
    assert result.objective_value == pytest.approx(2.0)


@pytest.mark.parametrize("build", [_build_unconditional, _build_conditional])
def test_e1_non_binding_when_already_balanced(build):
    # 1 fwd, 1 bwd -- already balanced (|1-1|=0<=alpha*2). E1 must not
    # additionally restrict anything.
    c1 = _candidate("ZZE", "ZZF", 201, 301)
    c3 = _candidate("ZZF", "ZZE", 203, 303)
    candidates = [c1, c3]
    model = build(candidates)
    model.objective = pyo.Objective(expr=sum(model.x[i] for i in model.CANDIDATES), sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(2.0)


@pytest.mark.parametrize("build", [_build_unconditional, _build_conditional])
def test_e1_skips_one_directional_markets(build):
    # Only fwd market has candidates at all (bwd doesn't exist as a market in
    # this scenario) -- E1 must NOT force fwd to 0 just because bwd is
    # structurally absent (a modeling-scope gap, not a real imbalance).
    # Activation mode is irrelevant here -- the pair is never built at all.
    c1 = _candidate("ZZE", "ZZF", 201, 301)
    c2 = _candidate("ZZE", "ZZF", 202, 302)
    candidates = [c1, c2]
    model = build(candidates)
    model.objective = pyo.Objective(expr=sum(model.x[i] for i in model.CANDIDATES), sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(2.0)


@pytest.mark.parametrize("build", [_build_unconditional, _build_conditional])
def test_e1_exempts_fully_frozen_market_pair_that_violates_at_baseline(build):
    # M5c (docs/lp_anatomy.md §1, generalizes VARSAYIM-9/11's exempt+log
    # pattern from A/G to E1): fwd market (ZZE,ZZF) has 2 candidates, bwd
    # (ZZF,ZZE) has 1 -- SAME imbalance as
    # test_e1_forces_connection_kill_to_restore_balance, but here EVERY
    # candidate is fully Rfix (gap_lo==gap_hi, forced x=1 by B since
    # gap=100 is legal) -- exactly what K-subset's leg-freezing produces
    # for markets outside the adjustable set. With zero freedom to move
    # ANY of these flights, forcing E1's inequality would make the model
    # UNCONDITIONALLY infeasible for a reason that has nothing to do with
    # genuine data -- it's an artifact of the K-subset relaxation itself.
    # The pair must be EXEMPTED (constraint not built) and logged, not
    # silently solved around (VARSAYIM-9/11's own "not a violation, a
    # data-fact we can't change" reasoning applies identically here). Both
    # directions are forced-ACTIVE here (frozen offered), so conditional
    # and unconditional modes agree.
    c1 = _frozen_candidate("ZZE", "ZZF", 201, 301, gap=100)
    c2 = _frozen_candidate("ZZE", "ZZF", 202, 302, gap=100)
    c3 = _frozen_candidate("ZZF", "ZZE", 203, 303, gap=100)
    candidates = [c1, c2, c3]
    model = build(candidates)
    assert ("ZZE", "ZZF", 1) not in model.E1_PAIRS, "fully-frozen violating pair must be exempted, not built"
    assert model._e1_fold_counts["exempted"] == 1
    model.objective = pyo.Objective(expr=sum(model.x[i] for i in model.CANDIDATES), sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(3.0), \
        "all three candidates are forced x=1 by B; exemption must not additionally kill any of them"


@pytest.mark.parametrize("build", [_build_unconditional, _build_conditional])
def test_e1_still_builds_for_fully_frozen_pair_that_already_balances(build):
    # Control case: fully-frozen pair whose FORCED counts already satisfy
    # E1 (|1-1|=0<=alpha*2) -- must NOT be exempted (nothing to exempt,
    # it's not a violation), the constraint can be safely built (or
    # omitted as trivially satisfied; the key invariant is no infeasibility
    # and no false exemption count).
    c1 = _frozen_candidate("ZZE", "ZZF", 201, 301, gap=100)
    c3 = _frozen_candidate("ZZF", "ZZE", 203, 303, gap=100)
    candidates = [c1, c3]
    model = build(candidates)
    assert model._e1_fold_counts["exempted"] == 0
    model.objective = pyo.Objective(expr=sum(model.x[i] for i in model.CANDIDATES), sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(2.0)


# --- Behavior DIVERGES: one direction is structurally present but ends up
# fully inactive (0 offered) in the optimum -- this is KARAR-0's central case ---

def test_e1_unconditional_still_binds_for_mixed_pair_with_one_adjustable_side():
    # Mixed pair: fwd is fully frozen (1 forced-x=1 candidate), bwd has ONE
    # genuinely adjustable candidate -- literal/unconditional E1 does not
    # know or care whether the reverse direction is "genuinely" active, it
    # just compares raw counts. |1-n_bwd|<=0.2*(1+n_bwd): n_bwd=1 -> 0<=0.4
    # TRUE; n_bwd=0 -> 1<=0.2 FALSE -- so E1 forces the adjustable candidate
    # to be OFFERED even though bwd's own count is entirely the adversarial
    # objective's choice, not a real imbalance.
    c1 = _frozen_candidate("ZZE", "ZZF", 201, 301, gap=100)
    c3 = _candidate("ZZF", "ZZE", 203, 303)  # genuinely adjustable
    candidates = [c1, c3]
    model = _build_unconditional(candidates)
    assert ("ZZE", "ZZF", 1) in model.E1_PAIRS, "mixed pair (one adjustable side) must still be built"
    assert model._e1_fold_counts["exempted"] == 0
    # Adversarial: reward killing the adjustable bwd candidate (x[1]=0) --
    # E1 must block it, forcing x[1]=1 despite the objective wanting 0.
    # (maximize(-x[1]) prefers -x[1]=0 i.e. x[1]=0 -- genuinely adversarial,
    # unlike minimize(-x[1]) which would prefer x[1]=1 for free.)
    model.objective = pyo.Objective(expr=-model.x[1], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.x[1]) == pytest.approx(1.0), \
        "unconditional E1 failed to force the adjustable bwd candidate to stay offered against the frozen fwd side"


def test_e1_conditional_allows_mixed_pair_to_go_one_sided():
    # Same scenario as the unconditional test above, but under KARAR-0's
    # default conditional activation: once bwd's only candidate is killed
    # (a_bwd=0), the pair no longer has BOTH directions active -- E1
    # becomes non-binding and must NOT force the adjustable candidate back
    # on. This is the direct behavioral consequence of KARAR-0 (brief §7:
    # "aksi halde pasif yönler dengeyi yapay olarak zorlar").
    c1 = _frozen_candidate("ZZE", "ZZF", 201, 301, gap=100)
    c3 = _candidate("ZZF", "ZZE", 203, 303)  # genuinely adjustable
    candidates = [c1, c3]
    model = _build_conditional(candidates)
    assert ("ZZE", "ZZF", 1) in model.E1_PAIRS, "mixed pair (one adjustable side) is still built (a_dir may vary)"
    # Adversarial: reward killing the adjustable bwd candidate (x[1]=0).
    model.objective = pyo.Objective(expr=-model.x[1], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.x[1]) == pytest.approx(0.0), \
        "conditional E1 must allow the reverse direction to go fully inactive, not force it back on"


def test_e1_conditional_allows_full_market_when_reverse_direction_is_structurally_dead():
    # KARAR-0's motivating case, made concrete: fwd has 3 genuinely
    # adjustable candidates the objective wants to maximize; bwd has ONE
    # candidate whose gap is fixed far OUTSIDE [L,U] -- B forces it off in
    # EVERY feasible solution (n_bwd is ALWAYS 0, not a choice). Literal
    # E1 would require |n_fwd-0|<=alpha*n_fwd, i.e. n_fwd*(1-alpha)<=0,
    # i.e. n_fwd=0 -- forcing the ENTIRE fwd market to be killed just
    # because bwd can structurally never be offered (the "amaç bastırıcı"
    # pathology, brief §7). Conditional E1 must allow all 3 fwd candidates
    # to stay offered: a_bwd is structurally pinned to 0 (a_ub_rule forces
    # it whenever sum(x_bwd)=0), so the gate term relaxes the inequality
    # regardless of fwd's own count.
    c1 = _candidate("ZZE", "ZZF", 201, 301)
    c2 = _candidate("ZZE", "ZZF", 202, 302)
    c3 = _candidate("ZZE", "ZZF", 203, 303)
    c4 = _dead_candidate("ZZF", "ZZE", 204, 304)
    candidates = [c1, c2, c3, c4]
    model = _build_conditional(candidates)
    assert ("ZZE", "ZZF", 1) in model.E1_PAIRS
    model.objective = pyo.Objective(expr=sum(model.x[i] for i in model.CANDIDATES), sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.x[0]) == pytest.approx(1.0)
    assert pyo.value(model.x[1]) == pytest.approx(1.0)
    assert pyo.value(model.x[2]) == pytest.approx(1.0)
    assert result.objective_value == pytest.approx(3.0), \
        "conditional E1 must not force the fwd market to 0 just because bwd is structurally dead"

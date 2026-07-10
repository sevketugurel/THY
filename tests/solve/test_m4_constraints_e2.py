"""Solve tests for E2 (yön-arası seyahat-süresi farkı, koşullu aktivasyon).

Doğruluk argümanı (ultrathink, kod öncesi): brief "her iki yönde de en az bir
bağlantı SUNULUYORSA, iki yönün EN İYİ (minimum) seyahat sürelerinin farkı
Gamma dakikayı aşmamalı" diyor. Bu, D'nin OR-aggregation'ından farklı bir yapı
gerektirir: bir pazarın "en iyi" J değeri, SEÇİLEBİLİR bir alt-kümenin
minimumu -- MIP'in doğal bir min() operatörü yok, bu yüzden bir "argmin
sandviç" gerekiyor:

    a_dir (aktivasyon, OR-aggregation, D'nin beaten_k'sıyla AYNI desen):
        a_dir >= x_pi            (herhangi biri sunulursa aktif)
        a_dir <= Sum(x_pi)       (hiçbiri sunulmazsa pasif)

    w_pi (argmin seçici, TAM OLARAK bir sunulan candidate'a "en iyi" etiketi):
        w_pi <= x_pi             (sunulmayan seçilemez)
        Sum(w_pi) == a_dir       (aktifse tam 1, pasifse 0)

    Jbest sandviç (candidate-bazlı, market-agregat sınırlardan türetilen
    Big-M'lerle -- src.model.big_m.derive_e2_candidate_big_ms):
        Jbest <= J_pi + M_up*(1-x_pi)      (her sunulan candidate bir ÜST sınır koyar)
        Jbest >= J_pi - M_down*(1-w_pi)    (SEÇİLEN candidate Jbest'i AŞAĞIDAN pinler)

    Neden doğru: "<=" HER sunulan candidate için ayrı ayrı çalışır (M_up=0
    olduğunda x=1 iken doğrudan Jbest<=J_pi) -- bu TEK BAŞINA Jbest'i true
    min'in ÜSTÜNE hiç çıkaramaz. "w_pi<=x_pi" + "Sum(w)=a_dir" solver'ı
    SADECE sunulan bir candidate'a w=1 vermeye zorlar; O candidate için ">="
    Jbest'i O candidate'ın J'sinin ALTINA inmekten alıkoyar. Bu iki yönün
    KESİŞİMİ (aynı anda hem üst hem alt sınırlanan Jbest) yalnızca gerçek
    min(J_pi : x_pi=1) noktasında FEASIBLE'dır -- solver'ın Jbest'i "sahte
    düşük" göstermesi (M_down eksik/kırık olsaydı mümkün olurdu) yapısal
    olarak İMKANSIZ, çünkü w=1 verdiği candidate'ın KENDİ J'si Jbest'i
    aşağıdan pinler (bkz. adversarial test).

    E2'nin kendisi (yalnızca HER İKİ yön de aktifken bağlayıcı):
        Jbest_fwd - Jbest_bwd <= Gamma + M_pair*(2-a_fwd-a_bwd)
        Jbest_bwd - Jbest_fwd <= Gamma + M_pair*(2-a_fwd-a_bwd)
    M_pair (derive_e2_pair_big_m) tam olarak "iki yönün kendi değişken
    sınırlarının izin verdiği en kötü fark - Gamma" -- faktör 1 veya 2 olduğu
    an (herhangi bir yön pasif) kısıt otomatik gevşer (kanıt: Jbest'in KENDİ
    ilan edilmiş bounds'u zaten bu farkı sağlıyor, M formülü tam bunu
    telafi ediyor).

4 satırlık aktivasyon doğruluk tablosu (a_fwd,a_bwd) ayrı testler olarak
aşağıda. Artı: Jbest'i "sahte düşük" göstermeye çalışan adversarial test.

marker: solve (small HiGHS solve, <60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_balance import add_e2_constraints
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300
GAMMA = 30
JOURNEY_CONST = {("ZZG", "ZZH"): 100, ("ZZH", "ZZG"): 100}


def _fixed_candidate(o, d, flno1, flno2, gap, gun=1):
    # arr fixed at 0, dep fixed at gap -> gap is a single point, always valid
    # (mandatory offering forces x=1 whenever gap in [L,U]).
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=gap, arr_lo=0, arr_hi=0, dep_lo=gap, dep_hi=gap,
        gap_lo=gap, gap_hi=gap,
    )


def _adjustable_candidate(o, d, flno1, flno2, gap_lo, gap_hi, gun=1):
    # arr fixed at 0, dep free in [gap_lo,gap_hi]. If [gap_lo,gap_hi] is
    # entirely INSIDE [L,U], gap always lands in-window regardless of choice
    # -> B mandatorily forces x=1. If entirely OUTSIDE [L,U], B mandatorily
    # forces x=0. Either way x is forced (no separate incentive needed);
    # which one depends on the caller's chosen range.
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=gap_lo, arr_lo=0, arr_hi=0, dep_lo=gap_lo, dep_hi=gap_hi,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )


def _unoffered_candidate(o, d, flno1, flno2, gun=1):
    # Fixed gap OUTSIDE [L,U] -- B forces x=0 unconditionally. Deliberately
    # given a LOW achievable J range (via a separate, very negative
    # journey_const override handled by the caller) to bait a broken sandwich.
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=1000, arr_lo=0, arr_hi=0, dep_lo=1000, dep_hi=1000,
        gap_lo=1000, gap_hi=1000,
    )


def _build(candidates, journey_constants=JOURNEY_CONST, gamma=GAMMA):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_e2_constraints(model, candidates, journey_constants, gamma=gamma)
    model._candidates = candidates
    return model


# --- 4-row activation truth table ---

def test_e2_row_00_both_inactive_is_non_binding():
    # Both directions' candidates are ADJUSTABLE but with a gap range entirely
    # OUTSIDE [L,U] (500-900) -> B's backward reification forces x=0
    # unconditionally, so a_fwd=a_bwd=0 -- but the (unfixed) gap still gives
    # Jbest a WIDE own-bounds range [600,1000], letting this test actually
    # probe whether E2 leaves that full range reachable when neither side is
    # offered (a single-point-fixed unofferable candidate would trivially
    # pass without exercising anything).
    c_fwd = _adjustable_candidate("ZZG", "ZZH", 201, 301, gap_lo=500, gap_hi=900)
    c_bwd = _adjustable_candidate("ZZH", "ZZG", 202, 302, gap_lo=500, gap_hi=900)
    candidates = [c_fwd, c_bwd]
    model = _build(candidates)
    model.objective = pyo.Objective(
        expr=model.Jbest["ZZG", "ZZH", 1] - model.Jbest["ZZH", "ZZG", 1], sense=pyo.maximize,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.a_dir["ZZG", "ZZH", 1]) == pytest.approx(0.0)
    assert pyo.value(model.a_dir["ZZH", "ZZG", 1]) == pytest.approx(0.0)
    # Unconstrained by Gamma: reaches the full spread between Jbest's own
    # declared bounds (market_j_hi(fwd)=1000, market_j_lo(bwd)=600 -> 400),
    # far beyond Gamma=30 -- proving E2 imposes nothing when neither side
    # offers anything.
    assert result.objective_value == pytest.approx(400.0)


def test_e2_row_10_fwd_only_active_jbest_still_correct():
    # fwd offered (forced x=1, fixed gap=100 -> J=200); bwd unoffered (forced
    # x=0). Even with bwd inactive, Jbest_fwd must still be pinned to the TRUE
    # fwd value (100+100=200) -- E2's cross-pair slack must not corrupt the
    # sandwich for the ACTIVE side.
    c_fwd = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=100)
    c_bwd = _unoffered_candidate("ZZH", "ZZG", 202, 302)
    candidates = [c_fwd, c_bwd]
    model = _build(candidates)
    model.objective = pyo.Objective(expr=model.Jbest["ZZG", "ZZH", 1], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.a_dir["ZZG", "ZZH", 1]) == pytest.approx(1.0)
    assert pyo.value(model.a_dir["ZZH", "ZZG", 1]) == pytest.approx(0.0)
    assert pyo.value(model.Jbest["ZZG", "ZZH", 1]) == pytest.approx(200.0)


def test_e2_row_01_bwd_only_active_jbest_still_correct():
    # Mirror of row 10.
    c_fwd = _unoffered_candidate("ZZG", "ZZH", 201, 301)
    c_bwd = _fixed_candidate("ZZH", "ZZG", 202, 302, gap=150)
    candidates = [c_fwd, c_bwd]
    model = _build(candidates)
    model.objective = pyo.Objective(expr=model.Jbest["ZZH", "ZZG", 1], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.a_dir["ZZG", "ZZH", 1]) == pytest.approx(0.0)
    assert pyo.value(model.a_dir["ZZH", "ZZG", 1]) == pytest.approx(1.0)
    assert pyo.value(model.Jbest["ZZH", "ZZG", 1]) == pytest.approx(250.0)


def test_e2_row_11_both_active_gamma_is_enforced():
    # fwd forced (fixed gap=100 -> J_fwd=200, x_fwd=1 mandatory). bwd
    # ADJUSTABLE, gap free in [100,250] (both endpoints inside [L,U]=[60,300],
    # so B mandatorily forces x_bwd=1 regardless of the chosen value) ->
    # J_bwd in [200,350]. Adversarial objective WANTS J_bwd (hence t_dep of
    # bwd's leg) as LARGE as possible, which would push the true gap to
    # 150 (violating Gamma=30) if E2 didn't bind. E2 must cap it at 130.
    c_fwd = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=100)
    c_bwd = _adjustable_candidate("ZZH", "ZZG", 202, 302, gap_lo=100, gap_hi=250)
    candidates = [c_fwd, c_bwd]
    model = _build(candidates)
    model.objective = pyo.Objective(expr=model.t_dep["OB", 302, 1], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.a_dir["ZZG", "ZZH", 1]) == pytest.approx(1.0)
    assert pyo.value(model.a_dir["ZZH", "ZZG", 1]) == pytest.approx(1.0)
    # Without E2 the adversarial objective would reach t_dep=250 (J_bwd=350,
    # diff=150). E2 forces J_bwd<=J_fwd+Gamma=230 -> t_dep<=130.
    assert pyo.value(model.t_dep["OB", 302, 1]) == pytest.approx(130.0)
    j_fwd = pyo.value(model.Jbest["ZZG", "ZZH", 1])
    j_bwd = pyo.value(model.Jbest["ZZH", "ZZG", 1])
    assert abs(j_fwd - j_bwd) <= GAMMA + 1e-6


# --- M5c: exempt+log fully K-subset-frozen pairs that violate Gamma ---

def test_e2_exempts_fully_frozen_pair_that_violates_gamma():
    # M5c (docs/lp_anatomy.md §1, VARSAYIM-9/11's exempt+log pattern
    # generalized to E2): both directions have exactly ONE fully-frozen
    # candidate each (gap_lo==gap_hi -- K-subset's Rfix legs). fwd: gap=60
    # -> J=100+60=160. bwd: gap=100 -> J=100+100=200. |200-160|=40>Gamma=30,
    # but NEITHER side has any freedom to change its journey time -- forcing
    # E2's pair constraint would make the model unconditionally infeasible
    # for a reason that's an artifact of K-subset freezing, not a genuine
    # data conflict. Must be exempted + logged, not hard-failed.
    c_fwd = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=60)
    c_bwd = _fixed_candidate("ZZH", "ZZG", 202, 302, gap=100)
    candidates = [c_fwd, c_bwd]
    model = _build(candidates)
    assert ("ZZG", "ZZH", 1) not in model.E2_PAIRS, "fully-frozen violating pair must be exempted, not built"
    assert model._e2_fold_counts["exempted"] == 1
    model.objective = pyo.Objective(expr=0)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.Jbest["ZZG", "ZZH", 1]) == pytest.approx(160.0)
    assert pyo.value(model.Jbest["ZZH", "ZZG", 1]) == pytest.approx(200.0)


def test_e2_still_builds_for_fully_frozen_pair_within_gamma():
    # Control case: fully-frozen pair whose FORCED Jbest values already
    # satisfy Gamma (both gap=100 -> J=200 both ways, diff=0) -- must NOT
    # be exempted (nothing to exempt).
    c_fwd = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=100)
    c_bwd = _fixed_candidate("ZZH", "ZZG", 202, 302, gap=100)
    candidates = [c_fwd, c_bwd]
    model = _build(candidates)
    assert model._e2_fold_counts["exempted"] == 0
    model.objective = pyo.Objective(expr=0)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"


def test_e2_still_binds_for_mixed_pair_with_one_adjustable_side():
    # Mixed pair: fwd fully frozen (gap=60 -> J=160). bwd genuinely
    # adjustable (gap free in [65,150], both endpoints inside [L,U] so B
    # mandatorily forces x_bwd=1 regardless of choice; window straddles the
    # Gamma boundary so both a satisfying and a violating gap are
    # achievable) -- E2 must still be BUILT and BINDING (there IS freedom).
    # Adversarial objective wants bwd's gap as LARGE as possible (J_bwd as
    # large as possible, which alone would reach J=250, diff=90>Gamma=30);
    # E2 must cap it at J_fwd+Gamma=190 (gap<=90).
    c_fwd = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=60)
    c_bwd = _adjustable_candidate("ZZH", "ZZG", 202, 302, gap_lo=65, gap_hi=150)
    candidates = [c_fwd, c_bwd]
    model = _build(candidates)
    assert ("ZZG", "ZZH", 1) in model.E2_PAIRS, "mixed pair (one adjustable side) must still be built"
    assert model._e2_fold_counts["exempted"] == 0
    model.objective = pyo.Objective(expr=model.t_dep["OB", 302, 1], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    j_fwd = pyo.value(model.Jbest["ZZG", "ZZH", 1])
    j_bwd = pyo.value(model.Jbest["ZZH", "ZZG", 1])
    assert abs(j_fwd - j_bwd) <= GAMMA + 1e-6


# --- adversarial: cannot fabricate a fraudulently low Jbest ---

def test_e2_sandwich_cannot_fabricate_jbest_below_true_min():
    # fwd market has TWO candidates: c1 fixed gap=100 (J=200, forced offered),
    # and c2 fixed gap=1000 (OUTSIDE [L,U] -> B forces x=0, but c2's
    # achievable range gives it a much LOWER floor -- J=220+1000=... wait,
    # use a candidate with a genuinely LOW achievable J range instead, to bait
    # Jbest downward via its wide variable bounds (market_j_lo would be very
    # negative if this unoffered candidate's range were included).
    #
    # Concretely: c1 (offered, fixed) J=200. c2 (unoffered, x forced 0 by B)
    # has gap fixed at 1000 (far outside [60,300]) -- its OWN J=100+1000=1100,
    # which actually widens market_j_hi, not market_j_lo, so use a NEGATIVE
    # extreme instead: c3 fixed gap=-500 (also outside [L,U], x forced 0),
    # J=100-500=-400. This makes market_j_lo=-400, tempting an under-sized
    # M_down to let Jbest sink toward -400 even though only c1 is offered.
    # bwd market: single fixed candidate, gap=100, J=100+100=200 (kept
    # trivially Gamma-compliant so E2 itself never forces anything here --
    # isolates the test to the sandwich's own integrity, not E2's coupling).
    c1 = _fixed_candidate("ZZG", "ZZH", 201, 301, gap=100)
    c3 = Candidate(
        od="ZZG-ZZH", o="ZZG", d="ZZH", gun=1, flno1=204, flno2=304,
        r1_id=("IB", 204, 1), r2_id=("OB", 304, 1), arr_time=None, dep_time=None,
        gap_min=-500, arr_lo=0, arr_hi=0, dep_lo=-500, dep_hi=-500,
        gap_lo=-500, gap_hi=-500,
    )
    c_bwd = _fixed_candidate("ZZH", "ZZG", 202, 302, gap=100)
    candidates = [c1, c3, c_bwd]
    model = _build(candidates)
    # Adversarial: WANTS Jbest_fwd as small as possible.
    model.objective = pyo.Objective(expr=model.Jbest["ZZG", "ZZH", 1], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    # c3 is genuinely unofferable (gap=-500 outside [L,U]) -> x forced 0.
    assert pyo.value(model.x[1]) == pytest.approx(0.0)
    # Despite the temptation (market_j_lo pulled down to -400 by c3's own
    # declared range), Jbest_fwd must settle at the TRUE offered minimum
    # (200, from c1 -- the only actually-offered candidate), never below it.
    assert pyo.value(model.Jbest["ZZG", "ZZH", 1]) == pytest.approx(200.0)

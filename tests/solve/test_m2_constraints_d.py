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


def _windowed_candidate(o, d, gun, gap_lo, gap_hi, flno1, flno2):
    # Genuinely CONDITIONAL candidate (real adjustable window, arr fixed at 0
    # so gap == dep) -- unlike _fixed_candidate's single point, this is used
    # for D-folding tests where the pair must NOT be classified as always/
    # never-beats (M5c, docs/lp_anatomy.md): both a beat=0 and a beat=1
    # outcome must remain achievable depending on which gap gets chosen.
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=gap_lo, arr_lo=0, arr_hi=0, dep_lo=gap_lo, dep_hi=gap_hi, gap_lo=gap_lo, gap_hi=gap_hi,
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
    # M5c: windowed so this pair is CONDITIONAL (gap in [60,100] -> J in
    # [280,320]), gap fixed to 100 (worst end, J=320>T_comp=300) -- should
    # NOT beat. Objective REWARDS beat=1 (adversarial) -- forward forcing
    # must block it.
    c = _windowed_candidate("ZZA", "ZZB", 1, gap_lo=60, gap_hi=100, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=True)
    model.gap[0].fix(100)
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beat[0, "R1"]) == pytest.approx(0.0)


def test_beat_can_be_one_when_j_within_tcomp_forward_mode():
    # M5c: same conditional pair, gap fixed to 60 (best end, J=280<=300) --
    # CAN beat (feasible).
    c = _windowed_candidate("ZZA", "ZZB", 1, gap_lo=60, gap_hi=100, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=True)
    model.gap[0].fix(60)
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beat[0, "R1"]) == pytest.approx(1.0)


def test_forward_only_mode_allows_under_claim_when_adversarial():
    # M5c (docs/lp_anatomy.md): moved to a genuinely CONDITIONAL candidate
    # (gap in [60,100] -> J in [280,320] straddles T_comp=300) -- an
    # "always-beats" candidate (J_hi<=T_comp for its WHOLE window) no longer
    # gets a real beat variable at all after D-folding (see
    # test_always_beats_pair_has_no_beat_variable below), so this property
    # ("beat=0 remains structurally feasible, just unrewarded, in
    # forward-only mode") can only be demonstrated on a pair where beat
    # genuinely depends on the solved gap. No backward forcing exists in
    # this mode -- beat=0 is a legitimate (if unhelpful) feasible point when
    # gap is pushed to the end of the window where J<=T_comp still holds.
    c = _windowed_candidate("ZZA", "ZZB", 1, gap_lo=60, gap_hi=100, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=True)
    model.gap[0].fix(60)  # force J=280<=300 (a beatable gap) so beat=0 is a genuine under-claim, not a forced non-beat
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beat[0, "R1"]) == pytest.approx(0.0)


def test_bidirectional_fallback_forces_beat_one_when_j_within_tcomp():
    # monotonic=False -> full bidirectional forcing. Same conditional setup
    # as the forward-only test above, but now beat=0 must be INFEASIBLE (not
    # just unrewarded) when J<=T_comp.
    c = _windowed_candidate("ZZA", "ZZB", 1, gap_lo=60, gap_hi=100, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=False)
    model.gap[0].fix(60)
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beat[0, "R1"]) == pytest.approx(1.0), \
        "beat=0 was chosen despite J<=T_comp in bidirectional mode -- backward forcing broken"


def test_always_beats_pair_has_no_beat_variable():
    # M5c D-folding (docs/lp_anatomy.md): a candidate whose J is <=T_comp
    # across its ENTIRE adjustable window (J_hi<=T_comp) can NEVER lose to
    # this rival regardless of the solved gap -- beat[i,k] is a data-fact
    # (== x[i] whenever offered), not a genuine decision. Folding eliminates
    # the variable entirely rather than adding a tightening constraint --
    # smaller AND tighter, and it reflects in build time too.
    c = _windowed_candidate("ZZA", "ZZB", 1, gap_lo=60, gap_hi=100, flno1=1, flno2=2)  # J in [280,320]
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 500}}, monotonic=True)  # T_comp=500 > J_hi=320
    assert (0, "R1") not in model.BEAT_PAIRS
    assert not hasattr(model, "beat") or (0, "R1") not in model.beat


def test_never_beats_pair_has_no_beat_variable():
    c = _windowed_candidate("ZZA", "ZZB", 1, gap_lo=60, gap_hi=100, flno1=1, flno2=2)  # J in [280,320]
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 100}}, monotonic=True)  # T_comp=100 < J_lo=280
    assert (0, "R1") not in model.BEAT_PAIRS
    assert not hasattr(model, "beat") or (0, "R1") not in model.beat


def test_beat_requires_x_one_cannot_beat_unoffered_connection():
    # M5c: windowed so this pair is CONDITIONAL (gap in [400,450], both
    # OUTSIDE [L,U]=[60,300] -> x forced to 0 by B regardless; J in
    # [620,670] straddles T_comp=640). Even though J might arithmetically be
    # <=T_comp for the low end of the window, an unoffered connection cannot
    # claim a win.
    c = _windowed_candidate("ZZA", "ZZB", 1, gap_lo=400, gap_hi=450, flno1=1, flno2=2)
    model = _build([c], {("ZZA", "ZZB"): 220}, {("ZZA", "ZZB", 1): {"R1": 640}}, monotonic=True)
    model.objective = pyo.Objective(expr=model.beat[0, "R1"], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.x[0]) == pytest.approx(0.0)
    assert pyo.value(model.beat[0, "R1"]) == pytest.approx(0.0)


def test_beaten_aggregation_forces_one_when_any_beat_is_one():
    # Two candidates both beating the same rival -- beaten_k must be forced to
    # 1 (structural OR consistency), even under an adversarial objective that
    # wants beaten_k=0. Both candidates are ALWAYS-beats here (gap=60/70,
    # J=280/290 both <=T_comp=300 for their whole -- fixed-point -- window),
    # so post-M5c-folding beat[0,"R1"] doesn't exist as a Var (folded to
    # x[0]) -- fixing x[0]=1 alone is enough to force beaten via the folded
    # d_beaten_lb constraint (beaten >= x[i] for always-beats pairs).
    c1 = _fixed_candidate("ZZA", "ZZB", 1, gap=60, flno1=1, flno2=2)
    c2 = _fixed_candidate("ZZA", "ZZB", 1, gap=70, flno1=3, flno2=4)
    model = _build(
        [c1, c2], {("ZZA", "ZZB"): 220},
        {("ZZA", "ZZB", 1): {"R1": 300}}, monotonic=True,
    )
    assert (0, "R1") not in model.BEAT_PAIRS, "expected an ALWAYS-beats fold for this fixture"
    model.x[0].fix(1)
    model.x[1].fix(1)
    model.objective = pyo.Objective(
        expr=model.beaten["ZZA", "ZZB", 1, "R1"], sense=pyo.minimize,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.beaten["ZZA", "ZZB", 1, "R1"]) == pytest.approx(1.0), \
        "beaten_k=0 was chosen despite x[0]=1 on an always-beats pair -- folded OR-aggregation lower bound broken"


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
    # M5c: both are ALWAYS/NEVER folds for this fixed-point candidate
    # (vs R1: J=280<=300 always-beats; vs R2: J=280>250 never-beats), so
    # neither beat[0,"R1"] nor beat[0,"R2"] exists as a Var anymore -- B
    # already forces x[0]=1 (gap=60 is legal), which is all that's needed to
    # drive the folded beaten_lb constraint; the objective just needs SOME
    # valid expression, x[0] mirrors the original "reward offering" intent.
    c = _fixed_candidate("ZZA", "ZZB", 1, gap=60, flno1=1, flno2=2)
    model = _build(
        [c], {("ZZA", "ZZB"): 220},
        {("ZZA", "ZZB", 1): {"R1": 300, "R2": 250}}, monotonic=True,
    )
    assert (0, "R1") not in model.BEAT_PAIRS and (0, "R2") not in model.BEAT_PAIRS
    model.objective = pyo.Objective(expr=model.x[0], sense=pyo.maximize)
    solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert pyo.value(model.rank["ZZA", "ZZB", 1]) == pytest.approx(1.0)

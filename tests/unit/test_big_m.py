"""Unit tests for src.model.big_m -- per-candidate Big-M derivation for B's
bidirectional reification.

Doğruluk argümanı (ultrathink, kod öncesi): x_pi=1 OLMALI ancak ve ancak
gap_pi in [L,U]. Forward direction alone (x=1 => gap in [L,U]) is not enough --
once E1/E2 exist (M4), the solver has an incentive to hide a genuinely-valid
connection (x=0) to dodge a balance penalty. The backward direction
(gap in [L,U] => x=1) closes that loophole. Each M is derived from the
CANDIDATE'S OWN achievable gap range [gap_lo,gap_hi] (not a global constant) --
this is both correctness-preserving (never relaxes less than needed) and tight
(usually far below any generic worst-case bound).

marker: unit (solver-free, pure arithmetic).
"""
import pytest

from src.candidates.generate import Candidate
from src.model.big_m import (
    derive_b_big_ms, derive_d_big_ms, derive_e1_pair_big_m,
    derive_e2_candidate_big_ms, derive_e2_pair_big_m,
)

pytestmark = pytest.mark.unit

L, U = 60, 300


def _candidate(gap_lo, gap_hi):
    return Candidate(
        od="ZZA-ZZB", o="ZZA", d="ZZB", gun=1, flno1=9101, flno2=9112,
        r1_id=(9101, 1), r2_id=(9112, 1), arr_time=None, dep_time=None,
        gap_min=60, arr_lo=660, arr_hi=1020, dep_lo=720, dep_hi=1080,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )


def test_worked_example_pi1_matches_hand_calc():
    # pi1=MI1xMO2, baseline_gap=60, w=180 (M1 design note worked example):
    # arr in [660,1020], dep in [720,1080] -> gap_lo=-300, gap_hi=420.
    c = _candidate(gap_lo=-300, gap_hi=420)
    m1, m2, m3, m4 = derive_b_big_ms(c, L=L, U=U)
    assert (m1, m2, m3, m4) == (360, 120, 361, 601)


def test_degenerate_rfix_candidate_gives_tiny_forcing_ms():
    # Both legs fixed (adjustable_set=none): gap_lo=gap_hi=60 (=L exactly).
    c = _candidate(gap_lo=60, gap_hi=60)
    m1, m2, m3, m4 = derive_b_big_ms(c, L=L, U=U)
    # Forward constraints already trivially satisfied by the fixed gap (M=0);
    # backward constraints still need a small nonzero force.
    assert (m1, m2) == (0, 0)
    assert (m3, m4) == (1, 241)


def test_all_ms_are_nonnegative():
    c = _candidate(gap_lo=-300, gap_hi=420)
    for m in derive_b_big_ms(c, L=L, U=U):
        assert m >= 0


def test_ms_never_exceed_1440_for_recommended_window():
    # Worst-case survivor of achievable-range pruning: baseline_gap at the very
    # edge of [L-2w, U+2w] (w=180) -- still must stay under 1440 per the
    # plan's Big-M discipline (this is the M1 design note's core finding).
    w = 180
    worst_gap_hi = U + 4 * w  # gap_hi = baseline_gap + 2w, baseline_gap survives up to U+2w
    worst_gap_lo = L - 4 * w
    c = _candidate(gap_lo=worst_gap_lo, gap_hi=worst_gap_hi)
    for m in derive_b_big_ms(c, L=L, U=U):
        assert m <= 1440


# --- D (beat reification) Big-M ---

def test_d_worked_example_matches_hand_calc():
    # journey_const=220, gap_hi=420 (pi1, w=180) -> J_hi=640. T_comp=300.
    # M_fwd = max(0, 640-300) = 340. gap_lo=-300 -> J_lo=-80.
    # M_bwd = max(0, (300+1)-(-80)) = 381.
    c = _candidate(gap_lo=-300, gap_hi=420)
    m_fwd, m_bwd = derive_d_big_ms(c, journey_const=220, t_comp=300)
    assert (m_fwd, m_bwd) == (340, 381)


def test_d_ms_are_nonnegative():
    c = _candidate(gap_lo=-300, gap_hi=420)
    m_fwd, m_bwd = derive_d_big_ms(c, journey_const=220, t_comp=300)
    assert m_fwd >= 0 and m_bwd >= 0


def test_d_zero_forcing_when_always_beats():
    # J_hi <= T_comp always -> beat=1 never needs relaxation (M_fwd=0).
    c = _candidate(gap_lo=0, gap_hi=10)
    m_fwd, _ = derive_d_big_ms(c, journey_const=100, t_comp=1000)
    assert m_fwd == 0


# --- E2 (Jbest sandwich) Big-M ---

def test_e2_candidate_big_ms_worked_example():
    # c: gap_lo=-300,gap_hi=420, journey_const=220 -> J_lo=-80, J_hi=640.
    # Market aggregate (other candidates in the same market widen the range):
    # market_j_lo=-100, market_j_hi=700.
    # m_up = max(0, market_j_hi - J_lo) = max(0, 700-(-80)) = 780
    # m_down = max(0, J_hi - market_j_lo) = max(0, 640-(-100)) = 740
    c = _candidate(gap_lo=-300, gap_hi=420)
    m_up, m_down = derive_e2_candidate_big_ms(c, journey_const=220, market_j_lo=-100, market_j_hi=700)
    assert (m_up, m_down) == (780, 740)


def test_e2_candidate_big_ms_zero_when_fixed_and_sole_in_market():
    # Fixed gap (Rfix, gap_lo==gap_hi=100) and sole candidate in its market ->
    # J is a single point (320) and market bounds collapse to that same point
    # -> both Ms are exactly 0 (no slack needed; x is mandatorily 1 anyway).
    c = _candidate(gap_lo=100, gap_hi=100)
    m_up, m_down = derive_e2_candidate_big_ms(c, journey_const=220, market_j_lo=320, market_j_hi=320)
    assert (m_up, m_down) == (0, 0)


def test_e2_candidate_big_ms_are_nonnegative():
    c = _candidate(gap_lo=-300, gap_hi=420)
    m_up, m_down = derive_e2_candidate_big_ms(c, journey_const=220, market_j_lo=-100, market_j_hi=700)
    assert m_up >= 0 and m_down >= 0


def test_e2_pair_big_m_worked_example():
    # jd_hi_side=700, jd_lo_other=-50, gamma=30 -> m=max(0,700-(-50)-30)=720.
    m = derive_e2_pair_big_m(jd_hi_side=700, jd_lo_other=-50, gamma=30)
    assert m == 720


def test_e2_pair_big_m_zero_when_ranges_already_within_gamma():
    # jd_hi_side - jd_lo_other = 20 <= gamma=30 -> no forcing ever needed.
    m = derive_e2_pair_big_m(jd_hi_side=20, jd_lo_other=0, gamma=30)
    assert m == 0


# --- E1 (conditional activation) Big-M, KARAR-0/VARSAYIM-16 ---

def test_e1_pair_big_m_worked_example():
    # alpha=0.2, n_fwd_max=5, n_bwd_max=3 -> M=(1-0.2)*max(5,3)=0.8*5=4.0.
    m = derive_e1_pair_big_m(alpha=0.2, n_fwd_max=5, n_bwd_max=3)
    assert m == pytest.approx(4.0)


def test_e1_pair_big_m_uses_larger_side():
    # Symmetric check: swapping which side is larger must not change M.
    m1 = derive_e1_pair_big_m(alpha=0.2, n_fwd_max=3, n_bwd_max=8)
    m2 = derive_e1_pair_big_m(alpha=0.2, n_fwd_max=8, n_bwd_max=3)
    assert m1 == m2 == pytest.approx(0.8 * 8)


def test_e1_pair_big_m_zero_when_alpha_is_one():
    # alpha=1.0 means the unconditional inequality is already always true
    # (n_fwd-n_bwd <= n_fwd+n_bwd always holds for nonnegative counts) --
    # no forcing needed regardless of activation state.
    m = derive_e1_pair_big_m(alpha=1.0, n_fwd_max=10, n_bwd_max=1)
    assert m == 0.0


def test_e1_pair_big_m_stays_far_below_1440_for_realistic_counts():
    # Candidate counts per market are small integers (tens, not thousands) --
    # this M is data-derived and naturally tiny relative to the project's own
    # <=1440 Big-M discipline (time-scaled Ms), never a risk of exceeding it.
    m = derive_e1_pair_big_m(alpha=0.2, n_fwd_max=50, n_bwd_max=40)
    assert m <= 1440

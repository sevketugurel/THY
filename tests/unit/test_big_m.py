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
from src.model.big_m import derive_b_big_ms, derive_d_big_ms

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

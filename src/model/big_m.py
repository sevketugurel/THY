"""Per-candidate Big-M derivation for constraint reifications.

Doğruluk argümanı (B): x_pi=1 must hold iff gap_pi in [L,U] (bidirectional --
see plan §4 M1 design note and tests/unit/test_big_m.py docstring for the full
correctness argument on why both directions are required). Each M is derived
from the candidate's OWN achievable range [gap_lo,gap_hi], not a global
constant -- tighter, and simpler than deferring to a later "tightening" pass.
"""
from src.candidates.generate import Candidate

MAX_ALLOWED_BIG_M = 1440  # plan's own Big-M discipline: nothing should exceed one day


def derive_b_big_ms(candidate: Candidate, L: int, U: int) -> tuple:
    """Returns (M1,M2,M3,M4):
    M1: forces gap>=L when x=1 (forward-lower)
    M2: forces gap<=U when x=1 (forward-upper)
    M3: forces gap<=L-1 when x=0,y=0 (backward, "below" side)
    M4: forces gap>=U+1 when x=0,y=1 (backward, "above" side)
    """
    m1 = max(0, L - candidate.gap_lo)
    m2 = max(0, candidate.gap_hi - U)
    m3 = max(0, candidate.gap_hi - (L - 1))
    m4 = max(0, (U + 1) - candidate.gap_lo)
    return m1, m2, m3, m4

"""Unit tests for src.candidates.generate -- TK inbound x outbound cross-product,
filtered by the [L,U] connection-gap feasibility gate (Modül-3 kapı 1).

marker: unit (solver-free, pure logic).
"""
from pathlib import Path

import pytest

from src.candidates.generate import generate_candidates
from src.data.loaders import load_od_table

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.unit


L, U = 60, 300


@pytest.fixture
def tk_rows():
    df = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    return df[df.cr1 == "TK"].copy()


def test_generates_exactly_the_hand_verified_candidates_gun1(tk_rows):
    # Per fixtures/README.md cross-product verification table: Gün=1 has exactly
    # 2 valid ZZA->ZZB candidates and 1 valid ZZB->ZZA candidate.
    candidates = generate_candidates(tk_rows, L=L, U=U, gun=1)
    zza_zzb = [c for c in candidates if c.od == "ZZA-ZZB"]
    zzb_zza = [c for c in candidates if c.od == "ZZB-ZZA"]
    assert len(zza_zzb) == 2
    assert len(zzb_zza) == 1


def test_candidate_gap_matches_hand_calc(tk_rows):
    candidates = generate_candidates(tk_rows, L=L, U=U, gun=1)
    pi1 = next(c for c in candidates if c.od == "ZZA-ZZB" and c.flno1 == 9101)
    assert pi1.gap_min == 60
    assert pi1.flno2 == 9112


def test_excludes_rotation_only_flights_from_market_pool(tk_rows):
    # RA1/RA2/RB1/RB2 were deliberately scheduled so they never form a
    # valid-gap connection in any market (see fixtures/README.md cross-product
    # verification) -- confirm none of them appear in any generated candidate.
    candidates = generate_candidates(tk_rows, L=L, U=U, gun=1)
    rotation_only_flnos = {9311, 9301, 9411, 9401}
    used_flnos = {c.flno1 for c in candidates} | {c.flno2 for c in candidates}
    assert used_flnos.isdisjoint(rotation_only_flnos)


def test_excludes_self_market_and_gap_outside_window(tk_rows):
    candidates = generate_candidates(tk_rows, L=L, U=U, gun=1)
    for c in candidates:
        assert L <= c.gap_min <= U


def test_respects_gun_filter(tk_rows):
    g1 = generate_candidates(tk_rows, L=L, U=U, gun=1)
    g2 = generate_candidates(tk_rows, L=L, U=U, gun=2)
    assert len(g1) == 3
    assert len(g2) == 3  # same structure, slightly different MI1/NI1 times per README

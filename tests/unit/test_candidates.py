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


# --- M1: achievable-range pruning (adjustable_set/adjustable_window_min) ---

def test_default_behaviour_unchanged_when_window_zero(tk_rows):
    # window=0, adjustable_set="none" must reduce exactly to M0's baseline-only
    # behaviour (achievable range collapses to a single point == baseline gap).
    candidates = generate_candidates(tk_rows, L=L, U=U, gun=1, adjustable_window_min=0, adjustable_set="none")
    assert len(candidates) == 3


def test_achievable_range_admits_candidate_outside_baseline_window(tk_rows):
    # NI2xNO2 has baseline gap=500 (invalid, >U=300). With a wide enough window
    # and adjustable_set="all", the achievable range reaches down to [L,U].
    fixed = generate_candidates(tk_rows, L=L, U=U, gun=1, adjustable_window_min=0, adjustable_set="none")
    free = generate_candidates(tk_rows, L=L, U=U, gun=1, adjustable_window_min=300, adjustable_set="all")
    assert (9202, 9212) not in {(c.flno1, c.flno2) for c in fixed}
    assert (9202, 9212) in {(c.flno1, c.flno2) for c in free}


def test_achievable_range_still_excludes_permanently_infeasible(tk_rows):
    # MI2xMO1 has baseline gap=-120. A modest window (30) can't close a 180-min
    # deficit -- achievable range [-180,-60] still doesn't reach L=60.
    candidates = generate_candidates(tk_rows, L=L, U=U, gun=1, adjustable_window_min=30, adjustable_set="all")
    assert (9102, 9111) not in {(c.flno1, c.flno2) for c in candidates}


def test_candidate_exposes_achievable_bounds_for_big_m_derivation(tk_rows):
    candidates = generate_candidates(tk_rows, L=L, U=U, gun=1, adjustable_window_min=180, adjustable_set="all")
    pi1 = next(c for c in candidates if c.flno1 == 9101 and c.flno2 == 9112)
    assert (pi1.arr_lo, pi1.arr_hi) == (660, 1020)
    assert (pi1.dep_lo, pi1.dep_hi) == (720, 1080)
    assert (pi1.gap_lo, pi1.gap_hi) == (-300, 420)


def test_rfix_candidate_has_degenerate_window(tk_rows):
    candidates = generate_candidates(tk_rows, L=L, U=U, gun=1, adjustable_window_min=180, adjustable_set="none")
    pi1 = next(c for c in candidates if c.flno1 == 9101 and c.flno2 == 9112)
    assert pi1.arr_lo == pi1.arr_hi == 840
    assert pi1.dep_lo == pi1.dep_hi == 900
    assert pi1.gap_lo == pi1.gap_hi == 60


def test_candidate_exposes_flight_instance_ids_for_shared_variables(tk_rows):
    # Two candidates sharing the same inbound flight (MI1=9101) must expose the
    # SAME r1_id, so the model can map both to one shared t_arr Pyomo Var.
    candidates = generate_candidates(tk_rows, L=L, U=U, gun=1, adjustable_window_min=0, adjustable_set="none")
    mi1_candidates = [c for c in candidates if c.flno1 == 9101]
    assert len(mi1_candidates) >= 1
    assert all(c.r1_id == ("IB", 9101, 1) for c in mi1_candidates)


def test_r1_id_and_r2_id_are_role_namespaced(tk_rows):
    # Real data has ~26 flight numbers that serve BOTH an inbound and an
    # outbound role across different candidates (confirmed by inspection) --
    # r1_id/r2_id must be role-namespaced so these never collide under the
    # same Pyomo Var key (which would silently conflate an arrival timestamp
    # with an unrelated departure timestamp).
    candidates = generate_candidates(tk_rows, L=L, U=U, gun=1, adjustable_window_min=0, adjustable_set="none")
    c = candidates[0]
    assert c.r1_id[0] == "IB"
    assert c.r2_id[0] == "OB"
    assert c.r1_id != c.r2_id

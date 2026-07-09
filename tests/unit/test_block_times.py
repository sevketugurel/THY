"""Unit tests for src.data.block_times.BlockTimeProvider.

K_od (journey constant) is directly observed per-row (gate_to_gate - gap) and
aggregated by median over valid-gap TK rows for that market.
R_o (rotation constant = T_IB_o + T_OB_o) is recovered via least-squares over a
bipartite system of per-station T_IB_x / T_OB_y unknowns; R_o is invariant to the
LS's shift ambiguity (see fixtures/README.md and plan §4), so ground truth is exactly
recoverable even though individual T_IB_x / T_OB_x are not.

marker: unit (solver-free, pure numeric logic).
"""
from pathlib import Path

import pandas as pd
import pytest

from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.unit

L, U = 60, 300


@pytest.fixture
def synthetic_tk_rows():
    df = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    return df[df.cr1 == "TK"].copy()


def test_journey_constant_matches_hand_calc_zza_zzb(synthetic_tk_rows):
    provider = BlockTimeProvider(synthetic_tk_rows, L=L, U=U)
    assert provider.get_journey_constant("ZZA", "ZZB") == pytest.approx(220.0)


def test_journey_constant_matches_hand_calc_zzb_zza(synthetic_tk_rows):
    provider = BlockTimeProvider(synthetic_tk_rows, L=L, U=U)
    assert provider.get_journey_constant("ZZB", "ZZA") == pytest.approx(240.0)


def _row(o, d, arr_min, dep_min, gate_to_gate_min):
    return {
        "cr1": "TK", "flno1": 1, "arr_time": pd.Timestamp(2026, 1, 1) + pd.Timedelta(minutes=arr_min),
        "flno2": 2, "dep_time": pd.Timestamp(2026, 1, 1) + pd.Timedelta(minutes=dep_min),
        "gate_to_gate_min": gate_to_gate_min, "od": f"{o}-{d}", "dep1": o, "arr2": d,
    }


def test_journey_constant_uses_median_over_multiple_valid_rows():
    rows = pd.DataFrame([
        _row("AA", "BB", 0, 100, 100 + 220),   # gap=100 (valid), implied K=220
        _row("AA", "BB", 0, 200, 200 + 230),   # gap=200 (valid), implied K=230
        _row("AA", "BB", 0, 40, 40 + 999),     # gap=40 (invalid, <L) -- must be excluded
    ])
    provider = BlockTimeProvider(rows, L=L, U=U)
    assert provider.get_journey_constant("AA", "BB") == pytest.approx(225.0)


def test_journey_constant_excludes_gap_above_u():
    rows = pd.DataFrame([
        _row("AA", "BB", 0, 100, 100 + 220),   # gap=100 (valid)
        _row("AA", "BB", 0, 400, 400 + 999),   # gap=400 (invalid, >U) -- must be excluded
    ])
    provider = BlockTimeProvider(rows, L=L, U=U)
    assert provider.get_journey_constant("AA", "BB") == pytest.approx(220.0)


def test_journey_constant_raises_for_unknown_market():
    rows = pd.DataFrame([_row("AA", "BB", 0, 100, 320)])
    provider = BlockTimeProvider(rows, L=L, U=U)
    with pytest.raises(KeyError):
        provider.get_journey_constant("XX", "YY")


def test_journey_constant_estimate_matches_direct_when_directly_observed(connected_pqr_rows):
    # Doğruluk argümanı (M5, full-data'da bulundu -- 575/1329 pazarda K_od
    # DOĞRUDAN gözlemlenmiyor, hiçbir baseline satırı [L,U] içinde değil).
    # T_IB_o+T_OB_d, R_o'nun AYNI kanıtıyla (global shift T_IB+=c,T_OB-=c
    # HER satır denklemini korur) shift-invariant -- bu yüzden fallback
    # tahmini, doğrudan gözlemlenen bir pazarda medyan-bazlı K_od ile
    # UYUMLU olmalı (aynı LS sisteminin bir yan ürünü).
    provider = BlockTimeProvider(connected_pqr_rows, L=L, U=U)
    direct = provider.get_journey_constant("P", "Q")
    estimate = provider.get_journey_constant_estimate("P", "Q")
    assert estimate == pytest.approx(direct, abs=1e-6)


def test_journey_constant_estimate_recovers_never_directly_paired_market():
    # S only ever appears paired with P (never with Q) -- P-S and S-Q markets
    # have ZERO direct rows, but S/P/Q are all in the SAME connected
    # bipartite component, so T_IB_S and T_OB_S are still recoverable.
    def r(o, d, k):
        return _row(o, d, 0, 100, 100 + k)

    rows = pd.DataFrame([
        r("P", "Q", 105), r("Q", "P", 130), r("Q", "R", 115),
        r("R", "Q", 95), r("P", "R", 95), r("R", "P", 100),
        r("S", "P", 90),  # connects S into the component (T_IB_S + T_OB_P = 90)
    ])
    provider = BlockTimeProvider(rows, L=L, U=U)
    with pytest.raises(KeyError):
        provider.get_journey_constant("S", "Q")  # never directly observed
    estimate = provider.get_journey_constant_estimate("S", "Q")
    assert estimate is not None


def test_journey_constant_estimate_raises_when_station_never_seen_at_all():
    rows = pd.DataFrame([_row("AA", "BB", 0, 100, 320)])
    provider = BlockTimeProvider(rows, L=L, U=U)
    with pytest.raises(KeyError):
        provider.get_journey_constant_estimate("AA", "ZZ_NEVER_SEEN")


@pytest.fixture
def connected_pqr_rows():
    # A minimal-but-connected 3-station bipartite system (unlike the 2-station
    # ZZA/ZZB market fixture, which has only 2 equations for 4 unknowns and is
    # provably underdetermined beyond the single global shift -- see
    # tests/fixtures/README.md discussion). Ground truth:
    #   T_IB_P=50, T_OB_P=60 -> R_P=110
    #   T_IB_Q=70, T_OB_Q=55 -> R_Q=125
    #   T_IB_R=40, T_OB_R=45 -> R_R=85
    def r(o, d, k):
        return _row(o, d, 0, 100, 100 + k)  # gap=100 (valid), implied K=k

    return pd.DataFrame([
        r("P", "Q", 50 + 55),   # 105
        r("Q", "P", 70 + 60),   # 130
        r("Q", "R", 70 + 45),   # 115
        r("R", "Q", 40 + 55),   # 95
        r("P", "R", 50 + 45),   # 95
        r("R", "P", 40 + 60),   # 100
    ])


def test_rotation_constant_recovers_ground_truth_r_p(connected_pqr_rows):
    provider = BlockTimeProvider(connected_pqr_rows, L=L, U=U)
    assert provider.get_rotation_constant("P") == pytest.approx(110.0, abs=1e-6)


def test_rotation_constant_recovers_ground_truth_r_q(connected_pqr_rows):
    provider = BlockTimeProvider(connected_pqr_rows, L=L, U=U)
    assert provider.get_rotation_constant("Q") == pytest.approx(125.0, abs=1e-6)


def test_rotation_constant_recovers_ground_truth_r_r(connected_pqr_rows):
    provider = BlockTimeProvider(connected_pqr_rows, L=L, U=U)
    assert provider.get_rotation_constant("R") == pytest.approx(85.0, abs=1e-6)


def test_rotation_constant_flags_single_role_station():
    # Station "CC" only ever appears as a destination (never an origin) -- T_IB_CC
    # is never directly observed, so it must be flagged as an assumption (VARSAYIM).
    rows = pd.DataFrame([
        _row("AA", "BB", 0, 100, 100 + 220),
        _row("AA", "CC", 0, 150, 150 + 240),
    ])
    provider = BlockTimeProvider(rows, L=L, U=U)
    r_cc = provider.get_rotation_constant("CC")
    assert r_cc == pytest.approx(r_cc)  # finite, doesn't raise
    assert "CC" in provider.single_role_stations


def test_rotation_constant_does_not_flag_two_role_station(connected_pqr_rows):
    provider = BlockTimeProvider(connected_pqr_rows, L=L, U=U)
    assert provider.single_role_stations == set()

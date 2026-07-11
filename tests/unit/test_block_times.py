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


# ---------------------------------------------------------------------------
# v2 Elapsed-preferred path (VARSAYIM-15, M5e) -- K_od/R_o become direct
# per-leg observations instead of a gap-dependent equation / bipartite LS.
# LS-fallback tests above are unmodified and remain the regression proof
# that the legacy path (no elapsed1_min/elapsed2_min columns) is untouched.
# ---------------------------------------------------------------------------
def _row_elapsed(o, d, arr_min, dep_min, elapsed1_min, elapsed2_min):
    return {
        "cr1": "TK", "flno1": 1, "arr_time": pd.Timestamp(2026, 1, 1) + pd.Timedelta(minutes=arr_min),
        "flno2": 2, "dep_time": pd.Timestamp(2026, 1, 1) + pd.Timedelta(minutes=dep_min),
        "gate_to_gate_min": elapsed1_min + (dep_min - arr_min) + elapsed2_min,
        "od": f"{o}-{d}", "dep1": o, "arr2": d,
        "elapsed1_min": elapsed1_min, "elapsed2_min": elapsed2_min,
    }


def test_journey_constant_elapsed_path_uses_median_over_all_rows_including_invalid_gap():
    # Row 3 has gap=40 (<L=60) -- the LEGACY LS path would exclude it (see
    # test_journey_constant_uses_median_over_multiple_valid_rows above), but
    # VARSAYIM-15 says Elapsed1/Elapsed2 are valid regardless of gap validity
    # (they're per-leg block times, not the [L,U]-filtered displayed field),
    # so all 3 rows must be included: median(220, 230, 200) == 220, NOT
    # median(220, 230) == 225 (what LS-style exclusion would give).
    rows = pd.DataFrame([
        _row_elapsed("AA", "BB", 0, 100, 50, 170),   # gap=100 (valid), k=220
        _row_elapsed("AA", "BB", 0, 200, 60, 170),   # gap=200 (valid), k=230
        _row_elapsed("AA", "BB", 0, 40, 10, 190),    # gap=40 (invalid, <L) -- MUST still count
    ])
    provider = BlockTimeProvider(rows, L=L, U=U)
    assert provider.get_journey_constant("AA", "BB") == pytest.approx(220.0)


def test_journey_constant_elapsed_path_matches_hand_calc():
    rows = pd.DataFrame([
        _row_elapsed("AA", "BB", 0, 100, 90, 150),   # k=240
        _row_elapsed("AA", "BB", 0, 100, 100, 160),  # k=260
    ])
    provider = BlockTimeProvider(rows, L=L, U=U)
    assert provider.get_journey_constant("AA", "BB") == pytest.approx(250.0)


def test_rotation_constant_elapsed_path_recovers_ground_truth_without_ls():
    # Deliberately only 2 stations (P, Q) -- the LEGACY LS path requires >=3
    # connected stations to be well-determined (see connected_pqr_rows'
    # comment on the 2-station case being "provably underdetermined"); the
    # elapsed path needs NO bipartite solve at all, T_IB_x/T_OB_x are each
    # directly observed per-leg medians, so 2 stations is sufficient.
    rows = pd.DataFrame([
        _row_elapsed("P", "Q", 0, 100, 50, 55),   # T_IB_P obs=50, T_OB_Q obs=55
        _row_elapsed("Q", "P", 0, 100, 70, 60),   # T_IB_Q obs=70, T_OB_P obs=60
    ])
    provider = BlockTimeProvider(rows, L=L, U=U)
    assert provider.get_rotation_constant("P") == pytest.approx(110.0)  # 50+60
    assert provider.get_rotation_constant("Q") == pytest.approx(125.0)  # 70+55


def test_rotation_constant_elapsed_path_flags_single_role_station():
    rows = pd.DataFrame([
        _row_elapsed("AA", "BB", 0, 100, 80, 140),
        _row_elapsed("AA", "CC", 0, 150, 80, 160),
    ])
    provider = BlockTimeProvider(rows, L=L, U=U)
    assert "CC" in provider.single_role_stations  # CC only ever arr2, never dep1


def test_journey_constant_estimate_elapsed_path_recovers_never_directly_paired_market():
    # S-Q has zero direct rows, but S is observed as dep1 (T_IB_S) elsewhere
    # and Q is observed as arr2 (T_OB_Q) elsewhere -- no connectivity/LS
    # needed, each is an independent per-station median.
    rows = pd.DataFrame([
        _row_elapsed("S", "P", 0, 100, 90, 60),   # T_IB_S obs=90
        _row_elapsed("R", "Q", 0, 100, 40, 55),   # T_OB_Q obs=55
    ])
    provider = BlockTimeProvider(rows, L=L, U=U)
    with pytest.raises(KeyError):
        provider.get_journey_constant("S", "Q")
    assert provider.get_journey_constant_estimate("S", "Q") == pytest.approx(145.0)  # 90+55


def test_synthetic_od_table_elapsed_fixture_matches_hand_calc():
    # Fixture-scale (real xlsx round-trip, string-parse primary path) version
    # of the elapsed-path proofs above -- see tests/fixtures/README.md "M5e
    # eki" for the full hand derivation.
    df = load_od_table(FIXDIR / "synthetic_od_table_elapsed.xlsx")
    provider = BlockTimeProvider(df, L=L, U=U)
    assert provider.get_journey_constant("ZZA", "ZZB") == pytest.approx(220.0)
    assert provider.get_journey_constant("EZE", "PEK") == pytest.approx(1565.0)  # k=elapsed1+elapsed2=1020+545


def test_block_time_provider_falls_back_to_ls_when_elapsed_columns_absent(synthetic_tk_rows):
    # Hidden-test schema-safety proof: the real fixture (no elapsed1_min/
    # elapsed2_min columns) must produce byte-identical numeric results to
    # today's LS-path hand-calc tests above.
    assert "elapsed1_min" not in synthetic_tk_rows.columns
    provider = BlockTimeProvider(synthetic_tk_rows, L=L, U=U)
    assert provider.get_journey_constant("ZZA", "ZZB") == pytest.approx(220.0)
    assert provider.get_journey_constant("ZZB", "ZZA") == pytest.approx(240.0)

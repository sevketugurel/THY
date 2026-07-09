"""M5 VARSAYIM-10 sanity check: R_o (rotation constant = T_IB_o+T_OB_o,
combined round-trip block time, NOT a ground turnaround) should be roughly
proportional to route distance/duration on real full data -- a long-haul
station (many hours each way) should have a much larger R_o than a
domestic one (a couple hours each way). This is an order-of-magnitude
sanity check, not exact validation (R_o is LS-estimated, not directly
measured).

marker: slow (touches data_raw/, real full-data files).
"""
from pathlib import Path

import pytest

from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table

pytestmark = pytest.mark.slow

FULL_OD = Path(__file__).parent.parent.parent / "data_raw" / "O&D Rakip Bağlantı Tablosu (1).xlsx"


@pytest.fixture(scope="module")
def provider():
    if not FULL_OD.exists():
        pytest.skip("data_raw/ full dataset not present")
    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    return BlockTimeProvider(tk, L=60, U=300)


def test_r_o_long_haul_far_exceeds_domestic(provider):
    # KUL (Kuala Lumpur, ~10-11h one-way from IST) round trip should be on
    # the order of many hours -- and clearly, by a wide margin, larger than
    # a domestic Turkish route (ASR=Kayseri, AYT=Antalya, ~1.5-2h one-way).
    r_o_kul = provider.get_rotation_constant("KUL")
    r_o_asr = provider.get_rotation_constant("ASR")
    assert r_o_kul > 5 * r_o_asr


def test_r_o_domestic_routes_are_plausible_order_of_magnitude(provider):
    # Domestic round trips: a few hours, not minutes and not days.
    for station in ("ASR", "AYT"):
        r_o = provider.get_rotation_constant(station)
        assert 30 <= r_o <= 600, f"R_o({station})={r_o} outside a plausible domestic round-trip range"


def test_r_o_long_haul_stations_are_plausible_order_of_magnitude(provider):
    # Long haul (KUL, ~20h+ round trip incl. ground time) should be many
    # hours but not absurdly larger than a full day-plus.
    r_o = provider.get_rotation_constant("KUL")
    assert 600 <= r_o <= 2 * 1440, f"R_o(KUL)={r_o} outside a plausible long-haul round-trip range"

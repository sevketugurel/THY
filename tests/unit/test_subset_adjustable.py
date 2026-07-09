"""Unit tests for src.candidates.subset -- M5 solve ladder step 2
(adjustable-subset mode: top-K markets by rho get free flight times, the
rest are fixed at baseline and folded into F's residual capacity).

Doğruluk argümanı (ultrathink, kod öncesi): bir flight instance (role,flno,gun)
BİRDEN FAZLA (o,d) pazarının adayında paylaşılabilir (cross-product) --
"pazar bazında ayarlanabilirlik" kavramı bu yüzden FLIGHT INSTANCE'a
UYGULANMADAN önce netleştirilmeli: bir instance, EN AZ BİR adjustable
pazarın adayında yer alıyorsa ADJUSTABLE kalır (izin verici birleşim) --
bu, o instance'ı paylaşan diğer (adjustable olmayan) pazarların da bu
esneklikten YAN ETKİ olarak faydalanmasına izin verir, ki bu ZARARSIZDIR
(daha fazla esneklik asla objektifi kötüleştirmez, sadece daha KISITLI
olması gereken bir pazara fazladan bir seçenek sunar). Adjustable OLMAYAN
bir instance'ın bounds'u kendi HAM baseline değerine (arr_time/dep_time'dan
epoch-min) collapse edilir -- Rfix ile AYNI temsil (`_window` mantığının
elle-tekrarı). Collapse sonrası bazı candidate'lar artık achievable-range
kapısını GEÇEMEYEBİLİR (geniş pencerede geçerliydi, dar/sabit pencerede
değil) -- bu candidate'lar DÜŞÜRÜLÜR (aksi halde model imkansız bir
candidate'ı hâlâ x_pi olarak taşırdı).

marker: unit (solver-free, pure logic).
"""
import pandas as pd
import pytest

from src.candidates.generate import Candidate
from src.candidates.subset import apply_adjustable_subset

pytestmark = pytest.mark.unit

L, U = 60, 300


def _candidate(o, d, flno1, flno2, arr_baseline, dep_baseline, w=180, gun=1):
    arr_lo, arr_hi = arr_baseline - w, arr_baseline + w
    dep_lo, dep_hi = dep_baseline - w, dep_baseline + w
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun),
        arr_time=pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=arr_baseline),
        dep_time=pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=dep_baseline),
        gap_min=dep_baseline - arr_baseline,
        arr_lo=arr_lo, arr_hi=arr_hi, dep_lo=dep_lo, dep_hi=dep_hi,
        gap_lo=dep_lo - arr_hi, gap_hi=dep_hi - arr_lo,
    )


def test_adjustable_market_candidate_keeps_wide_bounds():
    c = _candidate("ZZA", "ZZB", 1, 2, arr_baseline=800, dep_baseline=900)
    result = apply_adjustable_subset([c], adjustable_markets={("ZZA", "ZZB")}, L=L, U=U)
    assert len(result) == 1
    assert (result[0].arr_lo, result[0].arr_hi) == (620, 980)
    assert (result[0].dep_lo, result[0].dep_hi) == (720, 1080)


def test_non_adjustable_market_candidate_collapses_to_baseline():
    # baseline gap = 900-800 = 100, well within [L,U] -- survives collapse.
    c = _candidate("ZZA", "ZZB", 1, 2, arr_baseline=800, dep_baseline=900)
    result = apply_adjustable_subset([c], adjustable_markets=set(), L=L, U=U)
    assert len(result) == 1
    assert (result[0].arr_lo, result[0].arr_hi) == (800, 800)
    assert (result[0].dep_lo, result[0].dep_hi) == (900, 900)
    assert (result[0].gap_lo, result[0].gap_hi) == (100, 100)


def test_non_adjustable_candidate_dropped_if_baseline_gap_outside_window():
    # baseline gap = 900-500 = 400 > U=300 -- was only reachable via the wide
    # (adjustable) window; collapsed to Rfix it's genuinely infeasible, must
    # be dropped (not silently kept as an always-x=0 dead candidate).
    c = _candidate("ZZA", "ZZB", 1, 2, arr_baseline=500, dep_baseline=900)
    result = apply_adjustable_subset([c], adjustable_markets=set(), L=L, U=U)
    assert result == []


def test_shared_instance_stays_adjustable_via_permissive_union():
    # Same inbound instance (IB,1,1) feeds TWO markets: ZZA-ZZB (adjustable)
    # and ZZA-ZZC (not adjustable). The instance must stay ADJUSTABLE in
    # BOTH candidates (shared physical flight, one t_arr variable) -- the
    # ZZA-ZZC candidate benefits as a harmless side effect.
    c1 = _candidate("ZZA", "ZZB", 1, 2, arr_baseline=800, dep_baseline=900)
    c2 = _candidate("ZZA", "ZZC", 1, 3, arr_baseline=800, dep_baseline=850)
    result = apply_adjustable_subset(
        [c1, c2], adjustable_markets={("ZZA", "ZZB")}, L=L, U=U,
    )
    by_od = {c.od: c for c in result}
    assert (by_od["ZZA-ZZB"].arr_lo, by_od["ZZA-ZZB"].arr_hi) == (620, 980)
    # ZZC's own market isn't adjustable, but its SHARED inbound leg (IB,1,1)
    # is -- arr side stays wide even though dep side (unique to this market,
    # flno2=3) collapses.
    assert (by_od["ZZA-ZZC"].arr_lo, by_od["ZZA-ZZC"].arr_hi) == (620, 980)
    assert (by_od["ZZA-ZZC"].dep_lo, by_od["ZZA-ZZC"].dep_hi) == (850, 850)

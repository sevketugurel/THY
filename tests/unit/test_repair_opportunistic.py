"""M5i RCR Engine kampanya bug-fix (2026-07-12 gecesi, round-1 otopsisi):
fırsatçı kill seçimi -- bir iterasyonda x.fix(0) YALNIZCA o iterasyonun
serbestlik durumunda pencere-dışına GERÇEKTEN ulaşabilen adaylara uygulanır.

Kök neden: _lns_step_worker, kill listesinin TÜM adaylarına fix(0) basıyordu;
donuk (free-set dışı) bir adayın referans gap'i [L,U] İÇİNDEYSE B'nin çift
yönlü reifikasyonu x=1'i zorlar -> fix(0) ile çelişki -> alt-model KOŞULSUZ
infeasible (round 1: 20/20 iterasyon). Spec §4.1'in mekanizması ("kapatmalar
hedeflenen bileşende gerçekleşir") fırsatçı uygulamayı tarif eder."""
from src.candidates.generate import Candidate
from src.repair.opportunistic import select_opportunistic_kills

L, U = 60, 300


def _candidate(o, d, flno1, flno2, arr_lo, arr_hi, dep_lo, dep_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=0, arr_lo=arr_lo, arr_hi=arr_hi, dep_lo=dep_lo, dep_hi=dep_hi,
        gap_lo=dep_lo - arr_hi, gap_hi=dep_hi - arr_lo,
    )


def test_both_free_killable_is_fixed():
    # arr [0,200], dep [0,500] -> gap [-200,500], pencere dışına ulaşır
    c = _candidate("ZZG", "ZZH", 201, 301, 0, 200, 0, 500)
    fix_idx, skipped = select_opportunistic_kills(
        [c], [("ZZG", "ZZH", 1)],
        free_arr={("IB", 201, 1)}, free_dep={("OB", 301, 1)},
        reference_arr={("IB", 201, 1): 100}, reference_dep={("OB", 301, 1): 250},
        L=L, U=U)
    assert fix_idx == [0] and skipped == 0


def test_both_frozen_inwindow_is_skipped():
    # Donuk referans gap = 250-100 = 150 (pencere içi) -> fix(0) çelişki üretirdi
    c = _candidate("ZZG", "ZZH", 201, 301, 0, 200, 0, 500)
    fix_idx, skipped = select_opportunistic_kills(
        [c], [("ZZG", "ZZH", 1)],
        free_arr=set(), free_dep=set(),
        reference_arr={("IB", 201, 1): 100}, reference_dep={("OB", 301, 1): 250},
        L=L, U=U)
    assert fix_idx == [] and skipped == 1


def test_both_frozen_outwindow_is_fixed():
    # Donuk referans gap = 500-100 = 400 > U -> x=0 zaten tutarlı, fix güvenli
    c = _candidate("ZZG", "ZZH", 201, 301, 0, 200, 0, 500)
    fix_idx, skipped = select_opportunistic_kills(
        [c], [("ZZG", "ZZH", 1)],
        free_arr=set(), free_dep=set(),
        reference_arr={("IB", 201, 1): 100}, reference_dep={("OB", 301, 1): 500},
        L=L, U=U)
    assert fix_idx == [0] and skipped == 0


def test_one_side_free_reachable_outside_is_fixed():
    # arr donuk (=100), dep serbest [0,500] -> gap [-100,400], dışarı ulaşır
    c = _candidate("ZZG", "ZZH", 201, 301, 0, 200, 0, 500)
    fix_idx, skipped = select_opportunistic_kills(
        [c], [("ZZG", "ZZH", 1)],
        free_arr=set(), free_dep={("OB", 301, 1)},
        reference_arr={("IB", 201, 1): 100}, reference_dep={("OB", 301, 1): 250},
        L=L, U=U)
    assert fix_idx == [0] and skipped == 0


def test_one_side_free_unreachable_outside_is_skipped():
    # arr donuk (=100), dep serbest ama dar [160,360] -> gap [60,260] tamamen pencere içi
    c = _candidate("ZZG", "ZZH", 201, 301, 0, 200, 160, 360)
    fix_idx, skipped = select_opportunistic_kills(
        [c], [("ZZG", "ZZH", 1)],
        free_arr=set(), free_dep={("OB", 301, 1)},
        reference_arr={("IB", 201, 1): 100}, reference_dep={("OB", 301, 1): 250},
        L=L, U=U)
    assert fix_idx == [] and skipped == 1


def test_non_killed_directions_untouched():
    c1 = _candidate("ZZG", "ZZH", 201, 301, 0, 200, 0, 500)
    c2 = _candidate("ZZX", "ZZY", 202, 302, 0, 200, 0, 500)  # kill listesinde DEĞİL
    fix_idx, skipped = select_opportunistic_kills(
        [c1, c2], [("ZZG", "ZZH", 1)],
        free_arr={("IB", 201, 1), ("IB", 202, 1)}, free_dep={("OB", 301, 1), ("OB", 302, 1)},
        reference_arr={("IB", 201, 1): 100, ("IB", 202, 1): 100},
        reference_dep={("OB", 301, 1): 250, ("OB", 302, 1): 250},
        L=L, U=U)
    assert fix_idx == [0] and skipped == 0

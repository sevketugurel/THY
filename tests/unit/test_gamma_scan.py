"""Kapı-B (Γ-duyarlılık ön-tarama, docs/STATUS.md): pure, solver-free helpers
that turn compute_gamma_infeasible_pairs' boolean flag into numeric signals
so a Γ sweep can be scored without any MIP solve.

marker: unit (solver-free, pure logic).
"""
import pytest

from src.candidates.generate import Candidate
from src.model.gamma_scan import (
    baseline_e2_violations, best_case_gap_per_pair, independent_pair_lower_bound,
    static_infeasible_count,
)
from src.model.lns import compute_gamma_infeasible_pairs

pytestmark = pytest.mark.unit


def _candidate(o, d, gun, gap_min, gap_lo, gap_hi, flno1=1, flno2=2):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=gap_min, arr_lo=0, arr_hi=0, dep_lo=0, dep_hi=0,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )


# --- best_case_gap_per_pair ---

def test_best_case_gap_per_pair_computes_min_achievable_gap_between_directions():
    # fwd J range: journey_constant(50) + [10,20] = [60,70]
    # bwd J range: journey_constant(50) + [100,110] = [150,160]
    # best-case gap = 150 - 70 = 80
    candidates = [
        _candidate("A", "B", 1, gap_min=15, gap_lo=10, gap_hi=20),
        _candidate("B", "A", 1, gap_min=105, gap_lo=100, gap_hi=110),
    ]
    journey_constants = {("A", "B"): 50, ("B", "A"): 50}
    gaps = best_case_gap_per_pair(candidates, journey_constants, L=0, U=1000)
    assert gaps == {("A", "B", 1): 80}


def test_best_case_gap_per_pair_zero_when_ranges_overlap():
    candidates = [
        _candidate("A", "B", 1, gap_min=15, gap_lo=10, gap_hi=20),
        _candidate("B", "A", 1, gap_min=15, gap_lo=10, gap_hi=20),
    ]
    journey_constants = {("A", "B"): 50, ("B", "A"): 50}
    gaps = best_case_gap_per_pair(candidates, journey_constants, L=0, U=1000)
    assert gaps == {("A", "B", 1): 0}


def test_best_case_gap_per_pair_skips_one_sided_markets():
    candidates = [_candidate("A", "B", 1, gap_min=15, gap_lo=10, gap_hi=20)]
    journey_constants = {("A", "B"): 50}
    gaps = best_case_gap_per_pair(candidates, journey_constants, L=0, U=1000)
    assert gaps == {}


def test_best_case_gap_per_pair_agrees_with_compute_gamma_infeasible_pairs():
    candidates = [
        _candidate("A", "B", 1, gap_min=15, gap_lo=10, gap_hi=20),
        _candidate("B", "A", 1, gap_min=105, gap_lo=100, gap_hi=110),
        _candidate("C", "D", 1, gap_min=15, gap_lo=10, gap_hi=20),
        _candidate("D", "C", 1, gap_min=15, gap_lo=10, gap_hi=20),
    ]
    journey_constants = {("A", "B"): 50, ("B", "A"): 50, ("C", "D"): 50, ("D", "C"): 50}
    for gamma in (0, 30, 79, 80, 200):
        gaps = best_case_gap_per_pair(candidates, journey_constants, L=0, U=1000)
        expected = compute_gamma_infeasible_pairs(candidates, journey_constants, L=0, U=1000, gamma=gamma)
        assert static_infeasible_count(gaps, gamma) == len(expected)


# --- static_infeasible_count ---

def test_static_infeasible_count_counts_pairs_above_gamma():
    gaps = {("A", "B", 1): 80, ("C", "D", 1): 20}
    assert static_infeasible_count(gaps, gamma=30) == 1
    assert static_infeasible_count(gaps, gamma=90) == 0


# --- independent_pair_lower_bound ---

def test_independent_pair_lower_bound_sums_excess_over_gamma():
    gaps = {("A", "B", 1): 80, ("C", "D", 1): 20, ("E", "F", 1): 200}
    # excess over gamma=30: max(0,50) + max(0,-10) + max(0,170) = 220
    assert independent_pair_lower_bound(gaps, gamma=30) == 220


def test_independent_pair_lower_bound_zero_when_all_within_gamma():
    gaps = {("A", "B", 1): 10, ("C", "D", 1): 20}
    assert independent_pair_lower_bound(gaps, gamma=30) == 0


# --- baseline_e2_violations ---

def test_baseline_e2_violations_counts_and_sums_mass_at_baseline_schedule():
    # baseline (gap_min) journeys: fwd=50+15=65, bwd=50+105=155, diff=90
    candidates = [
        _candidate("A", "B", 1, gap_min=15, gap_lo=10, gap_hi=20),
        _candidate("B", "A", 1, gap_min=105, gap_lo=100, gap_hi=110),
    ]
    journey_constants = {("A", "B"): 50, ("B", "A"): 50}
    count, mass = baseline_e2_violations(candidates, journey_constants, L=0, U=1000, gamma=30)
    assert count == 1
    assert mass == pytest.approx(60.0)  # 90 - 30


def test_baseline_e2_violations_ignores_candidates_outside_l_u_window():
    candidates = [
        _candidate("A", "B", 1, gap_min=15, gap_lo=10, gap_hi=20),  # gap_min outside [50,1000]
        _candidate("B", "A", 1, gap_min=105, gap_lo=100, gap_hi=110),
    ]
    journey_constants = {("A", "B"): 50, ("B", "A"): 50}
    count, mass = baseline_e2_violations(candidates, journey_constants, L=50, U=1000, gamma=30)
    assert count == 0
    assert mass == 0.0


def test_baseline_e2_violations_zero_when_within_gamma():
    candidates = [
        _candidate("A", "B", 1, gap_min=15, gap_lo=10, gap_hi=20),
        _candidate("B", "A", 1, gap_min=15, gap_lo=10, gap_hi=20),
    ]
    journey_constants = {("A", "B"): 50, ("B", "A"): 50}
    count, mass = baseline_e2_violations(candidates, journey_constants, L=0, U=1000, gamma=30)
    assert count == 0
    assert mass == 0.0

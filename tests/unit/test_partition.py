"""M5d LNS fold-redesign (plan: .claude/plans/a-evet-ama-iki-tingly-canyon.md,
adim 1): src.model.partition.partition_by_freedom -- tek dogruluk kaynagi
olan serbest/donuk siniflandirma.

marker: unit (solver-free, pure logic).
"""
import pytest

from src.candidates.generate import Candidate
from src.model.partition import partition_by_freedom

pytestmark = pytest.mark.unit

L, U = 60, 300


def _candidate(o, d, flno1, flno2, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=0, arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500, gap_lo=-500, gap_hi=500,
    )


def test_candidate_free_if_either_end_in_free_set():
    # c1: both ends free. c2: only r1 free (mixed). c3: only r2 free (mixed).
    # c4: neither end free (fully frozen).
    c1 = _candidate("ZZG", "ZZH", 201, 301)
    c2 = _candidate("ZZG", "ZZH", 202, 302)
    c3 = _candidate("ZZG", "ZZH", 203, 303)
    c4 = _candidate("ZZG", "ZZH", 204, 304)
    candidates = [c1, c2, c3, c4]
    reference_arr = {c.r1_id: 10 for c in candidates}
    reference_dep = {c.r2_id: 150 for c in candidates}
    free_arr = {c1.r1_id, c2.r1_id}
    free_dep = {c1.r2_id, c3.r2_id}

    result = partition_by_freedom(candidates, free_arr, free_dep, reference_arr, reference_dep, L, U)

    assert result.is_free_candidate == {0: True, 1: True, 2: True, 3: False}
    # Only the fully-frozen candidate (index 3) gets a constant.
    assert set(result.x_const) == {3}
    assert set(result.gap_const) == {3}


def test_frozen_candidate_gap_and_x_const_match_reference():
    c1 = _candidate("ZZG", "ZZH", 201, 301)
    candidates = [c1]
    reference_arr = {c1.r1_id: 20}
    reference_dep = {c1.r2_id: 180}  # gap = 160, inside [60,300] -> offered
    result = partition_by_freedom(candidates, set(), set(), reference_arr, reference_dep, L, U)
    assert result.is_free_candidate == {0: False}
    assert result.gap_const[0] == 160
    assert result.x_const[0] == 1


def test_frozen_candidate_not_offered_when_gap_outside_window():
    c1 = _candidate("ZZG", "ZZH", 201, 301)
    candidates = [c1]
    reference_arr = {c1.r1_id: 0}
    reference_dep = {c1.r2_id: 1000}  # gap = 1000, outside [60,300]
    result = partition_by_freedom(candidates, set(), set(), reference_arr, reference_dep, L, U)
    assert result.x_const[0] == 0


def test_free_frozen_partition_sets_are_complements_of_full_universe():
    c1 = _candidate("ZZG", "ZZH", 201, 301)
    c2 = _candidate("ZZH", "ZZG", 202, 302)
    candidates = [c1, c2]
    reference_arr = {c1.r1_id: 0, c2.r1_id: 0}
    reference_dep = {c1.r2_id: 100, c2.r2_id: 100}
    free_arr = {c1.r1_id}
    result = partition_by_freedom(candidates, free_arr, set(), reference_arr, reference_dep, L, U)
    assert result.free_arr == {c1.r1_id}
    assert result.frozen_arr == {c2.r1_id}
    assert result.free_dep == frozenset()
    assert result.frozen_dep == {c1.r2_id, c2.r2_id}


def test_rejects_free_keys_outside_reference_universe():
    c1 = _candidate("ZZG", "ZZH", 201, 301)
    candidates = [c1]
    reference_arr = {c1.r1_id: 0}
    reference_dep = {c1.r2_id: 100}
    with pytest.raises(AssertionError):
        partition_by_freedom(candidates, {("IB", 999, 1)}, set(), reference_arr, reference_dep, L, U)

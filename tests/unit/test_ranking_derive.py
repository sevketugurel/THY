"""Unit tests for src.model.ranking_derive -- post-hoc D reporting derivation
from a concrete (x, gap) assignment (M5f Kapı-5, elastic-fallback path).

marker: unit (pure Python, no solver).
"""
import pytest

from src.candidates.generate import Candidate
from src.model.ranking_derive import derive_ranking_results

pytestmark = pytest.mark.unit


def _candidate(o, d, flno1, flno2, gap, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=gap, arr_lo=0, arr_hi=0, dep_lo=gap, dep_hi=gap, gap_lo=gap, gap_hi=gap,
    )


def test_beats_rivals_below_or_equal_journey_time():
    # journey_const=100, gap=50 -> J=150. Rival R1 at 200 (beaten, 150<=200),
    # R2 at 100 (not beaten, 150>100).
    c = _candidate("ZZA", "ZZB", 101, 201, gap=50)
    rival_data = {("ZZA", "ZZB", 1): {"R1": 200, "R2": 100}}
    journey_constants = {("ZZA", "ZZB"): 100}
    selected = {c: 1}
    gap_values = {c: 50}
    rank_values, beaten = derive_ranking_results(candidates=[c], rival_data=rival_data,
                                                   journey_constants=journey_constants,
                                                   selected=selected, gap_values=gap_values)
    assert beaten[("ZZA", "ZZB", 1)] == ["R1"]
    assert rank_values[("ZZA", "ZZB", 1)] == 2 - 1  # N=2, beaten=1 -> rank=1


def test_rank_floors_at_one_when_all_rivals_beaten():
    c = _candidate("ZZA", "ZZB", 101, 201, gap=0)
    rival_data = {("ZZA", "ZZB", 1): {"R1": 500, "R2": 500}}
    journey_constants = {("ZZA", "ZZB"): 0}
    selected = {c: 1}
    gap_values = {c: 0}
    rank_values, beaten = derive_ranking_results(candidates=[c], rival_data=rival_data,
                                                   journey_constants=journey_constants,
                                                   selected=selected, gap_values=gap_values)
    assert sorted(beaten[("ZZA", "ZZB", 1)]) == ["R1", "R2"]
    assert rank_values[("ZZA", "ZZB", 1)] == 1, "N-beaten=0 must floor at 1, not 0"


def test_unoffered_candidate_beats_nothing():
    c = _candidate("ZZA", "ZZB", 101, 201, gap=0)
    rival_data = {("ZZA", "ZZB", 1): {"R1": 500}}
    journey_constants = {("ZZA", "ZZB"): 0}
    selected = {c: 0}  # not offered
    gap_values = {c: 0}
    rank_values, beaten = derive_ranking_results(candidates=[c], rival_data=rival_data,
                                                   journey_constants=journey_constants,
                                                   selected=selected, gap_values=gap_values)
    assert beaten[("ZZA", "ZZB", 1)] == []
    assert rank_values[("ZZA", "ZZB", 1)] == 1  # N=1, beaten=0 -> rank=1


def test_market_with_no_rivals_is_skipped():
    c = _candidate("ZZA", "ZZB", 101, 201, gap=0)
    rival_data = {("ZZA", "ZZB", 1): {}}
    journey_constants = {("ZZA", "ZZB"): 0}
    rank_values, beaten = derive_ranking_results(candidates=[c], rival_data=rival_data,
                                                   journey_constants=journey_constants,
                                                   selected={c: 1}, gap_values={c: 0})
    assert ("ZZA", "ZZB", 1) not in rank_values
    assert ("ZZA", "ZZB", 1) not in beaten

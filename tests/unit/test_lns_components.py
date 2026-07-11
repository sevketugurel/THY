"""M5d LNS fold-redesign (plan: .claude/plans/a-evet-ama-iki-tingly-canyon.md,
adim 2): connected-component targeting for src.model.lns.

marker: unit (solver-free, pure logic).
"""
import pytest

from src.candidates.generate import Candidate
from src.model.lns import (
    build_pair_adjacency, connected_components, free_instances_for_pairs,
    select_pairs_by_component, split_oversized_component,
)

pytestmark = pytest.mark.unit


def _candidate(o, d, flno1, flno2, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=0, arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500, gap_lo=-500, gap_hi=500,
    )


def _shared_leg_candidates():
    # pair ("A","B",1) <-> pair ("C","D",1) share flno1=1 (leg-sharing);
    # pair ("E","F",1) and ("G","H",1) are both isolated (no shared legs).
    c1 = _candidate("A", "B", 1, 11)
    c2 = _candidate("B", "A", 2, 22)
    c3 = _candidate("C", "D", 1, 33)  # SAME r1_id=("IB",1,1) as c1
    c4 = _candidate("D", "C", 3, 44)
    c5 = _candidate("E", "F", 5, 55)
    c6 = _candidate("F", "E", 6, 66)
    c7 = _candidate("G", "H", 7, 77)
    c8 = _candidate("H", "G", 8, 88)
    return [c1, c2, c3, c4, c5, c6, c7, c8]


# --- build_pair_adjacency ---

def test_build_pair_adjacency_connects_pairs_sharing_a_leg():
    candidates = _shared_leg_candidates()
    pairs = [("A", "B", 1), ("C", "D", 1), ("E", "F", 1), ("G", "H", 1)]
    adjacency = build_pair_adjacency(candidates, pairs)
    assert adjacency[("A", "B", 1)] == {("C", "D", 1)}
    assert adjacency[("C", "D", 1)] == {("A", "B", 1)}
    assert adjacency[("E", "F", 1)] == set()
    assert adjacency[("G", "H", 1)] == set()


# --- connected_components ---

def test_connected_components_sorted_smallest_first():
    adjacency = {
        "a": {"b"}, "b": {"a"},
        "c": {"d", "e"}, "d": {"c"}, "e": {"c"},
        "f": set(),
    }
    components = connected_components(adjacency)
    sizes = [len(c) for c in components]
    assert sizes == [1, 2, 3]
    assert set(components[0]) == {"f"}
    assert set(components[1]) == {"a", "b"}
    assert set(components[2]) == {"c", "d", "e"}


def test_connected_components_from_shared_leg_candidates():
    candidates = _shared_leg_candidates()
    pairs = [("A", "B", 1), ("C", "D", 1), ("E", "F", 1), ("G", "H", 1)]
    adjacency = build_pair_adjacency(candidates, pairs)
    components = connected_components(adjacency)
    sizes = sorted(len(c) for c in components)
    assert sizes == [1, 1, 2]
    two_comp = next(c for c in components if len(c) == 2)
    assert set(two_comp) == {("A", "B", 1), ("C", "D", 1)}


# --- split_oversized_component ---

def test_split_oversized_component_no_split_when_under_budget():
    candidates = _shared_leg_candidates()
    component = [("A", "B", 1), ("C", "D", 1)]
    chunks = split_oversized_component(candidates, component, max_instances=1000, seed=1)
    assert chunks == [component]


def test_split_oversized_component_preserves_all_pairs_no_loss_no_duplication():
    # Chain: pair1-pair2 share a leg, pair2-pair3 share a different leg;
    # pair1/pair3 not directly adjacent. Any single pair's own footprint
    # (4 instances) fits under max_instances=6, but any two chain-adjacent
    # pairs together (7 instances, one shared) do not -- forces a split.
    c1 = _candidate("A", "B", 1, 11)   # IB1,OB11
    c2 = _candidate("B", "A", 2, 22)   # IB2,OB22
    c3 = _candidate("C", "D", 1, 33)   # IB1 (shared with pair1), OB33
    c4 = _candidate("D", "C", 3, 44)   # IB3,OB44
    c5 = _candidate("E", "F", 3, 55)   # IB3 (shared with pair2), OB55
    c6 = _candidate("F", "E", 4, 66)   # IB4,OB66
    candidates = [c1, c2, c3, c4, c5, c6]
    component = [("A", "B", 1), ("C", "D", 1), ("E", "F", 1)]

    chunks = split_oversized_component(candidates, component, max_instances=6, seed=7)

    all_pairs_in_chunks = [p for chunk in chunks for p in chunk]
    assert sorted(all_pairs_in_chunks) == sorted(component), "every pair must appear exactly once across chunks"
    assert len(all_pairs_in_chunks) == len(set(all_pairs_in_chunks)), "no pair duplicated across chunks"
    for chunk in chunks:
        free_arr, free_dep = free_instances_for_pairs(candidates, chunk)
        assert len(free_arr) + len(free_dep) <= 6


def test_split_oversized_component_single_oversized_pair_is_its_own_chunk():
    c1 = _candidate("A", "B", 1, 11)
    c2 = _candidate("B", "A", 2, 22)
    candidates = [c1, c2]
    component = [("A", "B", 1)]  # this pair alone has 4 instances
    chunks = split_oversized_component(candidates, component, max_instances=1, seed=1)
    assert chunks == [component]


# --- select_pairs_by_component ---

def _pair_slack_all_violated(pairs):
    return {p: {"e1": 1.0, "e2": 0.0, "total": 1.0} for p in pairs}


def test_select_pairs_by_component_picks_smallest_first_then_respects_stubborn():
    candidates = _shared_leg_candidates()
    pairs = [("A", "B", 1), ("C", "D", 1), ("E", "F", 1), ("G", "H", 1)]
    pair_slack = _pair_slack_all_violated(pairs)

    # First call: no stubborn components yet -> smallest component
    # (a singleton, tie-broken by min pair: ("E","F",1) < ("G","H",1)).
    chosen, free_arr, free_dep, comp_id, comp_size, revisit = select_pairs_by_component(
        pair_slack, candidates, gamma_infeasible=set(), stubborn=set(),
    )
    assert comp_size == 1
    assert not revisit
    assert set(chosen) == {("E", "F", 1)}
    first_comp_id = comp_id

    # Mark it stubborn -> next call must pick a DIFFERENT component.
    stubborn = {first_comp_id}
    chosen2, *_rest, comp_id2, comp_size2, revisit2 = select_pairs_by_component(
        pair_slack, candidates, gamma_infeasible=set(), stubborn=stubborn,
    )
    assert not revisit2
    assert comp_id2 != first_comp_id
    assert set(chosen2) == {("G", "H", 1)}

    # Mark ALL components stubborn -> must revisit (is_stubborn_revisit=True).
    all_comp_ids = {first_comp_id, comp_id2, frozenset({("A", "B", 1), ("C", "D", 1)})}
    chosen3, *_rest2, comp_id3, comp_size3, revisit3 = select_pairs_by_component(
        pair_slack, candidates, gamma_infeasible=set(), stubborn=all_comp_ids,
    )
    assert revisit3


def test_select_pairs_by_component_all_stubborn_rotates_by_least_attempts():
    # Bug found empirically (docs/decisions.md 2026-07-11): once every
    # component is stubborn, always falling back to the globally smallest
    # one starves every other stubborn component forever (112/126 real
    # iterations re-picked the same component). `attempts` must break the
    # tie by LEAST-retried first, not by size.
    candidates = _shared_leg_candidates()
    pairs = [("A", "B", 1), ("C", "D", 1), ("E", "F", 1), ("G", "H", 1)]
    pair_slack = _pair_slack_all_violated(pairs)
    two_comp_id = frozenset({("A", "B", 1), ("C", "D", 1)})
    ef_comp_id = frozenset({("E", "F", 1)})
    gh_comp_id = frozenset({("G", "H", 1)})
    all_stubborn = {two_comp_id, ef_comp_id, gh_comp_id}

    # Without attempts info: falls back to smallest-first (documented
    # default), which is exactly the behavior that caused the bug.
    chosen_default, *_r, comp_id_default, _s, _rv = select_pairs_by_component(
        pair_slack, candidates, gamma_infeasible=set(), stubborn=all_stubborn,
    )
    assert comp_id_default == ef_comp_id  # smallest, tie-broken -- the starved case

    # With attempts info showing ef_comp_id has already been retried twice
    # and gh_comp_id/two_comp_id have never been retried: must NOT pick
    # ef_comp_id again -- picks the least-attempted one instead.
    attempts = {ef_comp_id: 2, gh_comp_id: 0, two_comp_id: 0}
    chosen_rotated, *_r2, comp_id_rotated, _s2, _rv2 = select_pairs_by_component(
        pair_slack, candidates, gamma_infeasible=set(), stubborn=all_stubborn, attempts=attempts,
    )
    assert comp_id_rotated != ef_comp_id
    assert comp_id_rotated == gh_comp_id  # tie between gh/two at 0 attempts -> smaller size wins


def test_select_pairs_by_component_excludes_gamma_infeasible_and_zero_slack():
    candidates = _shared_leg_candidates()
    pairs = [("A", "B", 1), ("C", "D", 1)]
    pair_slack = {
        ("A", "B", 1): {"e1": 0.0, "e2": 0.0, "total": 0.0},  # not violated
        ("C", "D", 1): {"e1": 1.0, "e2": 0.0, "total": 1.0},
    }
    chosen, free_arr, free_dep, comp_id, comp_size, revisit = select_pairs_by_component(
        pair_slack, candidates, gamma_infeasible=set(), stubborn=set(),
    )
    assert set(chosen) == {("C", "D", 1)}


def test_select_pairs_by_component_returns_empty_when_nothing_eligible():
    candidates = _shared_leg_candidates()
    pair_slack = {("A", "B", 1): {"e1": 0.0, "e2": 0.0, "total": 0.0}}
    chosen, free_arr, free_dep, comp_id, comp_size, revisit = select_pairs_by_component(
        pair_slack, candidates, gamma_infeasible=set(), stubborn=set(),
    )
    assert chosen == []
    assert free_arr == set() and free_dep == set()
    assert comp_id is None and comp_size == 0 and revisit is False

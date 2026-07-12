"""K1 (bu oturum, E2-conflict kırma + kontrollü market-direction kapatma):
src.model.deactivation'ın saf-Python mekaniği -- killability, conflict-edge
inşası, greedy weighted-vertex-cover. Solver yok (marker yok = unit)."""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.deactivation import (
    apply_deactivation, build_conflict_edges, direction_cost, greedy_cover,
    is_direction_killable, market_direction_index,
)

L, U = 60, 300


def _candidate(o, d, flno1, flno2, gap_lo, gap_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=max(gap_lo, min(gap_hi, 0)), arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )


# --- market_direction_index ---

def test_market_direction_index_groups_by_directed_market_day():
    c1 = _candidate("ZZG", "ZZH", 201, 301, 50, 150)
    c2 = _candidate("ZZG", "ZZH", 202, 302, 50, 150)
    c3 = _candidate("ZZH", "ZZG", 203, 303, 50, 150)
    index = market_direction_index([c1, c2, c3])
    assert index[("ZZG", "ZZH", 1)] == [0, 1]
    assert index[("ZZH", "ZZG", 1)] == [2]


# --- is_direction_killable (D2, 3 cases) ---

def test_is_direction_killable_true_when_every_candidate_has_room_outside_window():
    # achievable range [50,350] straddles [L,U]=[60,300] but is not fully
    # contained -- some point (e.g. 301..350 or 50..59) is outside [L,U].
    c1 = _candidate("ZZG", "ZZH", 201, 301, 50, 350)
    assert is_direction_killable([c1], L, U) is True


def test_is_direction_killable_false_for_forced_on_singleton():
    # gap_lo==gap_hi==150, inside [L,U] -- add_b_constraints' own build-time
    # fold already fixes x=1 for this candidate; it cannot be forced to 0.
    c1 = _candidate("ZZG", "ZZH", 201, 301, 150, 150)
    assert is_direction_killable([c1], L, U) is False


def test_is_direction_killable_false_when_a_non_singleton_candidate_is_fully_contained():
    # Not a singleton (gap_lo != gap_hi) but the WHOLE achievable range
    # [100,200] sits inside [60,300] -- no schedule choice can push gap
    # outside [L,U], so x=0 could never be reified either.
    c1 = _candidate("ZZG", "ZZH", 201, 301, 100, 200)
    assert is_direction_killable([c1], L, U) is False


def test_is_direction_killable_one_bad_candidate_blocks_whole_direction():
    ok = _candidate("ZZG", "ZZH", 201, 301, 50, 350)
    bad = _candidate("ZZG", "ZZH", 202, 302, 100, 200)
    assert is_direction_killable([ok, bad], L, U) is False


# --- build_conflict_edges (D3) ---

def test_build_conflict_edges_only_positive_slack_excludes_exempt():
    pair_slack = {
        ("A", "B", 1): {"e1": 1.0, "e2": 0.0, "total": 1.0},
        ("C", "D", 1): {"e1": 0.0, "e2": 0.0, "total": 0.0},
        ("E", "F", 1): {"e1": 0.0, "e2": 5.0, "total": 5.0},
    }
    edges = build_conflict_edges(pair_slack, gamma_infeasible_pairs={("E", "F", 1)})
    assert edges == [(("A", "B", 1), ("B", "A", 1))]


# --- direction_cost (D4) ---

def test_direction_cost_uses_rho_times_max_one_n_candidates():
    direction_index = {("ZZG", "ZZH", 1): [0, 1, 2]}
    rho = {("ZZG", "ZZH"): 10}
    assert direction_cost(("ZZG", "ZZH", 1), direction_index, rho) == 30
    # unknown market -> rho defaults to 0
    assert direction_cost(("ZZX", "ZZY", 1), direction_index, rho) == 0
    # empty direction -> max(1, 0) floor
    direction_index2 = {("ZZG", "ZZH", 1): []}
    assert direction_cost(("ZZG", "ZZH", 1), direction_index2, rho) == 10


# --- greedy_cover (D4) ---

def test_greedy_cover_picks_lowest_cost_per_degree_first():
    # Vertex "cheap" (cost 10) touches BOTH edges -- covering it alone
    # clears both at cost 10 (ratio 5/edge). Vertex "expensive" (cost 100)
    # only clears one. Optimal greedy choice: kill "cheap" first.
    edges = [("cheap", "x1"), ("cheap", "x2")]
    costs = {"cheap": 10, "x1": 100, "x2": 100}
    killable = {"cheap", "x1", "x2"}
    deactivated, uncovered = greedy_cover(edges, costs, killable)
    assert deactivated == [("cheap", 10)]
    assert uncovered == []


def test_greedy_cover_skips_unkillable_directions():
    edges = [("a", "b")]
    costs = {"a": 1, "b": 1}
    killable = {"b"}  # "a" cannot be killed
    deactivated, uncovered = greedy_cover(edges, costs, killable)
    assert deactivated == [("b", 1)]
    assert uncovered == []


def test_greedy_cover_reports_both_ends_unkillable_edge_as_uncovered():
    edges = [("a", "b")]
    costs = {"a": 1, "b": 1}
    deactivated, uncovered = greedy_cover(edges, costs, killable=set())
    assert deactivated == []
    assert uncovered == [("a", "b")]


def test_greedy_cover_tie_break_prefers_fewer_selected_connections():
    # Both "p" and "q" would clear the single edge at equal cost/degree --
    # tie-break: fewer selected connections at the reference point (cheaper
    # to sacrifice) goes first.
    edges = [("p", "q")]
    costs = {"p": 10, "q": 10}
    selected_count = {"p": 5, "q": 1}
    deactivated, uncovered = greedy_cover(edges, costs, killable={"p", "q"}, selected_count=selected_count)
    assert deactivated == [("q", 10)]
    assert uncovered == []


def test_greedy_cover_deterministic_tuple_tiebreak():
    edges = [("b_dir", "a_dir")]
    costs = {"a_dir": 10, "b_dir": 10}
    deactivated, _ = greedy_cover(edges, costs, killable={"a_dir", "b_dir"})
    assert deactivated == [("a_dir", 10)]  # tuple order breaks the final tie


# --- apply_deactivation (D1) ---

def test_apply_deactivation_fixes_all_candidates_in_killed_directions():
    model = pyo.ConcreteModel()
    model.CANDIDATES = pyo.Set(initialize=[0, 1, 2, 3])
    model.x = pyo.Var(model.CANDIDATES, domain=pyo.Binary)
    direction_index = {
        ("ZZG", "ZZH", 1): [0, 1],
        ("ZZH", "ZZG", 1): [2],
        ("ZZG", "ZZI", 1): [3],
    }
    n_fixed = apply_deactivation(model, direction_index, [("ZZG", "ZZH", 1)])
    assert n_fixed == 2
    assert model.x[0].fixed and pyo.value(model.x[0]) == 0
    assert model.x[1].fixed and pyo.value(model.x[1]) == 0
    assert not model.x[2].fixed
    assert not model.x[3].fixed

"""M5d Fix-and-Optimize LNS (docs/decisions.md 2026-07-11): tests for
src.model.lns's block-selection, instance-mapping, and fix-and-solve
mechanics.

marker: solve (small HiGHS solve, <60s) for the fix+solve tests; the pure
block-selection tests need no solver at all.
"""
from pathlib import Path

import pyomo.environ as pyo
import pytest
import yaml

from src.candidates.generate import Candidate, compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.model.build import build_core_feasibility_model, build_elastic_feasibility_model
from src.model.constraints_elastic import add_elastic_feasibility_objective
from src.model.lns import (
    compute_gamma_infeasible_pairs, compute_pair_slack, fix_reference_except_free,
    free_instances_for_pairs, select_worst_pairs,
)
from src.solve.runner import solve

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_FP = "tests/fixtures/synthetic_flight_pairs.xlsx"


def _fixture_ingredients():
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]

    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXTURE_YV, strict=True)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    pairs_df = load_flight_pairs(FIXTURE_FP)

    anchor = compute_epoch_anchor(tk)
    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=config["adjustable_window_min"],
            adjustable_set=config["adjustable_set"], epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    provider = BlockTimeProvider(tk, L=L, U=U)
    journey_constants = {}
    for c in candidates:
        market = (c.o, c.d)
        if market not in journey_constants:
            journey_constants[market] = provider.get_journey_constant(c.o, c.d)

    rotation_stations = set(row["dest"] for row in pairs_df.to_dict("records") if row["orig"] == "IST")
    r_o_lookup = {}
    for station in rotation_stations:
        try:
            r_o_lookup[station] = provider.get_rotation_constant(station)
        except KeyError:
            continue

    return config, L, U, tk, candidates, journey_constants, pairs_df, r_o_lookup, anchor

pytestmark = pytest.mark.solve

L, U = 60, 300
ALPHA = 0.2
GAMMA = 30


def _candidate(o, d, flno1, flno2, arr, dep, gun=1):
    gap = dep - arr
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=gap, arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500,
        gap_lo=-500, gap_hi=500,
    )


# --- compute_pair_slack ---

def test_compute_pair_slack_matches_hand_computation():
    # fwd market ZZG-ZZH: 2 offered candidates (gap in [L,U]) -> n_fwd=2.
    # bwd market ZZH-ZZG: 1 offered candidate -> n_bwd=1.
    # E1: |2-1| - 0.2*(2+1) = 1 - 0.6 = 0.4 -> s_e1=0.4.
    c1 = _candidate("ZZG", "ZZH", 201, 301, arr=0, dep=100)   # gap=100, offered
    c2 = _candidate("ZZG", "ZZH", 202, 302, arr=0, dep=150)   # gap=150, offered
    c3 = _candidate("ZZH", "ZZG", 203, 303, arr=0, dep=120)   # gap=120, offered
    candidates = [c1, c2, c3]
    journey_constants = {("ZZG", "ZZH"): 100.0, ("ZZH", "ZZG"): 100.0}
    arr_times = {c.r1_id: c.arr_lo for c in candidates}  # all arr=0 (arr_lo used as fixed test value below)
    arr_times = {("IB", 201, 1): 0, ("IB", 202, 1): 0, ("IB", 203, 1): 0}
    dep_times = {("OB", 301, 1): 100, ("OB", 302, 1): 150, ("OB", 303, 1): 120}

    slack = compute_pair_slack(candidates, journey_constants, arr_times, dep_times, L, U, ALPHA, GAMMA)
    assert ("ZZG", "ZZH", 1) in slack
    s = slack[("ZZG", "ZZH", 1)]
    assert s["e1"] == pytest.approx(0.4)
    # Jbest_fwd = min(100+100, 100+150) = 200. Jbest_bwd = 100+120 = 220.
    # |200-220|=20 <= Gamma=30 -> e2 slack = 0.
    assert s["e2"] == pytest.approx(0.0)
    assert s["total"] == pytest.approx(0.4)


def test_compute_pair_slack_e2_violation():
    c1 = _candidate("ZZG", "ZZH", 201, 301, arr=0, dep=100)   # gap=100 -> J=200
    c2 = _candidate("ZZH", "ZZG", 202, 302, arr=0, dep=250)   # gap=250 -> J=350
    candidates = [c1, c2]
    journey_constants = {("ZZG", "ZZH"): 100.0, ("ZZH", "ZZG"): 100.0}
    arr_times = {("IB", 201, 1): 0, ("IB", 202, 1): 0}
    dep_times = {("OB", 301, 1): 100, ("OB", 302, 1): 250}
    slack = compute_pair_slack(candidates, journey_constants, arr_times, dep_times, L, U, ALPHA, GAMMA)
    s = slack[("ZZG", "ZZH", 1)]
    # |350-200|=150, Gamma=30 -> e2 slack=120.
    assert s["e2"] == pytest.approx(120.0)
    assert s["e1"] == pytest.approx(0.0)  # both single-candidate, n_fwd=n_bwd=1


# --- select_worst_pairs ---

def test_select_worst_pairs_orders_by_total_descending():
    pair_slack = {
        ("A", "B", 1): {"e1": 1.0, "e2": 0.0, "total": 1.0},
        ("C", "D", 1): {"e1": 5.0, "e2": 2.0, "total": 7.0},
        ("E", "F", 1): {"e1": 0.0, "e2": 0.0, "total": 0.0},
        ("G", "H", 1): {"e1": 0.0, "e2": 3.0, "total": 3.0},
    }
    assert select_worst_pairs(pair_slack, m=2) == [("C", "D", 1), ("G", "H", 1)]
    # zero-slack pairs never selected, even with a huge m.
    assert select_worst_pairs(pair_slack, m=10) == [("C", "D", 1), ("G", "H", 1), ("A", "B", 1)]


def test_select_worst_pairs_skips_excluded():
    pair_slack = {
        ("A", "B", 1): {"e1": 1.0, "e2": 0.0, "total": 1.0},
        ("C", "D", 1): {"e1": 5.0, "e2": 2.0, "total": 7.0},
        ("G", "H", 1): {"e1": 0.0, "e2": 3.0, "total": 3.0},
    }
    # ("C","D",1) is the worst pair but is provably Gamma-infeasible --
    # freeing its instances would only waste budget, must be skipped.
    result = select_worst_pairs(pair_slack, m=2, exclude={("C", "D", 1)})
    assert result == [("G", "H", 1), ("A", "B", 1)]


# --- compute_gamma_infeasible_pairs ---

def test_compute_gamma_infeasible_pairs_flags_asymmetric_journey_constants():
    # fwd: journey_const=1275, only achievable gap range (clipped to [L,U])
    # is [60,300] -> best-case J in [1335,1575]. bwd: journey_const=890,
    # same clipped range -> best-case J in [950,1190]. Best-case gap
    # 1335-1190=145 > Gamma=30 -- unfixable by ANY schedule choice (mirrors
    # the real VCE-CUN/CUN-VCE example from docs/decisions.md 2026-07-11).
    c_fwd = _candidate("ZZG", "ZZH", 201, 301, arr=0, dep=155)
    c_bwd = _candidate("ZZH", "ZZG", 202, 302, arr=0, dep=65)
    candidates = [c_fwd, c_bwd]
    journey_constants = {("ZZG", "ZZH"): 1275.0, ("ZZH", "ZZG"): 890.0}
    infeasible = compute_gamma_infeasible_pairs(candidates, journey_constants, L, U, GAMMA)
    assert ("ZZG", "ZZH", 1) in infeasible


def test_compute_gamma_infeasible_pairs_clean_when_ranges_overlap():
    # Same journey_constants but close enough (both 1000) that gap windows
    # can always bring Jbest within Gamma of each other.
    c_fwd = _candidate("ZZG", "ZZH", 201, 301, arr=0, dep=155)
    c_bwd = _candidate("ZZH", "ZZG", 202, 302, arr=0, dep=155)
    candidates = [c_fwd, c_bwd]
    journey_constants = {("ZZG", "ZZH"): 1000.0, ("ZZH", "ZZG"): 1000.0}
    infeasible = compute_gamma_infeasible_pairs(candidates, journey_constants, L, U, GAMMA)
    assert infeasible == set()


# --- free_instances_for_pairs ---

def test_free_instances_for_pairs_collects_both_directions():
    c1 = _candidate("ZZG", "ZZH", 201, 301, arr=0, dep=100)
    c2 = _candidate("ZZH", "ZZG", 202, 302, arr=0, dep=100)
    c3 = _candidate("ZZG", "ZZI", 203, 303, arr=0, dep=100)  # unrelated market
    candidates = [c1, c2, c3]
    free_arr, free_dep = free_instances_for_pairs(candidates, [("ZZG", "ZZH", 1)])
    assert free_arr == {("IB", 201, 1), ("IB", 202, 1)}
    assert free_dep == {("OB", 301, 1), ("OB", 302, 1)}


# --- fix_reference_except_free + solve: monotone descent ---

def _build_elastic(candidates, journey_constants, pairs_df, r_o_lookup, config, anchor, tk, L, U):
    model = build_elastic_feasibility_model(
        candidates, journey_constants, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U,
    )
    add_elastic_feasibility_objective(model)
    return model


def test_fix_reference_except_free_pins_non_free_instances_exactly():
    config, L, U, tk, candidates, journey_constants, pairs_df, r_o_lookup, anchor = _fixture_ingredients()
    model = _build_elastic(candidates, journey_constants, pairs_df, r_o_lookup, config, anchor, tk, L, U)

    reference_arr = {r: pyo.value((model.t_arr[r].lb + model.t_arr[r].ub) / 2) for r in model.ARR_INSTANCES}
    reference_dep = {r: pyo.value((model.t_dep[r].lb + model.t_dep[r].ub) / 2) for r in model.DEP_INSTANCES}
    # Free only ONE arbitrary instance from each set; everything else
    # (that isn't already Rfix-fixed) must be pinned to the reference.
    free_arr = {next(iter(model.ARR_INSTANCES))}
    free_dep = {next(iter(model.DEP_INSTANCES))}
    fix_reference_except_free(model, reference_arr, reference_dep, free_arr, free_dep)

    for r in model.ARR_INSTANCES:
        if r in free_arr:
            continue
        assert model.t_arr[r].fixed
        assert pyo.value(model.t_arr[r]) == pytest.approx(reference_arr[r])
    for r in model.DEP_INSTANCES:
        if r in free_dep:
            continue
        assert model.t_dep[r].fixed
        assert pyo.value(model.t_dep[r]) == pytest.approx(reference_dep[r])
    assert not model.t_arr[next(iter(free_arr))].fixed
    assert not model.t_dep[next(iter(free_dep))].fixed


def test_lns_iteration_never_increases_total_slack():
    # Reference: an arbitrary (deliberately not slack-minimizing) point --
    # every instance at the LOW end of its own window, rather than the
    # A+G+F-optimal point -- guaranteed to have some E1/E2 slack to work
    # with, without needing to hand-craft a specific market's imbalance.
    config, L, U, tk, candidates, journey_constants, pairs_df, r_o_lookup, anchor = _fixture_ingredients()
    core_model = build_core_feasibility_model(
        candidates, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, tk_rows=tk, bucket_size_min=config["bucket_size_min"],
        capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"],
    )
    reference_arr = {r: pyo.value(core_model.t_arr[r].lb) for r in core_model.ARR_INSTANCES}
    reference_dep = {r: pyo.value(core_model.t_dep[r].lb) for r in core_model.DEP_INSTANCES}

    before = compute_pair_slack(
        candidates, journey_constants, reference_arr, reference_dep, L, U, config["alpha"], config["gamma"],
    )
    before_total = sum(v["total"] for v in before.values())
    assert before_total > 0, "the all-lower-bound reference should have some E1/E2 slack to fix"

    pairs = select_worst_pairs(before, m=5)
    free_arr, free_dep = free_instances_for_pairs(candidates, pairs)

    model = _build_elastic(candidates, journey_constants, pairs_df, r_o_lookup, config, anchor, tk, L, U)
    fix_reference_except_free(model, reference_arr, reference_dep, free_arr, free_dep)
    result = solve(model, solver="highs", time_limit_sec=30, seed=42)
    assert result.status == "optimal"

    after = compute_pair_slack(
        candidates, journey_constants, result.arr_times, result.dep_times, L, U, config["alpha"], config["gamma"],
    )
    after_total = sum(v["total"] for v in after.values())
    assert after_total <= before_total + 1e-6

    # Every instance NOT in the free set must be untouched (bit-for-bit the
    # reference) -- the whole point of LNS is that fixing is real, not a
    # relaxed indicator.
    for r in core_model.ARR_INSTANCES:
        if r in free_arr:
            continue
        assert result.arr_times[r] == pytest.approx(reference_arr[r])
    for r in core_model.DEP_INSTANCES:
        if r in free_dep:
            continue
        assert result.dep_times[r] == pytest.approx(reference_dep[r])

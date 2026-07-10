"""M5d (docs/decisions.md 2026-07-10, user's "elastik model" redirect):
tests for build_core_feasibility_model (reification-free floor: A+G+F only,
no B/C/D/E1/E2) and build_elastic_feasibility_model (+ B + slack-relaxed
E1/E2, feasible BY CONSTRUCTION). Same synthetic fixture as
test_build_feasibility_model.py.

marker: solve (fixture-scale, <60s).
"""
from pathlib import Path

import pyomo.environ as pyo
import pytest
import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.model.build import build_core_feasibility_model, build_elastic_feasibility_model
from src.model.constraints_elastic import add_elastic_feasibility_objective
from src.model.deviation_objective import add_min_deviation_objective
from src.solve.runner import solve

pytestmark = pytest.mark.solve

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


def _build_core():
    config, L, U, tk, candidates, journey_constants, pairs_df, r_o_lookup, anchor = _fixture_ingredients()
    return build_core_feasibility_model(
        candidates, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, tk_rows=tk, bucket_size_min=config["bucket_size_min"],
        capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"],
    )


def _build_elastic():
    config, L, U, tk, candidates, journey_constants, pairs_df, r_o_lookup, anchor = _fixture_ingredients()
    return build_elastic_feasibility_model(
        candidates, journey_constants, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U,
    )


def test_core_model_excludes_selection_and_reward_machinery():
    model = _build_core()
    assert not hasattr(model, "x"), "B's x must not exist -- core model has no connection selection at all"
    assert not hasattr(model, "gap")
    assert not hasattr(model, "s"), "C's slot variable must not exist"
    assert not hasattr(model, "e1_fwd"), "E1 must not exist in the core model"
    assert not hasattr(model, "Jbest"), "E2 must not exist in the core model"


def test_core_model_includes_a_g_f():
    model = _build_core()
    assert hasattr(model, "a_rotation") or hasattr(model, "a_rotation_partial")
    assert hasattr(model, "g_lower") and hasattr(model, "g_upper")
    assert hasattr(model, "f_dep_decompose") and hasattr(model, "f_arr_decompose")


def test_core_model_solves_with_min_deviation_objective():
    model = _build_core()
    add_min_deviation_objective(model)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value is not None
    assert result.objective_value >= 0.0


def test_elastic_model_includes_b_and_slack_relaxed_e1_e2():
    model = _build_elastic()
    assert hasattr(model, "x") and hasattr(model, "gap")
    assert hasattr(model, "s_e1") and hasattr(model, "s_e2")
    assert not hasattr(model, "s"), "C's slot variable must not exist"
    assert not hasattr(model, "beat"), "D must not exist"


def test_elastic_model_is_feasible_by_construction_on_fixture():
    model = _build_elastic()
    add_elastic_feasibility_objective(model)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value is not None
    total_slack = pyo.value(model.total_slack)
    assert total_slack >= 0.0

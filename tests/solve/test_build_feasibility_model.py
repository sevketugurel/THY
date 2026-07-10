"""M5c §3 (docs/decisions.md 2026-07-10): build_feasibility_model excludes
C (monotonic slot) and D (rival-beating + rank_onehot) entirely -- neither
constrains t_arr/t_dep/x/gap, they only exist to compute the reward's
ranking term (see ultrathink in src/model/build.py). This test proves the
composition is correct (right constraint families present, reward-only
machinery absent) using the SAME synthetic fixture main.py --fixture uses,
combined with the min-deviation objective (src/model/deviation_objective.py)
-- the model must actually SOLVE to a feasible schedule, not just build.

marker: solve (fixture-scale, <60s).
"""
import pyomo.environ as pyo
import pytest
import yaml
from pathlib import Path

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi
from src.model.build import build_feasibility_model
from src.model.deviation_objective import add_min_deviation_objective
from src.solve.runner import solve

pytestmark = pytest.mark.solve

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_CR = "tests/fixtures/synthetic_change_ranking_input.xlsx"
FIXTURE_FP = "tests/fixtures/synthetic_flight_pairs.xlsx"


def _build_fixture_model():
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]

    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXTURE_YV, strict=True)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    load_change_ranking(FIXTURE_CR)  # unused by feasibility model, loaded for parity
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

    model = build_feasibility_model(
        candidates, journey_constants, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U,
    )
    return model


def test_feasibility_model_excludes_reward_only_machinery():
    model = _build_fixture_model()
    assert not hasattr(model, "s"), "C's slot variable must not exist -- reward-only"
    assert not hasattr(model, "beat"), "D's beat variable must not exist -- reward-only"
    assert not hasattr(model, "beaten"), "D's beaten variable must not exist -- reward-only"
    assert not hasattr(model, "rank_onehot"), "D's rank_onehot must not exist -- reward-only"
    assert not hasattr(model, "objective"), "no reward objective is built -- caller adds one"


def test_feasibility_model_includes_operational_constraint_families():
    model = _build_fixture_model()
    assert hasattr(model, "x") and hasattr(model, "gap")  # B
    assert hasattr(model, "a_rotation") or hasattr(model, "a_rotation_partial")  # A
    assert hasattr(model, "g_lower") and hasattr(model, "g_upper")  # G
    assert hasattr(model, "e1_fwd") and hasattr(model, "e1_bwd")  # E1
    assert hasattr(model, "Jbest") and hasattr(model, "e2_fwd")  # E2
    assert hasattr(model, "f_dep_decompose") and hasattr(model, "f_arr_decompose")  # F


def test_feasibility_model_solves_to_a_feasible_schedule_with_min_deviation_objective():
    model = _build_fixture_model()
    add_min_deviation_objective(model)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value is not None
    assert result.objective_value >= 0.0

"""M5d (docs/decisions.md 2026-07-10): end-to-end test of
derive_and_set_warm_start on the fixture -- builds A+G+F, solves it, derives
a full warm-start assignment for the elastic model from that point, and
confirms HiGHS actually ACCEPTS it (not just that the solve doesn't crash --
the HiGHS log must contain "MIP start solution is feasible", the same
confirmation string locked in by test_runner_warmstart.py).

marker: solve (fixture-scale, <60s).
"""
from pathlib import Path

import pytest
import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.model.build import build_core_feasibility_model, build_elastic_feasibility_model
from src.model.constraints_elastic import add_elastic_feasibility_objective
from src.model.deviation_objective import add_min_deviation_objective
from src.model.warm_start import derive_and_set_warm_start
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


def test_derived_warm_start_is_accepted_by_highs(tmp_path):
    config, L, U, tk, candidates, journey_constants, pairs_df, r_o_lookup, anchor = _fixture_ingredients()

    core_model = build_core_feasibility_model(
        candidates, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, tk_rows=tk, bucket_size_min=config["bucket_size_min"],
        capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"],
    )
    add_min_deviation_objective(core_model)
    core_result = solve(core_model, solver="highs", time_limit_sec=60, seed=42)
    assert core_result.status == "optimal"

    elastic_model = build_elastic_feasibility_model(
        candidates, journey_constants, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U,
    )
    # Order matters: add_elastic_feasibility_objective creates the
    # deviation-tracking vars (arr_dev_plus/minus etc) that
    # derive_and_set_warm_start also needs to set -- must run first.
    add_elastic_feasibility_objective(elastic_model)
    summary = derive_and_set_warm_start(
        elastic_model, candidates, journey_constants, core_result.arr_times, core_result.dep_times,
        L=L, U=U, alpha=config["alpha"], gamma=config["gamma"], bucket_size_min=config["bucket_size_min"],
        epoch_anchor=anchor,
    )
    assert summary["total_s_e1"] >= 0.0
    assert summary["total_s_e2"] >= 0.0

    log_path = tmp_path / "warm_start_fixture.log"
    result = solve(
        elastic_model, solver="highs", time_limit_sec=60, seed=42,
        log_file=log_path, warmstart=True,
    )
    assert result.status == "optimal"
    log_text = log_path.read_text()
    assert "MIP start solution is feasible" in log_text, (
        "HiGHS did not confirm accepting the derived warm start"
    )

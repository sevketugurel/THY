"""End-to-end fixture run for the benchmark pipeline with real HiGHS."""

import json

import pytest

from src.benchmark.pipeline import run_benchmark_pipeline
from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi
from src.data.ranking import compute_baseline_best_journey, derive_b_od, is_ranking_monotonic

pytestmark = pytest.mark.solve

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_CR = "tests/fixtures/synthetic_change_ranking_input.xlsx"
FIXTURE_FP = "tests/fixtures/synthetic_flight_pairs.xlsx"

CONFIG = {
    "L": 60,
    "U": 300,
    "tau": 45,
    "X_dev": 15,
    "alpha": 0.20,
    "gamma": 30,
    "bucket_size_min": 10,
    "capacity_departure": 10,
    "capacity_arrival": 15,
    "adjustable_window_min": 180,
    "adjustable_set": "all",
    "e1_activation": "conditional",
    "seed": 42,
    "solver": "highs",
    "watchdog_margin_sec": 60,
}


def test_benchmark_pipeline_fixture_improve_reaches_66875(tmp_path):
    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXTURE_YV)
    rho = {(row.orig, row.dest): row.rho for row in yolcu.itertuples()}
    ranking_table = load_change_ranking(FIXTURE_CR)
    pairs_df = load_flight_pairs(FIXTURE_FP)
    anchor = compute_epoch_anchor(tk)

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk,
            L=60,
            U=300,
            gun=gun,
            adjustable_window_min=180,
            adjustable_set="all",
            epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    provider = BlockTimeProvider(tk, L=60, U=300)
    journey_constants = {}
    for candidate in candidates:
        market = (candidate.o, candidate.d)
        if market not in journey_constants:
            try:
                journey_constants[market] = provider.get_journey_constant(*market)
            except KeyError:
                journey_constants[market] = provider.get_journey_constant_estimate(*market)

    rival_data = {}
    b_od_data = {}
    for candidate in candidates:
        market_day = (candidate.o, candidate.d, candidate.gun)
        if market_day not in rival_data:
            rival_data[market_day] = derive_rival_best_times(
                od_table,
                candidate.o,
                candidate.d,
                candidate.gun,
            )
        if (candidate.o, candidate.d) not in b_od_data:
            baseline_j = compute_baseline_best_journey(
                od_table,
                candidate.o,
                candidate.d,
                candidate.gun,
                L=60,
                U=300,
            )
            b_od_data[(candidate.o, candidate.d)] = (
                derive_b_od(od_table, candidate.o, candidate.d, candidate.gun, baseline_j)
                if baseline_j is not None
                else 0
            )

    rotation_stations = {row["dest"] for row in pairs_df.to_dict("records") if row["orig"] == "IST"}
    r_o_lookup = {}
    for station in rotation_stations:
        try:
            r_o_lookup[station] = provider.get_rotation_constant(station)
        except KeyError:
            continue

    rc = run_benchmark_pipeline(
        output_path=tmp_path / "output.json",
        od_path=FIXTURE_OD,
        yv_path=FIXTURE_YV,
        cr_path=FIXTURE_CR,
        fp_path=FIXTURE_FP,
        config=CONFIG,
        od_table=od_table,
        tk=tk,
        provider=provider,
        rho=rho,
        anchor=anchor,
        candidates=candidates,
        journey_constants=journey_constants,
        rival_data=rival_data,
        b_od_data=b_od_data,
        ranking_table=ranking_table,
        pairs_df=pairs_df,
        r_o_lookup=r_o_lookup,
        monotonic=is_ranking_monotonic(ranking_table),
        seed_deltas_path=tmp_path / "seed_missing.json",
        time_budget_sec=180,
        improve_enabled=True,
        yolcu_strict=True,
    )
    assert rc == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert data["solver_metrics"]["status"] == "strict_feasible_incumbent"
    assert data["objective_value"] == pytest.approx(668.75)
    assert data["diagnostics"]["strict_feasible"] is True
    assert data["diagnostics"]["claim_complete"] is True

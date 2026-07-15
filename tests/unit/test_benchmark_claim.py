"""Tests for claim-complete benchmark connection derivation."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.benchmark.claim import build_full_claim, derive_market_universe, derive_ranking_from_claim
from src.benchmark.times import build_baseline_times
from src.candidates.generate import compute_epoch_anchor
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table, load_yolcu_verisi

pytestmark = pytest.mark.unit

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_OUTPUT = "outputs/fixture_output.json"


def test_build_full_claim_gap_window():
    tk = pd.DataFrame([
        {
            "flno1": 10,
            "flno2": 20,
            "gun": 1,
            "arr_time": pd.Timestamp(2026, 3, 1, 10, 0),
            "dep_time": pd.Timestamp(2026, 3, 1, 12, 0),
            "dep1": "AAA",
            "arr2": "BBB",
            "cr1": "TK",
        },
        {
            "flno1": 11,
            "flno2": 20,
            "gun": 1,
            "arr_time": pd.Timestamp(2026, 3, 1, 11, 30),
            "dep_time": pd.Timestamp(2026, 3, 1, 12, 0),
            "dep1": "AAA",
            "arr2": "BBB",
            "cr1": "TK",
        },
    ])
    times = build_baseline_times(tk, pd.Timestamp(2026, 3, 1))
    claim = build_full_claim(tk, {("AAA", "BBB"): 100.0}, times, L=60, U=300)
    assert [(c["flno1"], c["flno2"], c["gap_min"]) for c in claim] == [(10, 20, 120)]


def test_full_claim_matches_fixture_models_selection():
    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    anchor = compute_epoch_anchor(tk)
    data = json.loads(Path(FIXTURE_OUTPUT).read_text())

    times = build_baseline_times(tk, anchor)
    times.update({
        (entry["role"], entry["flno"], entry["gun"]): entry["time_min"]
        for entry in data["adjusted_flight_times"]
    })

    yolcu = load_yolcu_verisi(FIXTURE_YV)
    rho = {(row.orig, row.dest): row.rho for row in yolcu.itertuples()}
    provider = BlockTimeProvider(tk, L=60, U=300)
    market_k_od, _, _ = derive_market_universe(tk, rho, provider)

    claim = build_full_claim(tk, market_k_od, times, L=60, U=300)
    derived = {(c["od"], c["flno1"], c["flno2"], c["gun"]) for c in claim}
    listed = {(c["od"], c["flno1"], c["flno2"], c["gun"]) for c in data["selected_connections"]}
    assert derived == listed


def test_derive_ranking_passes_independent_d_check(tmp_path):
    from src.validate.independent_validator import validate_output

    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXTURE_YV)
    rho = {(row.orig, row.dest): row.rho for row in yolcu.itertuples()}
    provider = BlockTimeProvider(tk, L=60, U=300)
    market_k_od, _, _ = derive_market_universe(tk, rho, provider)
    data = json.loads(Path(FIXTURE_OUTPUT).read_text())

    data["ranking_results"] = derive_ranking_from_claim(
        od_table, market_k_od, data["selected_connections"]
    )
    p = tmp_path / "out.json"
    p.write_text(json.dumps(data))

    res = validate_output(
        p,
        FIXTURE_OD,
        L=60,
        U=300,
        adjustable_window_min=180,
        adjustable_set="all",
        flight_pairs_path="tests/fixtures/synthetic_flight_pairs.xlsx",
        tau=45,
        x_dev=15,
        alpha=0.20,
        gamma=30,
        bucket_size_min=10,
        capacity_departure=10,
        capacity_arrival=15,
    )
    ranking_violations = [v for v in res.violations if v.startswith("ranking_results")]
    assert ranking_violations == []

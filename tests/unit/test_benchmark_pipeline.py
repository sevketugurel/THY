"""Benchmark pipeline contract tests without a real solver."""

import json

import pytest

from src.benchmark.pipeline import Assessment, _is_better, run_benchmark_pipeline
from src.candidates.generate import compute_epoch_anchor
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi

pytestmark = pytest.mark.unit

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


def _pipeline_kwargs(tmp_path, **overrides):
    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXTURE_YV)
    kwargs = dict(
        output_path=tmp_path / "output.json",
        od_path=FIXTURE_OD,
        yv_path=FIXTURE_YV,
        cr_path=FIXTURE_CR,
        fp_path=FIXTURE_FP,
        config=CONFIG,
        od_table=od_table,
        tk=tk,
        provider=BlockTimeProvider(tk, L=60, U=300),
        rho={(row.orig, row.dest): row.rho for row in yolcu.itertuples()},
        anchor=compute_epoch_anchor(tk),
        candidates=[],
        journey_constants={},
        rival_data={},
        b_od_data={},
        ranking_table=load_change_ranking(FIXTURE_CR),
        pairs_df=load_flight_pairs(FIXTURE_FP),
        r_o_lookup={},
        monotonic=True,
        seed_deltas_path=tmp_path / "seed_missing.json",
        time_budget_sec=600,
        improve_enabled=False,
        yolcu_strict=True,
    )
    kwargs.update(overrides)
    return kwargs


def test_floor_written_and_exit_zero_without_seed(tmp_path, capsys):
    rc = run_benchmark_pipeline(**_pipeline_kwargs(tmp_path))
    assert rc == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert data["objective_value"] is not None
    assert data["objective_value"] > 0
    assert data["diagnostics"]["claim_complete"] is True
    assert data["diagnostics"]["missing_claims"] == 0
    assert data["diagnostics"]["extra_claims"] == 0
    assert data["diagnostics"]["constraint_interpretation"] == (
        "strict_A_G_checked; E1_E2_reported_as_diagnostics"
    )
    assert "baseline_floor" in data["solver_metrics"]["status"]
    out = capsys.readouterr().out
    assert "valid=" not in out


def test_corrupt_seed_falls_back_to_floor(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text("{bad")
    rc = run_benchmark_pipeline(**_pipeline_kwargs(tmp_path, seed_deltas_path=seed))
    assert rc == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert "baseline_floor" in data["solver_metrics"]["status"]


def test_seed_with_zero_deltas_not_promoted(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"deltas": []}))
    rc = run_benchmark_pipeline(**_pipeline_kwargs(tmp_path, seed_deltas_path=seed))
    assert rc == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert "baseline_floor" in data["solver_metrics"]["status"]


def test_improve_crash_keeps_best_and_exit_zero(tmp_path):
    def boom_ladder(**kwargs):
        raise RuntimeError("solver crashed")

    rc = run_benchmark_pipeline(**_pipeline_kwargs(
        tmp_path,
        improve_enabled=True,
        candidates=["fake-candidate"],
        ladder_fn=boom_ladder,
    ))
    assert rc == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert data["objective_value"] is not None


def test_selection_prefers_cleaner_hard_family_profile_over_objective():
    floor = Assessment(
        stage="baseline_floor",
        status="baseline_floor_with_strict_violations",
        objective=2_983_669.09,
        n_strict_violations=1710,
        strict_feasible=False,
        claim={"claim_complete": True},
        families={"counts": {"A": 109, "D": 22, "E1": 296, "E2": 1199, "F": 31, "G": 53}, "examples": {}},
    )
    seed = Assessment(
        stage="heuristic_incumbent",
        status="heuristic_incumbent_with_strict_violations",
        objective=1_488_074.81,
        n_strict_violations=327,
        strict_feasible=False,
        claim={"claim_complete": True},
        families={"counts": {"E1": 106, "E2": 221}, "examples": {}},
    )
    assert _is_better(seed, floor)

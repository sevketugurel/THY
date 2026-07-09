"""End-to-end integration test for src.solve.subprocess_watchdog through the
REAL worker script (scripts/_solve_step_worker.py) -- not the fake workers
used in tests/unit/test_subprocess_watchdog.py, which only cover the
process-management mechanics. This runs the fixture data (same data
main.py --fixture uses) through solve_with_ladder with
use_subprocess_watchdog=True and the real default_solve, verifying the full
pickle round-trip -> subprocess -> build_model_m4 -> HiGHS -> pickle-back
path produces the same kind of result as an in-process solve.

marker: solve (spawns a real subprocess that does a real small HiGHS solve).
"""
from pathlib import Path

import pytest

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi
from src.data.ranking import compute_baseline_best_journey, derive_b_od, is_ranking_monotonic
from src.solve.ladder import solve_with_ladder

pytestmark = pytest.mark.solve

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_CR = "tests/fixtures/synthetic_change_ranking_input.xlsx"
FIXTURE_FP = "tests/fixtures/synthetic_flight_pairs.xlsx"
L, U = 60, 300


def _fixture_ladder_kwargs():
    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXTURE_YV)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    ranking_table = load_change_ranking(FIXTURE_CR)
    pairs_df = load_flight_pairs(FIXTURE_FP)

    anchor = compute_epoch_anchor(tk)
    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=180, adjustable_set="all", epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    provider = BlockTimeProvider(tk, L=L, U=U)
    journey_constants = {(c.o, c.d): provider.get_journey_constant(c.o, c.d) for c in candidates}

    rival_data, b_od_data = {}, {}
    for c in candidates:
        market = (c.o, c.d, c.gun)
        if market not in rival_data:
            rival_data[market] = derive_rival_best_times(od_table, c.o, c.d, c.gun)
        if (c.o, c.d) not in b_od_data:
            baseline_j = compute_baseline_best_journey(od_table, c.o, c.d, c.gun, L=L, U=U)
            b_od_data[(c.o, c.d)] = derive_b_od(od_table, c.o, c.d, c.gun, baseline_j) if baseline_j is not None else 0

    monotonic = is_ranking_monotonic(ranking_table)
    rotation_stations = set(row["dest"] for row in pairs_df.to_dict("records") if row["orig"] == "IST")
    r_o_lookup = {}
    for station in rotation_stations:
        try:
            r_o_lookup[station] = provider.get_rotation_constant(station)
        except KeyError:
            continue

    return dict(
        candidates_full=candidates, rho=rho, journey_constants=journey_constants,
        rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
        pairs_df=pairs_df, r_o_lookup=r_o_lookup, tau=45, x_dev=15, epoch_anchor=anchor,
        alpha=0.2, gamma=30, tk_rows=tk, bucket_size_min=10,
        capacity_departure=10, capacity_arrival=15, L=L, U=U, monotonic=monotonic,
    )


def test_real_subprocess_watchdog_matches_expected_fixture_objective():
    kwargs = _fixture_ladder_kwargs()
    model, result, ladder_log = solve_with_ladder(
        **kwargs, step1_time_limit_sec=60, seed=42, solver="highs",
        use_subprocess_watchdog=True, watchdog_margin_sec=30,
    )
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(668.75)
    assert model is None  # owned by the subprocess, never handed back
    assert ladder_log[0]["step"] == "step1_full_adjustable"
    assert ladder_log[0]["build_time_sec"] is not None

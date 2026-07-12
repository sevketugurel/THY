"""K1 (bu oturum): src.model.deactivation'ın fixture-ölçekli solve testi --
killable bir yön gerçekten kapatılınca model hâlâ optimal çözülüyor, o yönün
TÜM adayları x=0/gap [L,U] dışı, ve post-hoc ranking + write_output +
validate_output + recompute_objective zinciri tam bir deactivation'lı
noktada da geçiyor mu.

marker: solve (fixture-scale, <60s).
"""
from pathlib import Path

import pytest
import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.model.build import build_feasibility_model
from src.model.deactivation import apply_deactivation, is_direction_killable, market_direction_index
from src.model.deviation_objective import add_min_deviation_objective
from src.model.ranking_derive import derive_ranking_results
from src.output.writer import write_output
from src.solve.runner import solve
from src.validate.independent_validator import recompute_objective, validate_output

pytestmark = pytest.mark.solve

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_CR = "tests/fixtures/synthetic_change_ranking_input.xlsx"
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

    return config, L, U, tk, od_table, candidates, journey_constants, pairs_df, r_o_lookup, anchor


def _build(candidates, journey_constants, pairs_df, r_o_lookup, config, anchor, tk, L, U):
    model = build_feasibility_model(
        candidates, journey_constants, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U,
    )
    add_min_deviation_objective(model)
    return model


def test_deactivating_a_killable_direction_still_solves_with_all_its_candidates_fixed_off():
    config, L, U, tk, od_table, candidates, journey_constants, pairs_df, r_o_lookup, anchor = _fixture_ingredients()
    direction_index = market_direction_index(candidates)

    killed_direction = None
    for direction, idxs in direction_index.items():
        dir_candidates = [candidates[i] for i in idxs]
        if is_direction_killable(dir_candidates, L, U):
            killed_direction = direction
            break
    assert killed_direction is not None, "fixture must contain at least one killable direction"

    model = _build(candidates, journey_constants, pairs_df, r_o_lookup, config, anchor, tk, L, U)
    n_fixed = apply_deactivation(model, direction_index, [killed_direction])
    assert n_fixed == len(direction_index[killed_direction])

    result = solve(model, solver="highs", time_limit_sec=30, seed=42)
    assert result.status == "optimal"

    for i in direction_index[killed_direction]:
        c = candidates[i]
        assert result.selected[c] == 0
        gap = result.gap_values[c]
        assert not (L <= gap <= U), f"killed candidate {c.od} FlNo1={c.flno1} FlNo2={c.flno2} gap={gap} still in [L,U]"


def test_deactivated_point_passes_post_hoc_ranking_and_full_validation_chain(tmp_path):
    config, L, U, tk, od_table, candidates, journey_constants, pairs_df, r_o_lookup, anchor = _fixture_ingredients()
    direction_index = market_direction_index(candidates)

    killed_direction = None
    for direction, idxs in direction_index.items():
        dir_candidates = [candidates[i] for i in idxs]
        if is_direction_killable(dir_candidates, L, U):
            killed_direction = direction
            break
    assert killed_direction is not None

    model = _build(candidates, journey_constants, pairs_df, r_o_lookup, config, anchor, tk, L, U)
    apply_deactivation(model, direction_index, [killed_direction])
    result = solve(model, solver="highs", time_limit_sec=30, seed=42)
    assert result.status == "optimal"

    rival_data = {}
    for c in candidates:
        market = (c.o, c.d, c.gun)
        if market not in rival_data:
            rival_data[market] = derive_rival_best_times(od_table, c.o, c.d, c.gun)

    rank_values, beaten_rivals = derive_ranking_results(
        candidates, rival_data, journey_constants, result.selected, result.gap_values,
    )
    result.rank_values = rank_values
    result.beaten_rivals = beaten_rivals

    output_path = tmp_path / "deactivation_fixture_output.json"
    write_output(output_path, result)

    validation = validate_output(
        output_path, FIXTURE_OD, L=L, U=U,
        adjustable_window_min=config["adjustable_window_min"], adjustable_set=config["adjustable_set"],
        flight_pairs_path=FIXTURE_FP, tau=config["tau"], x_dev=config["X_dev"],
        alpha=config["alpha"], gamma=config["gamma"],
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"],
    )
    assert validation.is_valid, validation.violations

    recompute_total, _ = recompute_objective(output_path, FIXTURE_OD, FIXTURE_YV, FIXTURE_CR, L=L, U=U)
    assert recompute_total >= 0.0

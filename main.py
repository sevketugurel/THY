#!/usr/bin/env python3
"""Single-command entrypoint: read -> build -> solve -> validate -> write.

M1 scope: B (bağlantı uygunluğu) + C (Modül-5 monoton slot).
M2 scope: + D (rakip yenme ve sıralama). Real constraint groups A,E-G land
in M3+.
"""
import argparse
import sys
from pathlib import Path

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_od_table, load_yolcu_verisi
from src.data.ranking import compute_baseline_best_journey, derive_b_od, is_ranking_monotonic
from src.model.build import build_model_with_competition
from src.output.writer import write_output
from src.solve.runner import solve
from src.validate.independent_validator import validate_output

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_CR = "tests/fixtures/synthetic_change_ranking_input.xlsx"
FULL_OD = "data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx"
FULL_YV = "data_raw/Yolcu Verisi_masked.xlsx"
FULL_CR = "data_raw/change_ranking_input.xlsx"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--fixture", action="store_true", help="use tests/fixtures synthetic data")
    parser.add_argument("--full-data", action="store_true", help="use data_raw/ full competition data")
    parser.add_argument("--output", default="runs/output.json")
    args = parser.parse_args(argv)

    if args.fixture == args.full_data:
        parser.error("exactly one of --fixture or --full-data is required")

    config = yaml.safe_load(Path(args.config).read_text())
    L, U = config["L"], config["U"]

    if args.full_data:
        od_path, yv_path, cr_path = FULL_OD, FULL_YV, FULL_CR
    else:
        od_path, yv_path, cr_path = FIXTURE_OD, FIXTURE_YV, FIXTURE_CR

    od_table = load_od_table(od_path)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(yv_path)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    ranking_table = load_change_ranking(cr_path)

    anchor = compute_epoch_anchor(tk)
    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun,
            adjustable_window_min=config["adjustable_window_min"],
            adjustable_set=config["adjustable_set"], epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    provider = BlockTimeProvider(tk, L=L, U=U)
    journey_constants = {(c.o, c.d): provider.get_journey_constant(c.o, c.d) for c in candidates}

    rival_data = {}
    b_od_data = {}
    for c in candidates:
        market = (c.o, c.d, c.gun)
        if market not in rival_data:
            rival_data[market] = derive_rival_best_times(od_table, c.o, c.d, c.gun)
        if (c.o, c.d) not in b_od_data:
            baseline_j = compute_baseline_best_journey(od_table, c.o, c.d, c.gun, L=L, U=U)
            b_od_data[(c.o, c.d)] = (
                derive_b_od(od_table, c.o, c.d, c.gun, baseline_j) if baseline_j is not None else 0
            )

    monotonic = is_ranking_monotonic(ranking_table)

    model = build_model_with_competition(
        candidates, rho, journey_constants, rival_data, b_od_data, ranking_table,
        L=L, U=U, monotonic=monotonic,
    )
    result = solve(model, solver=config["solver"], time_limit_sec=config["time_limit_sec"], seed=config["seed"])

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_output(output_path, result)

    validation = validate_output(
        output_path, od_path, L=config["L"], U=config["U"],
        adjustable_window_min=config["adjustable_window_min"],
        adjustable_set=config["adjustable_set"],
    )

    n_selected = sum(result.selected.values()) if result.selected else 0
    print(f"status={result.status} objective={result.objective_value} "
          f"selected={n_selected} valid={validation.is_valid}")
    for v in validation.violations:
        print(f"  VIOLATION: {v}")

    return 0 if validation.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Single-command entrypoint: read -> build -> solve -> validate -> write.

M0 scope: trivial model only (free x_pi, linear rho-weighted reward, no
constraints) -- proves the full chain works end-to-end. Real constraint groups
(A-G) and the Modul-5 monotone-slot reward land in M1+.
"""
import argparse
import sys
from pathlib import Path

import yaml

from src.candidates.generate import generate_candidates
from src.data.loaders import load_od_table, load_yolcu_verisi
from src.model.build import build_trivial_model
from src.output.writer import write_output
from src.solve.runner import solve
from src.validate.independent_validator import validate_output

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FULL_OD = "data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx"
FULL_YV = "data_raw/Yolcu Verisi_masked.xlsx"


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

    od_path, yv_path = (FULL_OD, FULL_YV) if args.full_data else (FIXTURE_OD, FIXTURE_YV)

    od_table = load_od_table(od_path)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(yv_path)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(tk, L=config["L"], U=config["U"], gun=gun))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    model = build_trivial_model(candidates, rho)
    result = solve(model, solver=config["solver"], time_limit_sec=config["time_limit_sec"], seed=config["seed"])

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_output(output_path, result)

    validation = validate_output(output_path, od_path, L=config["L"], U=config["U"])

    n_selected = sum(result.selected.values()) if result.selected else 0
    print(f"status={result.status} objective={result.objective_value} "
          f"selected={n_selected} valid={validation.is_valid}")
    for v in validation.violations:
        print(f"  VIOLATION: {v}")

    return 0 if validation.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())

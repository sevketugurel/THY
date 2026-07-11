#!/usr/bin/env python3
"""M5 diagnostic (NOT a permanent pipeline stage): cheap yes/no feasibility
witness for the RAW baseline schedule, with ZERO MIP solve -- pure Python +
the independent validator, runs in seconds.

Why this exists: step1 of the full-data solve ladder ran 20+ minutes at the
root node with zero incumbent on a 605K-row presolved model (see
docs/decisions.md 2026-07-09 "appsi_highs time_limit cannot interrupt
root-node cut rounds"). Before spending more solver time, this answers a
narrower and much cheaper question: with EVERY adjustable flight time FIXED
at its raw baseline value (no adjustment at all), is the schedule itself
already consistent with A/E1/E2/F/G (after the VARSAYIM-9/10/11 exemptions
that are already baked into the validator)? If baseline itself violates a
constraint family, that family is a genuine blocker independent of solver
tuning -- no amount of MIP time will fix a structural infeasibility.

Key structural fact used here (VARSAYIM-6, ASSUMPTIONS.md): B's "gap in
[L,U] => x=1 mandatory" rule means that once every flight time is FIXED
(not just bounded) at baseline, there is NO freedom left in candidate
selection -- every candidate whose BASELINE gap already lands in [L,U] must
be offered (x=1 is the only feasible choice), and every other candidate must
be x=0. This makes "offer exactly the baseline-gap-valid candidates" the
UNIQUE selection consistent with a fully-fixed baseline, not a heuristic
choice among several -- so this witness's selected_connections set is not
an approximation, it's forced.

Kullanım: .venv/bin/python3 -u scripts/baseline_feasibility_witness.py
"""
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi
from src.validate.independent_validator import validate_output

from src.config.paths import FULL_OD, FULL_YV, FULL_CR, FULL_FP


def _violation_category(msg: str) -> str:
    # Every violation message in independent_validator.py starts with a
    # recognizable tag -- see validate_output's violations.append(...) call
    # sites. Longest/most-specific prefixes first to avoid misclassifying
    # ("F kova" before "F", "adjusted_flight_times" before "connection").
    prefixes = [
        ("E1 ", "E1"), ("E2 ", "E2"), ("F kova", "F"),
        ("regularity (x_dev)", "G"), ("rotation FlNo", "A"),
        ("ranking_results ", "D"),
        ("adjusted_flight_times entry", "window_bounds"),
        ("connection ", "connection_gap_or_existence"),
    ]
    for prefix, category in prefixes:
        if msg.startswith(prefix):
            return category
    return "uncategorized"


def main():
    t0 = time.time()
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]

    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FULL_YV, strict=False)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    pairs_df = load_flight_pairs(FULL_FP)

    anchor = compute_epoch_anchor(tk)

    def epoch_min(ts):
        return int((ts - anchor).total_seconds() // 60)

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun,
            adjustable_window_min=config["adjustable_window_min"],
            adjustable_set=config["adjustable_set"], epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    provider = BlockTimeProvider(tk, L=L, U=U)
    dropped_markets = set()
    for c in candidates:
        market = (c.o, c.d)
        if market in dropped_markets:
            continue
        try:
            provider.get_journey_constant(c.o, c.d)
        except KeyError:
            try:
                provider.get_journey_constant_estimate(c.o, c.d)
            except KeyError:
                dropped_markets.add(market)
    candidates = [c for c in candidates if (c.o, c.d) not in dropped_markets]

    # VARSAYIM-6 forced-x: baseline gap in [L,U] => x=1 is the ONLY feasible
    # choice once times are fixed (not just bounded) at baseline.
    reported_times = {}
    for c in candidates:
        reported_times[c.r1_id] = epoch_min(c.arr_time)
        reported_times[c.r2_id] = epoch_min(c.dep_time)
    selected_connections = [
        {"od": c.od, "flno1": c.flno1, "flno2": c.flno2, "gun": c.gun, "gap_min": c.gap_min}
        for c in candidates if L <= c.gap_min <= U
    ]

    data = {
        "objective_value": None,
        "selected_connections": selected_connections,
        "adjusted_flight_times": [
            {"role": role, "flno": flno, "gun": gun, "time_min": t}
            for (role, flno, gun), t in reported_times.items()
        ],
        "ranking_results": [],
        "k_od_sources": [],
        "solver_metrics": {"status": "baseline_witness_no_solve", "solve_time_sec": 0.0},
    }
    output_path = Path("runs/baseline_feasibility_witness_output.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, sort_keys=True))

    validation = validate_output(
        output_path, FULL_OD, L=L, U=U,
        adjustable_window_min=config["adjustable_window_min"],
        adjustable_set=config["adjustable_set"],
        flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
        alpha=config["alpha"], gamma=config["gamma"],
        bucket_size_min=config["bucket_size_min"],
        capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"],
    )

    by_category = Counter(_violation_category(v) for v in validation.violations)
    elapsed = round(time.time() - t0, 1)

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_sec": elapsed,
        "n_candidates_in_scope": len(candidates),
        "n_selected_connections_forced": len(selected_connections),
        "is_valid": validation.is_valid,
        "violation_count_total": len(validation.violations),
        "violation_count_by_category": dict(by_category),
        "sample_violations_by_category": {
            cat: [v for v in validation.violations if _violation_category(v) == cat][:5]
            for cat in by_category
        },
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = Path("runs") / f"baseline_feasibility_witness_{stamp}.json"
    log_path.write_text(json.dumps(summary, indent=2, sort_keys=True))

    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    print(f"\nFull log: {log_path}", flush=True)
    return summary


if __name__ == "__main__":
    main()

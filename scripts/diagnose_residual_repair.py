#!/usr/bin/env python3
"""M5i RCR Engine Adım-0 (spec docs/superpowers/specs/2026-07-12-residual-repair-design.md
§3.1): residual-repair fizibilite teşhisi -- SOLVER YOK, salt-okunur. Kampanyanın ve C1'in
zorunlu önkoşulu: killability, both-unkillable sayısı, yön-başına gerçek ödül katkısı
(recompute_objective breakdown'ından), C1 kayıp tahmini, istasyon kümeleri.

Kullanım: .venv/bin/python3 -u scripts/diagnose_residual_repair.py [--partial ...] [--out ...]
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.config.paths import FULL_CR, FULL_OD, FULL_YV
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table, load_yolcu_verisi
from src.data.provenance import file_provenance
from src.model.deactivation import market_direction_index
from src.model.lns import compute_gamma_infeasible_pairs, compute_pair_slack
from src.repair.diagnosis import build_residual_records, summarize_records
from src.repair.reference import load_reference_point
from src.validate.independent_validator import recompute_objective

DEFAULT_PARTIAL = "runs/lns_best_partial_20260712T150223Z.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--partial", default=DEFAULT_PARTIAL)
    parser.add_argument("--out", default="runs/residual_repair_diagnosis.json")
    args = parser.parse_args()

    t0 = time.time()
    # --- paylaşılan preprocessing bloğu (run_conflict_deactivation_feasibility.py ile aynı) ---
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U, alpha, gamma = config["L"], config["U"], config["alpha"], config["gamma"]

    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FULL_YV, strict=False)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
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
    dropped_markets = set()
    for c in candidates:
        market = (c.o, c.d)
        if market in journey_constants or market in dropped_markets:
            continue
        try:
            journey_constants[market] = provider.get_journey_constant(c.o, c.d)
        except KeyError:
            try:
                journey_constants[market] = provider.get_journey_constant_estimate(c.o, c.d)
            except KeyError:
                dropped_markets.add(market)
    candidates = [c for c in candidates if (c.o, c.d) in journey_constants]
    # --- preprocessing sonu ---

    print(f"[diagnose] preprocessing {time.time()-t0:.1f}s, n_candidates={len(candidates)}", flush=True)

    arr, dep = load_reference_point(args.partial, candidates)
    gamma_inf = compute_gamma_infeasible_pairs(candidates, journey_constants, L, U, gamma)
    pair_slack = compute_pair_slack(candidates, journey_constants, arr, dep, L, U, alpha, gamma,
                                    gamma_infeasible_pairs=gamma_inf)
    sigma = sum(v["total"] for v in pair_slack.values())
    print(f"[diagnose] Sigma-slack={sigma:.2f} at {args.partial}", flush=True)

    # Yön-başına seçili bağlantı sayısı (B semantiği: seçim=pencere-içi gap)
    selected_counts = {}
    for c in candidates:
        gap = dep[c.r2_id] - arr[c.r1_id]
        if L <= gap <= U:
            key = (c.o, c.d, c.gun)
            selected_counts[key] = selected_counts.get(key, 0) + 1

    # Yön-başına gerçek ödül katkısı: bağımsız recompute breakdown'ından
    breakdown_path = Path(args.out).with_suffix(".breakdown.json")
    recompute_total, breakdown = recompute_objective(
        Path(args.partial), FULL_OD, FULL_YV, FULL_CR, L=L, U=U,
        strict=False, breakdown_path=breakdown_path,
    )
    contributions = {
        (m["o"], m["d"], m["gun"]): m["connection_component"] + m["ranking_component"]
        for m in breakdown["markets"]
    }
    print(f"[diagnose] reference recompute objective={recompute_total:.2f}", flush=True)

    direction_index = market_direction_index(candidates)
    records = build_residual_records(pair_slack, direction_index, candidates,
                                     contributions, selected_counts, rho, L, U)
    summary = summarize_records(records)
    summary["sigma_slack"] = sigma
    summary["n_gamma_exempt_pairs"] = len(gamma_inf)

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "partial": args.partial,
        "data_provenance": {"FULL_OD": file_provenance(FULL_OD)},
        "reference_objective_recompute_total": recompute_total,
        "summary": summary,
        "records": records,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    print(f"[diagnose] written: {args.out} ({time.time()-t0:.1f}s total)", flush=True)


if __name__ == "__main__":
    main()

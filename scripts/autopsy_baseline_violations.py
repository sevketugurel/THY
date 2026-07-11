#!/usr/bin/env python3
"""M5 baseline violation autopsy (analysis only, NO code changes, NO solver
calls). Answers two questions raised by the user after M5's DAL C
investigation (docs/decisions.md 2026-07-09, ASSUMPTIONS.md VARSAYIM-12):

1. For each of the 2048 baseline-witness violations (A/E1/E2/F/G), is it a
   REAL constraint conflict, an INTERPRETATION artifact (our reading of the
   brief differs from what's intended), or an ACCOUNTING bug (double-count /
   wrong parameter)?
2. Phase 2 hypothesis: does the adjustable-subset ladder's infeasibility
   (K=50/100/200/400 all infeasible) trace back to flights FIXED to baseline
   carrying baseline's own violations into the K-subset model as
   unconditional hard constraints, regardless of which K or which single
   constraint family is toggled?

For (2): a witness violation is "baked in at K" if EVERY (o,d) market it
touches is OUTSIDE that K's top-K-by-rho adjustable set -- such a violation
is IDENTICAL in the K-subset model (those flights are Rfix there too, by
construction of apply_adjustable_subset) regardless of what the adjustable
markets do, because B's "gap in [L,U] => x=1 mandatory" rule (VARSAYIM-6)
leaves zero freedom for Rfix candidates.

Kullanım: .venv/bin/python3 -u scripts/autopsy_baseline_violations.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi

from src.config.paths import FULL_OD, FULL_YV, FULL_CR, FULL_FP
K_VALUES = (50, 100, 200, 400)


def main():
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]

    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FULL_YV, strict=False)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    ranking_table = load_change_ranking(FULL_CR)
    pairs_df = load_flight_pairs(FULL_FP)
    anchor = compute_epoch_anchor(tk)

    def epoch_min(ts):
        return int((ts - anchor).total_seconds() // 60)

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=config["adjustable_window_min"],
            adjustable_set=config["adjustable_set"], epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    provider = BlockTimeProvider(tk, L=L, U=U)
    journey_constants, dropped_markets = {}, set()
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
    candidates = [c for c in candidates if (c.o, c.d) not in dropped_markets]

    markets_by_rho = sorted({(c.o, c.d) for c in candidates}, key=lambda m: -rho.get(m, 0))
    topk_sets = {k: set(markets_by_rho[:k]) for k in K_VALUES}

    # ============ E2 full decomposition ============
    # journeys_by_market: (o,d,gun) -> list of (journey, gap, market_of_candidate)
    from collections import defaultdict
    groups = defaultdict(list)
    for c in candidates:
        if L <= c.gap_min <= U:  # VARSAYIM-6 forced-x set, same as baseline witness
            groups[(c.o, c.d, c.gun)].append(c)

    journeys_by_market = {}
    for (o, d, gun), cs in groups.items():
        journeys_by_market[(o, d, gun)] = [journey_constants[(o, d)] + c.gap_min for c in cs]

    e2_rows = []
    checked = set()
    for (o, d, gun) in list(journeys_by_market.keys()):
        if (o, d, gun) in checked or (d, o, gun) not in journeys_by_market:
            continue
        checked.add((o, d, gun))
        checked.add((d, o, gun))
        j_fwd = journeys_by_market[(o, d, gun)]
        j_bwd = journeys_by_market[(d, o, gun)]
        jbest_fwd, jbest_bwd = min(j_fwd), min(j_bwd)
        diff = abs(jbest_fwd - jbest_bwd)
        if diff > config["gamma"]:
            k_od_fwd, k_od_bwd = journey_constants[(o, d)], journey_constants[(d, o)]
            k_od_asymmetry = abs(k_od_fwd - k_od_bwd)
            both_in_k400 = (o, d) in topk_sets[400] and (d, o) in topk_sets[400]
            e2_rows.append({
                "o": o, "d": d, "gun": gun, "jbest_fwd": jbest_fwd, "jbest_bwd": jbest_bwd,
                "diff": diff, "k_od_fwd": k_od_fwd, "k_od_bwd": k_od_bwd,
                "k_od_asymmetry": k_od_asymmetry,
                "k_od_asymmetry_alone_exceeds_gamma": k_od_asymmetry > config["gamma"],
                "both_directions_in_k400_adjustable": both_in_k400,
            })

    # ============ E1 full decomposition ============
    all_groups = defaultdict(list)
    for c in candidates:
        all_groups[(c.o, c.d, c.gun)].append(c)
    e1_rows = []
    checked = set()
    for (o, d, gun) in list(all_groups.keys()):
        if (o, d, gun) in checked or (d, o, gun) not in all_groups:
            continue
        checked.add((o, d, gun))
        checked.add((d, o, gun))
        n_fwd = sum(1 for c in all_groups[(o, d, gun)] if L <= c.gap_min <= U)
        n_bwd = sum(1 for c in all_groups[(d, o, gun)] if L <= c.gap_min <= U)
        if n_fwd + n_bwd == 0:
            continue
        if abs(n_fwd - n_bwd) > config["alpha"] * (n_fwd + n_bwd):
            both_in_k400 = (o, d) in topk_sets[400] and (d, o) in topk_sets[400]
            e1_rows.append({
                "o": o, "d": d, "gun": gun, "n_fwd": n_fwd, "n_bwd": n_bwd,
                "both_directions_in_k400_adjustable": both_in_k400,
            })

    # ============ Phase 2: "baked in regardless of K" fraction ============
    # A violation is baked-in-at-K if NEITHER direction's market is in that K's
    # adjustable set (so ALL its candidates are Rfix there, per apply_adjustable_subset).
    baked_in_summary = {}
    for k in K_VALUES:
        topk = topk_sets[k]
        e1_baked = sum(1 for r in e1_rows if (r["o"], r["d"]) not in topk and (r["d"], r["o"]) not in topk)
        e2_baked = sum(1 for r in e2_rows if (r["o"], r["d"]) not in topk and (r["d"], r["o"]) not in topk)
        baked_in_summary[k] = {
            "e1_total": len(e1_rows), "e1_baked_in": e1_baked,
            "e2_total": len(e2_rows), "e2_baked_in": e2_baked,
        }

    result = {
        "e1_violation_count": len(e1_rows),
        "e2_violation_count": len(e2_rows),
        "e2_k_od_asymmetry_alone_sufficient": sum(1 for r in e2_rows if r["k_od_asymmetry_alone_exceeds_gamma"]),
        "e2_sample_rows": sorted(e2_rows, key=lambda r: -r["diff"])[:15],
        "e1_sample_rows": sorted(e1_rows, key=lambda r: -abs(r["n_fwd"] - r["n_bwd"]))[:15],
        "baked_in_by_k": baked_in_summary,
    }
    Path("runs/autopsy_baseline_violations.json").write_text(json.dumps(result, indent=2, sort_keys=True, default=str))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return result


if __name__ == "__main__":
    main()

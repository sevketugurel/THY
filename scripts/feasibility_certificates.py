#!/usr/bin/env python3
"""M5c (docs/decisions.md 2026-07-10, user's "önce fizibilite sorusunu kesin
cevaplıyoruz" redirect): pure-pandas STATIC feasibility certificates for
E1/E2, derived directly from B's own reification semantics -- NO solve, NO
MIP. Goal: determine whether our CURRENT E1/E2 constraint formulation is
PROVABLY infeasible on full data before spending more solve budget chasing
a "hard to solve" story that might actually be "impossible to solve" (which
would also explain the fast-converge-then-stuck symptom seen in all five
prior solve attempts -- B&B searching forever for a feasible integer point
that doesn't exist looks identical to B&B struggling with a huge but
feasible search space, from the outside).

Forced-candidate definition (B's bidirectional reification, ultrathink):
    forced_on:  gap_lo >= L and gap_hi <= U -- gap ALWAYS lands in [L,U]
                regardless of the adjustable choice -> B's backward
                reification structurally forces x=1 in EVERY feasible
                solution. NOTE this is BROADER than add_b_constraints'
                own .fix() (which only fires for the single-point case
                gap_lo==gap_hi) -- a genuinely adjustable candidate whose
                WHOLE window sits inside [L,U] is still forced-on, just
                left as a free binary that every feasible solution pins
                to 1 (the existing E1/E2 exempt+log machinery, keyed off
                model.x[i].fixed, does NOT see this broader set -- see
                the e1_code_scan section below).
    forced_off: gap_hi < L or gap_lo > U -- gap can NEVER land in [L,U] ->
                B's forward reification forces x=0 in EVERY feasible
                solution.
    undetermined: window straddles a boundary -- x's value depends on the
                adjustable choice, genuinely free.

Three certificates, each a NECESSARY-condition check using safe (loose)
outer bounds -- a failure is a sound proof of infeasibility under the
current formulation (the true achievable range is a SUBSET of the box
checked, so if even the generous box has no satisfying point, neither
does the true range):

    E1a: pairs where one direction has a forced-on candidate but the
         reverse direction has ZERO raw candidates -- cross-checked
         against a direct code scan of add_e1_constraints' own pair-build
         condition (does it even construct E1 there?).
    E1b: pairs where E1 IS built (both directions have >=1 raw candidate)
         -- does ANY (n_fwd,n_bwd) in [F_fwd,K_fwd]x[F_bwd,K_bwd] satisfy
         |n_fwd-n_bwd| <= alpha*(n_fwd+n_bwd)?
    E2:  pairs where both directions have >=1 forced-on candidate -- are
         the Jbest outer-bound ranges [min_all_J_lo, min_forced_J_hi] for
         fwd/bwd more than Gamma apart even in the best case?

Kullanım: .venv/bin/python3 -u scripts/feasibility_certificates.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table, load_yolcu_verisi

FULL_OD = "data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx"
FULL_YV = "data_raw/Yolcu Verisi_masked.xlsx"


def forced_status(c, L, U):
    if c.gap_lo >= L and c.gap_hi <= U:
        return "on"
    if c.gap_hi < L or c.gap_lo > U:
        return "off"
    return "undetermined"


def main():
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

    groups = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[(c.o, c.d, c.gun)].append(i)

    status = {i: forced_status(c, L, U) for i, c in enumerate(candidates)}

    summary = {}
    for key, idxs in groups.items():
        K = len(idxs)
        F = sum(1 for i in idxs if status[i] == "on")
        Z = sum(1 for i in idxs if status[i] == "off")
        summary[key] = {"K": K, "F": F, "Z": Z, "U": K - F - Z}

    pair_keys, seen = [], set()
    for (o, d, gun) in groups:
        if (o, d, gun) in seen:
            continue
        seen.add((o, d, gun))
        seen.add((d, o, gun))
        pair_keys.append((o, d, gun))

    # --- Kod taraması: add_e1_constraints' actual pair-build condition ---
    e1_would_be_built, e1_not_built_no_reverse = [], []
    for (o, d, gun) in pair_keys:
        fwd_present = (o, d, gun) in groups
        bwd_present = (d, o, gun) in groups
        if fwd_present and bwd_present:
            e1_would_be_built.append((o, d, gun))
        elif fwd_present or bwd_present:
            e1_not_built_no_reverse.append((o, d, gun))

    # --- Certificate E1a ---
    cert_e1a = []
    for (o, d, gun) in pair_keys:
        fwd = summary.get((o, d, gun), {"K": 0, "F": 0})
        bwd = summary.get((d, o, gun), {"K": 0, "F": 0})
        if fwd["F"] >= 1 and bwd["K"] == 0:
            cert_e1a.append((o, d, gun, fwd["F"], bwd["K"]))
        if bwd["F"] >= 1 and fwd["K"] == 0:
            cert_e1a.append((d, o, gun, bwd["F"], fwd["K"]))

    # --- Certificate E1b ---
    cert_e1b_fail = []
    for (o, d, gun) in e1_would_be_built:
        fwd, bwd = summary[(o, d, gun)], summary[(d, o, gun)]
        found = False
        for n_fwd in range(fwd["F"], fwd["K"] + 1):
            for n_bwd in range(bwd["F"], bwd["K"] + 1):
                if n_fwd + n_bwd == 0 or abs(n_fwd - n_bwd) <= alpha * (n_fwd + n_bwd):
                    found = True
                    break
            if found:
                break
        if not found:
            cert_e1b_fail.append({
                "o": o, "d": d, "gun": gun,
                "fwd_range": [fwd["F"], fwd["K"]], "bwd_range": [bwd["F"], bwd["K"]],
            })

    # --- Certificate E2 ---
    cert_e2_fail = []
    for (o, d, gun) in pair_keys:
        fwd_idxs, bwd_idxs = groups.get((o, d, gun), []), groups.get((d, o, gun), [])
        fwd_forced = [i for i in fwd_idxs if status[i] == "on"]
        bwd_forced = [i for i in bwd_idxs if status[i] == "on"]
        if not fwd_forced or not bwd_forced:
            continue
        j_lo_fwd = min(journey_constants[(o, d)] + candidates[i].gap_lo for i in fwd_idxs)
        j_hi_fwd = min(journey_constants[(o, d)] + candidates[i].gap_hi for i in fwd_forced)
        j_lo_bwd = min(journey_constants[(d, o)] + candidates[i].gap_lo for i in bwd_idxs)
        j_hi_bwd = min(journey_constants[(d, o)] + candidates[i].gap_hi for i in bwd_forced)
        if j_hi_fwd < j_lo_bwd:
            min_gap = j_lo_bwd - j_hi_fwd
        elif j_hi_bwd < j_lo_fwd:
            min_gap = j_lo_fwd - j_hi_bwd
        else:
            min_gap = 0
        if min_gap > gamma:
            cert_e2_fail.append({
                "o": o, "d": d, "gun": gun, "min_gap": min_gap,
                "fwd_range": [j_lo_fwd, j_hi_fwd], "bwd_range": [j_lo_bwd, j_hi_bwd],
            })

    report = {
        "n_candidates": len(candidates),
        "n_market_direction_groups": len(groups),
        "n_market_pairs": len(pair_keys),
        "e1_code_scan": {
            "would_be_built_both_directions_present": len(e1_would_be_built),
            "not_built_one_direction_has_zero_raw_candidates": len(e1_not_built_no_reverse),
        },
        "cert_e1a_forced_on_vs_zero_reverse": {
            "count": len(cert_e1a),
            "note": ("these pairs have K<-=0 -- per code scan, E1 is NOT built for them "
                     "(reverse direction absent from `groups` entirely) -- NOT a real "
                     "infeasibility under the current implementation, listed for completeness."),
            "examples": cert_e1a[:20],
        },
        "cert_e1b_no_satisfying_pair_in_box": {
            "count": len(cert_e1b_fail),
            "note": ("pairs where E1 IS built (both directions have >=1 raw candidate) but "
                     "NO (n_fwd,n_bwd) in [F,K]x[F,K] satisfies |n_fwd-n_bwd|<=alpha*(n_fwd+n_bwd) "
                     "-- since [F,K] is a SAFE OVER-approximation of the true achievable range, "
                     "failure here is a genuine PROOF of infeasibility under this E1 formulation. "
                     "NOTE the existing exempt+log machinery (model.x[i].fixed) does NOT catch "
                     "these -- .fix() only fires for gap_lo==gap_hi, not this broader forced set."),
            "examples": cert_e1b_fail[:20],
        },
        "cert_e2_disjoint_jbest_ranges": {
            "count": len(cert_e2_fail),
            "note": ("pairs where both directions have >=1 forced-on candidate, and the "
                     "Jbest outer-bound ranges [min_all_J_lo, min_forced_J_hi] for fwd/bwd "
                     "are more than Gamma apart in the BEST case -- genuine PROOF of "
                     "infeasibility under this E2 formulation, same blind spot as E1b."),
            "examples": cert_e2_fail[:20],
        },
    }

    Path("runs").mkdir(exist_ok=True)
    out_path = Path("runs/feasibility_certificates.json")
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    print(f"\nFull report: {out_path}")
    return report


if __name__ == "__main__":
    main()

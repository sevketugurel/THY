#!/usr/bin/env python3
"""Kapı-B (Γ-duyarlılık ön-tarama, solver YOK, ~dakikalar). Full-data'da
Γ ∈ {45,60,90,120,150,180} (+ resmî Γ=30 karşılaştırma satırı) için üç
solver-free sinyal (src.model.gamma_scan): (a) statik-imkânsız çift sayısı,
(b) baseline E2 ihlal sayısı/kütlesi, (c) bağımsız-çift alt sınırı (kuplajı
yok sayan iyimser tahmin -- gerçek bir solve'un Σs_e2'si bundan KÜÇÜK
OLAMAZ, bkz. src/model/gamma_scan.py docstring).

Karar kuralı: alt sınırın (c) ilk kez 0'a indiği EN KÜÇÜK Γ değeri Γ* adayı;
Γ* + bir sonraki kademe yedek olarak kaydedilir. Hiçbiri 0'a inmezse
kampanya KOŞULMAZ, bulgu raporlanır.

Kullanım: .venv/bin/python3 -u scripts/scan_gamma_sensitivity.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.config.paths import FULL_OD, FULL_YV
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table, load_yolcu_verisi
from src.data.provenance import file_provenance
from src.model.gamma_scan import (
    baseline_e2_violations, best_case_gap_per_pair, independent_pair_lower_bound,
    static_infeasible_count,
)

GAMMA_SWEEP = (45, 60, 90, 120, 150, 180)


def main():
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]
    official_gamma = config["gamma"]

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

    pair_gaps = best_case_gap_per_pair(candidates, journey_constants, L, U)

    gammas = sorted(set(GAMMA_SWEEP) | {official_gamma})
    rows = []
    for gamma in gammas:
        n_infeasible = static_infeasible_count(pair_gaps, gamma)
        b_count, b_mass = baseline_e2_violations(candidates, journey_constants, L, U, gamma)
        lower_bound = independent_pair_lower_bound(pair_gaps, gamma)
        rows.append({
            "gamma": gamma,
            "is_official": gamma == official_gamma,
            "static_infeasible_pairs": n_infeasible,
            "baseline_e2_violation_count": b_count,
            "baseline_e2_violation_mass_min": round(b_mass, 2),
            "independent_pair_lower_bound_min": round(lower_bound, 2),
        })

    zero_bound_gammas = sorted(r["gamma"] for r in rows if r["independent_pair_lower_bound_min"] == 0.0
                                and r["gamma"] in GAMMA_SWEEP)
    if zero_bound_gammas:
        gamma_star = zero_bound_gammas[0]
        remaining = [g for g in GAMMA_SWEEP if g > gamma_star]
        fallback = remaining[0] if remaining else None
        decision = {
            "gamma_star": gamma_star,
            "fallback_tier": fallback,
            "rationale": (
                f"lower bound (c) first reaches 0 at Γ={gamma_star} among the swept values "
                f"-- smallest Γ where the optimistic independent-pair estimate does not "
                f"rule out Σs_e2=0. Run Kapı-C campaign for Γ*={gamma_star}"
                + (f", fallback Γ={fallback} if it fails." if fallback else " (no fallback tier remains).")
            ),
            "run_campaign": True,
        }
    else:
        decision = {
            "gamma_star": None,
            "fallback_tier": None,
            "rationale": (
                "independent-pair lower bound (c) never reaches 0 within the swept range "
                f"{GAMMA_SWEEP} -- Γ*>180. Per Kapı-B instructions: do NOT run the Kapı-C "
                "campaign, report this finding, proceed to Kapı-D."
            ),
            "run_campaign": False,
        }

    report = {
        "data_provenance": {"FULL_OD": file_provenance(FULL_OD)},
        "n_candidates": len(candidates),
        "n_pairs_with_both_directions": len(pair_gaps),
        "official_gamma": official_gamma,
        "gamma_sweep": list(GAMMA_SWEEP),
        "rows": rows,
        "decision": decision,
    }

    Path("runs").mkdir(exist_ok=True)
    out_path = Path("runs/gamma_sensitivity_scan.json")
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    print(f"\nFull report: {out_path}")
    return report


if __name__ == "__main__":
    main()

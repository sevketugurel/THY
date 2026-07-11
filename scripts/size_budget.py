#!/usr/bin/env python3
"""M5: full-data boyut bütçesi logu -- model kurulmadan ÖNCE, budama
öncesi/sonrası aday sayıları + binary tahminleri. pytest DEĞİL (full-data
işlemleri için 60sn testi kuralı bunun için değil) -- ayrı komut,
timestamped log dosyasına yazar.

Kullanım: .venv/bin/python3 scripts/size_budget.py
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi

from src.config.paths import FULL_OD, FULL_YV, FULL_CR, FULL_FP

L, U = 60, 300
ADJUSTABLE_WINDOW_MIN = 180
BUCKET_SIZE_MIN = 10


def _window_reachable_bucket_count(lo, hi, bucket_size):
    return hi // bucket_size - lo // bucket_size + 1


def main():
    t0 = time.time()
    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FULL_YV, strict=False)
    ranking_table = load_change_ranking(FULL_CR)
    pairs_df = load_flight_pairs(FULL_FP)
    load_time = time.time() - t0

    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}

    anchor = compute_epoch_anchor(tk)
    t1 = time.time()
    candidates_pre_rho = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates_pre_rho.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=ADJUSTABLE_WINDOW_MIN,
            adjustable_set="all", epoch_anchor=anchor,
        ))
    gen_time = time.time() - t1

    candidates = [c for c in candidates_pre_rho if (c.o, c.d) in rho]

    arr_instances = {c.r1_id: (c.arr_lo, c.arr_hi) for c in candidates}
    dep_instances = {c.r2_id: (c.dep_lo, c.dep_hi) for c in candidates}
    markets = set((c.o, c.d, c.gun) for c in candidates)
    market_pairs_both_dirs = set()
    for (o, d, gun) in markets:
        if (d, o, gun) in markets:
            market_pairs_both_dirs.add(tuple(sorted([(o, d, gun), (d, o, gun)])))

    n_z_dep = sum(_window_reachable_bucket_count(lo, hi, BUCKET_SIZE_MIN) for lo, hi in dep_instances.values())
    n_z_arr = sum(_window_reachable_bucket_count(lo, hi, BUCKET_SIZE_MIN) for lo, hi in arr_instances.values())

    # D's beat/beaten binaries need rival data per market -- approximate via
    # average rivals/market from the real od_table (non-TK rows per (o,d,gun)).
    non_tk = od_table[od_table.cr1 != "TK"]
    rival_counts = non_tk.groupby(["od", "gun"])["cr1"].nunique()
    avg_rivals_per_market = float(rival_counts.mean()) if len(rival_counts) else 0.0
    n_beat_approx = int(len(candidates) * avg_rivals_per_market)

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "load_time_sec": round(load_time, 2),
        "candidate_gen_time_sec": round(gen_time, 2),
        "raw_data": {
            "od_table_rows": len(od_table),
            "tk_rows": len(tk),
            "tk_unique_od_markets": int(tk["od"].nunique()),
            "guns": sorted(int(g) for g in tk["gun"].unique()),
            "yolcu_rows_after_strict_false_drop": len(yolcu),
            "flight_pairs_rows": len(pairs_df),
            "flight_pairs_groups": int(pairs_df["pair"].nunique()),
        },
        "candidates": {
            "pre_rho_filter_achievable_range_gated": len(candidates_pre_rho),
            "post_rho_filter": len(candidates),
            "reduction_pct": round(100 * (1 - len(candidates) / max(1, len(candidates_pre_rho))), 1),
        },
        "flight_instances": {
            "unique_arr_instances": len(arr_instances),
            "unique_dep_instances": len(dep_instances),
        },
        "markets": {
            "unique_od_gun_markets_with_candidates": len(markets),
            "bidirectional_pairs_for_e1_e2": len(market_pairs_both_dirs),
        },
        "estimated_binary_counts": {
            "x_pi (B)": len(candidates),
            "y_pi (B aux)": len(candidates),
            "w_pi (E2 selector)": len(candidates),
            "z_dep (F, window-reachable only)": n_z_dep,
            "z_arr (F, window-reachable only)": n_z_arr,
            "z_dep_arr_if_full_144_per_day (NOT used, for comparison)":
                (len(dep_instances) + len(arr_instances)) * (1440 // BUCKET_SIZE_MIN),
            "beat_pi_k (D, approx via avg rivals/market)": n_beat_approx,
            "a_dir (E1/E2 activation, per market)": len(markets),
        },
        "total_time_sec": round(time.time() - t0, 2),
    }

    total_binaries = sum(v for v in report["estimated_binary_counts"].values()
                          if isinstance(v, int) and "NOT used" not in "")
    report["estimated_total_binaries_excluding_full_144_comparison"] = (
        report["estimated_binary_counts"]["x_pi (B)"]
        + report["estimated_binary_counts"]["y_pi (B aux)"]
        + report["estimated_binary_counts"]["w_pi (E2 selector)"]
        + report["estimated_binary_counts"]["z_dep (F, window-reachable only)"]
        + report["estimated_binary_counts"]["z_arr (F, window-reachable only)"]
        + report["estimated_binary_counts"]["beat_pi_k (D, approx via avg rivals/market)"]
        + report["estimated_binary_counts"]["a_dir (E1/E2 activation, per market)"]
    )

    out_dir = Path("runs")
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"size_budget_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True))

    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nWritten to {out_path}")
    return report


if __name__ == "__main__":
    main()

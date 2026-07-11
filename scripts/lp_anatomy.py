#!/usr/bin/env python3
"""M5c LP anatomy (analysis only, NO code changes to src/model/*.py): before
accepting "HiGHS can't solve this at full scale" as a final answer, check
whether the symptom (root-node cuts crawling forever, zero incumbent) is
actually a SOLVER problem or an LP-LOOSENESS problem -- a very loose LP
relaxation gives HiGHS little to work with at the root node regardless of
cut/heuristic settings, and no amount of solver tuning fixes a loose
formulation. This solves the FULL step1 model's LP relaxation alone (all
Binary/Integer domains relaxed to continuous, same bounds), which should be
fast (no branch-and-bound) even at this model's size, and reports:

1. LP relaxation objective value + solve time.
2. Theoretical objective ceiling computed directly from data (no solve):
   sum over markets of rho_od * (max connection-reward-per-market + max
   ranking-reward-per-market-given-its-own-N,b). LP value / ceiling = how
   many multiples of the true achievable maximum the LP relaxation allows
   -- a large ratio means the LP is far too loose to guide branch-and-bound.
3. Row count per constraint family (which family dominates model size).
4. Fractionality map: for each Binary-turned-continuous variable family,
   how many variables land strictly inside (0.01, 0.99) in the LP solution
   -- the most-fractional family is the best tightening target.

Kullanım: .venv/bin/python3 -u scripts/lp_anatomy.py
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyomo.environ as pyo
import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi
from src.data.ranking import compute_baseline_best_journey, derive_b_od, is_ranking_monotonic
from src.model.build import build_model_m4
from src.solve.runner import solve

from src.config.paths import FULL_OD, FULL_YV, FULL_CR, FULL_FP

_BINARY_FAMILIES = ["x", "y", "beat", "beaten", "rank_onehot", "a_dir", "w", "z_dep", "z_arr"]


def main():
    t_script0 = time.time()
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]

    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FULL_YV, strict=False)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    ranking_table = load_change_ranking(FULL_CR)
    pairs_df = load_flight_pairs(FULL_FP)
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

    print(f"[lp_anatomy] preprocessing done in {time.time()-t_script0:.1f}s, "
          f"n_candidates={len(candidates)}", flush=True)

    # ---------- theoretical ceiling from data (no solve) ----------
    from collections import defaultdict as _dd
    max_weight_by_nb = _dd(lambda: 0.0)
    for row in ranking_table.itertuples():
        if row.weight > max_weight_by_nb[(row.n, row.b)]:
            max_weight_by_nb[(row.n, row.b)] = row.weight
    max_slots = config["max_slots_per_market"]
    conn_reward_ceiling_per_market = sum(2 ** (-(j - 1)) for j in range(1, max_slots + 1))  # ~2.0

    n_by_market = {}
    for c in candidates:
        market = (c.o, c.d, c.gun)
        rivals = rival_data.get(market, {})
        n_by_market[market] = len(rivals)

    ceiling = 0.0
    ceiling_by_market = {}
    for (o, d, gun), n in n_by_market.items():
        b = b_od_data.get((o, d), 0)
        best_rank_weight = max(max_weight_by_nb.get((n, b), 0.0), 0.0)
        market_ceiling = rho.get((o, d), 0) * (conn_reward_ceiling_per_market + best_rank_weight)
        ceiling += market_ceiling
        ceiling_by_market[(o, d, gun)] = market_ceiling

    print(f"[lp_anatomy] theoretical ceiling (data-only, no solve) = {ceiling:.2f}", flush=True)

    # ---------- build full model ----------
    t0 = time.time()
    model = build_model_m4(
        candidates, rho, journey_constants, rival_data, b_od_data, ranking_table,
        pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U, monotonic=monotonic,
    )
    build_time_sec = time.time() - t0
    print(f"[lp_anatomy] model build done in {build_time_sec:.1f}s", flush=True)

    # ---------- row count per constraint family ----------
    row_counts = {}
    for comp in model.component_objects(pyo.Constraint, active=True):
        row_counts[comp.name] = len(comp)
    total_rows = sum(row_counts.values())
    print(f"[lp_anatomy] total constraint rows = {total_rows}", flush=True)

    # ---------- variable count per family (before relax) ----------
    var_counts = {}
    for comp in model.component_objects(pyo.Var, active=True):
        var_counts[comp.name] = len(comp)

    # ---------- relax all integrality, solve LP ----------
    pyo.TransformationFactory("core.relax_integer_vars").apply_to(model)
    t1 = time.time()
    lp_result = solve(model, solver="highs", time_limit_sec=1200, seed=42)
    lp_solve_time_sec = time.time() - t1
    print(f"[lp_anatomy] LP relaxation solved in {lp_solve_time_sec:.1f}s "
          f"status={lp_result.status} obj={lp_result.objective_value}", flush=True)

    # ---------- fractionality map ----------
    fractionality = {}
    for family in _BINARY_FAMILIES:
        if not hasattr(model, family):
            continue
        comp = getattr(model, family)
        values = [pyo.value(comp[idx]) for idx in comp]
        n_frac = sum(1 for v in values if 0.01 < v < 0.99)
        fractionality[family] = {
            "n_total": len(values), "n_fractional": n_frac,
            "fraction": round(n_frac / len(values), 4) if values else 0.0,
        }

    ratio = (lp_result.objective_value / ceiling) if (lp_result.objective_value and ceiling) else None

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "n_candidates": len(candidates),
        "build_time_sec": round(build_time_sec, 1),
        "lp_solve_time_sec": round(lp_solve_time_sec, 1),
        "lp_status": lp_result.status,
        "lp_objective_value": lp_result.objective_value,
        "theoretical_ceiling": round(ceiling, 2),
        "lp_to_ceiling_ratio": round(ratio, 4) if ratio is not None else None,
        "total_constraint_rows": total_rows,
        "row_counts_by_family": row_counts,
        "var_counts_by_family": var_counts,
        "fractionality_by_family": fractionality,
    }
    Path("runs/lp_anatomy.json").write_text(json.dumps(result, indent=2, sort_keys=True, default=str))
    print(json.dumps(result, indent=2, sort_keys=True, default=str), flush=True)
    return result


if __name__ == "__main__":
    main()

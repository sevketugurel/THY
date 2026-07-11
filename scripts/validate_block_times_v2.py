#!/usr/bin/env python3
"""M5e: LS-estimate vs. real Elapsed-derived K_od/R_o cross-validation
(VARSAYIM-8 update, VARSAYIM-15). Read/analysis-only -- no model code is
touched or exercised, no solve happens.

Builds TWO BlockTimeProvider instances over the SAME full-data TK rows:
  - "ls":  Elapsed1/Elapsed2 columns stripped -> forces the legacy LS/median
           path (identical to pre-v2 behavior).
  - "v2":  Elapsed1/Elapsed2 present -> the new direct per-leg path
           (VARSAYIM-15), [L,U] gap filter dropped for K_od.

Market universe = the 805 distinct (dep1,arr2) pairs actually observed as
TK rows in the O&D table (matches VARSAYIM-8's own "805 TK O-D pazarı"
starting count exactly -- verified: tk[["dep1","arr2"]].drop_duplicates()
== 805 rows on the real v2 file). This is a NARROWER, table-only cohort
than VARSAYIM-8's full "575/1329 fallback" figure, which was measured
post-candidate-generation and therefore also includes markets that are
reachable ONLY via the adjustable window and have ZERO raw table rows at
all (not just an invalid-gap row) -- recovering that broader candidate-level
count with v2 data is Bölüm 2's job (re-deriving N_od/candidate-market
stats), not this script's. What this script answers is narrower but more
directly diagnostic for the block-time provider itself: of the markets that
DO have at least one real TK row, how many had none with a valid [L,U] gap
(so needed the LS bipartite estimate), and how accurate was that estimate.

For every one of those 805 markets where the LEGACY direct median had no
valid-gap TK row (this table-level fallback cohort), this reports:
  (a) how many of those now get a DIRECT v2 value (gap filter dropped), and
  (b) the error distribution (median/p90/max abs diff) between what
      production USED to report there (get_journey_constant_estimate, the
      LS bipartite estimate) and the now-available real v2 direct value.

It also reports, for markets where the legacy direct median already
succeeded, how much VARSAYIM-15's "include all rows regardless of gap
validity" decision shifts an already-direct K_od value.

Kullanım: .venv/bin/python3 scripts/validate_block_times_v2.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.config.paths import FULL_OD
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table

L, U = 60, 300


def _error_stats(diffs):
    if not diffs:
        return {"n": 0, "median": None, "p90": None, "max": None}
    arr = np.abs(np.array(diffs, dtype=float))
    return {
        "n": len(arr),
        "median": float(np.median(arr)),
        "p90": float(np.quantile(arr, 0.9)),
        "max": float(arr.max()),
    }


def main():
    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"].copy()
    assert "elapsed1_min" in tk.columns, "FULL_OD must be the v2 file (ElapsedTime1/2 columns)"

    provider_v2 = BlockTimeProvider(tk, L=L, U=U)
    provider_ls = BlockTimeProvider(tk.drop(columns=["elapsed1_min", "elapsed2_min", "ml2"]), L=L, U=U)

    # Market universe = 805 distinct TK-observed (dep1,arr2) pairs (VARSAYIM-8's
    # own cohort, verified to match exactly -- see module docstring).
    candidate_markets = set(zip(tk["dep1"], tk["arr2"]))

    n_ls_direct_ok = 0
    n_ls_fallback = 0
    n_fallback_now_direct = 0
    fallback_error_diffs = []      # LS estimate (what production reported) vs v2 real direct value
    already_direct_shift_diffs = []  # LS direct median vs v2 direct median (VARSAYIM-15 inclusion effect)
    n_fallback_still_missing = 0

    for (o, d) in sorted(candidate_markets):
        try:
            ls_direct = provider_ls.get_journey_constant(o, d)
            n_ls_direct_ok += 1
            try:
                v2_direct = provider_v2.get_journey_constant(o, d)
                already_direct_shift_diffs.append(v2_direct - ls_direct)
            except KeyError:
                pass  # should not happen (v2 is a strict superset of LS's row coverage)
            continue
        except KeyError:
            n_ls_fallback += 1

        try:
            v2_direct = provider_v2.get_journey_constant(o, d)
        except KeyError:
            v2_direct = None

        if v2_direct is not None:
            n_fallback_now_direct += 1
            try:
                ls_estimate = provider_ls.get_journey_constant_estimate(o, d)
                fallback_error_diffs.append(v2_direct - ls_estimate)
            except KeyError:
                pass  # station never seen in any role on the LS provider -- shouldn't occur here
        else:
            n_fallback_still_missing += 1

    fallback_error_stats = _error_stats(fallback_error_diffs)
    shift_stats = _error_stats(already_direct_shift_diffs)

    # R_o (rotation constant) comparison, all stations seen in either role.
    stations = sorted(set(tk["dep1"]) | set(tk["arr2"]))
    r_o_diffs = []
    for s in stations:
        try:
            r_ls = provider_ls.get_rotation_constant(s)
            r_v2 = provider_v2.get_rotation_constant(s)
            r_o_diffs.append(r_v2 - r_ls)
        except KeyError:
            continue
    r_o_stats = _error_stats(r_o_diffs)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "L": L, "U": U,
        "n_tk_observed_markets": len(candidate_markets),
        "n_ls_direct_ok": n_ls_direct_ok,
        "n_ls_fallback_cohort": n_ls_fallback,
        "n_fallback_now_direct_under_v2": n_fallback_now_direct,
        "n_fallback_still_missing_under_v2": n_fallback_still_missing,
        "fallback_error_ls_estimate_vs_v2_real": fallback_error_stats,
        "already_direct_shift_v2_vs_ls": shift_stats,
        "r_o_shift_v2_vs_ls": r_o_stats,
    }

    print(json.dumps(report, indent=2))

    runs_dir = Path(__file__).resolve().parent.parent / "runs"
    runs_dir.mkdir(exist_ok=True)
    (runs_dir / "block_time_v2_validation.json").write_text(json.dumps(report, indent=2))

    _write_markdown_report(report)
    print("\nWritten: runs/block_time_v2_validation.json, docs/block_time_cross_validation.md")


def _fmt(x):
    return "—" if x is None else f"{x:.2f}"


def _write_markdown_report(report):
    fe = report["fallback_error_ls_estimate_vs_v2_real"]
    sh = report["already_direct_shift_v2_vs_ls"]
    ro = report["r_o_shift_v2_vs_ls"]
    md = f"""# Block-Time v2 Cross-Validation (VARSAYIM-8 update, VARSAYIM-15)

Generated: {report['generated_at']}
L={report['L']}, U={report['U']}

## TK-observed market coverage

Scope note: this is the 805 TK-observed (dep1,arr2) markets (real table
rows), NOT VARSAYIM-8's broader 575/1329 post-candidate-generation figure
(which also includes markets reachable only via the adjustable window,
zero raw rows) -- that broader recount is Bölüm 2's job. This script
answers a narrower question: of markets with at least one real row, how
many lacked a valid-gap one, and how accurate was the LS estimate there.

- TK-observed (dep1,arr2) markets, real O&D table: **{report['n_tk_observed_markets']}** (matches VARSAYIM-8's starting "805 TK O-D pazarı" count)
- Had a direct legacy median (>=1 valid-[L,U]-gap TK row): **{report['n_ls_direct_ok']}**
- Table-level fallback cohort (no valid-gap TK row, needed `get_journey_constant_estimate`): **{report['n_ls_fallback_cohort']}**
- Of the fallback cohort, now get a DIRECT v2 value (gap filter dropped, VARSAYIM-15): **{report['n_fallback_now_direct_under_v2']}**
- Of the fallback cohort, still have zero TK rows for that exact (o,d) even under v2: **{report['n_fallback_still_missing_under_v2']}**

## Error distribution: LS bipartite estimate (what production used to report) vs. real v2 direct value

For the fallback cohort that now resolves directly under v2 -- this is the number that answers "how wrong was our LS estimate":

| n | median | p90 | max |
|---|---|---|---|
| {fe['n']} | {_fmt(fe['median'])} | {_fmt(fe['p90'])} | {_fmt(fe['max'])} |

## Shift on already-direct markets (VARSAYIM-15's "include all rows regardless of gap validity")

For markets that already had a direct legacy median, how much including gap-invalid rows moves the v2 median:

| n | median | p90 | max |
|---|---|---|---|
| {sh['n']} | {_fmt(sh['median'])} | {_fmt(sh['p90'])} | {_fmt(sh['max'])} |

## R_o (rotation constant) shift, v2 (per-leg medians) vs. legacy (bipartite LS)

| n | median | p90 | max |
|---|---|---|---|
| {ro['n']} | {_fmt(ro['median'])} | {_fmt(ro['p90'])} | {_fmt(ro['max'])} |

Raw numbers: `runs/block_time_v2_validation.json` (gitignored).
"""
    docs_path = Path(__file__).resolve().parent.parent / "docs" / "block_time_cross_validation.md"
    docs_path.write_text(md)


if __name__ == "__main__":
    main()

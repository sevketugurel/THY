# Block-Time v2 Cross-Validation (VARSAYIM-8 update, VARSAYIM-15)

Generated: 2026-07-11T14:10:28.301052+00:00
L=60, U=300

## TK-observed market coverage

Scope note: this is the 805 TK-observed (dep1,arr2) markets (real table
rows), NOT VARSAYIM-8's broader 575/1329 post-candidate-generation figure
(which also includes markets reachable only via the adjustable window,
zero raw rows) -- that broader recount is Bölüm 2's job. This script
answers a narrower question: of markets with at least one real row, how
many lacked a valid-gap one, and how accurate was the LS estimate there.

- TK-observed (dep1,arr2) markets, real O&D table: **805** (matches VARSAYIM-8's starting "805 TK O-D pazarı" count)
- Had a direct legacy median (>=1 valid-[L,U]-gap TK row): **780**
- Table-level fallback cohort (no valid-gap TK row, needed `get_journey_constant_estimate`): **25**
- Of the fallback cohort, now get a DIRECT v2 value (gap filter dropped, VARSAYIM-15): **25**
- Of the fallback cohort, still have zero TK rows for that exact (o,d) even under v2: **0**

## Error distribution: LS bipartite estimate (what production used to report) vs. real v2 direct value

For the fallback cohort that now resolves directly under v2 -- this is the number that answers "how wrong was our LS estimate":

| n | median | p90 | max |
|---|---|---|---|
| 23 | 1.28 | 6.72 | 124.11 |

## Shift on already-direct markets (VARSAYIM-15's "include all rows regardless of gap validity")

For markets that already had a direct legacy median, how much including gap-invalid rows moves the v2 median:

| n | median | p90 | max |
|---|---|---|---|
| 780 | 0.00 | 0.00 | 80.00 |

## R_o (rotation constant) shift, v2 (per-leg medians) vs. legacy (bipartite LS)

| n | median | p90 | max |
|---|---|---|---|
| 258 | 1.77 | 9.22 | 1142.18 |

Raw numbers: `runs/block_time_v2_validation.json` (gitignored).

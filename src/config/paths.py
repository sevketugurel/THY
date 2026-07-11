"""Single source of truth for the 4 full-data input file paths.

Previously duplicated verbatim (with the stale "(1)" suffix) across 19
files (main.py + 17 scripts/*.py + tests/slow/test_r_o_sanity.py) --
consolidated here so a data-file rename (M5e, veri v2) only needs one edit.
"""

FULL_OD = "data_raw/O&D Rakip Bağlantı Tablosu.xlsx"  # "(1)" dropped, veri v2 (docs/decisions.md 2026-07-11)
FULL_YV = "data_raw/Yolcu Verisi_masked.xlsx"
FULL_CR = "data_raw/change_ranking_input.xlsx"
FULL_FP = "data_raw/Flight Pairs.xlsx"

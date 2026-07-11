"""Schema-validated readers for the 4 competition input files.

Each loader normalizes columns to snake_case and asserts the invariants observed
in the real data (see plan §2.1). Violations raise SchemaError with a message
naming the offending field, per the "anlamlı hata mesajıyla düşer" requirement.
"""
import logging
from pathlib import Path

import pandas as pd

from src.data.elapsed_parser import parse_elapsed_minutes, wrap_corrected_journey_minutes


class SchemaError(ValueError):
    """Raised when an input file violates an expected schema invariant."""


def _minutes(value) -> int:
    """Convert a datetime.time / datetime.timedelta duration to integer minutes."""
    if hasattr(value, "hour"):
        return value.hour * 60 + value.minute
    total_seconds = value.total_seconds()
    return int(round(total_seconds / 60))


def load_od_table(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    has_elapsed = "ElapsedTime1" in df.columns

    rename_map = {
        "Cr1": "cr1", "Carrier Name": "carrier_name", "Dep1": "dep1", "Arr1": "arr1",
        "FlNo1": "flno1", "Arr Time": "arr_time", "Cr2": "cr2", "Dep2": "dep2",
        "Arr2": "arr2", "FlNo2": "flno2", "Dep Time": "dep_time",
        "Gate-to-Gate Uçuş Süresi": "gate_to_gate_min", "O&D": "od", "Gün": "gun",
    }
    if has_elapsed:
        rename_map.update({
            "ElapsedTime1": "elapsed1_raw", "ElapsedTime2": "elapsed2_raw", "ML2": "ml2",
        })
    df = df.rename(columns=rename_map)

    mismatch = df[df.cr1 != df.cr2]
    if len(mismatch):
        raise SchemaError(f"Cr1 != Cr2 in {len(mismatch)} row(s); interline rows are not supported")

    mismatch = df[df.dep2 != df.arr1]
    if len(mismatch):
        raise SchemaError(f"Dep2 != Arr1 (hub inconsistency) in {len(mismatch)} row(s)")

    bad_gun = df[~df.gun.isin(range(1, 8))]
    if len(bad_gun):
        raise SchemaError(f"Gün outside 1..7 in {len(bad_gun)} row(s)")

    df["flno1"] = df["flno1"].astype(int)
    df["flno2"] = df["flno2"].astype(int)

    columns = ["cr1", "carrier_name", "dep1", "arr1", "flno1", "arr_time",
               "cr2", "dep2", "arr2", "flno2", "dep_time",
               "gate_to_gate_min", "od", "gun"]

    if has_elapsed:
        # Wrap-fix (VARSAYIM-14, docs/decisions.md 2026-07-11 M5e entry): the
        # displayed Gate-to-Gate field is a single Excel time-of-day cell that
        # silently wraps mod 1440 once the true multi-leg journey reaches 24h.
        # gap_min is already wrap-safe (dep_time/arr_time are full pd.Timestamps
        # with dates), so recomposing from elapsed1+gap+elapsed2 is exact --
        # applied unconditionally since the two formulas agree for every
        # non-wrapped row too (proven against the real file, 0 exceptions).
        gap_min = (df["dep_time"] - df["arr_time"]).dt.total_seconds() / 60
        elapsed1_min = df["elapsed1_raw"].apply(parse_elapsed_minutes)
        elapsed2_min = df["elapsed2_raw"].apply(parse_elapsed_minutes)
        df["gate_to_gate_min"] = [
            wrap_corrected_journey_minutes(e1, gap, e2)
            for e1, gap, e2 in zip(elapsed1_min, gap_min, elapsed2_min)
        ]
        df["elapsed1_min"] = elapsed1_min
        df["elapsed2_min"] = elapsed2_min
        columns = columns + ["elapsed1_min", "elapsed2_min", "ml2"]
    else:
        df["gate_to_gate_min"] = df["gate_to_gate_min"].apply(_minutes)

    return df[columns]


def load_yolcu_verisi(path: Path, strict: bool = True) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    df = df.rename(columns={
        "Orig Airport Code": "orig", "Dest Airport Code": "dest",
        "OD importance factor": "rho",
    })

    missing = df[df.orig.isna() | df.dest.isna()]
    if len(missing):
        if strict:
            raise SchemaError(f"orig/dest missing in {len(missing)} row(s)")
        # M5 VARSAYIM-2 (ASSUMPTIONS.md): organizer clarification pending
        # (Kayıt & Soru-Cevap penceresi 2026-07-16'ya kadar açık); dropping
        # loudly (not silently) is the pre-planned fallback so --full-data can
        # actually run before the deadline. rho values are non-trivial
        # (356-931) -- this is a LOGGED, visible decision, not a silent one.
        logging.warning(
            "load_yolcu_verisi: dropping %d row(s) with missing orig/dest "
            "(strict=False, VARSAYIM-2): %s",
            len(missing), missing[["orig", "dest", "rho"]].to_dict("records"),
        )
        df = df[~(df.orig.isna() | df.dest.isna())]

    # Real full-data file has ~12 duplicate (orig,dest) rows (confirmed by inspection);
    # treated as split rho contributions for the same market and summed.
    df = df.groupby(["orig", "dest"], as_index=False)["rho"].sum()

    bad = df[df.rho <= 0]
    if len(bad):
        raise SchemaError(f"rho must be positive; {len(bad)} row(s) violate this")

    return df[["orig", "dest", "rho"]]


def load_change_ranking(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    df = df.rename(columns={
        "Rakip Sayısı": "n", "İlk Rank": "b", "Son Rank": "r", "Weight": "weight",
    })

    dupes = df[df.duplicated(subset=["n", "b", "r"], keep=False)]
    if len(dupes):
        raise SchemaError(f"(n,b,r) must be unique; {len(dupes)} duplicate row(s) found")

    bad = df[(df.b < 1) | (df.b > df.n) | (df.r < 1) | (df.r > df.n)]
    if len(bad):
        raise SchemaError(f"rank (b or r) must be within [1,n]; {len(bad)} row(s) violate this")

    return df[["n", "b", "r", "weight"]]


def load_flight_pairs(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    df = df.rename(columns={
        "FlNo": "flno", "Orig": "orig", "Dest": "dest", "Pair": "pair",
    })
    df["flno"] = df["flno"].astype(str).str.strip().astype(int)
    return df[["flno", "orig", "dest", "pair"]]

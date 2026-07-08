"""Schema-validated readers for the 4 competition input files.

Each loader normalizes columns to snake_case and asserts the invariants observed
in the real data (see plan §2.1). Violations raise SchemaError with a message
naming the offending field, per the "anlamlı hata mesajıyla düşer" requirement.
"""
from pathlib import Path

import pandas as pd


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
    df = df.rename(columns={
        "Cr1": "cr1", "Carrier Name": "carrier_name", "Dep1": "dep1", "Arr1": "arr1",
        "FlNo1": "flno1", "Arr Time": "arr_time", "Cr2": "cr2", "Dep2": "dep2",
        "Arr2": "arr2", "FlNo2": "flno2", "Dep Time": "dep_time",
        "Gate-to-Gate Uçuş Süresi": "gate_to_gate_min", "O&D": "od", "Gün": "gun",
    })

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
    df["gate_to_gate_min"] = df["gate_to_gate_min"].apply(_minutes)

    return df[["cr1", "carrier_name", "dep1", "arr1", "flno1", "arr_time",
               "cr2", "dep2", "arr2", "flno2", "dep_time",
               "gate_to_gate_min", "od", "gun"]]


def load_yolcu_verisi(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    df = df.rename(columns={
        "Orig Airport Code": "orig", "Dest Airport Code": "dest",
        "OD importance factor": "rho",
    })

    missing = df[df.orig.isna() | df.dest.isna()]
    if len(missing):
        raise SchemaError(f"orig/dest missing in {len(missing)} row(s)")

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

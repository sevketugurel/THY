"""Candidate connection generation: TK inbound x outbound cross-product per (o,d,gun),
filtered by the [L,U] connection-gap feasibility gate (Modül-3 kapı 1, plan §4).

Since IST times are adjustable, the valid candidate set is not limited to the specific
inbound/outbound pairings already present in the O&D table -- any inbound leg landing
at IST and any outbound leg departing IST for the same day is a potential candidate.
"""
from dataclasses import dataclass
from itertools import product

import pandas as pd


@dataclass(frozen=True)
class Candidate:
    od: str
    o: str
    d: str
    gun: int
    flno1: int
    flno2: int
    arr_time: pd.Timestamp
    dep_time: pd.Timestamp
    gap_min: int


def generate_candidates(tk_rows: pd.DataFrame, L: int, U: int, gun: int) -> list[Candidate]:
    gun = int(gun)
    day_rows = tk_rows[tk_rows["gun"] == gun]

    inbound = day_rows[["dep1", "flno1", "arr_time"]].drop_duplicates(subset=["dep1", "flno1"])
    outbound = day_rows[["arr2", "flno2", "dep_time"]].drop_duplicates(subset=["arr2", "flno2"])

    candidates = []
    for (_, ib), (_, ob) in product(inbound.iterrows(), outbound.iterrows()):
        o, d = ib["dep1"], ob["arr2"]
        if o == d:
            continue
        gap_min = int((ob["dep_time"] - ib["arr_time"]).total_seconds() // 60)
        if not (L <= gap_min <= U):
            continue
        candidates.append(Candidate(
            od=f"{o}-{d}", o=o, d=d, gun=gun,
            flno1=int(ib["flno1"]), flno2=int(ob["flno2"]),
            arr_time=ib["arr_time"], dep_time=ob["dep_time"],
            gap_min=gap_min,
        ))
    return candidates

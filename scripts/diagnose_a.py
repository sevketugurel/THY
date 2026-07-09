#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.loaders import load_od_table, load_flight_pairs
from src.data.block_times import BlockTimeProvider
from src.candidates.generate import compute_epoch_anchor
from src.model.constraints_operations import build_rotation_pairs

L, U = 60, 300
TAU = 45
WINDOW = 180

od_table = load_od_table("data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx")
tk = od_table[od_table.cr1 == "TK"]
pairs_df = load_flight_pairs("data_raw/Flight Pairs.xlsx")
anchor = compute_epoch_anchor(tk)
provider = BlockTimeProvider(tk, L=L, U=U)

def epoch_min(ts):
    return int((ts - anchor).total_seconds() // 60)

# Build baseline lookup: (role, flno, gun) -> epoch time
ib_baseline = {}
ob_baseline = {}
for row in tk.itertuples():
    ib_baseline[(int(row.flno1), int(row.gun))] = epoch_min(row.arr_time)
    ob_baseline[(int(row.flno2), int(row.gun))] = epoch_min(row.dep_time)

# Replicate build_rotation_pairs' sub-pair extraction directly from pairs_df
worst = []
for _, group in pairs_df.groupby("pair"):
    rows = group.to_dict("records")
    for i in range(len(rows) - 1):
        leg1, leg2 = rows[i], rows[i + 1]
        if leg1["orig"] != "IST" or leg2["dest"] != "IST" or leg1["dest"] != leg2["orig"]:
            continue
        station = leg1["dest"]
        ob_flno, ib_flno = leg1["flno"], leg2["flno"]
        try:
            r_o = provider.get_rotation_constant(station)
        except KeyError:
            continue
        # find common guns
        ob_guns = set(g for (f, g) in ob_baseline if f == ob_flno)
        ib_guns = set(g for (f, g) in ib_baseline if f == ib_flno)
        for gun in ob_guns & ib_guns:
            dep_b = ob_baseline[(ob_flno, gun)]
            arr_b = ib_baseline[(ib_flno, gun)]
            slack = (arr_b + WINDOW) - ((dep_b - WINDOW) + r_o + TAU)
            if slack < 0:
                worst.append((slack, station, ob_flno, ib_flno, gun, r_o, dep_b, arr_b))

worst.sort()
print(f"Total unreconcilable rotation pairs: {len(worst)}")
for w in worst[:15]:
    print(w)

#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.loaders import load_od_table, load_flight_pairs
from src.data.block_times import BlockTimeProvider
from src.candidates.generate import compute_epoch_anchor

L, U = 60, 300
TAU = 45

od_table = load_od_table("data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx")
tk = od_table[od_table.cr1 == "TK"]
pairs_df = load_flight_pairs("data_raw/Flight Pairs.xlsx")
anchor = compute_epoch_anchor(tk)
provider = BlockTimeProvider(tk, L=L, U=U)

def epoch_min(ts):
    return int((ts - anchor).total_seconds() // 60)

# KUL example: ob_flno=174, ib_flno=175, gun=1. Look at ALL guns each flies.
for flno in [174, 175]:
    rows1 = tk[tk.flno1 == flno][["flno1","gun","arr_time"]]
    rows2 = tk[tk.flno2 == flno][["flno2","gun","dep_time"]]
    print(f"flno={flno} as IB(flno1):")
    print(rows1.to_string())
    print(f"flno={flno} as OB(flno2):")
    print(rows2.to_string())
    print()

r_o_kul = provider.get_rotation_constant("KUL")
print("R_o(KUL) =", r_o_kul, "minutes =", r_o_kul/60, "hours")

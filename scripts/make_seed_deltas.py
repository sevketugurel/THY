"""Convert the best known full-data run into portable baseline deltas."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.benchmark.times import build_baseline_times
from src.candidates.generate import compute_epoch_anchor
from src.config.paths import FULL_OD
from src.data.loaders import load_od_table
from src.data.provenance import file_provenance


MANUAL_REPAIRS = [
    {
        "role": "IB",
        "flno": 2845,
        "gun": 3,
        "delta_min": 10,
        "reason": "A micro-repair: TK2844 -> TK2845 rotation was 10 minutes short",
    },
    {
        "role": "IB",
        "flno": 2845,
        "gun": 5,
        "delta_min": 10,
        "reason": "A micro-repair: TK2844 -> TK2845 rotation was 10 minutes short",
    },
    {
        "role": "IB",
        "flno": 2845,
        "gun": 7,
        "delta_min": 10,
        "reason": "A micro-repair: TK2844 -> TK2845 rotation was 10 minutes short",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="runs/lns_best_partial_20260712T150223Z.json")
    parser.add_argument("--output", default="data_seed/full_data_best_deltas.json")
    args = parser.parse_args()

    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    anchor = compute_epoch_anchor(tk)
    baseline = build_baseline_times(tk, anchor)

    source = json.loads(Path(args.source).read_text())
    source_times = {
        (entry["role"], int(entry["flno"]), int(entry["gun"])): int(entry["time_min"])
        for entry in source["adjusted_flight_times"]
    }

    applied_repairs = []
    for repair in MANUAL_REPAIRS:
        key = (repair["role"], int(repair["flno"]), int(repair["gun"]))
        if key not in baseline:
            raise KeyError(f"manual repair target not in baseline: {key}")
        before = source_times.get(key, baseline[key])
        after = before + int(repair["delta_min"])
        source_times[key] = after
        applied_repairs.append({**repair, "before_time_min": before, "after_time_min": after})

    deltas = []
    missing = 0
    max_abs = 0
    for key, time_min in source_times.items():
        if key not in baseline:
            missing += 1
            continue
        delta_min = int(time_min) - baseline[key]
        if delta_min == 0:
            continue
        deltas.append({"role": key[0], "flno": key[1], "gun": key[2], "delta_min": delta_min})
        max_abs = max(max_abs, abs(delta_min))
    deltas.sort(key=lambda d: (d["role"], d["flno"], d["gun"]))

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_run": args.source,
        "source_campaign": "M5h/M5i elastik+LNS en iyi noktası (Sigma slack=10944)",
        "data_provenance": {"FULL_OD": file_provenance(FULL_OD)},
        "n_deltas": len(deltas),
        "n_source_entries_not_in_baseline": missing,
        "max_abs_delta_min": max_abs,
        "manual_repairs": applied_repairs,
        "deltas": deltas,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(
        f"wrote {output}: n_deltas={len(deltas)} missing={missing} "
        f"max_abs={max_abs} manual_repairs={len(applied_repairs)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

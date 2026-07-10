#!/usr/bin/env python3
"""M5c (docs/decisions.md 2026-07-10, user's branch-2 redirect after the
static E1/E2 certificates came back clean): a pure-Python greedy repair --
NO MIP, NO HiGHS -- that starts from the raw baseline schedule and uses the
INDEPENDENT VALIDATOR itself as the oracle, iteratively patching violations:

    A (rotation):  delay the connecting arrival (push t_arr later, clamped
                    to its own adjustable window) until the R_o+tau minimum
                    is met.
    F (capacity):  shift an overflowing bucket's least-constrained occupant
                    to a neighboring bucket (still within its own window).
    E1/E2:         "kill" a KILLABLE offered connection on the
                    over-represented/extreme side -- killable means its
                    forced_status (scripts/feasibility_certificates.py) is
                    "undetermined", i.e. NOT structurally forced-on by B's
                    reification, so its own window has enough slack to push
                    gap outside [L,U] and turn x from 1 to 0.

If the validator ever reports zero violations, the current (t_arr,t_dep)
state IS a feasibility witness -- written out as a real output.json
(recompute+validate confirm it independently) and usable as a warm-start /
local-branching seed for the full MIP, no Gurobi needed. If repair stalls
(violation count stops decreasing), the remaining violations ARE the
diagnosis -- dumped verbatim, no further guessing.

Kullanım: .venv/bin/python3 -u scripts/greedy_feasibility_witness.py
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.solve.runner import SolveResult
from src.output.writer import write_output
from src.validate.independent_validator import recompute_objective, validate_output

FULL_OD = "data_raw/O&D Rakip Bağlantı Tablosu (1).xlsx"
FULL_YV = "data_raw/Yolcu Verisi_masked.xlsx"
FULL_CR = "data_raw/change_ranking_input.xlsx"
FULL_FP = "data_raw/Flight Pairs.xlsx"
MAX_ITERATIONS = 40

_RE_A = re.compile(
    r"rotation FlNo\(OB\)=(\d+) Gün=(\d+) FlNo\(IB\)=(\d+) Gün=(\d+): "
    r"IST arrival (-?\d+) < required minimum (-?\d+)"
)
_RE_F = re.compile(r"F kova\((departure|arrival)\) bucket=(-?\d+): (\d+) uçuş, kalan kapasite (\d+)")
_RE_E1 = re.compile(r"E1 (\S+)-(\S+) Gün=(\d+): \|n_fwd\((\d+)\)-n_bwd\((\d+)\)\|")
_RE_E2 = re.compile(r"E2 (\S+)-(\S+) Gün=(\d+): \|Jbest_fwd\((-?\d+)\)-Jbest_bwd\((-?\d+)\)\|")


def forced_status(gap_lo, gap_hi, L, U):
    if gap_lo >= L and gap_hi <= U:
        return "on"
    if gap_hi < L or gap_lo > U:
        return "off"
    return "undetermined"


def try_kill(c, t, bounds, L, U):
    """Push candidate c's gap outside [L,U] by moving whichever leg has
    slack toward whichever boundary needs the LEAST movement. Returns True
    (and mutates t in place) on success, False if no leg has enough room."""
    arr_lo, arr_hi = bounds[c.r1_id]
    dep_lo, dep_hi = bounds[c.r2_id]
    gap = t[c.r2_id] - t[c.r1_id]
    options = []
    # push below L: increase t_arr (gap shrinks) or decrease t_dep
    need = (gap - L) + 1
    if need > 0:
        options.append((need, "arr", +need, arr_hi - t[c.r1_id]))
        options.append((need, "dep", -need, t[c.r2_id] - dep_lo))
    # push above U: decrease t_arr (gap grows) or increase t_dep
    need = (U - gap) + 1
    if need > 0:
        options.append((need, "arr", -need, t[c.r1_id] - arr_lo))
        options.append((need, "dep", +need, dep_hi - t[c.r2_id]))
    options = [o for o in options if o[3] >= abs(o[2])]
    if not options:
        return False
    options.sort(key=lambda o: o[0])
    _, leg, delta, _ = options[0]
    if leg == "arr":
        t[c.r1_id] += delta
    else:
        t[c.r2_id] += delta
    return True


def main():
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]
    alpha, gamma = config["alpha"], config["gamma"]
    tau, x_dev = config["tau"], config["X_dev"]
    bucket_size_min = config["bucket_size_min"]
    cap_dep, cap_arr = config["capacity_departure"], config["capacity_arrival"]
    window = config["adjustable_window_min"]

    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FULL_YV, strict=False)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    pairs_df = load_flight_pairs(FULL_FP)
    anchor = compute_epoch_anchor(tk)

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=window,
            adjustable_set=config["adjustable_set"], epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]
    print(f"[greedy] n_candidates={len(candidates)}", flush=True)

    bounds = {}
    for c in candidates:
        bounds[c.r1_id] = (c.arr_lo, c.arr_hi)
        bounds[c.r2_id] = (c.dep_lo, c.dep_hi)

    # baseline start: window midpoint == the raw baseline flight time
    # (window is symmetric around it, by construction).
    t = {r: (lo + hi) // 2 for r, (lo, hi) in bounds.items()}

    status = {i: forced_status(c.gap_lo, c.gap_hi, L, U) for i, c in enumerate(candidates)}

    prev_violation_count = None
    for it in range(1, MAX_ITERATIONS + 1):
        selected = {}
        gap_values = {}
        for i, c in enumerate(candidates):
            gap = t[c.r2_id] - t[c.r1_id]
            gap_values[c] = gap
            selected[c] = 1 if L <= gap <= U else 0

        result = SolveResult(
            status="optimal", objective_value=0.0, selected=selected,
            solve_time_sec=0.0, gap_values=gap_values,
            arr_times={r: v for r, v in t.items() if r[0] == "IB"},
            dep_times={r: v for r, v in t.items() if r[0] == "OB"},
        )
        out_path = Path("runs/greedy_witness_iter.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_output(out_path, result)

        validation = validate_output(
            out_path, FULL_OD, L=L, U=U, adjustable_window_min=window,
            adjustable_set=config["adjustable_set"], flight_pairs_path=FULL_FP,
            tau=tau, x_dev=x_dev, alpha=alpha, gamma=gamma,
            bucket_size_min=bucket_size_min, capacity_departure=cap_dep, capacity_arrival=cap_arr,
        )
        n_viol = len(validation.violations)
        by_family = defaultdict(int)
        for v in validation.violations:
            by_family[v.split(" ", 1)[0]] += 1
        print(f"[greedy] iter={it} violations={n_viol} by_family={dict(by_family)}", flush=True)

        if validation.is_valid:
            print("[greedy] SUCCESS -- zero violations, feasibility witness found", flush=True)
            recompute_total, _ = recompute_objective(
                out_path, FULL_OD, FULL_YV, FULL_CR, L=L, U=U,
                breakdown_path=out_path.with_suffix(".objective_breakdown.json"),
            )
            print(f"[greedy] reward_objective_at_witness={recompute_total}", flush=True)
            final_path = Path("runs/greedy_witness_output.json")
            write_output(final_path, result)
            print(f"[greedy] witness written to {final_path}", flush=True)
            return

        if prev_violation_count is not None and n_viol >= prev_violation_count:
            print(f"[greedy] STALLED -- violation count did not decrease "
                  f"({prev_violation_count} -> {n_viol}). Remaining violations:", flush=True)
            for v in validation.violations[:60]:
                print(f"  STUCK: {v}", flush=True)
            stuck_path = Path("runs/greedy_witness_stuck.json")
            stuck_path.write_text(json.dumps({
                "iteration": it, "violation_count": n_viol,
                "violations_by_family": dict(by_family), "violations": validation.violations,
            }, indent=2, default=str))
            print(f"[greedy] full stuck dump: {stuck_path}", flush=True)
            return
        prev_violation_count = n_viol

        # --- apply fixes, batched over this iteration's violations ---
        for v in validation.violations:
            m = _RE_A.match(v)
            if m:
                ob_flno, ob_gun, ib_flno, ib_gun, actual, required = (
                    int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)),
                    int(m.group(5)), int(m.group(6)),
                )
                arr_key = ("IB", ib_flno, ib_gun)
                lo, hi = bounds[arr_key]
                t[arr_key] = min(hi, t[arr_key] + (required - actual))
                continue
            m = _RE_F.match(v)
            if m:
                direction, bucket, count, cap = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
                overflow = count - cap
                role = "OB" if direction == "departure" else "IB"
                occupants = [r for r in t if r[0] == role and t[r] // bucket_size_min == bucket]
                moved = 0
                for r in occupants:
                    if moved >= overflow:
                        break
                    lo, hi = bounds[r]
                    for neighbor in ((bucket + 1) * bucket_size_min, (bucket - 1) * bucket_size_min + bucket_size_min - 1):
                        if lo <= neighbor <= hi and neighbor // bucket_size_min != bucket:
                            t[r] = neighbor
                            moved += 1
                            break
                continue
            m = _RE_E1.match(v)
            if m:
                o, d, gun, n_fwd, n_bwd = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5))
                over_o, over_d = (o, d) if n_fwd > n_bwd else (d, o)
                killable = [
                    (i, c) for i, c in enumerate(candidates)
                    if c.o == over_o and c.d == over_d and c.gun == gun
                    and status[i] == "undetermined" and L <= (t[c.r2_id] - t[c.r1_id]) <= U
                ]
                excess = abs(n_fwd - n_bwd)
                n_kill = max(1, excess // 2)
                for _, c in killable[:n_kill]:
                    try_kill(c, t, bounds, L, U)
                continue
            m = _RE_E2.match(v)
            if m:
                o, d, gun, jbest_fwd, jbest_bwd = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5))
                extreme_o, extreme_d = (o, d) if jbest_fwd > jbest_bwd else (d, o)
                offered = [
                    (i, c) for i, c in enumerate(candidates)
                    if c.o == extreme_o and c.d == extreme_d and c.gun == gun
                    and L <= (t[c.r2_id] - t[c.r1_id]) <= U
                ]
                if not offered:
                    continue
                # the argmin among offered on the extreme side
                i_min, c_min = min(offered, key=lambda ic: t[ic[1].r2_id] - t[ic[1].r1_id])
                if status[i_min] == "undetermined":
                    try_kill(c_min, t, bounds, L, U)
                continue

    print(f"[greedy] reached MAX_ITERATIONS={MAX_ITERATIONS} without convergence or stall detection", flush=True)


if __name__ == "__main__":
    main()

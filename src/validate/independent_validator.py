"""Independent feasibility validator -- deliberately does not import src.model.*
or src.candidates.*. Re-derives gap validity and legal-window membership from
raw data + the OUTPUT's own reported values, never trusting a value the solver
already computed internally (disqualification insurance, plan §1/§5). Some
logic (epoch anchor, window bounds) is intentionally duplicated from
src.candidates.generate rather than imported -- a shared bug there must not be
able to silently pass validation too.

M1 scope: B-style gap-window check now validated against the OUTPUT's own
reported adjusted times (not static baseline, since times can genuinely move),
plus a legal-window check per adjustable flight instance. A/D/E/F/G checks land
alongside their constraint groups in M2-M4.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from src.data.loaders import load_od_table


@dataclass
class ValidationResult:
    is_valid: bool
    violations: list = field(default_factory=list)


def _epoch_anchor(tk):
    return min(tk["arr_time"].min(), tk["dep_time"].min()).normalize()


def _epoch_min(ts, anchor):
    return int((ts - anchor).total_seconds() // 60)


def _baseline_bounds(tk, role, flno, gun, anchor, adjustable_window_min, adjustable_set):
    if role == "IB":
        match = tk[(tk.flno1 == flno) & (tk.gun == gun)]
        baseline_col = "arr_time"
    else:
        match = tk[(tk.flno2 == flno) & (tk.gun == gun)]
        baseline_col = "dep_time"
    if match.empty:
        return None
    baseline = _epoch_min(match.iloc[0][baseline_col], anchor)
    if adjustable_set == "all":
        return baseline - adjustable_window_min, baseline + adjustable_window_min
    return baseline, baseline


def validate_output(
    output_path: Path, od_table_path: Path, L: int, U: int,
    adjustable_window_min: int = 0, adjustable_set: str = "none",
) -> ValidationResult:
    data = json.loads(Path(output_path).read_text())
    od_table = load_od_table(od_table_path)
    tk = od_table[od_table.cr1 == "TK"]
    anchor = _epoch_anchor(tk)

    violations = []

    reported_times = {}
    for entry in data.get("adjusted_flight_times", []):
        key = (entry["role"], entry["flno"], entry["gun"])
        reported_times[key] = entry["time_min"]

        bounds = _baseline_bounds(tk, entry["role"], entry["flno"], entry["gun"],
                                   anchor, adjustable_window_min, adjustable_set)
        if bounds is None:
            violations.append(
                f"adjusted_flight_times entry role={entry['role']} FlNo={entry['flno']} "
                f"Gün={entry['gun']}: not found in raw O&D table"
            )
            continue
        lo, hi = bounds
        if not (lo <= entry["time_min"] <= hi):
            violations.append(
                f"adjusted_flight_times entry role={entry['role']} FlNo={entry['flno']} "
                f"Gün={entry['gun']}: reported time {entry['time_min']} outside legal window [{lo},{hi}]"
            )

    for conn in data["selected_connections"]:
        o, d = conn["od"].split("-")
        # Candidates are a full inbound x outbound cross-product (plan §4) --
        # a pairing never explicitly listed together as one raw row can still
        # be a legitimate candidate. Each leg must exist independently as a
        # real TK flight instance on this day (in the correct role/station),
        # not that the exact (flno1,flno2) pairing was pre-enumerated.
        inbound_exists = not tk[(tk.dep1 == o) & (tk.flno1 == conn["flno1"]) & (tk.gun == conn["gun"])].empty
        outbound_exists = not tk[(tk.arr2 == d) & (tk.flno2 == conn["flno2"]) & (tk.gun == conn["gun"])].empty
        if not (inbound_exists and outbound_exists):
            violations.append(
                f"connection {conn['od']} FlNo1={conn['flno1']} FlNo2={conn['flno2']} "
                f"Gün={conn['gun']}: not found in raw O&D table"
            )
            continue

        arr_key = ("IB", conn["flno1"], conn["gun"])
        dep_key = ("OB", conn["flno2"], conn["gun"])
        if arr_key not in reported_times or dep_key not in reported_times:
            violations.append(
                f"connection {conn['od']} FlNo1={conn['flno1']} FlNo2={conn['flno2']} "
                f"Gün={conn['gun']}: missing adjusted_flight_times entry for its legs"
            )
            continue

        actual_gap = reported_times[dep_key] - reported_times[arr_key]
        if not (L <= actual_gap <= U):
            violations.append(
                f"connection {conn['od']} FlNo1={conn['flno1']} FlNo2={conn['flno2']} "
                f"Gün={conn['gun']}: gap={actual_gap}min outside [{L},{U}]"
            )

    return ValidationResult(is_valid=not violations, violations=violations)

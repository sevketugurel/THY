"""Independent feasibility validator -- deliberately does not import src.model.*
or src.candidates.*. Re-derives gap validity, legal-window membership, and
beaten-rival/rank claims from raw data + the OUTPUT's own reported values,
never trusting a value the solver already computed internally (disqualification
insurance, plan §1/§5). Some logic (epoch anchor, window bounds) is
intentionally duplicated from src.candidates.generate rather than imported --
a shared bug there must not be able to silently pass validation too.

D-checking reuses src.data.block_times / src.data.competitors (the DATA layer,
not src.model.*/src.candidates.*) to recompute journey times and rival best
times -- this is a disclosed, narrower sharing than "zero shared code": a bug
in the block-time/rival DERIVATION itself could still slip through both the
model and the validator, but the DECISION LOGIC (which candidates get
selected, which beats get claimed) is independently re-verified.

M1: B-style gap-window check validated against the OUTPUT's own reported
adjusted times, plus a legal-window check per adjustable flight instance.
M2: beaten_rivals/rank claims re-derived and cross-checked. A/E/F/G land
alongside their constraint groups in M3-M4.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
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

    ranking_results = data.get("ranking_results", [])
    if ranking_results:
        provider = BlockTimeProvider(tk, L=L, U=U)
        offered_by_market = {}
        for conn in data["selected_connections"]:
            o, d = conn["od"].split("-")
            arr_key = ("IB", conn["flno1"], conn["gun"])
            dep_key = ("OB", conn["flno2"], conn["gun"])
            if arr_key not in reported_times or dep_key not in reported_times:
                continue
            gap = reported_times[dep_key] - reported_times[arr_key]
            try:
                journey = provider.get_journey_constant(o, d) + gap
            except KeyError:
                continue
            offered_by_market.setdefault((o, d, conn["gun"]), []).append(journey)

        for entry in ranking_results:
            market = (entry["o"], entry["d"], entry["gun"])
            rivals = derive_rival_best_times(od_table, entry["o"], entry["d"], entry["gun"])
            journeys = offered_by_market.get(market, [])
            actual_beaten = {k for k, t_comp in rivals.items() if any(j <= t_comp for j in journeys)}
            claimed_beaten = set(entry["beaten_rivals"])

            for k in claimed_beaten - actual_beaten:
                violations.append(
                    f"ranking_results {entry['o']}-{entry['d']} Gün={entry['gun']}: "
                    f"claims rival {k} beaten but no offered connection actually beats it"
                )
            # NOTE: actual_beaten - claimed_beaten (under-claiming) is deliberately
            # NOT flagged as a violation. D's beat reification is forward-only when
            # W(r) is monotonic (docs/model.md §5 D) -- this makes claimed_beaten
            # a PROVABLE SUBSET of actual_beaten (over-claiming is structurally
            # impossible, per the check above), so the reported reward can only be
            # an equal-or-lower bound on the true achievable reward, never inflated.
            # Under-claiming happens legitimately when W has a flat (tied) segment
            # (e.g. beating N-1 vs N rivals both land on r=1 -- see
            # tests/fixtures/README.md "M2 eki"); it costs nothing structurally and
            # is not a disqualifying inconsistency, only a missed reporting detail.

            # Clamped at 1 (never 0): the real change_ranking_input.xlsx table
            # never defines a reward for r=0 (min observed r is always 1 --
            # confirmed by inspection); beating ALL rivals lands on the same
            # r=1 "best available" tier as beating all-but-one. Must match
            # src/model/constraints_competition.py::add_rank_onehot's clamp
            # exactly, or a correctly-full beaten_rivals list would be
            # wrongly flagged here.
            expected_rank = max(1, len(rivals) - len(claimed_beaten)) if rivals else 0
            if entry["rank"] != expected_rank:
                violations.append(
                    f"ranking_results {entry['o']}-{entry['d']} Gün={entry['gun']}: "
                    f"claimed rank={entry['rank']} inconsistent with max(1,N({len(rivals)})"
                    f"-beaten({len(claimed_beaten)}))={expected_rank}"
                )

    return ValidationResult(is_valid=not violations, violations=violations)

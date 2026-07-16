#!/usr/bin/env python3
"""Extract full E1/E2 strict diagnostics and impacted flight instances."""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.repair_e1_e2_local import HARD_FAMILIES, RepairContext
from src.validate.independent_validator import summarize_violation_families, validate_output

E1_RE = re.compile(
    r"^E1 (?P<o>[^-]+)-(?P<d>\S+) Gün=(?P<gun>\d+): "
    r"\|n_fwd\((?P<fwd>\d+)\)-n_bwd\((?P<bwd>\d+)\)\| "
    r"exceeds alpha\((?P<alpha>[0-9.]+)\)\*\(n_fwd\+n_bwd\)$"
)
E2_RE = re.compile(
    r"^E2 (?P<o>[^-]+)-(?P<d>\S+) Gün=(?P<gun>\d+): "
    r"\|Jbest_fwd\((?P<fwd>[0-9.]+)\)-Jbest_bwd\((?P<bwd>[0-9.]+)\)\| "
    r"exceeds Gamma\((?P<gamma>[0-9.]+)\)$"
)


def _flight_key(role: str, flno: int, gun: int) -> str:
    return f"{role}:{flno}:G{gun}"


def _connections_by_market(connections: list) -> dict:
    by_market = defaultdict(list)
    for conn in connections:
        o, d = conn["od"].split("-")
        by_market[(o, d, int(conn["gun"]))].append(conn)
    return by_market


def _instances_from_connections(connections: list) -> list:
    instances = set()
    for conn in connections:
        gun = int(conn["gun"])
        instances.add(_flight_key("IB", int(conn["flno1"]), gun))
        instances.add(_flight_key("OB", int(conn["flno2"]), gun))
    return sorted(instances)


def _best_connection(ctx: RepairContext, market: tuple, connections: list) -> dict | None:
    o, d, _ = market
    k_od = ctx.market_k_od.get((o, d))
    if k_od is None:
        return None
    best = None
    best_journey = None
    for conn in connections:
        journey = k_od + int(conn["gap_min"])
        if best_journey is None or journey < best_journey:
            best = conn
            best_journey = journey
    return best


def analyze(input_path: Path, output_path: Path, config_path: Path, top: int) -> dict:
    cfg = yaml.safe_load(config_path.read_text())
    ctx = RepairContext(config_path)
    times = ctx.read_times(input_path)
    connections = ctx.build_claim(times)
    by_market = _connections_by_market(connections)

    validation = validate_output(
        input_path,
        ctx.od_path,
        L=cfg["L"],
        U=cfg["U"],
        adjustable_window_min=cfg["adjustable_window_min"],
        adjustable_set=cfg["adjustable_set"],
        flight_pairs_path=ctx.fp_path,
        tau=cfg["tau"],
        x_dev=cfg["X_dev"],
        alpha=cfg["alpha"],
        gamma=cfg["gamma"],
        bucket_size_min=cfg["bucket_size_min"],
        capacity_departure=cfg["capacity_departure"],
        capacity_arrival=cfg["capacity_arrival"],
        e1_activation=cfg.get("e1_activation", "conditional"),
    )
    families = summarize_violation_families(validation.violations)
    records = []
    flight_scores = defaultdict(lambda: {"touch_count": 0, "slack_sum": 0.0, "families": defaultdict(int)})

    for violation in validation.violations:
        family = None
        match = E1_RE.match(violation)
        if match:
            family = "E1"
            o = match.group("o")
            d = match.group("d")
            gun = int(match.group("gun"))
            n_fwd = int(match.group("fwd"))
            n_bwd = int(match.group("bwd"))
            alpha = float(match.group("alpha"))
            excess = abs(n_fwd - n_bwd) - alpha * (n_fwd + n_bwd)
            measured = {"n_fwd": n_fwd, "n_bwd": n_bwd, "alpha": alpha}
        else:
            match = E2_RE.match(violation)
            if match:
                family = "E2"
                o = match.group("o")
                d = match.group("d")
                gun = int(match.group("gun"))
                j_fwd = float(match.group("fwd"))
                j_bwd = float(match.group("bwd"))
                gamma = float(match.group("gamma"))
                excess = abs(j_fwd - j_bwd) - gamma
                measured = {"jbest_fwd": j_fwd, "jbest_bwd": j_bwd, "gamma": gamma}
        if family is None:
            continue

        fwd_market = (o, d, gun)
        bwd_market = (d, o, gun)
        related = by_market.get(fwd_market, []) + by_market.get(bwd_market, [])
        instances = _instances_from_connections(related)
        for instance in instances:
            flight_scores[instance]["touch_count"] += 1
            flight_scores[instance]["slack_sum"] += excess
            flight_scores[instance]["families"][family] += 1

        best_connections = {}
        if family == "E2":
            fwd_best = _best_connection(ctx, fwd_market, by_market.get(fwd_market, []))
            bwd_best = _best_connection(ctx, bwd_market, by_market.get(bwd_market, []))
            best_connections = {
                "fwd": fwd_best,
                "bwd": bwd_best,
            }

        records.append({
            "family": family,
            "o": o,
            "d": d,
            "gun": gun,
            "measured": measured,
            "excess": excess,
            "selected_connections": related,
            "best_connections": best_connections,
            "flight_instances": instances,
            "raw_violation": violation,
        })

    scored_flights = []
    for instance, score in flight_scores.items():
        scored_flights.append({
            "flight_instance": instance,
            "touch_count": score["touch_count"],
            "slack_sum": score["slack_sum"],
            "families": dict(score["families"]),
            "hard_family_current": [],
        })
    scored_flights.sort(key=lambda item: (-item["touch_count"], -item["slack_sum"], item["flight_instance"]))

    summary = {
        "input": str(input_path),
        "strict_counts": families["counts"],
        "hard_family_violations": sum(families["counts"].get(family, 0) for family in HARD_FAMILIES),
        "e1": families["counts"].get("E1", 0),
        "e2": families["counts"].get("E2", 0),
        "records": records,
        "flight_scores": scored_flights,
        "top_flights": scored_flights[:top],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/full_data_output.json")
    parser.add_argument("--output", default="runs/e1e2_violation_analysis.json")
    parser.add_argument("--config", default="src/config/standard.yaml")
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args(argv)

    summary = analyze(Path(args.input), Path(args.output), Path(args.config), args.top)
    print(
        f"E1={summary['e1']} E2={summary['e2']} "
        f"hard={summary['hard_family_violations']} records={len(summary['records'])} "
        f"top_flights={len(summary['top_flights'])} output={args.output}",
        flush=True,
    )
    for item in summary["top_flights"][:10]:
        print(
            f"  {item['flight_instance']} touch_count={item['touch_count']} "
            f"slack_sum={item['slack_sum']:.2f} families={item['families']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

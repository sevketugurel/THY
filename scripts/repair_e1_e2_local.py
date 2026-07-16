#!/usr/bin/env python3
"""Local E1/E2 repair attempt for the benchmark incumbent.

The script keeps the official output/package untouched while it searches. It
uses fast in-memory E1/E2/objective scoring to rank moves, then runs the full
recompute/claim/strict validation gate before accepting any candidate.
"""

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.benchmark.claim import build_full_claim, derive_market_universe, derive_ranking_from_claim
from src.benchmark.times import build_baseline_times
from src.benchmark.writer import stamp_recomputed_objective, write_benchmark_output
from src.config.paths import FULL_CR, FULL_FP, FULL_OD, FULL_YV
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_od_table, load_yolcu_verisi
from src.data.ranking import compute_baseline_best_journey, derive_b_od
from src.validate.independent_validator import (
    _epoch_anchor,
    _epoch_min,
    _is_gamma_statically_infeasible,
    recompute_objective,
    summarize_violation_families,
    validate_claim_completeness,
    validate_output,
)

HARD_FAMILIES = ("A", "B", "D", "F", "G")
E_FAMILIES = ("E1", "E2")
DELTA_SET = (-20, -15, -10, -5, 5, 10, 15, 20)
EXPANDED_DELTA_SET = (-30, -25, 25, 30)
INTERPRETATION = "strict_A_G_checked; E1_E2_reported_as_diagnostics"
BASE_NOTE = (
    "E1/E2 strict okuması altında yayınlanan baseline tarifesi de ihlallidir; "
    "bkz. docs/report.md"
)


def _build_gate_diagnostics(
    *,
    families: dict,
    claim: dict,
    strict_feasible: bool,
    moves: tuple,
    objective: float,
    dropped_markets: int,
) -> dict:
    counts = dict(families.get("counts", {}))
    examples = dict(families.get("examples", {}))
    n_violations = sum(counts.values())
    missing_claims = int(claim["missing_claims"])
    extra_claims = int(claim["extra_claims"])
    return {
        "mode": "benchmark_full_claim",
        "strict_feasible": bool(strict_feasible),
        "constraint_interpretation": INTERPRETATION,
        "claim_complete": bool(claim["claim_complete"]),
        "missing_claims": missing_claims,
        "extra_claims": extra_claims,
        "claim_check": {
            "missing_claims": missing_claims,
            "extra_claims": extra_claims,
        },
        "seed": {
            "file": None,
            "note": "local E1/E2 repair from claim-complete recompute-objective incumbent",
            "moves": [move.label() for move in moves],
        },
        "strict_violations": {
            "total": n_violations,
            "total_pairs": n_violations,
            "by_family": counts,
            "examples": examples,
        },
        "selection_priority": {
            "hard_family_violations": sum(counts.get(family, 0) for family in HARD_FAMILIES),
            "e1_e2_violations": sum(counts.get(family, 0) for family in E_FAMILIES),
            "objective": objective,
        },
        "dropped_markets_no_k_od": dropped_markets,
        "baseline_reference": None,
        "note": BASE_NOTE,
    }


def _assert_gate_consistency(
    data: dict,
    claim: dict,
    validation,
    recompute_total: float,
    families: dict | None = None,
    tolerance: float = 1e-6,
) -> None:
    families = families if families is not None else summarize_violation_families(validation.violations)
    family_counts = dict(families.get("counts", {}))
    diagnostics = data.get("diagnostics", {})
    strict_violations = diagnostics.get("strict_violations", {})
    errors = []

    def check(name: str, observed, expected) -> None:
        if observed != expected:
            errors.append(f"{name}: observed={observed!r} expected={expected!r}")

    check("diagnostics.claim_complete", diagnostics.get("claim_complete"), bool(claim["claim_complete"]))
    check("diagnostics.missing_claims", diagnostics.get("missing_claims"), int(claim["missing_claims"]))
    check("diagnostics.extra_claims", diagnostics.get("extra_claims"), int(claim["extra_claims"]))
    claim_check = diagnostics.get("claim_check", {})
    check("diagnostics.claim_check.missing_claims", claim_check.get("missing_claims"), int(claim["missing_claims"]))
    check("diagnostics.claim_check.extra_claims", claim_check.get("extra_claims"), int(claim["extra_claims"]))
    check("diagnostics.strict_feasible", diagnostics.get("strict_feasible"), bool(validation.is_valid))
    check("diagnostics.strict_violations.by_family", strict_violations.get("by_family", {}), family_counts)
    check("diagnostics.strict_violations.total", strict_violations.get("total"), sum(family_counts.values()))
    check("diagnostics.strict_violations.total_pairs", strict_violations.get("total_pairs"), sum(family_counts.values()))

    objective_value = data.get("objective_value")
    if not isinstance(objective_value, (int, float)) or not math.isclose(
        float(objective_value), recompute_total, rel_tol=0.0, abs_tol=tolerance
    ):
        errors.append(f"objective_value: observed={objective_value!r} expected={recompute_total!r}")

    if errors:
        raise RuntimeError("gate consistency failed: " + "; ".join(errors))


@dataclass(frozen=True)
class Move:
    changes: tuple

    @classmethod
    def single(cls, key: tuple, delta: int):
        return cls(((key, delta),))

    def label(self) -> str:
        parts = []
        for key, delta in self.changes:
            role, flno, gun = key
            sign = "+" if delta > 0 else ""
            parts.append(f"{role}{flno}/G{gun}{sign}{delta}")
        return "+".join(parts)


@dataclass
class Score:
    objective: float
    e1: int
    e2: int
    hard: int = 0
    claim_complete: bool = True
    missing_claims: int = 0
    extra_claims: int = 0
    strict_counts: dict = field(default_factory=dict)

    @property
    def soft(self) -> int:
        return self.e1 + self.e2

    def key(self) -> tuple:
        return (self.hard, self.soft, -self.objective)


@dataclass
class State:
    times: dict
    connections: list
    score: Score
    moves: tuple = ()


class RepairContext:
    def __init__(self, config_path: Path):
        self.config = yaml.safe_load(config_path.read_text())
        self.od_path = Path(FULL_OD)
        self.yv_path = Path(FULL_YV)
        self.cr_path = Path(FULL_CR)
        self.fp_path = Path(FULL_FP)
        self.od_table = load_od_table(self.od_path)
        self.tk = self.od_table[self.od_table.cr1 == "TK"]
        self.anchor = _epoch_anchor(self.tk)
        self.provider = BlockTimeProvider(self.tk, L=self.config["L"], U=self.config["U"])
        self.yolcu = load_yolcu_verisi(self.yv_path, strict=False)
        self.rho = {(row.orig, row.dest): row.rho for row in self.yolcu.itertuples()}
        self.market_k_od, self.dropped_markets, self.k_sources = derive_market_universe(
            self.tk,
            self.rho,
            self.provider,
        )
        ranking_table = load_change_ranking(self.cr_path)
        self.weight_lookup = {
            (row.n, row.b, row.r): row.weight
            for row in ranking_table.itertuples()
        }
        self.baseline_times = build_baseline_times(self.tk, self.anchor)
        window = self.config["adjustable_window_min"]
        self.bounds = {
            key: (value - window, value + window)
            for key, value in self.baseline_times.items()
        }
        self.regularity_groups = {}
        by_role_flno = {}
        for key in self.baseline_times:
            role, flno, _ = key
            by_role_flno.setdefault((role, flno), []).append(key)
        for keys in by_role_flno.values():
            group = tuple(sorted(keys))
            for key in group:
                self.regularity_groups[key] = group
        self.day_offsets = self._build_day_offsets()
        self.rival_cache = {}
        self.b_od_cache = {}
        self.static_e2_cache = {}
        self.best_journey_connections = {}

    @property
    def L(self) -> int:
        return self.config["L"]

    @property
    def U(self) -> int:
        return self.config["U"]

    def read_times(self, path: Path) -> dict:
        data = json.loads(path.read_text())
        return {
            (entry["role"], int(entry["flno"]), int(entry["gun"])): int(entry["time_min"])
            for entry in data.get("adjusted_flight_times", [])
        }

    def _build_day_offsets(self) -> dict:
        baseline_ts = {}
        for role, flno, gun in self.baseline_times:
            if role == "IB":
                match = self.tk[(self.tk.flno1 == flno) & (self.tk.gun == gun)]
                col = "arr_time"
            else:
                match = self.tk[(self.tk.flno2 == flno) & (self.tk.gun == gun)]
                col = "dep_time"
            if match.empty:
                continue
            baseline_ts[(role, flno, gun)] = match.iloc[0][col]

        cuts = {}
        for key, ts in baseline_ts.items():
            role, flno, _ = key
            if (role, flno) in cuts:
                continue
            tod = _epoch_min(ts, ts.normalize())
            cuts[(role, flno)] = (tod + 720) % 1440

        offsets = {}
        for key, ts in baseline_ts.items():
            role, flno, _ = key
            cut = cuts[(role, flno)]
            day_midnight = _epoch_min(ts.normalize(), self.anchor)
            tod = _epoch_min(ts, ts.normalize())
            offsets[key] = day_midnight + cut if tod >= cut else day_midnight + cut - 1440
        return offsets

    def build_claim(self, times: dict) -> list:
        return build_full_claim(self.tk, self.market_k_od, times, L=self.L, U=self.U)

    def _rivals(self, o: str, d: str, gun: int) -> dict:
        key = (o, d, gun)
        if key not in self.rival_cache:
            self.rival_cache[key] = derive_rival_best_times(self.od_table, o, d, gun)
        return self.rival_cache[key]

    def _b_od_for(self, o: str, d: str, gaps_by_market: dict) -> int:
        key = (o, d)
        if key not in self.b_od_cache:
            gun0 = min(gun for (mo, md, gun) in gaps_by_market if (mo, md) == key)
            baseline_j = compute_baseline_best_journey(self.od_table, o, d, gun0, L=self.L, U=self.U)
            self.b_od_cache[key] = (
                derive_b_od(self.od_table, o, d, gun0, baseline_j)
                if baseline_j is not None
                else 0
            )
        return self.b_od_cache[key]

    def objective_from_claim(self, connections: list) -> float:
        gaps_by_market = {}
        for conn in connections:
            o, d = conn["od"].split("-")
            gaps_by_market.setdefault((o, d, int(conn["gun"])), []).append(int(conn["gap_min"]))

        connection_reward = 0.0
        ranking_reward = 0.0
        for (o, d, gun), gaps in sorted(gaps_by_market.items()):
            rho = self.rho.get((o, d))
            if rho is None:
                continue
            count = len(gaps)
            connection_reward += rho * sum(2 ** -(j - 1) for j in range(1, count + 1))

            rivals = self._rivals(o, d, gun)
            if not rivals:
                continue
            k_od = self.market_k_od[(o, d)]
            journeys = [k_od + gap for gap in gaps]
            beaten = {name for name, rival_time in rivals.items() if any(j <= rival_time for j in journeys)}
            rank = max(1, len(rivals) - len(beaten))
            ranking_reward += rho * self.weight_lookup.get(
                (len(rivals), self._b_od_for(o, d, gaps_by_market), rank),
                0.0,
            )
        return connection_reward + ranking_reward

    def _static_e2_infeasible(self, o: str, d: str, gun: int) -> bool:
        a, b = sorted((o, d))
        key = (a, b, gun)
        if key not in self.static_e2_cache:
            self.static_e2_cache[key] = _is_gamma_statically_infeasible(
                self.tk,
                a,
                b,
                gun,
                self.anchor,
                self.config["adjustable_window_min"],
                self.config["adjustable_set"],
                self.L,
                self.U,
                self.config["gamma"],
                self.market_k_od[(a, b)],
                self.market_k_od[(b, a)],
            )
        return self.static_e2_cache[key]

    def e_counts_and_targets(self, connections: list) -> tuple:
        counts = {}
        best = {}
        best_conn = {}
        conns_by_market = {}
        for conn in connections:
            o, d = conn["od"].split("-")
            gun = int(conn["gun"])
            gap = int(conn["gap_min"])
            market = (o, d, gun)
            counts[market] = counts.get(market, 0) + 1
            conns_by_market.setdefault(market, []).append(conn)
            k_od = self.market_k_od.get((o, d))
            if k_od is None:
                continue
            journey = k_od + gap
            if market not in best or journey < best[market]:
                best[market] = journey
                best_conn[market] = conn

        e1_violations = []
        candidate_pairs = set()
        for o, d, gun in counts:
            candidate_pairs.add((o, d, gun))
            candidate_pairs.add((d, o, gun))
        checked = set()
        for o, d, gun in sorted(candidate_pairs):
            if (o, d, gun) in checked or (d, o, gun) in checked:
                continue
            n_fwd = counts.get((o, d, gun), 0)
            n_bwd = counts.get((d, o, gun), 0)
            if n_fwd == 0 or n_bwd == 0:
                continue
            checked.add((o, d, gun))
            checked.add((d, o, gun))
            if abs(n_fwd - n_bwd) > self.config["alpha"] * (n_fwd + n_bwd):
                e1_violations.append((o, d, gun, n_fwd, n_bwd))

        e2_violations = []
        checked = set()
        for o, d, gun in sorted(best):
            if (o, d, gun) in checked or (d, o, gun) not in best:
                continue
            checked.add((o, d, gun))
            checked.add((d, o, gun))
            diff = abs(best[(o, d, gun)] - best[(d, o, gun)])
            if diff <= self.config["gamma"]:
                continue
            if self._static_e2_infeasible(o, d, gun):
                continue
            e2_violations.append((o, d, gun, best[(o, d, gun)], best[(d, o, gun)]))

        target_weights = {}

        def add_conn(conn: dict, weight: float) -> None:
            key1 = ("IB", int(conn["flno1"]), int(conn["gun"]))
            key2 = ("OB", int(conn["flno2"]), int(conn["gun"]))
            target_weights[key1] = target_weights.get(key1, 0.0) + weight
            target_weights[key2] = target_weights.get(key2, 0.0) + weight

        for o, d, gun, n_fwd, n_bwd in e1_violations:
            heavy = (o, d, gun) if n_fwd >= n_bwd else (d, o, gun)
            light = (d, o, gun) if n_fwd >= n_bwd else (o, d, gun)
            for conn in conns_by_market.get(heavy, []):
                add_conn(conn, 2.0)
            for conn in conns_by_market.get(light, []):
                add_conn(conn, 1.0)

        for o, d, gun, j_fwd, j_bwd in e2_violations:
            for market in ((o, d, gun), (d, o, gun)):
                conn = best_conn.get(market)
                if conn is not None:
                    add_conn(conn, 4.0)
            for conn in conns_by_market.get((o, d, gun), []):
                add_conn(conn, 0.25)
            for conn in conns_by_market.get((d, o, gun), []):
                add_conn(conn, 0.25)

        self.best_journey_connections = best_conn
        return e1_violations, e2_violations, target_weights

    def local_score(self, connections: list) -> Score:
        e1_violations, e2_violations, _ = self.e_counts_and_targets(connections)
        return Score(
            objective=self.objective_from_claim(connections),
            e1=len(e1_violations),
            e2=len(e2_violations),
        )

    def make_state(self, times: dict, moves: tuple = ()) -> State:
        connections = self.build_claim(times)
        return State(times=times, connections=connections, score=self.local_score(connections), moves=moves)

    def _connections_by_market(self, connections: list) -> dict:
        conns_by_market = {}
        for conn in connections:
            o, d = conn["od"].split("-")
            conns_by_market.setdefault((o, d, int(conn["gun"])), []).append(conn)
        return conns_by_market

    def _is_legal_move(self, state: State, move: Move) -> bool:
        seen = set()
        for key, delta in move.changes:
            if key in seen:
                return False
            seen.add(key)
            current = state.times.get(key)
            bounds = self.bounds.get(key)
            if current is None or bounds is None:
                return False
            lo, hi = bounds
            if not (lo <= current + delta <= hi):
                return False
        return True

    def _regularity_closed_move(self, move: Move) -> Move:
        changes = {}
        for key, delta in move.changes:
            for grouped_key in self.regularity_groups.get(key, (key,)):
                changes[grouped_key] = changes.get(grouped_key, 0) + delta
        return Move(tuple(sorted(changes.items())))

    @staticmethod
    def _round_up_to_five(value: float) -> int:
        return int(math.ceil(value / 5.0) * 5)

    def _regularity_repaired_move(self, state: State, move: Move) -> Move:
        changes = {key: delta for key, delta in move.changes}
        affected = {(key[0], key[1]) for key, _ in move.changes}
        for role, flno in sorted(affected):
            group = [
                key for key in self.regularity_groups.get((role, flno, next(k[2] for k, _ in move.changes if k[:2] == (role, flno))), ())
                if key in self.day_offsets
            ]
            if len(group) < 2:
                continue

            def values_with(extra_changes):
                return {
                    key: state.times[key] + extra_changes.get(key, 0) - self.day_offsets[key]
                    for key in group
                    if key in state.times
                }

            values = values_with(changes)
            if not values:
                continue
            spread = max(values.values()) - min(values.values())
            if spread <= self.config["X_dev"]:
                continue

            max_value = max(values.values())
            min_value = min(values.values())
            changed_keys = {key for key, _ in move.changes if key in values}
            max_keys = {key for key, value in values.items() if value == max_value}
            min_keys = {key for key, value in values.items() if value == min_value}

            raise_lows = {}
            target_min = max_value - self.config["X_dev"]
            for key, value in values.items():
                if value < target_min:
                    raise_lows[key] = self._round_up_to_five(target_min - value)

            lower_highs = {}
            target_max = min_value + self.config["X_dev"]
            for key, value in values.items():
                if value > target_max:
                    lower_highs[key] = -self._round_up_to_five(value - target_max)

            if changed_keys & max_keys:
                chosen = raise_lows
            elif changed_keys & min_keys:
                chosen = lower_highs
            else:
                chosen = raise_lows if sum(abs(v) for v in raise_lows.values()) <= sum(abs(v) for v in lower_highs.values()) else lower_highs
            for key, delta in chosen.items():
                changes[key] = changes.get(key, 0) + delta
        return Move(tuple(sorted((key, delta) for key, delta in changes.items() if delta)))

    def legal_moves(self, state: State, max_targets: int, deltas: tuple = DELTA_SET) -> list:
        _, _, target_weights = self.e_counts_and_targets(state.connections)
        ranked = sorted(target_weights.items(), key=lambda item: (-item[1], item[0]))[:max_targets]
        moves = []
        for key, _ in ranked:
            current = state.times.get(key)
            bounds = self.bounds.get(key)
            if current is None or bounds is None:
                continue
            lo, hi = bounds
            for delta in deltas:
                new_time = current + delta
                if lo <= new_time <= hi:
                    move = Move.single(key, delta)
                    moves.append(move)
                    repaired = self._regularity_repaired_move(state, move)
                    if repaired != move and self._is_legal_move(state, repaired):
                        moves.append(repaired)
                    closed = self._regularity_closed_move(move)
                    if closed != move and self._is_legal_move(state, closed):
                        moves.append(closed)
        return moves

    def pair_moves(self, state: State, max_targets: int, deltas: tuple = DELTA_SET) -> list:
        e1_violations, e2_violations, _ = self.e_counts_and_targets(state.connections)
        conns_by_market = self._connections_by_market(state.connections)
        steps = sorted({abs(delta) for delta in deltas if delta})
        moves = []
        seen = set()

        def add_move(changes):
            raw = Move(tuple(changes))
            for move in (raw, self._regularity_repaired_move(state, raw), self._regularity_closed_move(raw)):
                if move.changes in seen:
                    continue
                seen.add(move.changes)
                if self._is_legal_move(state, move):
                    moves.append(move)

        def add_gap_move(conn: dict, direction: int):
            # direction=-1 reduces gap (later IB, earlier OB); +1 increases it.
            ib = ("IB", int(conn["flno1"]), int(conn["gun"]))
            ob = ("OB", int(conn["flno2"]), int(conn["gun"]))
            for step in steps:
                if direction < 0:
                    add_move(((ib, step), (ob, -step)))
                else:
                    add_move(((ib, -step), (ob, step)))

        for o, d, gun, j_fwd, j_bwd in e2_violations:
            fwd = (o, d, gun)
            bwd = (d, o, gun)
            fwd_conn = self.best_journey_connections.get(fwd)
            bwd_conn = self.best_journey_connections.get(bwd)
            if j_fwd > j_bwd:
                if fwd_conn:
                    add_gap_move(fwd_conn, -1)
                if bwd_conn:
                    add_gap_move(bwd_conn, 1)
            else:
                if bwd_conn:
                    add_gap_move(bwd_conn, -1)
                if fwd_conn:
                    add_gap_move(fwd_conn, 1)

        for o, d, gun, n_fwd, n_bwd in e1_violations:
            heavy = (o, d, gun) if n_fwd >= n_bwd else (d, o, gun)
            light = (d, o, gun) if n_fwd >= n_bwd else (o, d, gun)
            for conn in conns_by_market.get(heavy, []):
                direction = -1 if int(conn["gap_min"]) - self.L <= self.U - int(conn["gap_min"]) else 1
                add_gap_move(conn, direction)
            self._add_light_side_near_miss_moves(state, light, steps, add_move, limit=max_targets)
            if len(moves) >= max_targets * 8:
                break

        return moves[: max_targets * 8]

    def _add_light_side_near_miss_moves(self, state: State, market: tuple, steps: list, add_move, limit: int) -> None:
        o, d, gun = market
        day = self.tk[self.tk["gun"] == gun]
        inbound = sorted({int(row.flno1) for row in day[day["dep1"] == o].itertuples()})
        outbound = sorted({int(row.flno2) for row in day[day["arr2"] == d].itertuples()})
        near = []
        for f1 in inbound:
            ib = ("IB", f1, gun)
            t_arr = state.times.get(ib)
            if t_arr is None:
                continue
            for f2 in outbound:
                ob = ("OB", f2, gun)
                t_dep = state.times.get(ob)
                if t_dep is None:
                    continue
                gap = t_dep - t_arr
                if self.L <= gap <= self.U:
                    continue
                if self.L - 60 <= gap < self.L:
                    near.append((self.L - gap, ib, ob, 1))
                elif self.U < gap <= self.U + 60:
                    near.append((gap - self.U, ib, ob, -1))
        for _, ib, ob, direction in sorted(near)[:limit]:
            for step in steps:
                if direction < 0:
                    add_move(((ib, step), (ob, -step)))
                else:
                    add_move(((ib, -step), (ob, step)))

    def apply_move(self, state: State, move: Move) -> State:
        times = dict(state.times)
        for key, delta in move.changes:
            times[key] = times[key] + delta
        return self.make_state(times, moves=state.moves + (move,))

    def write_provisional_candidate(self, path: Path, state: State, elapsed_sec: float) -> None:
        ranking = derive_ranking_from_claim(self.od_table, self.market_k_od, state.connections)
        write_benchmark_output(
            path,
            state.times,
            state.connections,
            ranking,
            self.k_sources,
            status="heuristic_incumbent_pending_full_gate",
            solve_time_sec=elapsed_sec,
            diagnostics={
                "mode": "benchmark_full_claim",
                "gate_status": "pending_full_gate",
                "constraint_interpretation": INTERPRETATION,
                "strict_feasible": False,
                "note": "provisional candidate; do not use diagnostics until full_gate completes",
            },
        )

    def write_candidate(
        self,
        path: Path,
        state: State,
        objective: float,
        families: dict,
        claim: dict,
        strict_feasible: bool,
        elapsed_sec: float,
    ) -> None:
        ranking = derive_ranking_from_claim(self.od_table, self.market_k_od, state.connections)
        diagnostics = _build_gate_diagnostics(
            families=families,
            claim=claim,
            strict_feasible=strict_feasible,
            moves=state.moves,
            objective=objective,
            dropped_markets=len(self.dropped_markets),
        )
        write_benchmark_output(
            path,
            state.times,
            state.connections,
            ranking,
            self.k_sources,
            status="heuristic_incumbent_with_strict_violations",
            solve_time_sec=elapsed_sec,
            diagnostics=diagnostics,
        )
        stamp_recomputed_objective(path, objective)

    def full_gate(self, state: State, path: Path, elapsed_sec: float) -> tuple:
        self.write_provisional_candidate(path, state, elapsed_sec)
        objective, _ = recompute_objective(
            path,
            self.od_path,
            self.yv_path,
            self.cr_path,
            L=self.L,
            U=self.U,
            strict=False,
        )
        local_objective = state.score.objective
        objective_mismatch = not math.isclose(objective, local_objective, rel_tol=0.0, abs_tol=1e-6)

        claim = validate_claim_completeness(
            path,
            self.od_path,
            self.yv_path,
            L=self.L,
            U=self.U,
            strict=False,
        )
        validation = validate_output(
            path,
            self.od_path,
            L=self.L,
            U=self.U,
            adjustable_window_min=self.config["adjustable_window_min"],
            adjustable_set=self.config["adjustable_set"],
            flight_pairs_path=self.fp_path,
            tau=self.config["tau"],
            x_dev=self.config["X_dev"],
            alpha=self.config["alpha"],
            gamma=self.config["gamma"],
            bucket_size_min=self.config["bucket_size_min"],
            capacity_departure=self.config["capacity_departure"],
            capacity_arrival=self.config["capacity_arrival"],
            e1_activation=self.config.get("e1_activation", "conditional"),
        )
        families = summarize_violation_families(validation.violations)
        hard = sum(families["counts"].get(family, 0) for family in HARD_FAMILIES)
        e1 = families["counts"].get("E1", 0)
        e2 = families["counts"].get("E2", 0)
        gated_score = Score(
            objective=objective,
            e1=e1,
            e2=e2,
            hard=hard,
            claim_complete=claim["claim_complete"],
            missing_claims=claim["missing_claims"],
            extra_claims=claim["extra_claims"],
            strict_counts=families["counts"],
        )
        state.score = gated_score
        self.write_candidate(path, state, objective, families, claim, validation.is_valid, elapsed_sec)
        _assert_gate_consistency(
            json.loads(path.read_text()),
            claim,
            validation,
            objective,
            families,
        )
        if objective_mismatch:
            return None, f"recompute mismatch local={local_objective} full={objective}"
        if not claim["claim_complete"] or claim["missing_claims"] or claim["extra_claims"]:
            return gated_score, "claim completeness failed"
        if hard:
            return gated_score, f"hard family violations nonzero: {hard}"
        return gated_score, "accepted by full gate"


def acceptance_reason(before: Score, after: Score) -> tuple:
    if not after.claim_complete or after.missing_claims or after.extra_claims:
        return False, "claim_complete/missing/extra gate failed"
    if after.hard != 0:
        return False, "hard-family gate failed"
    if after.soft < before.soft:
        return True, "E1+E2 decreased"
    if after.soft == before.soft and after.objective > before.objective + 1e-6:
        return True, "E1+E2 tied and objective increased"
    return False, "no accepted improvement"


def better_local(candidate: State, incumbent: State) -> bool:
    return (candidate.score.soft, candidate.score.e2, -candidate.score.objective) < (
        incumbent.score.soft,
        incumbent.score.e2,
        -incumbent.score.objective,
    )


def _best_local_candidates(ctx: RepairContext, state: State, moves: list) -> list:
    local_candidates = []
    seen_times = set()
    for move in moves:
        candidate = ctx.apply_move(state, move)
        signature = tuple(sorted(candidate.times.items()))
        if signature in seen_times:
            continue
        seen_times.add(signature)
        if better_local(candidate, state):
            local_candidates.append(candidate)
    local_candidates.sort(
        key=lambda s: (s.score.soft, s.score.e2, -s.score.objective, [m.label() for m in s.moves])
    )
    return local_candidates


def _try_full_gates(ctx: RepairContext, incumbent: State, candidates: list, scratch: Path, limit: int, t0: float):
    gate_attempts = 0
    last_reason = "no candidate evaluated"
    for candidate in candidates[:limit]:
        gate_attempts += 1
        gated_score, gate_reason = ctx.full_gate(candidate, scratch, time.time() - t0)
        last_reason = gate_reason
        if gated_score is None:
            print(f"[repair] gate rejected: {gate_reason}", flush=True)
            continue
        ok, reason = acceptance_reason(incumbent.score, gated_score)
        print(
            f"[repair] gate moves={','.join(m.label() for m in candidate.moves[-2:])} "
            f"objective={gated_score.objective} E1={gated_score.e1} E2={gated_score.e2} "
            f"hard={gated_score.hard} claim_complete={gated_score.claim_complete} "
            f"reason={reason}",
            flush=True,
        )
        if ok:
            return candidate, reason, gate_attempts
    return None, last_reason, gate_attempts


def run_greedy(ctx: RepairContext, initial: State, args, t0: float) -> tuple:
    best = initial
    gate_attempts = 0
    last_reason = "no candidate evaluated"
    scratch = Path(args.output).with_suffix(".gate_tmp.json")
    for iteration in range(1, args.max_iters + 1):
        if time.time() - t0 > args.time_budget_sec:
            return best, f"time budget reached during greedy after {iteration - 1} iteration(s)", gate_attempts
        moves = ctx.legal_moves(best, args.max_targets)
        if not moves:
            return best, "no target moves from current E1/E2 violations", gate_attempts
        local_candidates = _best_local_candidates(ctx, best, moves)
        print(
            f"[repair] greedy iter={iteration} moves={len(moves)} "
            f"local_improvers={len(local_candidates)} incumbent_soft={best.score.soft}",
            flush=True,
        )
        if local_candidates:
            accepted_candidate, last_reason, gates = _try_full_gates(
                ctx, best, local_candidates, scratch, args.full_gate_per_iter, t0
            )
            gate_attempts += gates
            if accepted_candidate is not None:
                best = accepted_candidate
                continue

        pair_moves = ctx.pair_moves(best, args.max_targets)
        pair_candidates = _best_local_candidates(ctx, best, pair_moves)
        print(
            f"[repair] greedy iter={iteration} pair_moves={len(pair_moves)} "
            f"pair_local_improvers={len(pair_candidates)}",
            flush=True,
        )
        if pair_candidates:
            accepted_candidate, last_reason, gates = _try_full_gates(
                ctx, best, pair_candidates, scratch, args.full_gate_per_iter, t0
            )
            gate_attempts += gates
            if accepted_candidate is not None:
                best = accepted_candidate
                continue

        expanded = ctx.legal_moves(best, args.max_targets, deltas=EXPANDED_DELTA_SET)
        expanded += ctx.pair_moves(best, args.max_targets, deltas=EXPANDED_DELTA_SET)
        expanded_candidates = _best_local_candidates(ctx, best, expanded)
        print(
            f"[repair] greedy iter={iteration} expanded_moves={len(expanded)} "
            f"expanded_local_improvers={len(expanded_candidates)}",
            flush=True,
        )
        if expanded_candidates:
            accepted_candidate, last_reason, gates = _try_full_gates(
                ctx, best, expanded_candidates, scratch, args.full_gate_per_iter, t0
            )
            gate_attempts += gates
            if accepted_candidate is not None:
                best = accepted_candidate
                continue

        return best, f"greedy found no accepted move ({last_reason})", gate_attempts
    return best, "max greedy iterations reached", gate_attempts


def cleanup_scratch(output_path: Path) -> None:
    for path in (
        output_path.with_suffix(".gate_tmp.json"),
        output_path.with_suffix(".beam_gate_tmp.json"),
    ):
        if path.exists():
            path.unlink()


def run_beam(ctx: RepairContext, initial: State, args, t0: float) -> tuple:
    beam = [initial]
    best = initial
    scratch = Path(args.output).with_suffix(".beam_gate_tmp.json")
    gate_attempts = 0
    last_reason = "beam not started"
    seen = {tuple(sorted(initial.times.items()))}
    for depth in range(1, args.beam_depth + 1):
        if time.time() - t0 > args.time_budget_sec:
            return best, f"time budget reached during beam at depth {depth}", gate_attempts
        pool = []
        for state in beam:
            state_moves = ctx.legal_moves(state, args.beam_targets) + ctx.pair_moves(state, args.beam_targets)
            for move in state_moves:
                if time.time() - t0 > args.time_budget_sec:
                    break
                candidate = ctx.apply_move(state, move)
                signature = tuple(sorted(candidate.times.items()))
                if signature in seen:
                    continue
                seen.add(signature)
                pool.append(candidate)
        pool.sort(key=lambda state: (state.score.soft, state.score.e2, -state.score.objective, len(state.moves)))
        beam = pool[: args.beam_width]
        print(
            f"[repair] beam depth={depth} pool={len(pool)} "
            f"best_local_soft={beam[0].score.soft if beam else 'none'}",
            flush=True,
        )
        if not beam:
            return best, "beam exhausted", gate_attempts
        for candidate in beam:
            if not better_local(candidate, initial):
                continue
            if time.time() - t0 > args.time_budget_sec:
                return best, "time budget reached before beam full gate", gate_attempts
            gate_attempts += 1
            gated_score, gate_reason = ctx.full_gate(candidate, scratch, time.time() - t0)
            last_reason = gate_reason
            if gated_score is None:
                print(f"[repair] beam gate rejected: {gate_reason}", flush=True)
                continue
            ok, reason = acceptance_reason(initial.score, gated_score)
            print(
                f"[repair] beam gate moves={','.join(m.label() for m in candidate.moves)} "
                f"objective={gated_score.objective} E1={gated_score.e1} E2={gated_score.e2} "
                f"hard={gated_score.hard} claim_complete={gated_score.claim_complete} "
                f"reason={reason}",
                flush=True,
            )
            if ok and better_local(candidate, best):
                best = candidate
                last_reason = reason
                return best, reason, gate_attempts
    return best, f"beam found no accepted repair ({last_reason})", gate_attempts


def print_table(before: Score, after: Score, accepted: bool, reason: str) -> None:
    print("")
    print("metric,before,after")
    print(f"objective,{before.objective},{after.objective}")
    print(f"hard,{before.hard},{after.hard}")
    print(f"E1,{before.e1},{after.e1}")
    print(f"E2,{before.e2},{after.e2}")
    print(f"claim_complete,{before.claim_complete},{after.claim_complete}")
    print(f"missing_claims,{before.missing_claims},{after.missing_claims}")
    print(f"extra_claims,{before.extra_claims},{after.extra_claims}")
    print(f"accepted,{accepted},{reason}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/full_data_output.json")
    parser.add_argument("--output", default="runs/e1e2_repair_candidate.json")
    parser.add_argument("--config", default="src/config/standard.yaml")
    parser.add_argument("--time-budget-sec", type=float, default=3600)
    parser.add_argument("--max-iters", type=int, default=60)
    parser.add_argument("--max-targets", type=int, default=80)
    parser.add_argument("--top-flights", type=int, default=None)
    parser.add_argument("--full-gate-per-iter", type=int, default=3)
    parser.add_argument("--beam-width", type=int, default=5)
    parser.add_argument("--beam-depth", type=int, default=3)
    parser.add_argument("--beam-targets", type=int, default=20)
    args = parser.parse_args(argv)
    if args.top_flights is not None:
        args.max_targets = args.top_flights

    t0 = time.time()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ctx = RepairContext(Path(args.config))
    initial = ctx.make_state(ctx.read_times(input_path))
    source = json.loads(input_path.read_text())
    diag = source.get("diagnostics", {})
    diag_counts = diag.get("strict_violations", {}).get("by_family", {})
    diag_hard = sum(diag_counts.get(family, 0) for family in HARD_FAMILIES)
    claim_check = diag.get("claim_check", {})
    before = Score(
        objective=source["objective_value"],
        e1=diag_counts.get("E1", initial.score.e1),
        e2=diag_counts.get("E2", initial.score.e2),
        hard=diag_hard,
        claim_complete=diag.get("claim_complete", True),
        missing_claims=claim_check.get("missing_claims", diag.get("missing_claims", 0)),
        extra_claims=claim_check.get("extra_claims", diag.get("extra_claims", 0)),
    )
    if not math.isclose(before.objective, initial.score.objective, rel_tol=0.0, abs_tol=1e-6):
        print(
            f"[repair] STOP: local objective mismatch reported={before.objective} "
            f"local={initial.score.objective}",
            flush=True,
        )
        return 2
    if before.e1 != initial.score.e1 or before.e2 != initial.score.e2:
        print(
            f"[repair] STOP: E-count mismatch diagnostics=({before.e1},{before.e2}) "
            f"local=({initial.score.e1},{initial.score.e2})",
            flush=True,
        )
        return 2
    if before.hard != 0 or not before.claim_complete or before.missing_claims or before.extra_claims:
        print(
            f"[repair] STOP: starting incumbent fails hard/claim gate "
            f"hard={before.hard} claim_complete={before.claim_complete} "
            f"missing={before.missing_claims} extra={before.extra_claims}",
            flush=True,
        )
        return 2
    initial.score = before
    print(
        f"[repair] before objective={before.objective} hard={before.hard} "
        f"E1={before.e1} E2={before.e2} claim_complete={before.claim_complete}",
        flush=True,
    )

    best, reason, greedy_gates = run_greedy(ctx, initial, args, t0)
    gate_attempts = greedy_gates
    if best is initial:
        print(f"[repair] greedy did not accept a repair: {reason}", flush=True)
        beam_best, beam_reason, beam_gates = run_beam(ctx, initial, args, t0)
        gate_attempts += beam_gates
        if beam_best is not initial:
            best = beam_best
            reason = beam_reason
        else:
            reason = beam_reason

    accepted, accept_reason = acceptance_reason(before, best.score)
    if accepted:
        # Re-run the final full gate at the requested output path so the saved
        # artifact carries full diagnostics/examples, not the scratch file.
        final_score, final_reason = ctx.full_gate(best, output_path, time.time() - t0)
        gate_attempts += 1
        if final_score is None:
            accepted = False
            accept_reason = final_reason
        else:
            best.score = final_score
            accepted, accept_reason = acceptance_reason(before, best.score)
    after = best.score
    print_table(before, after, accepted, accept_reason if accepted else reason)
    print(f"[repair] full_gate_attempts={gate_attempts} elapsed_sec={time.time() - t0:.1f}")
    cleanup_scratch(output_path)
    if accepted:
        print(f"[repair] accepted candidate written to {output_path}")
        return 0
    print("[repair] no accepted repair found; original package retained")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

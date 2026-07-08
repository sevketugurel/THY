"""Solve tests for C (monotone slot) + the real connection-count objective.

Doğruluk argümanı (ultrathink, kod öncesi): with s[j] in [0,1] continuous,
Sum_j s[j] = Sum x_pi, and s[j+1]<=s[j] (monotonic), a STRICTLY decreasing
W(c)_j=2^-(j-1) forces any optimum to pack low-j (high-weight) slots first --
shifting weight from a filled low-j slot to a higher-j slot while holding the
sum fixed can never increase reward (weighted sum can only fall or stay flat).
This makes the LP optimum sit exactly at an integer vertex (0/1 pattern)
without ever declaring s as binary -- fewer integer variables than a naive
binary-slot encoding, which is a direct Performans win.

marker: solve (small HiGHS solve, <60s).
"""
from pathlib import Path

import pyomo.environ as pyo
import pytest

from src.candidates.generate import generate_candidates
from src.data.loaders import load_od_table, load_yolcu_verisi
from src.model.build import build_model
from src.solve.runner import solve

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.solve

L, U = 60, 300


@pytest.fixture
def fixture_data():
    od_table = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXDIR / "synthetic_yolcu_verisi.xlsx")
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    return tk, rho


def test_fixture_objective_matches_hand_calc_under_adjustable_none(fixture_data):
    # adjustable_set="none" -> all TK flights Rfix -> unique feasible point,
    # matching tests/fixtures/README.md's Gün1(200)+Gün2(200)=400.0 hand calc
    # (connection-count reward only -- ranking reward is M2's job).
    tk, rho = fixture_data
    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=0, adjustable_set="none",
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    model = build_model(candidates, rho)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)

    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(400.0)


def test_slot_values_settle_at_integer_vertices_not_fractional(fixture_data):
    tk, rho = fixture_data
    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=0, adjustable_set="none",
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    model = build_model(candidates, rho)
    solve(model, solver="highs", time_limit_sec=60, seed=42)

    for key in model.SLOTS:
        val = pyo.value(model.s[key])
        assert val == pytest.approx(0.0, abs=1e-6) or val == pytest.approx(1.0, abs=1e-6), \
            f"slot {key} settled at fractional value {val}, LP-integrality argument violated"


def test_connection_reward_component_logged_separately(fixture_data):
    tk, rho = fixture_data
    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=0, adjustable_set="none",
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    model = build_model(candidates, rho)
    solve(model, solver="highs", time_limit_sec=60, seed=42)

    assert pyo.value(model.connection_reward) == pytest.approx(400.0)


def test_free_time_model_is_deterministic_across_repeated_runs(fixture_data):
    # Real branch-and-bound (binary x/y + integer t_arr/t_dep) -- unlike M0's
    # trivial model, tie-breaking order could plausibly vary without proper
    # seeding. Same seed must give bit-identical objective AND selection.
    from src.candidates.generate import compute_epoch_anchor

    tk, rho = fixture_data
    anchor = compute_epoch_anchor(tk)

    def run_once():
        candidates = []
        for gun in sorted(int(g) for g in tk["gun"].unique()):
            candidates.extend(generate_candidates(
                tk, L=L, U=U, gun=gun, adjustable_window_min=180, adjustable_set="all",
                epoch_anchor=anchor,
            ))
        candidates = [c for c in candidates if (c.o, c.d) in rho]
        model = build_model(candidates, rho, L=L, U=U)
        result = solve(model, solver="highs", time_limit_sec=60, seed=42)
        selection = sorted(
            ((c.od, c.flno1, c.flno2, c.gun, x) for c, x in result.selected.items()),
        )
        return result.objective_value, selection

    run1 = run_once()
    run2 = run_once()
    assert run1 == run2

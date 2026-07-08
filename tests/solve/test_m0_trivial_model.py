"""M0 walking-skeleton solve test: trivial model (free x_pi, linear rho-weighted
reward, no constraints) solved end-to-end with HiGHS.

This is NOT the real objective (Modül-5 monoton slot reward is M1's job) -- it only
proves the full build->solve->extract chain works. Since there are no constraints,
the optimal solution trivially selects every positive-reward candidate; the test
value asserted below is computed by hand from that fact, not by running the solver
and copying its output.

marker: solve (small HiGHS solve against synthetic fixture).
"""
from pathlib import Path

import pytest

from src.candidates.generate import generate_candidates
from src.data.loaders import load_od_table, load_yolcu_verisi
from src.model.build import build_trivial_model
from src.solve.runner import solve

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.solve

L, U = 60, 300


@pytest.fixture
def gun1_candidates():
    tk = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    tk = tk[tk.cr1 == "TK"]
    return generate_candidates(tk, L=L, U=U, gun=1)


@pytest.fixture
def rho_lookup():
    df = load_yolcu_verisi(FIXDIR / "synthetic_yolcu_verisi.xlsx")
    return {(r.orig, r.dest): r.rho for r in df.itertuples()}


def test_trivial_model_selects_all_positive_reward_candidates(gun1_candidates, rho_lookup):
    # No constraints in M0 -> optimal trivially selects every candidate (all rho>0).
    # Hand calc: 2 ZZA-ZZB candidates (rho=100 each) + 1 ZZB-ZZA candidate (rho=50)
    # -> objective = 100 + 100 + 50 = 250.
    model = build_trivial_model(gun1_candidates, rho_lookup)
    result = solve(model, solver="highs", time_limit_sec=30, seed=42)

    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(250.0)
    assert sum(1 for c in gun1_candidates if result.selected[c] == 1) == 3


def test_trivial_model_is_deterministic_across_runs(gun1_candidates, rho_lookup):
    model1 = build_trivial_model(gun1_candidates, rho_lookup)
    result1 = solve(model1, solver="highs", time_limit_sec=30, seed=42)

    model2 = build_trivial_model(gun1_candidates, rho_lookup)
    result2 = solve(model2, solver="highs", time_limit_sec=30, seed=42)

    assert result1.objective_value == result2.objective_value
    assert [result1.selected[c] for c in gun1_candidates] == [result2.selected[c] for c in gun1_candidates]

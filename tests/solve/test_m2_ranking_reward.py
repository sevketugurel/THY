"""Solve tests for D's rank one-hot linking + the ranking reward objective
component.

Doğruluk argümanı (ultrathink, kod öncesi): r_{od,h} zaten bir Expression
(D'de tanımlı, N-sum(beaten)). W(N,b,r) KEYFİ bir lookup (negatif ağırlıklar
dahil, r'nin doğrusal bir fonksiyonu değil), bu yüzden r'yi ödüle bağlamak
için one-hot indicator gerekir: onehot[o,d,gun,r] in {0,1}, r=1..N,
Sum_r onehot_r = 1 (tam olarak bir r seçilir), Sum_r r*onehot_r = rank
(linking equality -- Big-M GEREKMEZ, tam eşitlik zaten r'yi tek bir noktaya
sabitler). Ödül = Sum_r W(N,b_od,r)*onehot_r.

marker: solve (small HiGHS solve, <60s).
"""
from pathlib import Path

import pyomo.environ as pyo
import pytest

from src.candidates.generate import generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_od_table, load_yolcu_verisi
from src.data.ranking import derive_b_od, is_ranking_monotonic
from src.model.build import build_model_with_competition
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
    ranking_table = load_change_ranking(FIXDIR / "synthetic_change_ranking_input.xlsx")
    return od_table, tk, rho, ranking_table


def test_fixture_objective_matches_corrected_hand_calc(fixture_data):
    # adjustable_set="none" -> unique feasible point. Connection reward covers
    # BOTH days (200.0 Gün1 + 200.0 Gün2 = 400.0, per fixtures/README.md's
    # established 2-day pattern); ranking reward only Gün1 has rival data
    # (100.0), Gün2 markets have N=0 (no onehot slots, zero contribution).
    # Total = 500.0. (b_od now derived, not hand-picked -- docs/decisions.md
    # 2026-07-09.)
    od_table, tk, rho, ranking_table = fixture_data
    provider = BlockTimeProvider(tk, L=L, U=U)

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=0, adjustable_set="none",
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    journey_constants = {(c.o, c.d): provider.get_journey_constant(c.o, c.d) for c in candidates}
    rival_data = {}
    b_od_data = {}
    for c in candidates:
        market = (c.o, c.d, c.gun)
        if market not in rival_data:
            rival_data[market] = derive_rival_best_times(od_table, c.o, c.d, c.gun)
        if (c.o, c.d) not in b_od_data:
            baseline_j = journey_constants[(c.o, c.d)] + c.gap_min
            b_od_data[(c.o, c.d)] = derive_b_od(od_table, c.o, c.d, c.gun, baseline_j)

    monotonic = is_ranking_monotonic(ranking_table)
    model = build_model_with_competition(
        candidates, rho, journey_constants, rival_data, b_od_data, ranking_table,
        L=L, U=U, monotonic=monotonic,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)

    assert result.status == "optimal"
    assert pyo.value(model.connection_reward) == pytest.approx(400.0)
    assert pyo.value(model.ranking_reward) == pytest.approx(100.0)
    assert result.objective_value == pytest.approx(500.0)


def test_negative_weight_contribution_logged_when_rank_worsens():
    # Dedicated small scenario (not the big fixture): a market where the ONLY
    # offered connection is forced to NOT beat any rival (gap invalid for the
    # market's rivals given a tight T_comp), landing on a worse-than-baseline
    # rank that hits a genuinely negative W(N,b,r) entry.
    from src.candidates.generate import Candidate
    from src.model.constraints_competition import add_d_constraints, add_rank_onehot
    from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
    from src.model.objective import add_ranking_reward_objective

    c = Candidate(
        od="ZZA-ZZB", o="ZZA", d="ZZB", gun=1, flno1=1, flno2=2,
        r1_id=("IB", 1, 1), r2_id=("OB", 2, 1), arr_time=None, dep_time=None,
        gap_min=60, arr_lo=0, arr_hi=0, dep_lo=60, dep_hi=60, gap_lo=60, gap_hi=60,
    )
    # J=220+60=280, but T_comp=200 (rival is FASTER -- pi cannot beat it).
    journey_constants = {("ZZA", "ZZB"): 220}
    rival_data = {("ZZA", "ZZB", 1): {"R1": 200}}
    # b_od=0: baseline was already beating this rival (VARSAYIM for this
    # synthetic scenario -- baseline_j=150 beats T_comp=200).
    b_od_data = {("ZZA", "ZZB"): 0}
    ranking_table = __import__("pandas").DataFrame([
        {"n": 1, "b": 0, "r": 0, "weight": 0.0},
        {"n": 1, "b": 0, "r": 1, "weight": -0.5},  # worsening from b=0 to r=1 -- penalized
    ])

    model = pyo.ConcreteModel()
    add_flight_time_variables(model, [c])
    add_b_constraints(model, [c], L=L, U=U)
    add_c_constraints(model, [c])
    add_d_constraints(model, [c], journey_constants, rival_data, monotonic=True)
    n_by_market = {("ZZA", "ZZB", 1): 1}
    add_rank_onehot(model, n_by_market)
    add_ranking_reward_objective(model, {("ZZA", "ZZB"): 100}, b_od_data, ranking_table, n_by_market)
    model._candidates = [c]

    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    # x=1 is still better than x=0 for connection_reward, but ranking_reward
    # must show the negative contribution explicitly (not hidden/cancelled).
    assert pyo.value(model.ranking_reward) == pytest.approx(100 * -0.5)

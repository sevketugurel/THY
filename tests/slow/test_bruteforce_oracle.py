"""Brute-force oracle: a pure-Python (NO src.model import) 10-minute grid
search over (dep,arr) combinations, cross-validating the solver's B+C+D
reification logic against direct combinatorial enumeration.

Doğruluk argümanı: modelin B+C+D reifikasyonlarının doğru bir MIP kodlaması
olduğunu kanıtlamanın en güçlü yolu, Pyomo/HiGHS'e hiç dokunmadan AYNI
sonucu üretmektir. Brute-force grid search bunun için ideal: hiçbir
yaklaşıklık/gevşetme yok, saf if/else mantığıyla TAM DOĞRU bir taban çizgi
verir.

İki test:
1. Solver'a "t mod 10 == 0" ek kısıtı koyarsak, arama uzayı brute-force'un
   taradığı grid ile TAM ÖRTÜŞÜR -> optimal objektifler TAM EŞİT olmalı.
2. mod-10 kısıtı olmadan (gerçek Integer domain), solver'ın arama uzayı
   grid'i KAPSAR (superset) -> solver'ın objektifi brute-force'unkinden
   KÜÇÜK OLAMAZ (>=).

marker: slow (full-ish combinatorial sweep, still <60s for this micro-scenario).
"""
from itertools import product

import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_competition import add_d_constraints, add_rank_onehot
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.model.objective import add_connection_reward_objective, add_ranking_reward_objective
from src.solve.runner import solve

pytestmark = pytest.mark.slow

L, U = 60, 300
K_OD = 150
RHO = 100
ARR_LO, ARR_HI = 400, 600   # inbound (7001, ZZQ->IST) window
DEP_LO, DEP_HI = 550, 750   # outbound (7002, IST->ZZQ) window
RIVALS = {"RX": 200, "RY": 250}
B_OD = 2  # baseline arr=500,dep=650 -> gap=150,J=300 -> beats neither -> b_od=max(1,2-0)=2
RANKING_TABLE_ROWS = [
    {"n": 2, "b": 2, "r": 1, "weight": 1.6321205588285577},
    {"n": 2, "b": 2, "r": 2, "weight": 1.0},
]


def _candidate():
    return Candidate(
        od="ZZQ-IST", o="ZZQ", d="IST", gun=1, flno1=7001, flno2=7002,
        r1_id=("IB", 7001, 1), r2_id=("OB", 7002, 1), arr_time=None, dep_time=None,
        gap_min=150, arr_lo=ARR_LO, arr_hi=ARR_HI, dep_lo=DEP_LO, dep_hi=DEP_HI,
        gap_lo=DEP_LO - ARR_HI, gap_hi=DEP_HI - ARR_LO,
    )


def brute_force_best_objective(grid_step=10):
    """Pure-Python re-implementation of the B+C+D core reward logic -- no
    Pyomo, no src.model. Exhaustively tries every (dep,arr) pair on the grid."""
    import pandas as pd
    ranking_table = pd.DataFrame(RANKING_TABLE_ROWS)
    weight_lookup = {(row.n, row.b, row.r): row.weight for row in ranking_table.itertuples()}

    best = 0.0  # x=0 (never offering) is always achievable, reward=0
    for dep, arr in product(range(DEP_LO, DEP_HI + 1, grid_step), range(ARR_LO, ARR_HI + 1, grid_step)):
        gap = dep - arr
        if not (L <= gap <= U):
            continue  # x forced to 0 here, reward=0, already covered by best's floor
        journey = K_OD + gap
        beaten = sum(1 for t_comp in RIVALS.values() if journey <= t_comp)
        rank = max(1, len(RIVALS) - beaten)
        conn_reward = RHO * 1.0  # single candidate -> single slot, W(c)_1=1
        rank_reward = RHO * weight_lookup.get((len(RIVALS), B_OD, rank), 0.0)
        best = max(best, conn_reward + rank_reward)
    return best


def _build_model(force_multiples_of_10: bool):
    candidates = [_candidate()]
    journey_constants = {("ZZQ", "IST"): K_OD}
    rival_data = {("ZZQ", "IST", 1): RIVALS}
    b_od_data = {("ZZQ", "IST"): B_OD}
    rho = {("ZZQ", "IST"): RHO}
    import pandas as pd
    ranking_table = pd.DataFrame(RANKING_TABLE_ROWS)

    model = pyo.ConcreteModel()
    model._candidates = candidates
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_connection_reward_objective(model, rho)
    n_by_market = add_d_constraints(model, candidates, journey_constants, rival_data, monotonic=True)
    add_rank_onehot(model, n_by_market)
    add_ranking_reward_objective(model, rho, b_od_data, ranking_table, n_by_market)

    if force_multiples_of_10:
        model.k_arr = pyo.Var(domain=pyo.Integers, bounds=(ARR_LO // 10, ARR_HI // 10))
        model.k_dep = pyo.Var(domain=pyo.Integers, bounds=(DEP_LO // 10, DEP_HI // 10))
        model.arr_grid = pyo.Constraint(expr=model.t_arr["IB", 7001, 1] == 10 * model.k_arr)
        model.dep_grid = pyo.Constraint(expr=model.t_dep["OB", 7002, 1] == 10 * model.k_dep)

    return model


def test_grid_constrained_solver_matches_brute_force_exactly():
    expected = brute_force_best_objective(grid_step=10)
    model = _build_model(force_multiples_of_10=True)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value == pytest.approx(expected)


def test_unconstrained_solver_is_at_least_as_good_as_brute_force():
    expected = brute_force_best_objective(grid_step=10)
    model = _build_model(force_multiples_of_10=False)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert result.objective_value >= expected - 1e-6


def test_brute_force_best_matches_hand_calc():
    # gap=80 (e.g. arr=500,dep=580) beats RY(250) not RX(200) -> beaten=1 ->
    # rank=max(1,2-1)=1 -> reward=100*(1.0+1.6321205588285577)=263.21205588285577.
    # This is the ceiling for this scenario (only one candidate, one slot).
    assert brute_force_best_objective(grid_step=10) == pytest.approx(263.21205588285577)

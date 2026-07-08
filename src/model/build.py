"""Pyomo model construction.

M0 scope (kept for M0's own tests): a deliberately trivial model (free x_pi in
{0,1}, linear rho-weighted reward, no constraints) that proved the
build->solve->extract chain works end-to-end.

M1 scope (build_model): B (bağlantı uygunluğu, bidirectional reification) + C
(Modul-5 monoton slot).

M2 scope (build_model_with_competition): + D (rakip yenme ve sıralama).
Real constraint groups A,E-G land in M3+.
"""
import pyomo.environ as pyo

from src.candidates.generate import Candidate
from src.model.constraints_competition import add_d_constraints, add_rank_onehot
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.model.objective import add_connection_reward_objective, add_ranking_reward_objective


def build_trivial_model(candidates: list[Candidate], rho: dict) -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()

    model.CANDIDATES = pyo.Set(initialize=list(range(len(candidates))), ordered=True)
    model.x = pyo.Var(model.CANDIDATES, domain=pyo.Binary)

    model._candidates = candidates  # stashed for result extraction

    def obj_rule(m):
        return sum(rho[(candidates[i].o, candidates[i].d)] * m.x[i] for i in m.CANDIDATES)

    model.objective = pyo.Objective(rule=obj_rule, sense=pyo.maximize)

    return model


def build_model(candidates: list[Candidate], rho: dict, L: int = 60, U: int = 300) -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model._candidates = candidates

    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_connection_reward_objective(model, rho)

    return model


def build_model_with_competition(
    candidates: list[Candidate], rho: dict, journey_constants: dict, rival_data: dict,
    b_od_data: dict, ranking_table, L: int = 60, U: int = 300, monotonic: bool = True,
) -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model._candidates = candidates

    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_connection_reward_objective(model, rho)

    n_by_market = add_d_constraints(model, candidates, journey_constants, rival_data, monotonic=monotonic)
    add_rank_onehot(model, n_by_market)
    add_ranking_reward_objective(model, rho, b_od_data, ranking_table, n_by_market)

    return model

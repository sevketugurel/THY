"""Pyomo model construction.

M0 scope: a deliberately trivial model (free x_pi in {0,1}, linear rho-weighted
reward, no constraints at all) to prove the build->solve->extract chain works
end-to-end. Real constraints (A-G) and the Modul-5 monotone-slot decreasing-return
reward (C) land in M1+.
"""
import pyomo.environ as pyo

from src.candidates.generate import Candidate


def build_trivial_model(candidates: list[Candidate], rho: dict) -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()

    model.CANDIDATES = pyo.Set(initialize=list(range(len(candidates))), ordered=True)
    model.x = pyo.Var(model.CANDIDATES, domain=pyo.Binary)

    model._candidates = candidates  # stashed for result extraction

    def obj_rule(m):
        return sum(rho[(candidates[i].o, candidates[i].d)] * m.x[i] for i in m.CANDIDATES)

    model.objective = pyo.Objective(rule=obj_rule, sense=pyo.maximize)

    return model

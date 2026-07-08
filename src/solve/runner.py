"""Solver abstraction: config-selected solver (HiGHS for MVP; Gurobi pluggable
later behind the same interface, per plan §6 -- not installed/tested this round).
"""
import time
from dataclasses import dataclass

import pyomo.environ as pyo

_SOLVER_NAMES = {
    "highs": "appsi_highs",
    "gurobi": "gurobi",
}


@dataclass
class SolveResult:
    status: str
    objective_value: float
    selected: dict
    solve_time_sec: float


def solve(model: pyo.ConcreteModel, solver: str, time_limit_sec: float, seed: int) -> SolveResult:
    pyomo_solver_name = _SOLVER_NAMES[solver]
    opt = pyo.SolverFactory(pyomo_solver_name)

    if solver == "highs":
        opt.config.time_limit = time_limit_sec
        opt.config.stream_solver = False
        opt.highs_options = {"random_seed": seed}

    t0 = time.time()
    result = opt.solve(model)
    solve_time_sec = time.time() - t0

    term = result.solver.termination_condition
    if term == pyo.TerminationCondition.optimal:
        status = "optimal"
    elif term == pyo.TerminationCondition.infeasible:
        status = "infeasible"
    elif term == pyo.TerminationCondition.maxTimeLimit:
        status = "time_limit"
    else:
        status = str(term)

    selected = {}
    objective_value = None
    if status in ("optimal", "time_limit"):
        objective_value = pyo.value(model.objective)
        for i in model.CANDIDATES:
            candidate = model._candidates[i]
            selected[candidate] = int(round(pyo.value(model.x[i])))

    return SolveResult(
        status=status,
        objective_value=objective_value,
        selected=selected,
        solve_time_sec=solve_time_sec,
    )

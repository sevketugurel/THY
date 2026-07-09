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
    gap_values: dict = None
    arr_times: dict = None
    dep_times: dict = None
    rank_values: dict = None
    beaten_rivals: dict = None


def solve(model: pyo.ConcreteModel, solver: str, time_limit_sec: float, seed: int) -> SolveResult:
    pyomo_solver_name = _SOLVER_NAMES[solver]
    opt = pyo.SolverFactory(pyomo_solver_name)

    if solver == "highs":
        opt.config.time_limit = time_limit_sec
        opt.config.stream_solver = False
        opt.highs_options = {"random_seed": seed}

    # load_solutions=False: an infeasible/unbounded model has no solution to
    # load -- letting the default (True) crash with a RuntimeError instead of
    # a clean TerminationCondition would make it impossible for callers (and
    # the M4/F/G solve tests) to assert on result.status=="infeasible".
    t0 = time.time()
    result = opt.solve(model, load_solutions=False)
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
    gap_values = {}
    arr_times = {}
    dep_times = {}
    rank_values = {}
    beaten_rivals = {}
    objective_value = None
    has_incumbent = True
    if status in ("optimal", "time_limit"):
        try:
            model.solutions.load_from(result)
        except RuntimeError:
            # maxTimeLimit can be reached with ZERO feasible incumbent found
            # yet (a real risk for a heavily-reified, large-scale M5 model) --
            # appsi_highs raises the SAME "no solution to load" RuntimeError
            # as the genuinely-infeasible case rather than returning cleanly.
            # Treat this as "no incumbent yet" (status stays time_limit,
            # objective_value stays None) instead of crashing the caller.
            has_incumbent = False
    if status in ("optimal", "time_limit") and has_incumbent:
        objective_value = pyo.value(model.objective)
        if hasattr(model, "CANDIDATES"):
            for i in model.CANDIDATES:
                candidate = model._candidates[i]
                selected[candidate] = int(round(pyo.value(model.x[i])))
                if hasattr(model, "gap"):
                    gap_values[candidate] = int(round(pyo.value(model.gap[i])))
        if hasattr(model, "t_arr"):
            for r in model.ARR_INSTANCES:
                arr_times[r] = int(round(pyo.value(model.t_arr[r])))
        if hasattr(model, "t_dep"):
            for r in model.DEP_INSTANCES:
                dep_times[r] = int(round(pyo.value(model.t_dep[r])))
        if hasattr(model, "rank"):
            # model.rank is the RAW N-beaten Expression -- can be 0 when ALL
            # rivals are beaten, but the real change_ranking_input.xlsx table
            # never defines an r=0 row (min observed r is always 1). Clamp to
            # the SAME max(1,.) floor add_rank_onehot's linking constraint and
            # the validator's expected_rank both already use -- but only for
            # markets that HAVE rivals (N=0 markets correctly report 0,
            # un-clamped).
            n_by_market = {}
            if hasattr(model, "MARKET_RIVALS"):
                for (o, d, gun, k) in model.MARKET_RIVALS:
                    n_by_market[o, d, gun] = n_by_market.get((o, d, gun), 0) + 1
            for market in model.MARKETS:
                raw_rank = int(round(pyo.value(model.rank[market])))
                rank_values[market] = max(1, raw_rank) if n_by_market.get(market, 0) > 0 else raw_rank
        if hasattr(model, "beaten"):
            for (o, d, gun, k) in model.MARKET_RIVALS:
                if int(round(pyo.value(model.beaten[o, d, gun, k]))) == 1:
                    beaten_rivals.setdefault((o, d, gun), []).append(k)

    return SolveResult(
        status=status,
        objective_value=objective_value,
        selected=selected,
        solve_time_sec=solve_time_sec,
        gap_values=gap_values,
        arr_times=arr_times,
        dep_times=dep_times,
        rank_values=rank_values,
        beaten_rivals=beaten_rivals,
    )

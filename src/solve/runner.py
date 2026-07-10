"""Solver abstraction: config-selected solver (HiGHS for MVP; Gurobi pluggable
later behind the same interface, per plan §6 -- not installed/tested this round).
"""
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pyomo.environ as pyo

_SOLVER_NAMES = {
    "highs": "appsi_highs",
    "gurobi": "gurobi",
}

# Best-effort regexes against HiGHS's own log text (captured via the
# `log_file` HiGHS option) -- format observed empirically from a real
# appsi_highs solve, not documented API, so every field degrades to None
# rather than raising if HiGHS changes its wording in a future version.
_RE_ORIG_SIZE = re.compile(
    r"MIP has (\d+) rows; (\d+) cols; (\d+) nonzeros; \d+ integer variables \((\d+) binary\)"
)
_RE_PRESOLVED_SIZE = re.compile(
    r"Presolve reductions: rows (\d+)\(-?\d+\); columns (\d+)\(-?\d+\); nonzeros (\d+)\(-?\d+\)"
)
_RE_GAP = re.compile(r"Gap\s+([\d.]+)%")


def parse_highs_log(log_text: str) -> dict:
    """Extract model-size + gap stats from HiGHS log text for run reporting
    (M5 full-data runs -- rows/cols/nonzeros/binary belong in the closure
    report, per-run not per-test). Missing fields are None, never raised.
    """
    stats = {
        "orig_rows": None, "orig_cols": None, "orig_nonzeros": None, "orig_binary": None,
        "presolved_rows": None, "presolved_cols": None, "presolved_nonzeros": None,
        "final_gap_pct": None,
    }
    m = _RE_ORIG_SIZE.search(log_text)
    if m:
        stats["orig_rows"], stats["orig_cols"], stats["orig_nonzeros"], stats["orig_binary"] = (
            int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)),
        )
    m = _RE_PRESOLVED_SIZE.search(log_text)
    if m:
        stats["presolved_rows"], stats["presolved_cols"], stats["presolved_nonzeros"] = (
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
        )
    m = _RE_GAP.search(log_text)
    if m:
        stats["final_gap_pct"] = float(m.group(1))
    return stats


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
    model_stats: dict = None


def solve(
    model: pyo.ConcreteModel, solver: str, time_limit_sec: float, seed: int,
    mip_gap: float = None, log_file=None, mip_heuristic_effort: float = None,
    extra_highs_options: dict = None, warmstart: bool = False,
) -> SolveResult:
    pyomo_solver_name = _SOLVER_NAMES[solver]
    opt = pyo.SolverFactory(pyomo_solver_name)

    if solver == "highs":
        opt.config.time_limit = time_limit_sec
        highs_options = {"random_seed": seed}
        if mip_gap is not None:
            highs_options["mip_rel_gap"] = mip_gap
        if mip_heuristic_effort is not None:
            # M5 finding (docs/decisions.md 2026-07-09): appsi_highs's own
            # time_limit does not reliably interrupt root-node cut generation
            # on large models -- raising heuristic effort trades exhaustive
            # cutting for a faster shot at ANY feasible incumbent, which is
            # what an exploratory run needs (gap/optimality is secondary).
            highs_options["mip_heuristic_effort"] = mip_heuristic_effort
        if extra_highs_options:
            # M5c (docs/decisions.md 2026-07-10): generic escape hatch for
            # ad-hoc HiGHS options not worth a named parameter -- e.g.
            # testing whether root-node stalls are a symmetry/cut-generation
            # artifact (mip_detect_symmetry) rather than a size artifact.
            highs_options.update(extra_highs_options)
        if log_file is not None:
            # Stream to terminal (visible under nohup/tee) AND persist to a
            # parseable per-step file -- M5's observability requirement
            # (previously solve_with_ladder ran completely silently).
            opt.config.stream_solver = True
            highs_options["log_file"] = str(log_file)
        else:
            opt.config.stream_solver = False
        opt.highs_options = highs_options

    # load_solutions=False: an infeasible/unbounded model has no solution to
    # load -- letting the default (True) crash with a RuntimeError instead of
    # a clean TerminationCondition would make it impossible for callers (and
    # the M4/F/G solve tests) to assert on result.status=="infeasible".
    #
    # warmstart (M5d, docs/decisions.md 2026-07-10): appsi_highs's legacy
    # solve() interface accepts warmstart=True, which triggers its own
    # _warm_start() -- reads every Var's CURRENT .value (caller must set
    # them before calling solve()) and passes them to HiGHS via
    # highspy.HighsSolution/setSolution as a MIP start. A no-op if no
    # variable has a value set.
    t0 = time.time()
    result = opt.solve(model, load_solutions=False, warmstart=warmstart)
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

    model_stats = None
    if log_file is not None:
        log_path = Path(log_file)
        if log_path.exists():
            model_stats = parse_highs_log(log_path.read_text())

    return SolveResult(
        status=status,
        objective_value=objective_value,
        model_stats=model_stats,
        selected=selected,
        solve_time_sec=solve_time_sec,
        gap_values=gap_values,
        arr_times=arr_times,
        dep_times=dep_times,
        rank_values=rank_values,
        beaten_rivals=beaten_rivals,
    )

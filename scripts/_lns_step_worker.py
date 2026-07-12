#!/usr/bin/env python3
"""Internal worker for scripts/run_lns.py's subprocess watchdog -- NOT meant
to be invoked directly. Builds build_elastic_feasibility_model, fixes every
t_arr/t_dep instance NOT in the current iteration's free set to the
reference point (src.model.lns.fix_reference_except_free), then solves
normally (no warm-start needed -- the fixed portion IS the reference,
already feasible by construction; only the small free portion is a genuine
search).

Usage: python -u scripts/_lns_step_worker.py <input.pkl> <output.pkl>
"""
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model.build import build_elastic_feasibility_model
from src.model.constraints_elastic import add_elastic_feasibility_objective
from src.model.deactivation import apply_deactivation, market_direction_index
from src.model.lns import fix_reference_except_free
from src.model.warm_start import derive_and_set_warm_start
from src.solve.runner import solve


def main():
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)

    t0 = time.time()
    model_kwargs = spec["build_kwargs"]["model_kwargs"]
    model = build_elastic_feasibility_model(**model_kwargs)
    print(f"[_lns_step_worker] model built in {time.time()-t0:.1f}s", flush=True)
    # M5d finding (docs/decisions.md 2026-07-11): epsilon=0 (no deviation
    # tie-breaker) -- with epsilon=1e-6 the same sub-problem showed the
    # familiar "Nodes=0, no incumbent" stall even after shrinking to ~90K
    # presolved rows; epsilon=0 reached PROVEN OPTIMAL on the same scale.
    # Not fully explained (possibly numerical conditioning from mixing
    # 1e-06-scale costs with the slack terms' O(1) scale) but empirically
    # decisive -- kept as an explicit, overridable parameter.
    epsilon = spec["build_kwargs"].get("epsilon", 0.0)
    add_elastic_feasibility_objective(model, epsilon=epsilon)
    fix_kwargs = spec["build_kwargs"]["fix_kwargs"]
    fix_reference_except_free(
        model, fix_kwargs["reference_arr"], fix_kwargs["reference_dep"],
        fix_kwargs["free_arr"], fix_kwargs["free_dep"],
    )
    # M5d LNS (docs/decisions.md 2026-07-11): also seed EVERY variable
    # (x/gap/y/z/a_dir/w/Jbest/s_e1/s_e2) from the same reference point via
    # the already-proven derive_and_set_warm_start (not just t_arr/t_dep) --
    # without this, HiGHS searches the free portion from a cold start and
    # showed the same "Nodes=0, dual bound climbs via cuts, no incumbent"
    # symptom even on a much smaller (post-fix) presolved model. Order
    # matters: the objective already ran (creates deviation-tracking vars
    # that derive_and_set_warm_start also needs to set).
    derive_and_set_warm_start(
        model, model_kwargs["candidates"], model_kwargs["journey_constants"],
        fix_kwargs["reference_arr"], fix_kwargs["reference_dep"],
        L=model_kwargs["L"], U=model_kwargs["U"], alpha=model_kwargs["alpha"], gamma=model_kwargs["gamma"],
        bucket_size_min=model_kwargs["bucket_size_min"], epoch_anchor=model_kwargs["epoch_anchor"],
    )
    # D6 (Plan B, conflict-deactivation campaign): optional, runs LAST for
    # the same reason as _warm_start_elastic_step_worker.py -- .fix(0) must
    # be the final word over whatever the pre-deactivation reference point's
    # warm-start hint set. Absent/empty is a no-op, identical to before this.
    directions_to_kill = spec["build_kwargs"].get("directions_to_kill") or []
    if directions_to_kill:
        direction_index = market_direction_index(model_kwargs["candidates"])
        apply_deactivation(model, direction_index, directions_to_kill)
    build_time_sec = time.time() - t0
    print(f"[_lns_step_worker] fixed+warm-started in total {build_time_sec:.1f}s, solving...", flush=True)

    result = solve(model, warmstart=True, **spec["solve_kwargs"])
    print(f"[_lns_step_worker] solve finished status={result.status}", flush=True)

    with open(output_path, "wb") as f:
        pickle.dump({
            "status": result.status, "objective_value": result.objective_value,
            "selected": result.selected, "solve_time_sec": result.solve_time_sec,
            "gap_values": result.gap_values, "arr_times": result.arr_times,
            "dep_times": result.dep_times, "rank_values": result.rank_values,
            "beaten_rivals": result.beaten_rivals, "model_stats": result.model_stats,
            "build_time_sec": build_time_sec,
        }, f)


if __name__ == "__main__":
    main()

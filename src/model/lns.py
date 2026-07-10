"""M5d Fix-and-Optimize LNS (docs/decisions.md 2026-07-11, user redirect):
elastic model is feasible BY CONSTRUCTION (slack absorbs any E1/E2
violation), so unlike local branching's Big-M indicators, freezing here is
REAL variable fixing (`.fix()`) -- HiGHS presolve substitutes fixed
variables directly (no probing needed), so a subproblem with most
instances fixed is genuinely small. And unlike K-subset (freezing chosen
BEFORE seeing any solve result), the free set here is chosen FROM the
current incumbent's own worst slack -- so the fixed portion is always a
real feasible assignment (the incumbent itself), meaning every LNS
subproblem is trivially feasible before HiGHS even starts (fix everything
to the incumbent, free a few instances -- the incumbent's own slack values
are always achievable, so no subproblem can be infeasible or worse than
the current incumbent)."""
from collections import defaultdict


def compute_pair_slack(candidates, journey_constants: dict, arr_times: dict, dep_times: dict,
                        L: int, U: int, alpha: float, gamma: int) -> dict:
    """Independent (pure-Python) recompute of s_e1/s_e2 EXACTLY matching
    src.model.constraints_elastic's formulas, for every (o,d,gun) pair that
    the elastic model would build E1/E2 constraints for (both directions
    present in `groups`). Returns {(o,d,gun): {"e1":..., "e2":..., "total":...}}."""
    groups = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[(c.o, c.d, c.gun)].append(i)

    gap_of, x_of = {}, {}
    for i, c in enumerate(candidates):
        gap = dep_times[c.r2_id] - arr_times[c.r1_id]
        gap_of[i] = gap
        x_of[i] = 1 if L <= gap <= U else 0

    pairs, seen = [], set()
    for (o, d, gun) in groups:
        if (o, d, gun) in seen:
            continue
        if (d, o, gun) in groups:
            pairs.append((o, d, gun))
            seen.add((o, d, gun))
            seen.add((d, o, gun))

    jbest_of = {}
    for (o, d, gun), idxs in groups.items():
        offered = [i for i in idxs if x_of[i] == 1]
        if offered:
            jbest_of[(o, d, gun)] = min(journey_constants[(o, d)] + gap_of[i] for i in offered)

    result = {}
    for (o, d, gun) in pairs:
        n_fwd = sum(x_of[i] for i in groups[(o, d, gun)])
        n_bwd = sum(x_of[i] for i in groups[(d, o, gun)])
        s_e1 = max(0.0, abs(n_fwd - n_bwd) - alpha * (n_fwd + n_bwd))
        if (o, d, gun) in jbest_of and (d, o, gun) in jbest_of:
            s_e2 = max(0.0, abs(jbest_of[(o, d, gun)] - jbest_of[(d, o, gun)]) - gamma)
        else:
            s_e2 = 0.0
        result[(o, d, gun)] = {"e1": s_e1, "e2": s_e2, "total": s_e1 + s_e2}
    return result


def compute_gamma_infeasible_pairs(candidates, journey_constants: dict, L: int, U: int, gamma: int) -> set:
    """Static (schedule-independent) set of (o,d,gun) pairs where E2 can
    NEVER be satisfied regardless of which candidate is chosen or how gap is
    adjusted within its own window -- i.e. the BEST-CASE achievable Jbest
    ranges for the two directions are still more than gamma apart. Depends
    only on candidates' own gap_lo/gap_hi and journey_constants, so it's
    computed ONCE per run, not per iteration.

    Found empirically (docs/decisions.md 2026-07-11): selecting "worst
    slack" pairs for LNS disproportionately picks these -- the underlying
    journey_constant ASYMMETRY between directions (VARSAYIM-12 GÜNCELLEME 1:
    ~78%% of real E2 violations) makes them unfixable by construction, and
    including even one in a free set stalls the whole sub-solve (HiGHS never
    stops trying to satisfy something that provably cannot be satisfied)."""
    groups = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[(c.o, c.d, c.gun)].append(i)

    def best_case_j_range(direction):
        o, d, _ = direction
        los, his = [], []
        for i in groups.get(direction, []):
            c = candidates[i]
            lo, hi = max(c.gap_lo, L), min(c.gap_hi, U)
            if lo <= hi:
                los.append(journey_constants[(o, d)] + lo)
                his.append(journey_constants[(o, d)] + hi)
        return (min(los), max(his)) if los else None

    pairs, seen = [], set()
    for (o, d, gun) in groups:
        if (o, d, gun) in seen:
            continue
        if (d, o, gun) in groups:
            pairs.append((o, d, gun))
            seen.add((o, d, gun))
            seen.add((d, o, gun))

    infeasible = set()
    for (o, d, gun) in pairs:
        r_fwd = best_case_j_range((o, d, gun))
        r_bwd = best_case_j_range((d, o, gun))
        if r_fwd is None or r_bwd is None:
            continue  # neither side can ever be offered -- E2 is non-binding, not infeasible
        best_gap = max(0.0, r_fwd[0] - r_bwd[1], r_bwd[0] - r_fwd[1])
        if best_gap > gamma:
            infeasible.add((o, d, gun))
    return infeasible


def select_worst_pairs(pair_slack: dict, m: int, exclude: set = frozenset()) -> list:
    """Top-m (o,d,gun) pairs by total slack, descending, ties broken by the
    pair tuple itself (determinism). Stops early once slack hits 0 -- freeing
    an already-satisfied pair wastes budget without helping. `exclude` (e.g.
    compute_gamma_infeasible_pairs' output) is skipped entirely -- freeing a
    provably-unfixable pair's instances only wastes the free-instance budget
    and stalls the solve for nothing."""
    ranked = sorted(pair_slack.items(), key=lambda kv: (-kv[1]["total"], kv[0]))
    return [pair for pair, s in ranked if s["total"] > 0 and pair not in exclude][:m]


def free_instances_for_pairs(candidates, pairs: list) -> tuple:
    """Returns (free_arr: set, free_dep: set) of r1_id/r2_id instances
    belonging to either direction's candidates for the given pairs."""
    groups = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[(c.o, c.d, c.gun)].append(i)

    free_arr, free_dep = set(), set()
    for (o, d, gun) in pairs:
        for i in groups.get((o, d, gun), []) + groups.get((d, o, gun), []):
            c = candidates[i]
            free_arr.add(c.r1_id)
            free_dep.add(c.r2_id)
    return free_arr, free_dep


def fix_reference_except_free(model, reference_arr: dict, reference_dep: dict,
                               free_arr: set, free_dep: set) -> None:
    """Fixes every t_arr/t_dep instance NOT in the free sets to its
    reference value. Called on a freshly-built model -- every non-frozen
    (gap_lo!=gap_hi) instance starts unfixed, so only the complement needs
    an explicit .fix() call."""
    for r in model.ARR_INSTANCES:
        if r not in free_arr:
            model.t_arr[r].fix(reference_arr[r])
    for r in model.DEP_INSTANCES:
        if r not in free_dep:
            model.t_dep[r].fix(reference_dep[r])

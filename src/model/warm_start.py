"""M5d (docs/decisions.md 2026-07-10): derive a full MIP-start assignment
for build_elastic_feasibility_model, given a raw (arr_times, dep_times)
point -- e.g. from build_core_feasibility_model's A+G+F solve. Every
variable family gets an explicit, hand-derived .value (no partial starts):
see the ultrathink in each block below for why the derivation is exact or
a safe (never-too-small) overestimate.
"""
from collections import defaultdict

from src.model.constraints_operations import _day_offsets


def derive_and_set_warm_start(
    model, candidates, journey_constants: dict, arr_times: dict, dep_times: dict,
    L: int, U: int, alpha: float, gamma: int, bucket_size_min: int, epoch_anchor=None,
) -> dict:
    """Sets .value on every Var in an already-built elastic model. Returns a
    small summary dict (total_s_e1, total_s_e2) for logging."""
    for r in model.ARR_INSTANCES:
        model.t_arr[r].value = arr_times[r]
    for r in model.DEP_INSTANCES:
        model.t_dep[r].value = dep_times[r]

    # G's T_ref (cluster reference time, constraints_operations.py): each
    # cluster's constraint is T_ref <= t-day_offset <= T_ref+x_dev for every
    # gun in the cluster -- since the SOURCE point (arr_times/dep_times)
    # already satisfies G (it came from a solved A+G+F model), the min over
    # the cluster's own (t-day_offset) values is a valid T_ref: it satisfies
    # g_lower exactly for the minimizing gun and by construction for the
    # rest, and g_upper holds for all because max-min<=x_dev already (G was
    # genuinely satisfied at the source).
    if hasattr(model, "T_ref"):
        day_offset = _day_offsets(candidates, epoch_anchor)
        cluster_guns = defaultdict(list)
        for (role, flno, cluster_key, gun) in model.G_FLIGHT_DAYS:
            cluster_guns[(role, flno, cluster_key)].append(gun)
        for (role, flno, cluster_key) in model.G_FLIGHTS:
            guns = cluster_guns[(role, flno, cluster_key)]
            times = arr_times if role == "IB" else dep_times
            normalized = [times[(role, flno, g)] - day_offset[(role, flno, g)] for g in guns]
            model.T_ref[role, flno, cluster_key].value = min(normalized)

    groups = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[(c.o, c.d, c.gun)].append(i)

    # B's reification, applied deterministically (no choice involved): gap
    # is fully determined by t, x is fully determined by gap.
    gap_of, x_of = {}, {}
    for i, c in enumerate(candidates):
        gap = dep_times[c.r2_id] - arr_times[c.r1_id]
        gap_of[i] = gap
        x_of[i] = 1 if L <= gap <= U else 0
        model.x[i].value = x_of[i]
        model.gap[i].value = gap
        # y only matters when x=0 (B's backward-reification switch selects
        # which side of [L,U] gap sits on to relax the correct half of the
        # backward pair) -- see constraints_selection.py's backward_below/
        # backward_above rules for the derivation.
        model.y[i].value = 1 if (x_of[i] == 0 and gap > U) else 0

    # F: bucket assignment is an EXACT decomposition of t (matches the
    # row-explosion-fix equality t = bucket_start*z + offset).
    for (role, flno, gun, b) in model.DEP_Z_INDEX:
        t = dep_times[(role, flno, gun)]
        model.z_dep[role, flno, gun, b].value = 1 if b == t // bucket_size_min else 0
    for r in model.DEP_INSTANCES:
        t = dep_times[r]
        model.dep_offset[r].value = t - (t // bucket_size_min) * bucket_size_min
    for (role, flno, gun, b) in model.ARR_Z_INDEX:
        t = arr_times[(role, flno, gun)]
        model.z_arr[role, flno, gun, b].value = 1 if b == t // bucket_size_min else 0
    for r in model.ARR_INSTANCES:
        t = arr_times[r]
        model.arr_offset[r].value = t - (t // bucket_size_min) * bucket_size_min

    # E2's a_dir/w (only the real backing vars for multi-candidate
    # directions -- singleton markets are folded Expressions, no .value).
    for (o, d, gun) in model.A_DIR_MARKETS:
        offered = [i for i in groups[(o, d, gun)] if x_of[i] == 1]
        model._a_dir_var[o, d, gun].value = 1 if offered else 0
    for i in model.W_CANDIDATES:
        o, d, gun = candidates[i].o, candidates[i].d, candidates[i].gun
        offered = [j for j in groups[(o, d, gun)] if x_of[j] == 1]
        if not offered:
            model._w_var[i].value = 0
            continue
        j_of = {j: journey_constants[(o, d)] + gap_of[j] for j in offered}
        argmin_j = min(offered, key=lambda j: j_of[j])
        model._w_var[i].value = 1 if i == argmin_j else 0

    market_j_bounds = {}
    for (o, d, gun), idxs in groups.items():
        j_los = [journey_constants[(o, d)] + candidates[i].gap_lo for i in idxs]
        j_his = [journey_constants[(o, d)] + candidates[i].gap_hi for i in idxs]
        market_j_bounds[(o, d, gun)] = (min(j_los), max(j_his))

    jbest_of = {}
    for (o, d, gun) in model.E2_MARKETS:
        offered = [i for i in groups[(o, d, gun)] if x_of[i] == 1]
        # If nobody's offered, Jbest is non-binding (every jbest_le relaxes
        # via Big-M since x=0 everywhere in the group) -- any value in its
        # own declared bounds is valid; jd_lo is as good as any.
        jbest = min(journey_constants[(o, d)] + gap_of[i] for i in offered) if offered \
            else market_j_bounds[(o, d, gun)][0]
        jbest_of[(o, d, gun)] = jbest
        model.Jbest[o, d, gun].value = jbest

    # s_e1: EXACT (E1 has no Big-M term at all).
    total_s_e1 = 0.0
    for (o, d, gun) in model.E1_PAIRS:
        n_fwd = sum(x_of[i] for i in groups[(o, d, gun)])
        n_bwd = sum(x_of[i] for i in groups[(d, o, gun)])
        s = max(0.0, abs(n_fwd - n_bwd) - alpha * (n_fwd + n_bwd))
        model.s_e1[o, d, gun].value = s
        total_s_e1 += s

    # s_e2: a safe conservative OVERESTIMATE -- ignores the Big-M relaxation
    # term (2-a_fwd-a_bwd), which only ever makes the TRUE required slack
    # SMALLER, never larger, so this is always sufficient for feasibility
    # even if not perfectly tight.
    total_s_e2 = 0.0
    for (o, d, gun) in model.E2_PAIRS:
        j_fwd, j_bwd = jbest_of[(o, d, gun)], jbest_of[(d, o, gun)]
        s = max(0.0, abs(j_fwd - j_bwd) - gamma)
        model.s_e2[o, d, gun].value = s
        total_s_e2 += s

    # Deviation-tracking vars (add_elastic_feasibility_objective's own
    # add_deviation_tracking call) -- ONLY exist if that's already run
    # before this function (required call order: build -> add objective ->
    # derive_and_set_warm_start). EXACT: dev_plus/dev_minus is the standard
    # absolute-value linearization of t-baseline, baseline is already fixed
    # by add_deviation_tracking (window midpoint).
    if hasattr(model, "arr_dev_plus"):
        for r in model.ARR_INSTANCES:
            delta = arr_times[r] - model._arr_baseline[r]
            model.arr_dev_plus[r].value = max(0, delta)
            model.arr_dev_minus[r].value = max(0, -delta)
        for r in model.DEP_INSTANCES:
            delta = dep_times[r] - model._dep_baseline[r]
            model.dep_dev_plus[r].value = max(0, delta)
            model.dep_dev_minus[r].value = max(0, -delta)

    return {"total_s_e1": total_s_e1, "total_s_e2": total_s_e2}

"""M5d (docs/decisions.md 2026-07-10): derive a full MIP-start assignment
for build_elastic_feasibility_model, given a raw (arr_times, dep_times)
point -- e.g. from build_core_feasibility_model's A+G+F solve. Every
variable family gets an explicit, hand-derived .value (no partial starts):
see the ultrathink in each block below for why the derivation is exact or
a safe (never-too-small) overestimate.

M5d LNS fold-redesign note (plan a-evet-ama-iki-tingly-canyon.md, adım 10):
this function is written against build_elastic_feasibility_model's Vars
(x/gap/y, Jbest, s_e1/s_e2 all real Vars). build_elastic_feasibility_model_folded
makes model.Jbest a pyo.Expression (real Var only for non-fully-frozen
markets, via model._jbest_var) -- `.value =` on an Expression is not
meaningful, so this function is NOT correctness-safe for a folded model
beyond the x/gap/y loop (already guarded below). The new folded LNS worker
does not call this -- the folded free-subproblem is small enough to solve
cold, and warm-starting was never free of subtlety even for the fix-based
model (the s_e2 conservative-overestimate was part of what caused earlier
plateaus, see docs/decisions.md). Retrofitting full Jbest/s_e2 support here
for the folded model is a follow-up, not required for this task.
"""
from collections import defaultdict

from src.model.constraints_operations import _day_offsets


def _derive_x_gap(arr_times, dep_times, candidates, L, U):
    """B's deterministic reification: gap from times, x from gap interval."""
    gap_of, x_of = {}, {}
    for i, c in enumerate(candidates):
        gap = dep_times[c.r2_id] - arr_times[c.r1_id]
        gap_of[i] = gap
        x_of[i] = 1 if L <= gap <= U else 0
    return gap_of, x_of


def _set_agf_and_bef_vars(model, candidates, journey_constants, arr_times, dep_times, gap_of, x_of,
                          L, U, bucket_size_min, epoch_anchor, alpha, gamma, include_elastic_slack):
    """Shared warm-start assignment for t/x/gap/F/G/E1/E2 vars."""
    for r in model.ARR_INSTANCES:
        model.t_arr[r].value = arr_times[r]
    for r in model.DEP_INSTANCES:
        model.t_dep[r].value = dep_times[r]

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
    # M5d LNS fold-redesign (plan a-evet-ama-iki-tingly-canyon.md, adım 10):
    # gap_of/x_of are still computed for EVERY candidate (needed below for
    # a_dir/w/Jbest derivation regardless of fold status), but .value is
    # only SET for candidates model.CANDIDATES actually declares a Var for
    # -- a folded model excludes fully-frozen candidates from x/gap/y
    # entirely (their value is already implicit in the model structure via
    # partition.x_const/gap_const), so indexing model.x[i] for one would
    # raise a KeyError.
    model_candidates = set(model.CANDIDATES)
    for i, c in enumerate(candidates):
        gap, x = gap_of[i], x_of[i]
        if i not in model_candidates:
            continue
        model.x[i].value = x
        model.gap[i].value = gap
        model.y[i].value = 1 if (x == 0 and gap > U) else 0

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

    if hasattr(model, "A_DIR_MARKETS"):
        for (o, d, gun) in model.A_DIR_MARKETS:
            offered = [i for i in groups[(o, d, gun)] if x_of[i] == 1]
            model._a_dir_var[o, d, gun].value = 1 if offered else 0
    if hasattr(model, "W_CANDIDATES"):
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
    if hasattr(model, "E2_MARKETS"):
        for (o, d, gun) in model.E2_MARKETS:
            offered = [i for i in groups[(o, d, gun)] if x_of[i] == 1]
            jbest = min(journey_constants[(o, d)] + gap_of[i] for i in offered) if offered \
                else market_j_bounds[(o, d, gun)][0]
            jbest_of[(o, d, gun)] = jbest
            model.Jbest[o, d, gun].value = jbest

    total_s_e1 = 0.0
    if include_elastic_slack and hasattr(model, "s_e1"):
        for (o, d, gun) in model.E1_PAIRS:
            n_fwd = sum(x_of[i] for i in groups[(o, d, gun)])
            n_bwd = sum(x_of[i] for i in groups[(d, o, gun)])
            s = max(0.0, abs(n_fwd - n_bwd) - alpha * (n_fwd + n_bwd))
            model.s_e1[o, d, gun].value = s
            total_s_e1 += s

    total_s_e2 = 0.0
    if include_elastic_slack and hasattr(model, "s_e2"):
        for (o, d, gun) in model.E2_PAIRS:
            j_fwd, j_bwd = jbest_of[(o, d, gun)], jbest_of[(d, o, gun)]
            s = max(0.0, abs(j_fwd - j_bwd) - gamma)
            model.s_e2[o, d, gun].value = s
            total_s_e2 += s

    if hasattr(model, "arr_dev_plus"):
        for r in model.ARR_INSTANCES:
            delta = arr_times[r] - model._arr_baseline[r]
            model.arr_dev_plus[r].value = max(0, delta)
            model.arr_dev_minus[r].value = max(0, -delta)
        for r in model.DEP_INSTANCES:
            delta = dep_times[r] - model._dep_baseline[r]
            model.dep_dev_plus[r].value = max(0, delta)
            model.dep_dev_minus[r].value = max(0, -delta)

    return groups, jbest_of, {"total_s_e1": total_s_e1, "total_s_e2": total_s_e2}


def derive_and_set_warm_start(
    model, candidates, journey_constants: dict, arr_times: dict, dep_times: dict,
    L: int, U: int, alpha: float, gamma: int, bucket_size_min: int, epoch_anchor=None,
) -> dict:
    gap_of, x_of = _derive_x_gap(arr_times, dep_times, candidates, L, U)
    _, _, summary = _set_agf_and_bef_vars(
        model, candidates, journey_constants, arr_times, dep_times, gap_of, x_of,
        L, U, bucket_size_min, epoch_anchor, alpha, gamma, include_elastic_slack=True,
    )
    return summary


def derive_and_set_warm_start_full(
    model, candidates, journey_constants: dict, rival_data: dict,
    arr_times: dict, dep_times: dict, L: int, U: int, gamma: int, bucket_size_min: int,
    epoch_anchor=None, alpha: float = 0.0,
) -> dict:
    """Warm-start for build_model_m4: A-G operational vars + C slots + D rank."""
    gap_of, x_of = _derive_x_gap(arr_times, dep_times, candidates, L, U)
    groups, _, summary = _set_agf_and_bef_vars(
        model, candidates, journey_constants, arr_times, dep_times, gap_of, x_of,
        L, U, bucket_size_min, epoch_anchor, alpha, gamma, include_elastic_slack=False,
    )

    for (o, d, gun), idxs in groups.items():
        n_offered = sum(x_of[i] for i in idxs)
        j_max = len(idxs)
        for j in range(1, j_max + 1):
            model.s[o, d, gun, j].value = 1.0 if j <= n_offered else 0.0

    always_beats, never_beats = set(), set()
    for (o, d, gun) in model.MARKETS:
        rivals = rival_data.get((o, d, gun), {})
        for i in groups[(o, d, gun)]:
            c = candidates[i]
            for k in rivals:
                t_comp = rivals[k]
                j_lo = journey_constants[(c.o, c.d)] + c.gap_lo
                j_hi = journey_constants[(c.o, c.d)] + c.gap_hi
                if j_hi <= t_comp:
                    always_beats.add((i, k))
                elif j_lo > t_comp:
                    never_beats.add((i, k))

    if hasattr(model, "BEAT_PAIRS"):
        for (i, k) in model.BEAT_PAIRS:
            c = candidates[i]
            j_pi = journey_constants[(c.o, c.d)] + gap_of[i]
            t_comp = rival_data[(c.o, c.d, c.gun)][k]
            model.beat[i, k].value = 1 if x_of[i] == 1 and j_pi <= t_comp else 0

    if hasattr(model, "MARKET_RIVALS"):
        for (o, d, gun, k) in model.MARKET_RIVALS:
            beaten = 0
            for i in groups[(o, d, gun)]:
                if (i, k) in never_beats:
                    continue
                if (i, k) in always_beats:
                    if x_of[i] == 1:
                        beaten = 1
                        break
                elif (i, k) in model.BEAT_PAIRS and int(model.beat[i, k].value) == 1:
                    beaten = 1
                    break
            model.beaten[o, d, gun, k].value = beaten

    if hasattr(model, "ACTIVE_RANK_MARKETS"):
        for (o, d, gun) in model.ACTIVE_RANK_MARKETS:
            rivals = rival_data.get((o, d, gun), {})
            n = len(rivals)
            beaten_count = sum(int(model.beaten[o, d, gun, k].value) for k in rivals)
            r = max(1, n - beaten_count) if n > 0 else 0
            for rr in range(1, n + 1):
                model.rank_onehot[o, d, gun, rr].value = 1 if rr == r else 0

    summary["n_offered"] = sum(x_of.values())
    return summary

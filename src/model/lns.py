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


# --- M5d LNS redesign, adim 2 (plan: a-evet-ama-iki-tingly-canyon.md):
# baglantili-bilesen hedefleme. Worst-slack duz listesi, bacak-paylasimi
# uzerinden bagli bir ihlal-komsulugunu parcalayarak seciyordu (bir
# pair'in bir tarafi serbest, digeri donuk kalinca komsu pair hic
# duzelmiyor -- K-subset'in leg-sharing bulgusuyla ayni yapisal gercek,
# VARSAYIM-12). Burada bagli-bilesenin TAMAMI serbest birakilir, hicbir
# zaman parcalanmaz (dev bilesenler haric, ki onlar da rastgele-BFS ile
# tam-alt-kumelere bolunur, tek pair kaybolmaz/tekrarlanmaz).
import random


def build_pair_adjacency(candidates, violated_fixable_pairs: list) -> dict:
    """{(o,d,gun) pair: set(other pairs sharing >=1 flight-time instance)}.
    Two pairs are adjacent iff any candidate belonging to either of their
    two directions shares an r1_id/r2_id with a candidate belonging to
    either direction of the other pair -- an O(n) instance->pairs inverted
    index, not an O(n^2) all-pairs comparison."""
    groups = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[(c.o, c.d, c.gun)].append(i)

    instance_to_pairs = defaultdict(set)
    for (o, d, gun) in violated_fixable_pairs:
        for i in groups.get((o, d, gun), []) + groups.get((d, o, gun), []):
            c = candidates[i]
            instance_to_pairs[c.r1_id].add((o, d, gun))
            instance_to_pairs[c.r2_id].add((o, d, gun))

    adjacency = {p: set() for p in violated_fixable_pairs}
    for pairs_sharing in instance_to_pairs.values():
        if len(pairs_sharing) > 1:
            for p in pairs_sharing:
                adjacency[p] |= (pairs_sharing - {p})
    return adjacency


def connected_components(adjacency: dict) -> list:
    """Plain BFS over `adjacency`'s keys. Returns components sorted
    smallest-first (user's "easy first" directive), ties broken by the
    component's own smallest pair (determinism)."""
    visited = set()
    components = []
    for start in adjacency:
        if start in visited:
            continue
        comp = []
        queue = [start]
        visited.add(start)
        while queue:
            node = queue.pop()
            comp.append(node)
            for neighbor in adjacency.get(node, ()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(comp)
    components.sort(key=lambda c: (len(c), min(c)))
    return components


def split_oversized_component(candidates, component: list, max_instances: int, seed: int) -> list:
    """If the component's total free-instance footprint exceeds
    max_instances, partitions it into sub-chunks via random-seed BFS (NOT
    spectral clustering -- plain Python, no new dependency) so every
    sub-chunk stays under budget where possible. A single pair whose OWN
    footprint alone exceeds max_instances is returned as its own
    over-budget singleton chunk (documented edge case, not an infinite
    loop). Union of all returned chunks' pairs == the original component's
    pairs exactly (no pair lost or duplicated)."""
    free_arr, free_dep = free_instances_for_pairs(candidates, component)
    if len(free_arr) + len(free_dep) <= max_instances:
        return [component]

    sub_adj = build_pair_adjacency(candidates, component)
    rng = random.Random(seed)
    remaining = set(component)
    chunks = []
    while remaining:
        seed_pair = rng.choice(sorted(remaining))
        chunk = [seed_pair]
        remaining.discard(seed_pair)
        frontier = [n for n in sub_adj.get(seed_pair, ()) if n in remaining]
        while frontier:
            candidate_pair = frontier.pop()
            if candidate_pair not in remaining:
                continue
            trial_arr, trial_dep = free_instances_for_pairs(candidates, chunk + [candidate_pair])
            if len(trial_arr) + len(trial_dep) > max_instances:
                continue  # doesn't fit THIS chunk -- stays in remaining for a later one
            chunk.append(candidate_pair)
            remaining.discard(candidate_pair)
            frontier.extend(n for n in sub_adj.get(candidate_pair, ()) if n in remaining)
        chunks.append(chunk)
    return chunks


def select_pairs_by_component(pair_slack: dict, candidates, gamma_infeasible: set, stubborn: set,
                               attempts: dict = None, max_instances: int = 800, seed: int = 42,
                               chunk_index: int = 0) -> tuple:
    """Stateless entry point scripts/run_lns.py calls each iteration.
    `stubborn` (a set of frozenset(component_pairs)), `attempts` (a dict of
    frozenset(component_pairs) -> attempt count), and `chunk_index`
    (round-robin position within an oversized component's sub-chunks) are
    DRIVER state owned by the caller -- this function only reads them,
    mirroring how select_worst_pairs/_tune_m are pure functions with
    m_base/randomize_mode owned by the loop.

    Bug found empirically (docs/decisions.md 2026-07-11, isolated
    component/fix measurement): once EVERY component is stubborn, always
    falling back to the globally smallest one (as the non-stubborn branch
    correctly does) starves every OTHER stubborn component forever -- 112
    of 126 real iterations re-picked the exact same component. In the
    all-stubborn case, `attempts` breaks the tie by LEAST-retried first
    (falling back to size then min-pair when `attempts` is empty/absent),
    so retries actually rotate through the stubborn pool instead of
    fixating on one.

    Returns (pairs, free_arr, free_dep, component_id, component_size,
    is_stubborn_revisit)."""
    attempts = attempts or {}
    violated_fixable = [p for p, s in pair_slack.items() if s["total"] > 0 and p not in gamma_infeasible]
    if not violated_fixable:
        return [], set(), set(), None, 0, False

    adjacency = build_pair_adjacency(candidates, violated_fixable)
    components = connected_components(adjacency)

    non_stubborn = [c for c in components if frozenset(c) not in stubborn]
    is_stubborn_revisit = not non_stubborn
    if non_stubborn:
        pool = non_stubborn
    else:
        pool = sorted(components, key=lambda c: (attempts.get(frozenset(c), 0), len(c), min(c)))

    chosen_component = pool[0]
    component_id = frozenset(chosen_component)
    chunks = split_oversized_component(candidates, chosen_component, max_instances, seed)
    chosen_pairs = chunks[chunk_index % len(chunks)]

    free_arr, free_dep = free_instances_for_pairs(candidates, chosen_pairs)
    return chosen_pairs, free_arr, free_dep, component_id, len(chosen_component), is_stubborn_revisit

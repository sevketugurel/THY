"""Kapı-B (Γ-duyarlılık ön-tarama, docs/STATUS.md 2026-07-12): solver-free
numeric refactor of src.model.lns.compute_gamma_infeasible_pairs' core
best-case-gap computation, so a Γ sweep {45,60,90,120,150,180} can be scored
without a single MIP solve.

Three signals per Γ, all derived from candidates+journey_constants only:
    (a) static-infeasible pair count -- static_infeasible_count
    (b) baseline schedule's own E2 violation count/mass -- baseline_e2_violations
    (c) independent-pair lower bound on total E2 elastic slack -- independent_pair_lower_bound

(c) is an OPTIMISTIC lower bound: it assumes each cross-market pair can
independently reach its own best-case Jbest gap, ignoring that candidates in
DIFFERENT pairs may share flight legs (the same coupling that made the
K-subset ladder structurally ineffective, M5c docs/decisions.md). A real
solve's Σs_e2 can only be >= this number -- so if this bound is already
nonzero at some Γ, no amount of solver time will reach Σslack=0 there.
"""
from collections import defaultdict


def best_case_gap_per_pair(candidates, journey_constants: dict, L: int, U: int) -> dict:
    """Γ-independent: for each cross-market (o,d,gun) pair with both
    directions present, the best-case achievable |Jbest_fwd - Jbest_bwd|,
    computed independently per side (same box as
    compute_gamma_infeasible_pairs' best_case_j_range). Pairs missing one
    direction entirely are omitted (E2 is never built for them)."""
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

    result = {}
    for (o, d, gun) in pairs:
        r_fwd = best_case_j_range((o, d, gun))
        r_bwd = best_case_j_range((d, o, gun))
        if r_fwd is None or r_bwd is None:
            continue
        result[(o, d, gun)] = max(0.0, r_fwd[0] - r_bwd[1], r_bwd[0] - r_fwd[1])
    return result


def static_infeasible_count(pair_gaps: dict, gamma: int) -> int:
    """(a): pairs whose best-case gap still exceeds gamma -- no candidate
    selection, however favorable, can satisfy E2 for these."""
    return sum(1 for g in pair_gaps.values() if g > gamma)


def independent_pair_lower_bound(pair_gaps: dict, gamma: int) -> float:
    """(c): sum over all pairs of max(0, best_gap - gamma) -- see module
    docstring for the coupling caveat."""
    return sum(max(0.0, g - gamma) for g in pair_gaps.values())


def baseline_e2_violations(candidates, journey_constants: dict, L: int, U: int, gamma: int) -> tuple:
    """(b): at the UNADJUSTED baseline schedule (gap_min, no candidate
    freedom used) -- how many cross-market pairs violate E2 at this gamma,
    and what's the total excess mass. Mirrors
    scripts/autopsy_baseline_violations.py's E2 decomposition, generalized
    to take gamma as a parameter. Only candidates whose baseline gap lands
    in [L,U] are forced-on (VARSAYIM-6) and considered."""
    groups = defaultdict(list)
    for c in candidates:
        if L <= c.gap_min <= U:
            groups[(c.o, c.d, c.gun)].append(c)

    journeys_by_market = {
        key: [journey_constants[(key[0], key[1])] + c.gap_min for c in cs]
        for key, cs in groups.items()
    }

    count, mass, checked = 0, 0.0, set()
    for (o, d, gun) in list(journeys_by_market.keys()):
        if (o, d, gun) in checked or (d, o, gun) not in journeys_by_market:
            continue
        checked.add((o, d, gun))
        checked.add((d, o, gun))
        jbest_fwd = min(journeys_by_market[(o, d, gun)])
        jbest_bwd = min(journeys_by_market[(d, o, gun)])
        diff = abs(jbest_fwd - jbest_bwd)
        if diff > gamma:
            count += 1
            mass += diff - gamma
    return count, mass

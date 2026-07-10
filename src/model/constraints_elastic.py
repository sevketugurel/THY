"""M5d (docs/decisions.md 2026-07-10, user's "elastik model" redirect):
slack-relaxed E1/E2 -- same machinery as constraints_balance.py's strict
add_e1_constraints/add_e2_constraints, but every inequality gets a
NonNegativeReals slack term instead of an exempt+log escape hatch. A model
built with these is feasible BY CONSTRUCTION (slack can always absorb any
violation) -- HiGHS can therefore never report "no incumbent found", only
"here is the optimal (or best-found) slack allocation", which is itself the
answer to the standing feasibility question: min slack == 0 means a truly
feasible tariff exists, min slack > 0 is a genuine unresolvability MAP
(which pairs, how much), not a guess.

Doğruluk argümanı: strict versiyonun HER kısıt yapısı (a_dir/w argmin
sandviç, Big-M türetimi, singleton-pazar fold'u) BİREBİR korunuyor --
tek fark sağ tarafa eklenen s_e1/s_e2 >= 0 terimleri. s=0 iken bu
kısıtlar strict versiyonla TAMAMEN özdeş (gevşetme değil, üstüne bir
"ödünç alma" mekanizması).
"""
from collections import defaultdict

import pyomo.environ as pyo

from src.model.big_m import derive_e2_candidate_big_ms, derive_e2_pair_big_m
from src.model.constraints_balance import _market_groups
from src.model.deviation_objective import add_deviation_tracking


def add_elastic_e1_constraints(model, candidates, alpha):
    groups = _market_groups(candidates)
    pairs, seen = [], set()
    for (o, d, gun) in groups:
        if (o, d, gun) in seen:
            continue
        if (d, o, gun) in groups:
            pairs.append((o, d, gun))
            seen.add((o, d, gun))
            seen.add((d, o, gun))

    model.E1_PAIRS = pyo.Set(initialize=pairs, dimen=3, ordered=True)
    model.s_e1 = pyo.Var(model.E1_PAIRS, domain=pyo.NonNegativeReals)

    def fwd_rule(m, o, d, gun):
        fwd = sum(m.x[i] for i in groups[(o, d, gun)])
        bwd = sum(m.x[i] for i in groups[(d, o, gun)])
        return fwd - bwd <= alpha * (fwd + bwd) + m.s_e1[o, d, gun]
    model.e1_fwd = pyo.Constraint(model.E1_PAIRS, rule=fwd_rule)

    def bwd_rule(m, o, d, gun):
        fwd = sum(m.x[i] for i in groups[(o, d, gun)])
        bwd = sum(m.x[i] for i in groups[(d, o, gun)])
        return bwd - fwd <= alpha * (fwd + bwd) + m.s_e1[o, d, gun]
    model.e1_bwd = pyo.Constraint(model.E1_PAIRS, rule=bwd_rule)

    return groups, pairs


def add_elastic_e2_constraints(model, candidates, journey_constants: dict, gamma: int):
    groups = _market_groups(candidates)
    candidate_market = {i: (c.o, c.d, c.gun) for i, c in enumerate(candidates)}

    market_j_bounds = {}
    for (o, d, gun), idxs in groups.items():
        j_los = [journey_constants[(o, d)] + candidates[i].gap_lo for i in idxs]
        j_his = [journey_constants[(o, d)] + candidates[i].gap_hi for i in idxs]
        market_j_bounds[(o, d, gun)] = (min(j_los), max(j_his))

    model.E2_MARKETS = pyo.Set(initialize=list(groups.keys()), dimen=3, ordered=True)

    # M5c fold reused as-is (docs/lp_anatomy.md öncelik #2): singleton
    # pazar-yönleri için a_dir/w gerçek değişken değil, x[i]'ye katlanan
    # Expression -- gerçek bir seçim özgürlüğü olmadığından slack ile
    # ilişkisi yok, aynen taşınıyor.
    singleton_markets = {k for k, idxs in groups.items() if len(idxs) == 1}
    multi_markets = [k for k in groups if k not in singleton_markets]
    multi_candidates = [i for i in range(len(candidates)) if candidate_market[i] not in singleton_markets]

    model.A_DIR_MARKETS = pyo.Set(initialize=multi_markets, dimen=3, ordered=True)
    model.W_CANDIDATES = pyo.Set(initialize=multi_candidates, ordered=True)
    model._a_dir_var = pyo.Var(model.A_DIR_MARKETS, domain=pyo.Binary)
    model._w_var = pyo.Var(model.W_CANDIDATES, domain=pyo.Binary)

    def a_dir_expr_rule(m, o, d, gun):
        if (o, d, gun) in singleton_markets:
            return m.x[groups[(o, d, gun)][0]]
        return m._a_dir_var[o, d, gun]
    model.a_dir = pyo.Expression(model.E2_MARKETS, rule=a_dir_expr_rule)

    def w_expr_rule(m, i):
        if candidate_market[i] in singleton_markets:
            return m.x[i]
        return m._w_var[i]
    model.w = pyo.Expression(model.CANDIDATES, rule=w_expr_rule)

    def jbest_bounds_rule(m, o, d, gun):
        return market_j_bounds[(o, d, gun)]
    # M5d fix (docs/decisions.md 2026-07-10): same fix as the strict
    # add_e2_constraints -- Jbest must be continuous, not Integers (see
    # ultrathink there).
    model.Jbest = pyo.Var(model.E2_MARKETS, domain=pyo.Reals, bounds=jbest_bounds_rule)

    def a_lb_rule(m, i):
        o, d, gun = candidate_market[i]
        return m._a_dir_var[o, d, gun] >= m.x[i]
    model.e2_a_lb = pyo.Constraint(model.W_CANDIDATES, rule=a_lb_rule)

    def a_ub_rule(m, o, d, gun):
        return m._a_dir_var[o, d, gun] <= sum(m.x[i] for i in groups[(o, d, gun)])
    model.e2_a_ub = pyo.Constraint(model.A_DIR_MARKETS, rule=a_ub_rule)

    def w_sum_rule(m, o, d, gun):
        return sum(m._w_var[i] for i in groups[(o, d, gun)]) == m._a_dir_var[o, d, gun]
    model.e2_w_sum = pyo.Constraint(model.A_DIR_MARKETS, rule=w_sum_rule)

    def w_le_x_rule(m, i):
        return m._w_var[i] <= m.x[i]
    model.e2_w_le_x = pyo.Constraint(model.W_CANDIDATES, rule=w_le_x_rule)

    e2_candidate_ms = {}
    for i, c in enumerate(candidates):
        o, d, gun = candidate_market[i]
        jd_lo, jd_hi = market_j_bounds[(o, d, gun)]
        e2_candidate_ms[i] = derive_e2_candidate_big_ms(c, journey_constants[(o, d)], jd_lo, jd_hi)

    def jbest_le_rule(m, i):
        o, d, gun = candidate_market[i]
        m_up, _ = e2_candidate_ms[i]
        j_pi = journey_constants[(o, d)] + m.gap[i]
        return m.Jbest[o, d, gun] <= j_pi + m_up * (1 - m.x[i])
    model.e2_jbest_le = pyo.Constraint(model.CANDIDATES, rule=jbest_le_rule)

    def jbest_ge_rule(m, i):
        o, d, gun = candidate_market[i]
        _, m_down = e2_candidate_ms[i]
        j_pi = journey_constants[(o, d)] + m.gap[i]
        return m.Jbest[o, d, gun] >= j_pi - m_down * (1 - m.w[i])
    model.e2_jbest_ge = pyo.Constraint(model.CANDIDATES, rule=jbest_ge_rule)

    all_pairs, seen = [], set()
    for (o, d, gun) in groups:
        if (o, d, gun) in seen:
            continue
        if (d, o, gun) in groups:
            all_pairs.append((o, d, gun))
            seen.add((o, d, gun))
            seen.add((d, o, gun))

    model.E2_PAIRS = pyo.Set(initialize=all_pairs, dimen=3, ordered=True)
    model.s_e2 = pyo.Var(model.E2_PAIRS, domain=pyo.NonNegativeReals)

    pair_ms = {}
    for (o, d, gun) in all_pairs:
        jd_lo_fwd, jd_hi_fwd = market_j_bounds[(o, d, gun)]
        jd_lo_bwd, jd_hi_bwd = market_j_bounds[(d, o, gun)]
        m_fwd = derive_e2_pair_big_m(jd_hi_fwd, jd_lo_bwd, gamma)
        m_bwd = derive_e2_pair_big_m(jd_hi_bwd, jd_lo_fwd, gamma)
        pair_ms[o, d, gun] = (m_fwd, m_bwd)

    def e2_fwd_rule(m, o, d, gun):
        m_fwd, _ = pair_ms[o, d, gun]
        return (m.Jbest[o, d, gun] - m.Jbest[d, o, gun]
                <= gamma + m_fwd * (2 - m.a_dir[o, d, gun] - m.a_dir[d, o, gun]) + m.s_e2[o, d, gun])
    model.e2_fwd = pyo.Constraint(model.E2_PAIRS, rule=e2_fwd_rule)

    def e2_bwd_rule(m, o, d, gun):
        _, m_bwd = pair_ms[o, d, gun]
        return (m.Jbest[d, o, gun] - m.Jbest[o, d, gun]
                <= gamma + m_bwd * (2 - m.a_dir[o, d, gun] - m.a_dir[d, o, gun]) + m.s_e2[o, d, gun])
    model.e2_bwd = pyo.Constraint(model.E2_PAIRS, rule=e2_bwd_rule)

    return all_pairs


def add_elastic_feasibility_objective(model, epsilon: float = 1e-6):
    """min Sum(s_e1)+Sum(s_e2) [+ epsilon*total_deviation as a tie-breaker
    only -- epsilon is NOT a formal lexicographic guarantee, just small
    enough that slack dominates in practice for this problem's scale
    (docs/decisions.md 2026-07-10)]. Requires add_elastic_e1_constraints
    and/or add_elastic_e2_constraints to have already run (at least one of
    model.s_e1/model.s_e2 must exist)."""
    if hasattr(model, "objective"):
        model.del_component(model.objective)

    slack_terms = []
    if hasattr(model, "s_e1"):
        slack_terms += [model.s_e1[k] for k in model.s_e1]
    if hasattr(model, "s_e2"):
        slack_terms += [model.s_e2[k] for k in model.s_e2]
    if not slack_terms:
        raise ValueError("add_elastic_feasibility_objective requires s_e1 and/or s_e2 to exist")

    model.total_slack = pyo.Expression(expr=sum(slack_terms))
    add_deviation_tracking(model)
    model.objective = pyo.Objective(
        expr=model.total_slack + epsilon * model.total_deviation, sense=pyo.minimize,
    )

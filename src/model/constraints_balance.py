"""E1/E2 (yönsel denge) kısıt grupları.

Doğruluk argümanları için bkz. tests/solve/test_m4_constraints_e1.py ve
test_m4_constraints_e2.py docstring.
"""
from collections import defaultdict

import pyomo.environ as pyo

from src.model.big_m import derive_e2_candidate_big_ms, derive_e2_pair_big_m


def _market_groups(candidates):
    groups = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[(c.o, c.d, c.gun)].append(i)
    return groups


def add_e1_constraints(model, candidates, alpha: float):
    """n_fwd,n_bwd zaten Sum(x_pi) -- Big-M/reifikasyon gerekmiyor, doğrudan
    lineer iki-yönlü mutlak-değer eşitsizliği. Yalnızca HER İKİ yönde de
    candidate'ı olan pazar çiftlerine uygulanır -- tek-yönlü pazarlar (bwd
    modelin kapsamı dışındaysa) VARSAYIM gereği atlanır (ASSUMPTIONS.md)."""
    groups = _market_groups(candidates)

    pairs = []
    seen = set()
    for (o, d, gun) in groups:
        if (o, d, gun) in seen:
            continue
        if (d, o, gun) in groups:
            pairs.append((o, d, gun))
            seen.add((o, d, gun))
            seen.add((d, o, gun))

    model.E1_PAIRS = pyo.Set(initialize=pairs, dimen=3, ordered=True)

    def fwd_rule(m, o, d, gun):
        fwd = sum(m.x[i] for i in groups[(o, d, gun)])
        bwd = sum(m.x[i] for i in groups[(d, o, gun)])
        return fwd - bwd <= alpha * (fwd + bwd)
    model.e1_fwd = pyo.Constraint(model.E1_PAIRS, rule=fwd_rule)

    def bwd_rule(m, o, d, gun):
        fwd = sum(m.x[i] for i in groups[(o, d, gun)])
        bwd = sum(m.x[i] for i in groups[(d, o, gun)])
        return bwd - fwd <= alpha * (fwd + bwd)
    model.e1_bwd = pyo.Constraint(model.E1_PAIRS, rule=bwd_rule)

    return groups, pairs


def add_e2_constraints(model, candidates, journey_constants: dict, gamma: int):
    """Doğruluk argümanı: bkz. tests/solve/test_m4_constraints_e2.py modül
    docstring'i (tam argüman orada). Özet: Jbest bir "argmin sandviç" ile
    inşa edilir (D'nin OR-aggregation'ından farklı -- burada bir SEÇİLEBİLİR
    minimum gerekiyor, MIP'in doğal min() operatörü yok). a_dir (aktivasyon)
    D'nin beaten_k desenindeki OR-aggregation ile birebir aynı yapı. Tüm
    Big-M'ler candidate/market-bazlı türetilir (src.model.big_m), global
    sabit YOK. Gerektirir: model.x, model.gap (add_b_constraints'ten)."""
    groups = _market_groups(candidates)
    candidate_market = {i: (c.o, c.d, c.gun) for i, c in enumerate(candidates)}

    market_j_bounds = {}
    for (o, d, gun), idxs in groups.items():
        j_los = [journey_constants[(o, d)] + candidates[i].gap_lo for i in idxs]
        j_his = [journey_constants[(o, d)] + candidates[i].gap_hi for i in idxs]
        market_j_bounds[(o, d, gun)] = (min(j_los), max(j_his))

    model.E2_MARKETS = pyo.Set(initialize=list(groups.keys()), dimen=3, ordered=True)
    model.a_dir = pyo.Var(model.E2_MARKETS, domain=pyo.Binary)
    model.w = pyo.Var(model.CANDIDATES, domain=pyo.Binary)

    def jbest_bounds_rule(m, o, d, gun):
        return market_j_bounds[(o, d, gun)]
    model.Jbest = pyo.Var(model.E2_MARKETS, domain=pyo.Integers, bounds=jbest_bounds_rule)

    def a_lb_rule(m, i):
        o, d, gun = candidate_market[i]
        return m.a_dir[o, d, gun] >= m.x[i]
    model.e2_a_lb = pyo.Constraint(model.CANDIDATES, rule=a_lb_rule)

    def a_ub_rule(m, o, d, gun):
        return m.a_dir[o, d, gun] <= sum(m.x[i] for i in groups[(o, d, gun)])
    model.e2_a_ub = pyo.Constraint(model.E2_MARKETS, rule=a_ub_rule)

    def w_sum_rule(m, o, d, gun):
        return sum(m.w[i] for i in groups[(o, d, gun)]) == m.a_dir[o, d, gun]
    model.e2_w_sum = pyo.Constraint(model.E2_MARKETS, rule=w_sum_rule)

    def w_le_x_rule(m, i):
        return m.w[i] <= m.x[i]
    model.e2_w_le_x = pyo.Constraint(model.CANDIDATES, rule=w_le_x_rule)

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

    pairs = []
    seen = set()
    for (o, d, gun) in groups:
        if (o, d, gun) in seen:
            continue
        if (d, o, gun) in groups:
            pairs.append((o, d, gun))
            seen.add((o, d, gun))
            seen.add((d, o, gun))
    model.E2_PAIRS = pyo.Set(initialize=pairs, dimen=3, ordered=True)

    pair_ms = {}
    for (o, d, gun) in pairs:
        jd_lo_fwd, jd_hi_fwd = market_j_bounds[(o, d, gun)]
        jd_lo_bwd, jd_hi_bwd = market_j_bounds[(d, o, gun)]
        m_fwd = derive_e2_pair_big_m(jd_hi_fwd, jd_lo_bwd, gamma)
        m_bwd = derive_e2_pair_big_m(jd_hi_bwd, jd_lo_fwd, gamma)
        pair_ms[o, d, gun] = (m_fwd, m_bwd)

    def e2_fwd_rule(m, o, d, gun):
        m_fwd, _ = pair_ms[o, d, gun]
        return m.Jbest[o, d, gun] - m.Jbest[d, o, gun] <= gamma + m_fwd * (2 - m.a_dir[o, d, gun] - m.a_dir[d, o, gun])
    model.e2_fwd = pyo.Constraint(model.E2_PAIRS, rule=e2_fwd_rule)

    def e2_bwd_rule(m, o, d, gun):
        _, m_bwd = pair_ms[o, d, gun]
        return m.Jbest[d, o, gun] - m.Jbest[o, d, gun] <= gamma + m_bwd * (2 - m.a_dir[o, d, gun] - m.a_dir[d, o, gun])
    model.e2_bwd = pyo.Constraint(model.E2_PAIRS, rule=e2_bwd_rule)

    return pairs


def e1_diagnostics(model, candidates, result) -> list:
    """Post-solve: her E1 çifti için n_fwd/n_bwd/slack ve pazarın sıfıra
    inip inmediğini raporlar (rapora girecek metrik, plan §9)."""
    groups = _market_groups(candidates)
    diagnostics = []
    for (o, d, gun) in model.E1_PAIRS:
        n_fwd = sum(result.selected.get(candidates[i], 0) for i in groups[(o, d, gun)])
        n_bwd = sum(result.selected.get(candidates[i], 0) for i in groups[(d, o, gun)])
        diagnostics.append({
            "o": o, "d": d, "gun": gun, "n_fwd": n_fwd, "n_bwd": n_bwd,
            "suppressed_to_zero": n_fwd == 0 and n_bwd == 0,
        })
    return diagnostics

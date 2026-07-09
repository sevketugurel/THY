"""E1/E2 (yönsel denge) kısıt grupları.

Doğruluk argümanları için bkz. tests/solve/test_m4_constraints_e1.py ve
test_m4_constraints_e2.py docstring.
"""
from collections import defaultdict

import pyomo.environ as pyo


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

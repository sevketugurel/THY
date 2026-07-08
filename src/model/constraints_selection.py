"""B (bağlantı uygunluğu) ve C (monoton slot) kısıt grupları.

Doğruluk argümanı (B): x_pi=1 ancak ve ancak gap_pi in [L,U] (integer dakika).
Bidirectional -- forward (x=1 => gap in [L,U]) tek başına yeterli değil, çünkü
E1/E2 (M4) devreye girince solver'a "gerçekten geçerli bir bağlantıyı gizle"
motivasyonu doğar. Backward (gap in [L,U] => x=1) bu açığı kapatır. Standart
4-kısıtlı interval reifikasyonu + yardımcı y_pi (hangi taraftan ihlal
edildiğini seçen switch), her M candidate'in KENDİ achievable range'inden
türetiliyor (src.model.big_m) -- global sabit değil, hem doğru hem sıkı.

Integer domain zorunlu: continuous zaman + epsilon=1 kombinasyonu (L-1,L) ve
(U,U+1) gap aralıklarını TÜM tarifelere yasaklardı (meşru çözüm keser); veri
zaten dakika-hassasiyetinde olduğu için integer domain kayıpsızdır.
"""
from collections import defaultdict

import pyomo.environ as pyo

from src.model.big_m import MAX_ALLOWED_BIG_M, derive_b_big_ms


def add_flight_time_variables(model, candidates):
    """Integer t_arr[r]/t_dep[r] Vars, bir tane her benzersiz (role-namespaced)
    uçuş örneği için -- birden fazla candidate aynı r'yi paylaşabilir. Rfix
    (lo==hi) örnekler .fix() ile sabitlenir, aynı kod yolunu kullanır (iki ayrı
    dal gerekmez)."""
    arr_bounds, dep_bounds = {}, {}
    for c in candidates:
        if c.r1_id in arr_bounds:
            assert arr_bounds[c.r1_id] == (c.arr_lo, c.arr_hi), f"inconsistent bounds for {c.r1_id}"
        else:
            arr_bounds[c.r1_id] = (c.arr_lo, c.arr_hi)
        if c.r2_id in dep_bounds:
            assert dep_bounds[c.r2_id] == (c.dep_lo, c.dep_hi), f"inconsistent bounds for {c.r2_id}"
        else:
            dep_bounds[c.r2_id] = (c.dep_lo, c.dep_hi)

    model.ARR_INSTANCES = pyo.Set(initialize=sorted(arr_bounds.keys()), dimen=3, ordered=True)
    model.DEP_INSTANCES = pyo.Set(initialize=sorted(dep_bounds.keys()), dimen=3, ordered=True)

    model.t_arr = pyo.Var(model.ARR_INSTANCES, domain=pyo.Integers,
                           bounds=lambda m, *r: arr_bounds[r])
    model.t_dep = pyo.Var(model.DEP_INSTANCES, domain=pyo.Integers,
                           bounds=lambda m, *r: dep_bounds[r])

    for r, (lo, hi) in arr_bounds.items():
        if lo == hi:
            model.t_arr[r].fix(lo)
    for r, (lo, hi) in dep_bounds.items():
        if lo == hi:
            model.t_dep[r].fix(lo)


def add_b_constraints(model, candidates, L: int, U: int):
    model.CANDIDATES = pyo.Set(initialize=list(range(len(candidates))), ordered=True)

    model.x = pyo.Var(model.CANDIDATES, domain=pyo.Binary)
    model.y = pyo.Var(model.CANDIDATES, domain=pyo.Binary)
    model.gap = pyo.Var(model.CANDIDATES, domain=pyo.Integers)

    def gap_def_rule(m, i):
        c = candidates[i]
        return m.gap[i] == m.t_dep[c.r2_id] - m.t_arr[c.r1_id]
    model.gap_definition = pyo.Constraint(model.CANDIDATES, rule=gap_def_rule)

    big_ms = {}
    for i, c in enumerate(candidates):
        ms = derive_b_big_ms(c, L, U)
        for m_val in ms:
            if m_val > MAX_ALLOWED_BIG_M:
                raise ValueError(
                    f"Big-M {m_val} exceeds {MAX_ALLOWED_BIG_M} for candidate {c.od} "
                    f"FlNo1={c.flno1} FlNo2={c.flno2} -- reduce adjustable_window_min "
                    f"or investigate this candidate's achievable range."
                )
        big_ms[i] = ms

    def forward_lower_rule(m, i):
        m1, _, _, _ = big_ms[i]
        return m.gap[i] >= L - m1 * (1 - m.x[i])

    def forward_upper_rule(m, i):
        _, m2, _, _ = big_ms[i]
        return m.gap[i] <= U + m2 * (1 - m.x[i])

    def backward_below_rule(m, i):
        _, _, m3, _ = big_ms[i]
        return m.gap[i] <= (L - 1) + m3 * (m.x[i] + m.y[i])

    def backward_above_rule(m, i):
        _, _, _, m4 = big_ms[i]
        return m.gap[i] >= (U + 1) - m4 * (m.x[i] + (1 - m.y[i]))

    model.b_forward_lower = pyo.Constraint(model.CANDIDATES, rule=forward_lower_rule)
    model.b_forward_upper = pyo.Constraint(model.CANDIDATES, rule=forward_upper_rule)
    model.b_backward_below = pyo.Constraint(model.CANDIDATES, rule=backward_below_rule)
    model.b_backward_above = pyo.Constraint(model.CANDIDATES, rule=backward_above_rule)


def add_c_constraints(model, candidates):
    """Modul-5 monoton slot: Sum_j s[od,d,gun,j] = Sum_{pi in market} x_pi,
    s[j+1]<=s[j]. J_max(od,gun) = |candidates(od,gun)| -- data-derived, no
    magic ceiling (Sum x_pi can never exceed the candidate count anyway, so a
    larger J_max would only add unused slot variables)."""
    groups = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[(c.o, c.d, c.gun)].append(i)

    slot_index = [
        (o, d, gun, j)
        for (o, d, gun), idxs in groups.items()
        for j in range(1, len(idxs) + 1)
    ]
    model.SLOTS = pyo.Set(initialize=slot_index, dimen=4, ordered=True)
    model.s = pyo.Var(model.SLOTS, domain=pyo.UnitInterval)

    def monotonic_rule(m, o, d, gun, j):
        j_max = len(groups[(o, d, gun)])
        if j + 1 > j_max:
            return pyo.Constraint.Skip
        return m.s[o, d, gun, j + 1] <= m.s[o, d, gun, j]
    model.c_monotonic = pyo.Constraint(model.SLOTS, rule=monotonic_rule)

    def count_rule(m, o, d, gun):
        idxs = groups[(o, d, gun)]
        j_max = len(idxs)
        return sum(m.s[o, d, gun, j] for j in range(1, j_max + 1)) == sum(m.x[i] for i in idxs)
    model.MARKETS = pyo.Set(initialize=list(groups.keys()), dimen=3, ordered=True)
    model.c_count = pyo.Constraint(model.MARKETS, rule=count_rule)

    return groups

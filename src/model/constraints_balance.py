"""E1/E2 (yönsel denge) kısıt grupları.

Doğruluk argümanları için bkz. tests/solve/test_m4_constraints_e1.py ve
test_m4_constraints_e2.py docstring.
"""
from collections import defaultdict

import pyomo.environ as pyo

from src.model.big_m import derive_e1_pair_big_m, derive_e2_candidate_big_ms, derive_e2_pair_big_m
from src.model.lns import compute_gamma_infeasible_pairs


def _market_groups(candidates):
    groups = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[(c.o, c.d, c.gun)].append(i)
    return groups


def add_e1_constraints(model, candidates, alpha: float, activation: str = "conditional"):
    """n_fwd,n_bwd zaten Sum(x_pi) -- Big-M/reifikasyon gerekmiyor, doğrudan
    lineer iki-yönlü mutlak-değer eşitsizliği. Yalnızca HER İKİ yönde de
    candidate'ı olan pazar çiftlerine uygulanır -- tek-yönlü pazarlar (bwd
    modelin kapsamı dışındaysa) VARSAYIM gereği atlanır (ASSUMPTIONS.md).

    M5c (docs/lp_anatomy.md §1, VARSAYIM-9/11'in exempt+log deseninin E1'e
    genellemesi): bir pazar çiftinin HER İKİ yönü de TAMAMEN dondurulmuşsa
    (K-subset'in Rfix'lediği, gap_lo==gap_hi -- add_b_constraints zaten
    x[i]'yi buna göre .fix() etmiş), n_fwd/n_bwd artık SABİT sayılardır,
    karar değişkeni DEĞİL. Bu sabit sayılar E1'i ihlal ediyorsa, kısıtı
    KURMAK modeli KOŞULSUZ infeasible yapar -- bu gerçek bir dengesizlik
    değil, K-subset'in kendi tractability gevşetmesinin bir yan etkisi
    (aynen VARSAYIM-9'un G için, VARSAYIM-11'in A için yaptığı gibi). Bu
    çift MUAF tutulur + loglanır. KARIŞIK (bir taraf hâlâ ayarlanabilir)
    çiftler her zaman kurulur -- orada gerçek bir seçim özgürlüğü var.

    KARAR-0 (docs/CLOSING_PLAN.md, VARSAYIM-16, M5f): `activation="conditional"`
    (varsayılan) modda E1 yalnızca HER İKİ yön de AKTİFKEN (>=1 sunulan
    bağlantı, yani n_fwd>=1 VE n_bwd>=1) bağlayıcıdır -- brief §7'nin ipucu
    ("koşullu... aksi halde pasif yönler dengeyi yapay olarak zorlar") ve
    ampirik kanıt (organizatörün kendi baseline'ı literal okumada 690
    pair-gün ihlalli; ulaşılan her noktada E1 fazlalık oranı sabit
    0.800=1-alpha, yani ihlallerin ~tamamı tek-yön-sıfır vakası). Aktivasyon
    göstergesi E2'nin `model.a_dir`'i YENİDEN KULLANILIR (satır/binary
    ekonomisi) -- bu fonksiyon çağrılmadan ÖNCE add_e2_constraints'in
    çalışmış olması ŞARTTIR. `activation="unconditional"` eski literal
    okumayı duyarlılık analizi olarak korur (M terimi eklenmez, davranış
    bu fonksiyonun önceki sürümüyle BİREBİR aynı)."""
    if activation not in ("conditional", "unconditional"):
        raise ValueError(f"add_e1_constraints: unknown activation mode {activation!r}")
    if activation == "conditional" and not hasattr(model, "a_dir"):
        raise RuntimeError(
            "add_e1_constraints(activation='conditional') requires add_e2_constraints "
            "to have already run on this model (needs model.a_dir)."
        )

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

    def _is_fully_frozen(idxs):
        return all(model.x[i].fixed for i in idxs)

    def _frozen_count(idxs):
        return sum(int(pyo.value(model.x[i])) for i in idxs)

    genuine_pairs = []
    exempted_count = 0
    for (o, d, gun) in pairs:
        fwd_idxs, bwd_idxs = groups[(o, d, gun)], groups[(d, o, gun)]
        if _is_fully_frozen(fwd_idxs) and _is_fully_frozen(bwd_idxs):
            n_fwd, n_bwd = _frozen_count(fwd_idxs), _frozen_count(bwd_idxs)
            if activation == "conditional" and (n_fwd == 0 or n_bwd == 0):
                continue  # one side inactive -- conditional gate makes this trivially non-binding
            if n_fwd + n_bwd == 0 or abs(n_fwd - n_bwd) <= alpha * (n_fwd + n_bwd):
                continue  # trivially satisfied by fixed values -- redundant row, skip
            exempted_count += 1
            continue  # unconditionally violated by frozen values alone -- exempt
        genuine_pairs.append((o, d, gun))

    if exempted_count:
        print(
            f"WARNING: E1 -- {exempted_count} market pair(s) exempted (M5c): "
            f"fully K-subset-frozen and unreconcilable, no adjustable freedom exists.",
            flush=True,
        )

    model.E1_PAIRS = pyo.Set(initialize=genuine_pairs, dimen=3, ordered=True)
    model._e1_fold_counts = {"exempted": exempted_count, "genuine": len(genuine_pairs)}
    model._e1_activation = activation

    pair_big_ms = {}
    if activation == "conditional":
        for (o, d, gun) in genuine_pairs:
            pair_big_ms[(o, d, gun)] = derive_e1_pair_big_m(
                alpha, len(groups[(o, d, gun)]), len(groups[(d, o, gun)]),
            )

    def fwd_rule(m, o, d, gun):
        fwd = sum(m.x[i] for i in groups[(o, d, gun)])
        bwd = sum(m.x[i] for i in groups[(d, o, gun)])
        if activation == "unconditional":
            return fwd - bwd <= alpha * (fwd + bwd)
        M = pair_big_ms[(o, d, gun)]
        return fwd - bwd <= alpha * (fwd + bwd) + M * (2 - m.a_dir[o, d, gun] - m.a_dir[d, o, gun])
    model.e1_fwd = pyo.Constraint(model.E1_PAIRS, rule=fwd_rule)

    def bwd_rule(m, o, d, gun):
        fwd = sum(m.x[i] for i in groups[(o, d, gun)])
        bwd = sum(m.x[i] for i in groups[(d, o, gun)])
        if activation == "unconditional":
            return bwd - fwd <= alpha * (fwd + bwd)
        M = pair_big_ms[(o, d, gun)]
        return bwd - fwd <= alpha * (fwd + bwd) + M * (2 - m.a_dir[o, d, gun] - m.a_dir[d, o, gun])
    model.e1_bwd = pyo.Constraint(model.E1_PAIRS, rule=bwd_rule)

    return groups, pairs


def add_e2_constraints(model, candidates, journey_constants: dict, gamma: int, L: int, U: int):
    """Doğruluk argümanı: bkz. tests/solve/test_m4_constraints_e2.py modül
    docstring'i (tam argüman orada). Özet: Jbest bir "argmin sandviç" ile
    inşa edilir (D'nin OR-aggregation'ından farklı -- burada bir SEÇİLEBİLİR
    minimum gerekiyor, MIP'in doğal min() operatörü yok). a_dir (aktivasyon)
    D'nin beaten_k desenindeki OR-aggregation ile birebir aynı yapı. Tüm
    Big-M'ler candidate/market-bazlı türetilir (src.model.big_m), global
    sabit YOK. Gerektirir: model.x, model.gap (add_b_constraints'ten).

    KARAR-0b (docs/CLOSING_PLAN.md, VARSAYIM-17, M5f): `L`/`U` yalnızca
    `compute_gamma_infeasible_pairs` (src.model.lns) için kullanılır --
    journey_constant asimetrisi yüzünden HANGİ seçim yapılırsa yapılsın
    (schedule-independent, veri-sabit) E2'yi asla sağlayamayan çiftleri
    statik olarak tespit eder. Bu çiftler MUAF tutulur + loglanır (A/G'nin
    VARSAYIM-9/11 exempt+log deseninin birebir uzantısı) -- K-subset-frozen
    exemption'dan (aşağıda) BAĞIMSIZ bir ikinci muafiyet kaynağı."""
    groups = _market_groups(candidates)
    candidate_market = {i: (c.o, c.d, c.gun) for i, c in enumerate(candidates)}

    market_j_bounds = {}
    for (o, d, gun), idxs in groups.items():
        j_los = [journey_constants[(o, d)] + candidates[i].gap_lo for i in idxs]
        j_his = [journey_constants[(o, d)] + candidates[i].gap_hi for i in idxs]
        market_j_bounds[(o, d, gun)] = (min(j_los), max(j_his))

    model.E2_MARKETS = pyo.Set(initialize=list(groups.keys()), dimen=3, ordered=True)

    # M5c w/a_dir fold (docs/lp_anatomy.md öncelik #2, ultrathink): bir pazar
    # yönünün TEK adayı varsa (group size==1), a_dir bu adayın x'inin
    # AYNISI olmak ZORUNDA (a_dir>=x[i] VE a_dir<=Sum(x in group)=x[i] ->
    # a_dir=x[i] cebirsel olarak), ve Sum(w)=a_dir tek terimli olduğundan
    # w[i]=a_dir=x[i] de ZORUNLU -- ayrı bir binary hiçbir yeni bilgi
    # taşımıyor (D-folding'deki AYNI desen: gerçek bir seçim özgürlüğü
    # yoksa değişken ELE). Full-data'da singleton pazar-yönleri grupların
    # %51.4'ü (3935/7656), adayların %21.7'si (3935/18118) -- K-subset'in
    # aksine burada gerçek bir yapısal fold var (bkz. `docs/decisions.md`).
    # `model.a_dir[key]`/`model.w[i]` dışarıya HER ZAMAN aynı arayüzü
    # (Expression, pyo.value() ile okunabilir) sunar -- katlanmış olsun ya
    # olmasın çağıran kod (testler, e1_diagnostics) fark etmez.
    singleton_markets = {k for k, idxs in groups.items() if len(idxs) == 1}
    multi_markets = [k for k in groups if k not in singleton_markets]
    multi_candidates = [i for i in range(len(candidates)) if candidate_market[i] not in singleton_markets]

    model.A_DIR_MARKETS = pyo.Set(initialize=multi_markets, dimen=3, ordered=True)
    model.W_CANDIDATES = pyo.Set(initialize=multi_candidates, ordered=True)
    model._a_dir_var = pyo.Var(model.A_DIR_MARKETS, domain=pyo.Binary)
    model._w_var = pyo.Var(model.W_CANDIDATES, domain=pyo.Binary)
    model._e2_fold_counts = {
        "singleton_markets": len(singleton_markets), "multi_markets": len(multi_markets),
        "singleton_candidates": len(candidates) - len(multi_candidates),
        "multi_candidates": len(multi_candidates),
    }

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
    # M5d fix (docs/decisions.md 2026-07-10): J itself is a continuous
    # quantity (journey_constant, possibly a fractional LS-estimate, plus
    # an integer gap) -- Integers domain forced Jbest to equal a fraction
    # exactly whenever a candidate was its market's argmin, which NO
    # integer can satisfy (found via a real full-data warm-start attempt:
    # ~803/1583 markets have a fractional K_od, making E2 unconditionally
    # infeasible for any argmin selection from one of them).
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

    all_pairs = []
    seen = set()
    for (o, d, gun) in groups:
        if (o, d, gun) in seen:
            continue
        if (d, o, gun) in groups:
            all_pairs.append((o, d, gun))
            seen.add((o, d, gun))
            seen.add((d, o, gun))

    # M5c (docs/lp_anatomy.md §1, VARSAYIM-9/11'in exempt+log deseninin
    # E2'ye genellemesi): bir pazar çiftinin HER İKİ yönü de TAMAMEN
    # dondurulmuşsa (K-subset'in Rfix'lediği, add_b_constraints zaten
    # x[i]'yi buna göre .fix() etmiş), o yönün Jbest'i artık SABİTTİR
    # (offered/forced adaylar arasında min -- hiçbiri offered değilse yön
    # PASİF, E2 zaten koşullu aktivasyonla bağlayıcı değil). Bu sabit
    # Jbest'ler Gamma'yı ihlal ediyorsa, kısıtı KURMAK modeli KOŞULSUZ
    # infeasible yapar -- gerçek bir dengesizlik değil, K-subset'in kendi
    # tractability gevşetmesinin bir yan etkisi. Çift MUAF tutulur + loglanır.
    def _frozen_jbest(idxs):
        offered = [i for i in idxs if model.x[i].fixed and pyo.value(model.x[i]) == 1]
        if not offered:
            return None  # inactive direction, not exempt-worthy (already non-binding via a_dir)
        c0 = candidates[offered[0]]
        return min(journey_constants[(c0.o, c0.d)] + candidates[i].gap_lo for i in offered)

    def _is_fully_frozen(idxs):
        return all(model.x[i].fixed for i in idxs)

    # KARAR-0b / VARSAYIM-17: schedule-independent static exemption -- computed
    # ONCE from candidates' own gap ranges + journey_constants, regardless of
    # any freezing state (a strictly data-level fact, not a solve-time artifact).
    statically_infeasible = compute_gamma_infeasible_pairs(candidates, journey_constants, L, U, gamma)

    pairs = []
    exempted_count = 0
    exempted_static_count = 0
    for (o, d, gun) in all_pairs:
        if (o, d, gun) in statically_infeasible:
            exempted_static_count += 1
            continue  # provably gamma-infeasible regardless of selection -- exempt, not built
        fwd_idxs, bwd_idxs = groups[(o, d, gun)], groups[(d, o, gun)]
        if _is_fully_frozen(fwd_idxs) and _is_fully_frozen(bwd_idxs):
            j_fwd, j_bwd = _frozen_jbest(fwd_idxs), _frozen_jbest(bwd_idxs)
            if j_fwd is None or j_bwd is None or abs(j_fwd - j_bwd) <= gamma:
                pairs.append((o, d, gun))  # inactive-side or within-Gamma -- safe to build (or trivially satisfied)
                continue
            exempted_count += 1
            continue  # unconditionally violated by frozen Jbest values alone -- exempt
        pairs.append((o, d, gun))

    if exempted_static_count:
        print(
            f"WARNING: E2 -- {exempted_static_count} market pair(s) exempted (KARAR-0b/VARSAYIM-17): "
            f"schedule-independent journey-constant asymmetry exceeds Gamma in the best case.",
            flush=True,
        )
    if exempted_count:
        print(
            f"WARNING: E2 -- {exempted_count} market pair(s) exempted (M5c): "
            f"fully K-subset-frozen and Gamma-unreconcilable, no adjustable freedom exists.",
            flush=True,
        )

    model.E2_PAIRS = pyo.Set(initialize=pairs, dimen=3, ordered=True)
    model._e2_fold_counts.update({
        "exempted": exempted_count, "exempted_static": exempted_static_count, "genuine": len(pairs),
    })

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

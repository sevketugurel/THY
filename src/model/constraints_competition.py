"""D (rakip yenme ve sıralama) kısıt grubu.

Doğruluk argümanı için bkz. tests/solve/test_m2_constraints_d.py docstring.
Özet: beat_{pi,k}=1 <=> J_pi<=T_comp_k. Gerçek change_ranking_input.xlsx
tablosu monotonik (0/820 grup ihlali, tests/unit/test_ranking.py) -- bu
doğruyken tek-yönlü (forward, over-claim engelleyen) zorlama yeterli, çünkü
under-claim (W monoton azalan olduğundan) objektifi asla artıramaz. Monotonluk
bozulursa `monotonic=False` ile tam bidirectional moda geçilir (ikisi de
kodda hazır, veri-güdümlü seçim `is_ranking_monotonic` ile main.py'de yapılır).

OR-aggregation (beaten_k) HER ZAMAN iki yönlü -- monotonluktan bağımsız
yapısal bir gereklilik (iç tutarlılık).

Not: bu milestone'da rank/beaten yalnızca EN AZ BİR candidate'ı olan
(o,d,gun) pazarları için hesaplanıyor (C'nin MARKETS kümesiyle aynı kapsam).
Hiç adayı olmayan pazarlar (r=N_od trivially) M3+'ta ele alınacak -- VARSAYIM,
bkz. docs/decisions.md.
"""
import pyomo.environ as pyo

from src.model.big_m import derive_d_big_ms


def add_d_constraints(model, candidates, journey_constants: dict, rival_data: dict, monotonic: bool):
    beat_pairs = []
    market_rivals = []
    for (o, d, gun) in model.MARKETS:
        rivals = rival_data.get((o, d, gun), {})
        if rivals:
            market_rivals.extend((o, d, gun, k) for k in rivals)
        for i in model.CANDIDATES:
            c = candidates[i]
            if (c.o, c.d, c.gun) != (o, d, gun):
                continue
            beat_pairs.extend((i, k) for k in rivals)

    model.BEAT_PAIRS = pyo.Set(initialize=beat_pairs, dimen=2, ordered=True)
    model.MARKET_RIVALS = pyo.Set(initialize=market_rivals, dimen=4, ordered=True)

    model.beat = pyo.Var(model.BEAT_PAIRS, domain=pyo.Binary)
    model.beaten = pyo.Var(model.MARKET_RIVALS, domain=pyo.Binary)

    big_ms = {}
    for (i, k) in beat_pairs:
        c = candidates[i]
        t_comp = rival_data[(c.o, c.d, c.gun)][k]
        big_ms[i, k] = derive_d_big_ms(c, journey_constants[(c.o, c.d)], t_comp)

    def forward_rule(m, i, k):
        c = candidates[i]
        t_comp = rival_data[(c.o, c.d, c.gun)][k]
        m_fwd, _ = big_ms[i, k]
        j_pi = journey_constants[(c.o, c.d)] + m.gap[i]
        return j_pi <= t_comp + m_fwd * (1 - m.beat[i, k])
    model.d_beat_forward = pyo.Constraint(model.BEAT_PAIRS, rule=forward_rule)

    def offer_rule(m, i, k):
        return m.beat[i, k] <= m.x[i]
    model.d_beat_requires_offer = pyo.Constraint(model.BEAT_PAIRS, rule=offer_rule)

    if not monotonic:
        def backward_rule(m, i, k):
            c = candidates[i]
            t_comp = rival_data[(c.o, c.d, c.gun)][k]
            _, m_bwd = big_ms[i, k]
            j_pi = journey_constants[(c.o, c.d)] + m.gap[i]
            return j_pi >= t_comp + 1 - m_bwd * m.beat[i, k]
        model.d_beat_backward = pyo.Constraint(model.BEAT_PAIRS, rule=backward_rule)

    def beaten_lb_flat_rule(m, i, k):
        c = candidates[i]
        return m.beaten[c.o, c.d, c.gun, k] >= m.beat[i, k]
    model.d_beaten_lb = pyo.Constraint(model.BEAT_PAIRS, rule=beaten_lb_flat_rule)

    def beaten_ub_rule(m, o, d, gun, k):
        relevant = [i for (i, kk) in beat_pairs if kk == k and (candidates[i].o, candidates[i].d, candidates[i].gun) == (o, d, gun)]
        return m.beaten[o, d, gun, k] <= sum(m.beat[i, k] for i in relevant)
    model.d_beaten_ub = pyo.Constraint(model.MARKET_RIVALS, rule=beaten_ub_rule)

    n_by_market = {}
    for (o, d, gun) in model.MARKETS:
        n_by_market[o, d, gun] = len(rival_data.get((o, d, gun), {}))

    model.rank = pyo.Expression(
        model.MARKETS,
        rule=lambda m, o, d, gun: n_by_market[o, d, gun] - sum(
            m.beaten[o, d, gun, k] for k in rival_data.get((o, d, gun), {})
        ),
    )

    return n_by_market


def add_rank_onehot(model, n_by_market: dict):
    """One-hot rank indicator per market: onehot[o,d,gun,r] for r=1..N.

    Doğruluk argümanı (kritik düzeltme, ultrathink sonrası bulundu): r =
    N - beaten formülü [0,N] aralığında değer üretebilir (TÜM rakipler
    yenilirse r=0), ama gerçek change_ranking_input.xlsx tablosunda r HİÇBİR
    ZAMAN 0 değil -- her zaman [1,N] (doğrulandı: r.min()==1 tüm N için).
    Gerçek tablo r=1'i "en iyi ulaşılabilir seviye" olarak davranıyor (N-1
    rakip yenmekle N rakip yenmek AYNI r=1 ödülünü alır, ayrı bir r=0 katmanı
    yok). Linking kısıtını EŞİTLİK olarak kurmak (r=N-beaten TAM eşitlik) bir
    infeasibility tuzağı yaratır: solver beaten=N'e ulaşırsa r=0 gerekir ama
    onehot'un r=0 karşılığı YOK -- bu da solver'ı YAPISAL OLARAK en az bir
    rakibi kasıtlı yenilmemiş bırakmaya ZORLAR (gerçekte bedava olsa bile).
    Bu CLI end-to-end testinde YAKALANDI (bağımsız validator, R4'ün gerçekte
    yenildiğini ama rapor edilmediğini tespit etti).

    Çözüm: linking'i EŞİTSİZLİK yap (r >= N-beaten). r'nin KENDİ domain'i
    zaten [1,N] (onehot aralığı), bu yüzden r>=N-beaten + r>=1 (domain'den)
    birlikte r>=max(1,N-beaten) demek. W(N,b,r) r arttıkça hiç artmadığından
    (monotonluk, tests/unit/test_ranking.py), optimizer HER ZAMAN mümkün olan
    EN KÜÇÜK r'yi seçer (en yüksek ödül) -- bu da otomatik olarak doğru
    r=max(1,N-beaten) değerine oturur, max()/min() lineerleştirmesi
    gerekmeden (C'nin monoton slot argümanıyla AYNI mantık).

    Markets with N=0 (no rivals) are skipped: rank is trivially 0, no onehot
    needed."""
    onehot_index = [
        (o, d, gun, r)
        for (o, d, gun), n in n_by_market.items() if n > 0
        for r in range(1, n + 1)
    ]
    model.RANK_ONEHOT = pyo.Set(initialize=onehot_index, dimen=4, ordered=True)
    model.rank_onehot = pyo.Var(model.RANK_ONEHOT, domain=pyo.Binary)

    active_markets = [(o, d, gun) for (o, d, gun), n in n_by_market.items() if n > 0]
    model.ACTIVE_RANK_MARKETS = pyo.Set(initialize=active_markets, dimen=3, ordered=True)

    def sum_to_one_rule(m, o, d, gun):
        n = n_by_market[o, d, gun]
        return sum(m.rank_onehot[o, d, gun, r] for r in range(1, n + 1)) == 1
    model.rank_onehot_sum = pyo.Constraint(model.ACTIVE_RANK_MARKETS, rule=sum_to_one_rule)

    def linking_rule(m, o, d, gun):
        n = n_by_market[o, d, gun]
        return sum(r * m.rank_onehot[o, d, gun, r] for r in range(1, n + 1)) >= m.rank[o, d, gun]
    model.rank_onehot_link = pyo.Constraint(model.ACTIVE_RANK_MARKETS, rule=linking_rule)

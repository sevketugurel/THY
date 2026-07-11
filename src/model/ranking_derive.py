"""M5f Kapı-5: post-hoc derivation of D's reporting fields (rank/beaten_rivals)
from a CONCRETE (x, gap) assignment -- no MIP required.

Doğruluk argümanı: add_d_constraints/add_rank_onehot'un mantığı (beat_{pi,k}=1
iff J_pi<=T_comp_k, beaten_k=OR over offered candidates, rank=max(1,N-beaten))
yalnızca bir DEĞİŞKEN olarak modellenmesi gerektiğinde (solver'ın x/gap'i
KENDİSİ seçtiği durumda) MIP reifikasyonu gerektirir. Burada x/gap ZATEN
sabit (elastic-fallback modelinin A/B/E1/E2/F/G-only sonucudur, C/D hiç
kurulmamıştır) -- aynı formülü saf Python'da doğrudan değerlendirmek yeterli
ve KESİN olarak aynı sonucu üretir (aynı reifikasyon mantığının fixed-point
özel durumu).
"""
from collections import defaultdict


def derive_ranking_results(candidates, rival_data: dict, journey_constants: dict,
                            selected: dict, gap_values: dict) -> tuple:
    """Returns (rank_values, beaten_rivals) matching src.solve.runner.SolveResult's
    own fields -- {(o,d,gun): rank} and {(o,d,gun): [beaten rival ids]}."""
    offered_by_market = defaultdict(list)
    for c, x in selected.items():
        if x == 1:
            offered_by_market[(c.o, c.d, c.gun)].append(c)

    rank_values, beaten_rivals = {}, {}
    for (o, d, gun), rivals in rival_data.items():
        n = len(rivals)
        if n == 0:
            continue
        beaten = set()
        for c in offered_by_market.get((o, d, gun), []):
            gap = gap_values.get(c, c.gap_min)
            journey = journey_constants[(o, d)] + gap
            for rival_id, t_comp in rivals.items():
                if journey <= t_comp:
                    beaten.add(rival_id)
        rank_values[(o, d, gun)] = max(1, n - len(beaten))
        beaten_rivals[(o, d, gun)] = sorted(beaten)
    return rank_values, beaten_rivals

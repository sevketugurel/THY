"""E2-conflict kırma + kontrollü market-direction kapatma (bu oturum, K1).

D1 (mimari karar, önceden verildi): bir (o,d,gun) YÖNÜNÜN tamamı kapatılır --
o yöne ait TÜM adayların model.x[i]'si build SONRASI .fix(0)'lanır. B'nin
kısıtları (constraints_selection.py::add_b_constraints) AYNEN kalır --
backward reifikasyon (b_backward_below/b_backward_above), x=0 iken gap'i
[L,U] DIŞINA zorlar (y serbest binary'si hangi tarafın seçileceğini seçer).
Böylece "uygun olan sunulmak zorunda" kuralı (B'nin kendi mantığı) ihlal
edilmez -- uygunluk saat kararıyla (t_arr/t_dep'in başka bir yöne kayması)
kaldırılır, kural bükülmez.

D2: bu yüzden bir yön ancak İÇİNDEKİ HER ADAY için achievable range'i
TAMAMEN [L,U] içinde değilse (yani NOT(gap_lo>=L AND gap_hi<=U)) kapatılabilir
-- aksi halde backward reifikasyon (gap [L,U] dışına, ama bu adayın
ULAŞABİLECEĞİ hiçbir nokta [L,U] dışında değil) sağlanamaz, model infeasible
olur. Bu, gap_lo==gap_hi olan (add_b_constraints'in kendi build-time
fold'unda zaten x=1'e sabitlenmiş) forced-on tekil adayları da kapsar --
aynı kural, ayrı bir dal gerekmez.

D3: "conflict edge" -- bir (o,d,gun) pair'inin İKİ yönü arasında, referans
noktada E1/E2 slack'i pozitifse (compute_pair_slack) bir kenar. VARSAYIM-17
muaf çiftler (compute_gamma_infeasible_pairs) kenar DEĞİL -- model zaten o
çiftler için E2 kısıtı KURMUYOR (KARAR-0b), kapatmanın çözebileceği gerçek
bir çakışma değiller.

D4: cost(dir) = rho(o,d) * max(1, n_candidates(dir)) -- rho'nun ödül
ağırlığına ve o yönün hâlâ sunabileceği bağlantı sayısına (kaybedilen
opsiyonelliğin bir vekili) orantılı. Greedy ağırlıklı-vertex-cover: kalan
kenar kaldıkça cost/uncovered_degree EN DÜŞÜK killable düğümü kapat;
eşitlik kırıcı önce referans noktadaki seçili-bağlantı sayısı (azsa ucuz,
çoksa pahalı -- azı önce kapatılır), sonra yön tuple'ının kendisi
(determinizm). Her iki ucu da unkillable olan bir kenar asla kapatılamaz --
sonsuz döngü yerine ayrı bir listede raporlanır.
"""
from collections import defaultdict


def market_direction_index(candidates) -> dict:
    """{(o,d,gun): [candidate indices]} -- bir yöndeki TÜM adaylar."""
    index = defaultdict(list)
    for i, c in enumerate(candidates):
        index[(c.o, c.d, c.gun)].append(i)
    return dict(index)


def is_direction_killable(direction_candidates: list, L: int, U: int) -> bool:
    """D2: bkz. modül docstring'i. `direction_candidates`, o yöne ait
    Candidate nesnelerinin listesi (market_direction_index'in bir değeri
    üzerinden candidates[i] ile alınır)."""
    return all(not (c.gap_lo >= L and c.gap_hi <= U) for c in direction_candidates)


def build_conflict_edges(pair_slack: dict, gamma_infeasible_pairs: set) -> list:
    """D3: her pozitif-slack (o,d,gun) pair'i için, iki yönünü birbirine
    bağlayan bir kenar -- ((o,d,gun), (d,o,gun)). `pair_slack`,
    src.model.lns.compute_pair_slack'in çıktısıdır (her pair yalnızca TEK
    bir anahtar altında görünür, iki yönü de kapsar)."""
    edges = []
    for (o, d, gun), s in pair_slack.items():
        if s["total"] <= 0:
            continue
        if (o, d, gun) in gamma_infeasible_pairs:
            continue
        edges.append(((o, d, gun), (d, o, gun)))
    return edges


def direction_cost(direction: tuple, direction_index: dict, rho: dict) -> float:
    """D4: rho(o,d) * max(1, n_candidates(direction))."""
    o, d, _gun = direction
    n_candidates = len(direction_index.get(direction, []))
    return rho.get((o, d), 0) * max(1, n_candidates)


def greedy_cover(edges: list, direction_costs: dict, killable: set, selected_count: dict = None) -> tuple:
    """D4: greedy ağırlıklı-vertex-cover. Bkz. modül docstring'i.

    Returns (deactivated: [(direction, cost), ...] kapatma sırasıyla,
    uncovered_unkillable_edges: kalan kenarların listesi -- her ikisi de
    unkillable olan kenarlar burada biter, boş liste = tam kapsama)."""
    selected_count = selected_count or {}
    remaining = list(edges)
    deactivated = []
    killed = set()

    while remaining:
        degree = defaultdict(int)
        for a, b in remaining:
            if a in killable and a not in killed:
                degree[a] += 1
            if b in killable and b not in killed:
                degree[b] += 1
        options = [d for d, deg in degree.items() if deg > 0]
        if not options:
            break

        def sort_key(d):
            return (direction_costs[d] / degree[d], selected_count.get(d, 0), d)

        chosen = min(options, key=sort_key)
        deactivated.append((chosen, direction_costs[chosen]))
        killed.add(chosen)
        remaining = [(a, b) for (a, b) in remaining if a != chosen and b != chosen]

    return deactivated, remaining


def apply_deactivation(model, direction_index: dict, directions_to_kill: list) -> int:
    """D1: build SONRASI çağrılır -- her kapatılan yöne ait TÜM adayların
    model.x[i]'sini .fix(0) yapar. B'nin kısıtları/model yapısı DEĞİŞMEZ,
    yalnızca x'in değeri. Returns kaç adayın fix'lendiği (loglama için)."""
    n_fixed = 0
    for direction in directions_to_kill:
        for i in direction_index.get(direction, []):
            model.x[i].fix(0)
            n_fixed += 1
    return n_fixed

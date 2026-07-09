"""Unit tests for src.model.day_clustering.cluster_flight_days -- M5 VARSAYIM-9
(bkz. ASSUMPTIONS.md): G'nin regularity kısıtı, gerçek veride EN AZ BİR uçuş
numarası için (TK2841, TZX-IST) KOŞULSUZ olarak tatmin edilemez -- 4 günde
03:25, 1 günde 14:10 (645dk fark), ±180dk ayarlanabilir pencereyle en fazla
2*180+15=375dk uzlaştırılabilir. Kesin (100%) okumada TÜM problem infeasible
olurdu -- bu marka olamaz (yarışma çözümsüz bir problem kurgulamaz).

Doğruluk argümanı (ultrathink, kod öncesi): bir grubun (aynı role,flno'nun
gün-örnekleri) TEK bir ortak T_ref ile uzlaştırılabilmesi ⟺ (1D Helly
özelliği, aralıklar için) HER ÖRNEĞİN kendi [baseline-w,baseline+w]
aralığının [T_ref,T_ref+X_dev] ile kesişmesi ⟺ T_ref ∈ ∩_h[baseline_h-w_h-X_dev,
baseline_h+w_h] ⟺ bu kesişim boş değil ⟺ max_h(baseline_h-w_h) -
min_h(baseline_h+w_h) <= X_dev ⟺ (tüm w_h eşit özel durumda) max(baseline)-
min(baseline) <= w_min_baseline_ornek + w_max_baseline_ornek + X_dev -- bu bir
ÇAP (diameter) koşuludur, ARDIŞIK-boşluk (single-linkage) koşulu DEĞİL: 0dk,
300dk, 600dk'lık üç nokta (window=0, X_dev=310) ARDIŞIK bakışta (300<=310 her
iki komşu çift için) tek kümeye birleşirdi, ama 0 ile 600 arasındaki 600dk'lık
GERÇEK fark 310'u aşıyor -- ortak bir 310dk'lık pencereye ASLA sığmazlar.

Algoritma: (1) dairesel eksende (mod 1440, gün-içi dakika) EN BÜYÜK boşluktan
kes (gerçek kümeleri rastgele bir kesim noktasıyla bölmemek için -- gece
yarısı sarması aynı mantıkla ele alınır, G'nin kendi _flight_cut_points'iyle
AYNI motivasyon), (2) doğrusallaştırılmış (unwrap edilmiş) diziyi soldan sağa
AÇGÖZLÜ ÇAP taraması: her nokta, KÜME BAŞLANGICINA (en küçük tod'lu üye,
sıralı taramada her zaman İLK eklenen) göre kontrol edilir -- ardışık öğeye
göre DEĞİL. Her döndürülen kümenin çap koşulunu sağladığı invariant olarak
assert edilir.

marker: unit (solver-free, pure logic).
"""
import pytest

from src.model.day_clustering import cluster_flight_days

pytestmark = pytest.mark.unit


def test_all_reconcilable_forms_single_cluster():
    # Matches existing (M3) behavior exactly when nothing is a genuine
    # outlier: identical baseline tod, trivially reconcilable.
    occ = [(1, 795, 180), (2, 800, 180), (3, 790, 180)]
    clusters = cluster_flight_days(occ, x_dev=15)
    assert len(clusters) == 1
    assert sorted(clusters[0]) == [1, 2, 3]


def test_far_outlier_splits_into_its_own_cluster():
    # TK2841-shaped: 4 occurrences at tod=205 (03:25), 1 at tod=850 (14:10).
    # window=180 each -> limit=180+180+15=375. |850-205|=645>375 -- must split.
    occ = [(2, 205, 180), (3, 205, 180), (4, 205, 180), (7, 205, 180), (5, 850, 180)]
    clusters = cluster_flight_days(occ, x_dev=15)
    assert len(clusters) == 2
    by_size = sorted(clusters, key=len)
    assert by_size[0] == [5]
    assert sorted(by_size[1]) == [2, 3, 4, 7]


def test_diameter_not_single_linkage_for_0_300_600_chain():
    # window=0 (Rfix), x_dev=310 -- each ADJACENT gap (300) is individually
    # <=310 (single-linkage would wrongly chain-merge all three), but the
    # TRUE diameter 0-to-600 is 600>310 -- must split after the 2nd point.
    occ = [(1, 0, 0), (2, 300, 0), (3, 600, 0)]
    clusters = cluster_flight_days(occ, x_dev=310)
    assert clusters == [[1, 2], [3]]


def test_midnight_wraparound_does_not_split_a_true_cluster():
    # 23:50 (1430) and 00:10 (10) are only 20min apart circularly -- a naive
    # linear (non-circular) view would see them as 1420min apart and wrongly
    # split them. window=10 each -> limit=10+10+15=35>=20 -- must merge.
    occ = [("A", 1430, 10), ("B", 10, 10)]
    clusters = cluster_flight_days(occ, x_dev=15)
    assert len(clusters) == 1
    assert sorted(clusters[0]) == ["A", "B"]


def test_single_occurrence_is_its_own_trivial_cluster():
    occ = [(1, 500, 180)]
    clusters = cluster_flight_days(occ, x_dev=15)
    assert clusters == [[1]]


def test_deterministic_across_repeated_calls():
    occ = [(3, 600, 0), (1, 0, 0), (2, 300, 0)]
    r1 = cluster_flight_days(occ, x_dev=310)
    r2 = cluster_flight_days(occ, x_dev=310)
    assert r1 == r2


def test_heterogeneous_windows_use_each_instances_own_width_not_a_global_one():
    # Non-uniform per-instance windows -- proves the limit is w_i+w_j+x_dev
    # (each instance's OWN window), not a single global w. (4,5) have LARGE
    # windows (300) which is enough to reconcile with (6)'s Rfix outlier
    # (700 vs 900: gap=200 <= 0+300+15=315) even though (6) is far from the
    # TIGHT, small-window cluster (1,2,3) (gap to 110 is 590, way past
    # anything those small windows could cover).
    occ = [
        (1, 100, 50), (2, 110, 10), (3, 105, 5),   # tight cluster, small windows
        (4, 900, 300), (5, 950, 300),               # far cluster, large windows
        (6, 700, 0),                                 # Rfix -- reconciles with (4,5) via THEIR large windows
    ]
    clusters = cluster_flight_days(occ, x_dev=15)
    all_keys = sorted(k for cluster in clusters for k in cluster)
    assert all_keys == [1, 2, 3, 4, 5, 6]
    key_to_cluster = {k: tuple(sorted(c)) for c in clusters for k in c}
    assert key_to_cluster[1] == key_to_cluster[2] == key_to_cluster[3]
    assert key_to_cluster[4] == key_to_cluster[5] == key_to_cluster[6]
    assert key_to_cluster[1] != key_to_cluster[4]

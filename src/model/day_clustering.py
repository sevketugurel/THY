"""M5 VARSAYIM-9 (ASSUMPTIONS.md): G'nin regularity kısıtı gerçek veride EN
AZ BİR uçuş numarası için KOŞULSUZ tatmin edilemez (TK2841 TZX-IST: 4 günde
03:25, 1 günde 14:10, 645dk fark -- ±180dk pencereyle en fazla 375dk
uzlaştırılabilir). Katı okuma TÜM problemi infeasible yapardı. Çözüm: her
(role,flno)'nun gün-örneklerini EN AZ sayıda "uzlaştırılabilir" kümeye ayır
-- her küme kendi içinde G'yi (bugünkü, M3 formülasyonuyla BİREBİR aynı
şekilde) sağlar, kümeler ARASINDA G hiç uygulanmaz. Tüm örnekler zaten
uzlaştırılabilirse (yaygın durum) TEK küme = M3 davranışı DEĞİŞMEDEN korunur.

Doğruluk argümanı için bkz. tests/unit/test_day_clustering.py modül
docstring'i (1D Helly özelliği ile ÇAP koşulunun türetilmesi, neden
ARDIŞIK-boşluk/single-linkage YANLIŞ, neden dairesel en-büyük-boşluktan
kesim gerekli).
"""


def cluster_flight_days(occurrences: list, x_dev: int) -> list:
    """occurrences: list of (key, baseline_tod_min, half_width_min).
    key: herhangi bir tanımlayıcı (ör. gun), hesaplamada kullanılmaz, dönüşte
      aynen geri verilir.
    baseline_tod_min: bu örneğin baseline saat-of-day'i, dakika [0,1440).
    half_width_min: bu örneğin KENDİ ayarlanabilir yarı-penceresi (Rfix
      için 0).
    x_dev: düzenlilik toleransı (dakika).

    Dönüş: küme listesi, her küme `key`lerin bir listesi. Her döndürülen
    kümenin ÇAP koşulunu sağladığı (max(tod)-min(tod) <=
    half_width(min-tod-örnek)+half_width(max-tod-örnek)+x_dev) invariant
    olarak assert edilir.
    """
    if len(occurrences) <= 1:
        return [[key for key, _, _ in occurrences]]

    sorted_occ = sorted(occurrences, key=lambda o: o[1])
    n = len(sorted_occ)

    gaps = []
    for i in range(n):
        cur_tod = sorted_occ[i][1]
        nxt_tod = sorted_occ[(i + 1) % n][1]
        gap = (nxt_tod + 1440 - cur_tod) if i == n - 1 else (nxt_tod - cur_tod)
        gaps.append(gap)
    cut_after = max(range(n), key=lambda i: gaps[i])

    linear = list(sorted_occ[cut_after + 1:]) + [
        (key, tod + 1440, hw) for (key, tod, hw) in sorted_occ[:cut_after + 1]
    ]

    clusters = []
    current = [linear[0]]
    start_tod, start_hw = linear[0][1], linear[0][2]
    for occ in linear[1:]:
        key, tod, hw = occ
        if tod - start_tod <= start_hw + hw + x_dev:
            current.append(occ)
        else:
            clusters.append(current)
            current = [occ]
            start_tod, start_hw = tod, hw
    clusters.append(current)

    for cluster in clusters:
        tods = [o[1] for o in cluster]
        min_idx = tods.index(min(tods))
        max_idx = tods.index(max(tods))
        diam = max(tods) - min(tods)
        limit = cluster[min_idx][2] + cluster[max_idx][2] + x_dev
        assert diam <= limit, (
            f"cluster diameter invariant violated: diam={diam} > limit={limit} "
            f"(keys={[o[0] for o in cluster]})"
        )

    return [[o[0] for o in cluster] for cluster in clusters]

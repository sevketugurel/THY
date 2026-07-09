"""M5 VARSAYIM-10 (ASSUMPTIONS.md): A'nın rotasyon eşleştirmesi artık "aynı
gun" DEĞİL, BASELINE KRONOLOJİSİNE dayanıyor. Doğruluk argümanı için bkz.
tests/unit/test_rotation_matching.py modül docstring'i.
"""

WEEK_PERIOD_MIN = 7 * 1440  # Gün in {1..7}, haftalık tekrarlanan desen


def _position(gun: int, tod_min: int) -> int:
    return (gun - 1) * 1440 + tod_min


def match_rotation_legs(ob_occurrences: list, ib_occurrences: list) -> list:
    """ob_occurrences/ib_occurrences: (gun, baseline_tod_min) ikilileri.
    Açgözlü, birebir eşleştirme: OB kalkışları dairesel pozisyona göre
    sıralı işlenir; her biri KULLANILMAMIŞ IB varışları arasından EN KÜÇÜK
    ileri-dairesel mesafeye (mod WEEK_PERIOD_MIN, Gün=7'den Gün=1'e sarar)
    sahip olanla eşleşir. Sayıca eşit değilse partnersiz kalanlar dönüş
    listesinde YOKTUR (çağıran taraf sayar/loglar)."""
    if not ob_occurrences or not ib_occurrences:
        return []

    ob_sorted = sorted(ob_occurrences, key=lambda o: _position(*o))
    ib_available = {ib: _position(*ib) for ib in ib_occurrences}

    matches = []
    for ob in ob_sorted:
        if not ib_available:
            break
        ob_pos = _position(*ob)
        best_ib = min(ib_available, key=lambda ib: (ib_available[ib] - ob_pos) % WEEK_PERIOD_MIN)
        matches.append((ob[0], best_ib[0]))
        del ib_available[best_ib]
    return matches

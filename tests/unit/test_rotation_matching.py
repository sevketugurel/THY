"""Unit tests for src.model.rotation_matching.match_rotation_legs -- M5
VARSAYIM-10 (bkz. ASSUMPTIONS.md): A'nın "aynı gun" eşleştirmesi, uzun
menzilli rotasyonlarda (R_o çoğu zaman 6-21 saat) GERÇEK dönüş bacağını
DEĞİL, GENELLİKLE tamamen alakasız bir rotasyonu eşliyordu -- gerçek veride
1496 rotasyon-çift örneğinin 818'i (%54.7) baseline'da uzlaştırılamaz,
%45.3'ü KRONOLOJİK OLARAK TERS (IB varışı OB kalkışından ÖNCE).

Doğruluk argümanı (ultrathink, kod öncesi): Flight Pair'deki (OB_flno,
IB_flno) çifti "aynı uçak gidip-döner" ilişkisini ifade ediyor -- doğru
eşleştirme R_o'nun (LS-tahminli, hataya açık) DEĞİL, BASELINE
KRONOLOJİSİNİN kendisinin işi olmalı: her OB kalkışının GERÇEK partneri,
o kalkıştan SONRAKİ EN YAKIN IB varışıdır (`gun` haftalık TEKRARLANAN bir
desen olduğundan -- Gün∈{1..7} -- dairesel/wrap-around: Gün=7'den sonra
Gün=1'e sarar, G'nin gece-yarısı sarmasıyla AYNI motivasyon ama GÜNLÜK
değil HAFTALIK periyotta). Kısa menzilde (aynı gün içinde döner) bu kural
zaten "aynı gun" ile AYNI sonucu verir -- M3 davranışı korunur.

Eşleştirme AÇGÖZLÜ ve BİREBİR: her OB kalkışı, KULLANILMAMIŞ IB varışları
arasından EN KÜÇÜK ileri-dairesel mesafeye sahip olanla eşleşir. Sayıca
eşit değillerse (nadir), partnersiz kalan uçlar kısıtsız bırakılır
(sayıları loglanır, sessizce yok sayılmaz).

marker: unit (solver-free, pure logic).
"""
import pytest

from src.model.rotation_matching import match_rotation_legs

pytestmark = pytest.mark.unit


def test_short_haul_matches_same_gun():
    # OB gun=1 tod=500, IB gun=1 tod=700 (same-day round trip, small gap) --
    # must reproduce M3's "same gun" behavior for the common short-haul case.
    ob = [(1, 500)]
    ib = [(1, 700)]
    matches = match_rotation_legs(ob, ib)
    assert matches == [(1, 1)]


def test_long_haul_matches_later_day_not_same_gun():
    # OB gun=1 tod=950 (15:50). IB has an occurrence on gun=1 tod=660 (11:00
    # -- BEFORE the departure, chronologically backwards, a same-gun match
    # would wrongly pick this) and gun=3 tod=660 (forward, ~2590min later --
    # the TRUE next available return). Must pick gun=3, not gun=1.
    ob = [(1, 950)]
    ib = [(1, 660), (3, 660)]
    matches = match_rotation_legs(ob, ib)
    assert matches == [(1, 3)]


def test_weekend_wraparound_to_next_cycle():
    # OB on gun=7 (last day of the week), IB's only occurrence is gun=1 --
    # the recurring weekly schedule means gun=7's return is "next week's
    # gun=1," reachable by wrapping past the gun=7/gun=1 boundary (same
    # spirit as G's midnight wraparound, but over the weekly cycle).
    ob = [(7, 100)]
    ib = [(1, 200)]
    matches = match_rotation_legs(ob, ib)
    assert matches == [(7, 1)]


def test_kul_shaped_example_matches_hand_calc():
    # Real TK174(OB)/TK175(IB) shape (KUL): OB flies guns 1,2,3,4,6 at
    # tod=950 (15:50); IB flies guns 1,3,4,5,6 at tod=660 (11:00). Hand-
    # verified (see docs/decisions.md): every OB matches an IB exactly
    # 2 guns later (consistent ~2590min gap each time), wrapping gun=6->1.
    ob = [(1, 950), (2, 950), (3, 950), (4, 950), (6, 950)]
    ib = [(1, 660), (3, 660), (4, 660), (5, 660), (6, 660)]
    matches = match_rotation_legs(ob, ib)
    assert sorted(matches) == sorted([(1, 3), (2, 4), (3, 5), (4, 6), (6, 1)])


def test_unequal_counts_leaves_some_unmatched():
    # 2 OB, 1 IB -- ob(1,100) is processed first (smallest position) and
    # takes the sole IB (forward distance 100); ob(2,100) then has no
    # available partner and is correctly left unmatched.
    ob = [(1, 100), (2, 100)]
    ib = [(1, 200)]
    matches = match_rotation_legs(ob, ib)
    assert matches == [(1, 1)]


def test_no_ib_occurrence_reused():
    ob = [(1, 100), (2, 100), (3, 100)]
    ib = [(1, 150), (2, 150), (3, 150)]
    matches = match_rotation_legs(ob, ib)
    matched_ib_guns = [m[1] for m in matches]
    assert len(matched_ib_guns) == len(set(matched_ib_guns))


def test_empty_inputs_produce_no_matches():
    assert match_rotation_legs([], [(1, 100)]) == []
    assert match_rotation_legs([(1, 100)], []) == []
    assert match_rotation_legs([], []) == []


def test_deterministic_across_repeated_calls():
    ob = [(3, 950), (1, 950), (6, 950)]
    ib = [(5, 660), (1, 660), (4, 660)]
    r1 = match_rotation_legs(ob, ib)
    r2 = match_rotation_legs(ob, ib)
    assert r1 == r2

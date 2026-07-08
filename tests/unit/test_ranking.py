"""Unit tests for src.data.ranking -- W(r) monotonicity check + b_od derivation.

Doğruluk argümanı (monotonluk, ultrathink kod öncesi): r_od,h = N_od,h -
(yenilen rakip sayısı). r KÜÇÜLDÜKÇE rekabetçi konum İYİLEŞİR (daha çok rakip
yenildi). Eğer W(N,b,r), sabit (N,b) için r arttıkça HİÇ ARTMIYORSA (weakly
decreasing), optimal bir çözüm objektifi maksimize ederken DOĞAL olarak
mümkün olduğunca çok rakibi yenmeye çalışır -- under-claim (gerçekte yenilen
bir rakibi yenilmemiş göstermek) objektifi ASLA artıramaz, dolayısıyla
beat_{pi,k}'yi yalnızca FORWARD yönde zorlamak (over-claim engellenir) yeterli
olur, backward zorlamaya gerek kalmaz (daha az kısıt, Performans kazancı).
Eğer monotonluk BOZULURSA bu argüman çöker -- sistem otomatik çift-yönlü
(tam biconditional) moda geçmeli.

Doğruluk argümanı (b_od): TK'nin BASELINE (mevcut/optimize-edilmemiş) en iyi
itinerary'sinin, D kısıtının AYNI <= kuralıyla (Jpi <= Tcomp yenilmiş sayılır)
kaç rakibi yendiği sayılır; b_od = N - (baseline'da yenilen rakip sayısı).
Bu, r'nin AYNI formülünün baseline zamanına uygulanmış hali -- b_od ayrı bir
kural değil, r formülünün "optimizasyon öncesi" fotoğrafı.

marker: unit (solver-free, pure logic).
"""
from pathlib import Path

import pandas as pd
import pytest

from src.data.loaders import load_change_ranking, load_od_table
from src.data.ranking import compute_baseline_best_journey, derive_b_od, is_ranking_monotonic

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.unit


def test_real_change_ranking_table_is_monotonic():
    # Confirmed by inspection: 0 violations across all 820 (N,b) groups in the
    # real competition file -- single-directional forcing is safe to use.
    df = load_change_ranking(FIXDIR.parent.parent / "data_raw" / "change_ranking_input.xlsx")
    assert is_ranking_monotonic(df)


def test_synthetic_fixture_table_is_monotonic():
    df = load_change_ranking(FIXDIR / "synthetic_change_ranking_input.xlsx")
    assert is_ranking_monotonic(df)


def test_detects_monotonicity_violation():
    df = pd.DataFrame([
        {"n": 2, "b": 1, "r": 1, "weight": 1.0},
        {"n": 2, "b": 1, "r": 2, "weight": 1.5},  # INCREASES with r -- violation
    ])
    assert not is_ranking_monotonic(df)


def test_flat_weights_count_as_monotonic():
    # Weakly decreasing allows equal consecutive weights.
    df = pd.DataFrame([
        {"n": 2, "b": 1, "r": 1, "weight": 1.0},
        {"n": 2, "b": 1, "r": 2, "weight": 1.0},
    ])
    assert is_ranking_monotonic(df)


def test_derive_b_od_matches_fixture_hand_calc():
    # ZZA-ZZB baseline best = MI1xMO2, J=K_od(220)+gap(60)=280.
    # Rivals (from fixtures/README.md, now carrier-distinct): R1(300,beaten
    # since 280<=300), R2(250, NOT beaten since 280<=250 is false).
    # beaten_at_baseline=1 -> b_od = N(2) - 1 = 1.
    od_table = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    b_od = derive_b_od(od_table, o="ZZA", d="ZZB", gun=1, baseline_journey_min=280)
    assert b_od == 1


def test_derive_b_od_zzb_zza():
    # ZZB-ZZA baseline best = NI1xNO2, J=K_od(240)+gap(205)=445.
    # Rivals: R3(500,beaten), R4(400,not beaten), R5(445,beaten,boundary tie).
    # beaten_at_baseline=2 -> b_od = N(3) - 2 = 1.
    od_table = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    b_od = derive_b_od(od_table, o="ZZB", d="ZZA", gun=1, baseline_journey_min=445)
    assert b_od == 1


def test_compute_baseline_best_journey_zza_zzb():
    # Two valid-gap TK rows for ZZA-ZZB gun=1: MI1xMO2 (gate_to_gate=280) and
    # MI2xMO2 (gate_to_gate=520) -- min is 280.
    od_table = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    baseline = compute_baseline_best_journey(od_table, o="ZZA", d="ZZB", gun=1, L=60, U=300)
    assert baseline == 280


def test_compute_baseline_best_journey_excludes_invalid_gap_rows():
    # Only NI1xNO2 (gate_to_gate=445) has a valid baseline gap for ZZB-ZZA
    # gun=1 -- other rows are placeholder/invalid-gap discoverability rows.
    od_table = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    baseline = compute_baseline_best_journey(od_table, o="ZZB", d="ZZA", gun=1, L=60, U=300)
    assert baseline == 445


def test_compute_baseline_best_journey_returns_none_for_empty_market():
    od_table = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    baseline = compute_baseline_best_journey(od_table, o="ZZA", d="ZZB", gun=99, L=60, U=300)
    assert baseline is None

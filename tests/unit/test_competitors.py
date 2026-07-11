"""Unit tests for src.data.competitors -- N_od,h / T_comp_{od,h,k} derivation.

Doğruluk argümanı (ultrathink, kod öncesi): brief'in D kısıtı "bir rakip ancak
onu yenen en az bir bağlantı sunuluyorsa yenilmiş sayılır" diyor -- yani bir
"rakip" (rival) TEK BİR TAŞIYICI (Cr1), o taşıyıcının o (o,d,h) pazarındaki
TÜM itineraryleri (satırları) o rakibin PARÇASI, ayrı rakipler değil. TK bir
rakibi yenmek için rakibin EN İYİ (en hızlı) alternatifinden daha hızlı
olmalı -- aksi halde yolcu hala rakibin daha hızlı seçeneğini tercih eder,
"yenilmiş" sayılmaz. Bu yüzden:
  N_{od,h} = o (o,d,h) üçlüsünde en az bir TK-dışı satırı olan DİSTİNCT Cr1
             sayısı.
  T_comp_{od,h,k} = carrier k'nin o (o,d,h)'deki TÜM satırlarının
             gate-to-gate süresinin MİNİMUMU.

marker: unit (solver-free, pure logic).
"""
import datetime as dt
from pathlib import Path

import openpyxl
import pytest

from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_od_table

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.unit


@pytest.fixture
def od_table():
    return load_od_table(FIXDIR / "synthetic_od_table.xlsx")


def test_zza_zzb_has_two_distinct_rivals(od_table):
    rivals = derive_rival_best_times(od_table, o="ZZA", d="ZZB", gun=1)
    assert rivals == {"R1": 300, "R2": 250}


def test_zzb_zza_consolidates_same_carrier_multiple_itineraries(od_table):
    # R4 has two itineraries (400, 450) -- must consolidate to min=400 and
    # NOT count as two separate rivals (N stays 3, not 4).
    rivals = derive_rival_best_times(od_table, o="ZZB", d="ZZA", gun=1)
    assert rivals == {"R3": 500, "R4": 400, "R5": 445}
    assert len(rivals) == 3


def test_excludes_tk_from_rival_set(od_table):
    rivals = derive_rival_best_times(od_table, o="ZZA", d="ZZB", gun=1)
    assert "TK" not in rivals


def test_empty_market_returns_empty_dict(od_table):
    rivals = derive_rival_best_times(od_table, o="ZZA", d="ZZB", gun=99)
    assert rivals == {}


def test_derive_rival_best_times_uses_wrap_corrected_duration(tmp_path):
    # Propagation regression (M5e, zero production changes in this file):
    # load_od_table's wrap-fix (VARSAYIM-14) flows through gate_to_gate_min
    # with no code change here. A rival row with a real >=24h journey (real
    # EZE->IST->PEK numbers, docs/decisions.md 2026-07-11) must be reported
    # at its true (unwrapped) 1720min, not the displayed 280min.
    header = [
        "Cr1", "Carrier Name", "Dep1", "Arr1", "FlNo1", "ElapsedTime1", "Arr Time",
        "Cr2", "Dep2", "Arr2", "FlNo2", "ML2", "ElapsedTime2", "Dep Time",
        "Gate-to-Gate Uçuş Süresi", "O&D", "Gün",
    ]
    arr_time = dt.datetime(2026, 1, 5, 10, 0)
    dep_time = arr_time + dt.timedelta(minutes=155)
    row = [
        "R1", "Rival Air", "EZE", "IST", 1, "30.12.1899 17:00:00", arr_time,
        "R1", "IST", "PEK", 2, "M", "30.12.1899 09:05:00", dep_time,
        dt.time(4, 40), "EZE-PEK", 1,
    ]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bağlantı Tablosu"
    ws.append(header)
    ws.append(row)
    path = tmp_path / "v2_rival.xlsx"
    wb.save(path)

    od_table = load_od_table(path)
    rivals = derive_rival_best_times(od_table, o="EZE", d="PEK", gun=1)
    assert rivals == {"R1": 1720}

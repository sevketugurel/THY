"""Unit tests for src.model.constraints_capacity -- F'in pencere-ulaşılabilir
kova ve rezidüel kapasite yardımcı fonksiyonları (solver-free, pure logic).

Doğruluk argümanı (ultrathink, kod öncesi):
- `derive_window_reachable_buckets`: bir örneğin z[r,b] binary'lerini GÜNÜN
  TÜM kovalarına (144, bucket_size=10 için) değil, yalnızca kendi [lo,hi]
  Var bounds'unun kesiştiği kovalara kısıtlamak M5 performansı için kritik
  (kullanıcının kendi tahmini: ~19/uçuş, TAM 144 değil). Kova k canonik
  olarak [k*Δ,(k+1)*Δ) aralığını temsil eder (floor division, negatif lo
  için de doğru -- Python'un // operatörü zaten floor).
- `compute_residual_capacity`: kapsam-dışı (out-of-scope) TK bacakları
  kendi ham baseline zamanlarında SABİT operasyonda kabul edilir (VARSAYIM,
  ASSUMPTIONS.md) ve o bucket'ın kapasitesinden düşülür -- model kurulmadan
  ÖNCE bir kez, tam-tarama precompute.
- `compute_out_of_scope_baselines`: ham TK tablosunu tarar, modelin
  ARR_INSTANCES/DEP_INSTANCES kapsamı DIŞINDA kalan (role,flno,gun)
  bacaklarının HAM (baseline) epoch-dakika zamanını döner -- hem F'nin
  rezidüel kapasitesi hem A'nın kısmi-kapsam rotasyon edge-case'i için
  ortak kaynak.

marker: unit.
"""
import pandas as pd
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_capacity import (
    compute_out_of_scope_baselines,
    compute_out_of_scope_baselines_from_keys,
    compute_residual_capacity,
    derive_window_reachable_buckets,
)
from src.model.constraints_selection import add_flight_time_variables

pytestmark = pytest.mark.unit


def test_derive_window_reachable_buckets_worked_example():
    # [95,114], bucket_size=10 -> bucket9=[90,99] (contains 95), bucket10=
    # [100,109], bucket11=[110,119] (contains 114) -> {9,10,11}.
    assert derive_window_reachable_buckets(95, 114, 10) == [9, 10, 11]


def test_derive_window_reachable_buckets_single_point_fixed():
    # Rfix (lo==hi=100) -> exactly one bucket.
    assert derive_window_reachable_buckets(100, 100, 10) == [10]


def test_derive_window_reachable_buckets_exact_boundary():
    # hi exactly on a bucket boundary (120) -> bucket12=[120,129] included.
    assert derive_window_reachable_buckets(110, 120, 10) == [11, 12]


def test_derive_window_reachable_buckets_negative_lo():
    # Floor division must handle negative lo correctly: -5 falls in
    # bucket -1 ([-10,0)), not bucket 0.
    assert derive_window_reachable_buckets(-5, 15, 10) == [-1, 0, 1]


def test_derive_window_reachable_buckets_is_far_smaller_than_full_day():
    # A realistic adjustable window (+-180min, width 360) must produce far
    # fewer than 144 buckets/day (bucket_size=10) -- the whole point of F's
    # window-reachable restriction (M5 performance).
    buckets = derive_window_reachable_buckets(500 - 180, 500 + 180, 10)
    assert len(buckets) < 40
    assert len(buckets) < 144


def test_compute_residual_capacity_worked_example():
    # Two out-of-scope OB legs baseline at 95 and 97 -> both in bucket 9
    # (bucket_size=10) -> occupies 2 of departure capacity there. One
    # out-of-scope IB leg at 205 -> bucket 20, occupies 1 of arrival
    # capacity there.
    out_of_scope = {
        ("OB", 1, 1): 95,
        ("OB", 2, 1): 97,
        ("IB", 3, 1): 205,
    }
    residual_dep, residual_arr = compute_residual_capacity(
        out_of_scope, bucket_size_min=10, capacity_departure=10, capacity_arrival=15,
    )
    assert residual_dep == {9: 8}
    assert residual_arr == {20: 14}


def test_compute_residual_capacity_clamped_at_zero_never_negative():
    # 3 out-of-scope legs in the same bucket, capacity_departure=2 -> would
    # go negative without clamping.
    out_of_scope = {("OB", 1, 1): 10, ("OB", 2, 1): 11, ("OB", 3, 1): 12}
    residual_dep, _ = compute_residual_capacity(
        out_of_scope, bucket_size_min=10, capacity_departure=2, capacity_arrival=15,
    )
    assert residual_dep == {1: 0}


def test_compute_residual_capacity_empty_when_no_out_of_scope_flights():
    residual_dep, residual_arr = compute_residual_capacity(
        {}, bucket_size_min=10, capacity_departure=10, capacity_arrival=15,
    )
    assert residual_dep == {}
    assert residual_arr == {}


def test_compute_out_of_scope_baselines_identifies_missing_legs():
    # Row1's legs (flno1=101,flno2=201) ARE in the model's scope (the sole
    # candidate references them). Row2's legs (flno1=102,flno2=202) are NOT
    # -- out of scope, must be reported at their RAW baseline epoch-minute.
    anchor = pd.Timestamp("2024-01-01")
    tk_rows = pd.DataFrame([
        {"dep1": "X", "flno1": 101, "arr_time": anchor + pd.Timedelta(minutes=500),
         "arr2": "Y", "flno2": 201, "dep_time": anchor + pd.Timedelta(minutes=600), "gun": 1},
        {"dep1": "X", "flno1": 102, "arr_time": anchor + pd.Timedelta(minutes=700),
         "arr2": "Z", "flno2": 202, "dep_time": anchor + pd.Timedelta(minutes=800), "gun": 1},
    ])
    c = Candidate(
        od="X-Y", o="X", d="Y", gun=1, flno1=101, flno2=201,
        r1_id=("IB", 101, 1), r2_id=("OB", 201, 1),
        arr_time=None, dep_time=None, gap_min=100,
        arr_lo=500, arr_hi=500, dep_lo=600, dep_hi=600,
        gap_lo=100, gap_hi=100,
    )
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, [c])
    baselines = compute_out_of_scope_baselines(tk_rows, model, anchor)
    assert baselines == {("IB", 102, 1): 700, ("OB", 202, 1): 800}


def test_compute_out_of_scope_baselines_empty_when_everything_in_scope():
    anchor = pd.Timestamp("2024-01-01")
    tk_rows = pd.DataFrame([
        {"dep1": "X", "flno1": 101, "arr_time": anchor + pd.Timedelta(minutes=500),
         "arr2": "Y", "flno2": 201, "dep_time": anchor + pd.Timedelta(minutes=600), "gun": 1},
    ])
    c = Candidate(
        od="X-Y", o="X", d="Y", gun=1, flno1=101, flno2=201,
        r1_id=("IB", 101, 1), r2_id=("OB", 201, 1),
        arr_time=None, dep_time=None, gap_min=100,
        arr_lo=500, arr_hi=500, dep_lo=600, dep_hi=600,
        gap_lo=100, gap_hi=100,
    )
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, [c])
    baselines = compute_out_of_scope_baselines(tk_rows, model, anchor)
    assert baselines == {}


def test_compute_out_of_scope_baselines_matches_from_keys_core():
    # M5d LNS fold-redesign (plan a-evet-ama-iki-tingly-canyon.md adım 4):
    # behavior-preserving refactor regression -- the model-based wrapper
    # must produce EXACTLY what the model-free core produces given the
    # model's own ARR_INSTANCES/DEP_INSTANCES as the in-scope sets.
    anchor = pd.Timestamp("2024-01-01")
    tk_rows = pd.DataFrame([
        {"dep1": "X", "flno1": 101, "arr_time": anchor + pd.Timedelta(minutes=500),
         "arr2": "Y", "flno2": 201, "dep_time": anchor + pd.Timedelta(minutes=600), "gun": 1},
        {"dep1": "X", "flno1": 102, "arr_time": anchor + pd.Timedelta(minutes=700),
         "arr2": "Z", "flno2": 202, "dep_time": anchor + pd.Timedelta(minutes=800), "gun": 1},
    ])
    c = Candidate(
        od="X-Y", o="X", d="Y", gun=1, flno1=101, flno2=201,
        r1_id=("IB", 101, 1), r2_id=("OB", 201, 1),
        arr_time=None, dep_time=None, gap_min=100,
        arr_lo=500, arr_hi=500, dep_lo=600, dep_hi=600,
        gap_lo=100, gap_hi=100,
    )
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, [c])
    via_model = compute_out_of_scope_baselines(tk_rows, model, anchor)
    via_keys = compute_out_of_scope_baselines_from_keys(
        tk_rows, set(model.ARR_INSTANCES), set(model.DEP_INSTANCES), anchor,
    )
    assert via_model == via_keys == {("IB", 102, 1): 700, ("OB", 202, 1): 800}

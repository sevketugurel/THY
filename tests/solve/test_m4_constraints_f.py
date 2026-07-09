"""Solve tests for F (hub kova/kapasite bağlama).

Doğruluk argümanı (ultrathink, kod öncesi): her ayarlanabilir uçuş örneği
(t_arr/t_dep) HER ZAMAN hub'da fiziksel olarak bir 10-dakikalık kovaya denk
gelir -- bu, x_pi'den (bağlantı sunuluyor mu) TAMAMEN bağımsız bir fiziksel
gerçek (uçak havaalanında bir yerde duruyor, hangi bağlantının parçası
olduğuna bakılmaksızın). Bu yüzden z[role,flno,gun,b] TÜM ARR_INSTANCES/
DEP_INSTANCES için kurulur (candidate/x_pi değil, ham flight instance
bazında), Sum_b z=1 KOŞULSUZ.

z'nin binary sayısını patlatmamak için (M5'te ~5.471 ayarlanabilir örnek x
144 kova/gün = ~788K binary olurdu) yalnızca PENCERE-ULAŞILABİLİR kovalar
(t'nin kendi [lo,hi] Var bounds'unun kesiştiği kovalar) için z tanımlanır --
`derive_window_reachable_buckets`. Bucket-time bağlama, B/D'yle aynı
Big-M reifikasyon deseni (candidate-bazlı, global sabit değil):

    t >= bucket_lo(b) - M_lo(1-z[r,b])
    t <= bucket_hi(b) + M_hi(1-z[r,b])
    Sum_b z[r,b] = 1

Kapasite (ayrı departure/arrival aileleri, ayrı kapasiteler):

    Sum_{r: b reachable} z[r,b] <= residual_capacity[b]

residual_capacity, kapsam-dışı (modelin hiç değişkeni olmayan) TK
bacaklarının kendi HAM baseline zamanlarında sabit işgal ettiği kapasiteyi
düşer (VARSAYIM, `compute_residual_capacity`) -- model kurulmadan önce bir
kez, tam-tarama precompute.

marker: solve (<60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_capacity import add_f_constraints, compute_residual_capacity
from src.model.constraints_selection import add_flight_time_variables
from src.solve.runner import solve

pytestmark = pytest.mark.solve


def _dep_candidate(flno2, dep_lo, dep_hi, o="X", d="Y", flno1=901, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun),
        arr_time=None, dep_time=None, gap_min=100,
        arr_lo=0, arr_hi=0, dep_lo=dep_lo, dep_hi=dep_hi,
        gap_lo=dep_lo, gap_hi=dep_hi,
    )


def _build(candidates, capacity_departure=10, capacity_arrival=15, residual_dep=None, residual_arr=None):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_f_constraints(
        model, bucket_size_min=10, capacity_departure=capacity_departure,
        capacity_arrival=capacity_arrival, residual_dep=residual_dep, residual_arr=residual_arr,
    )
    model._candidates = candidates
    return model


def test_f_only_creates_window_reachable_bucket_binaries():
    # A realistic +-180min window (width 360) must produce far fewer than
    # 144 z-binaries for this ONE instance -- the whole point of F's
    # window-reachable restriction (M5 performance, user's own estimate:
    # ~19/flight, NOT 144).
    c = _dep_candidate(1, dep_lo=500 - 180, dep_hi=500 + 180)
    model = _build([c])
    count = len([1 for (role, flno, gun, b) in model.DEP_Z_INDEX])
    assert count < 40
    assert count < 144


def test_f_non_binding_when_capacity_is_generous():
    # Two instances sharing a reachable bucket, ample capacity -- both
    # should be free to land wherever an adversarial objective wants.
    c1 = _dep_candidate(1, dep_lo=95, dep_hi=114)
    c2 = _dep_candidate(2, dep_lo=95, dep_hi=114)
    model = _build([c1, c2], capacity_departure=10)
    model.objective = pyo.Objective(
        expr=model.t_dep["OB", 1, 1] + model.t_dep["OB", 2, 1], sense=pyo.minimize,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.t_dep["OB", 1, 1]) == pytest.approx(95.0)
    assert pyo.value(model.t_dep["OB", 2, 1]) == pytest.approx(95.0)


def test_f_tight_capacity_forces_candidates_into_different_buckets():
    # Both instances' ONLY overlap is buckets {9,10,11} ([95,114], bucket
    # size 10). capacity_departure=1 (global) forces at most ONE flight per
    # 10-min slot. Adversarial objective wants BOTH as early as possible
    # (bucket 9, t=95) -- with cap=1, only one gets bucket 9; the other is
    # pushed to the next viable bucket (10, earliest reachable value 100).
    c1 = _dep_candidate(1, dep_lo=95, dep_hi=114)
    c2 = _dep_candidate(2, dep_lo=95, dep_hi=114)
    model = _build([c1, c2], capacity_departure=1)
    model.objective = pyo.Objective(
        expr=model.t_dep["OB", 1, 1] + model.t_dep["OB", 2, 1], sense=pyo.minimize,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    times = sorted([pyo.value(model.t_dep["OB", 1, 1]), pyo.value(model.t_dep["OB", 2, 1])])
    assert times == pytest.approx([95.0, 100.0])


def test_f_residual_capacity_from_out_of_scope_flights_reduces_room():
    # A single in-scope instance, window [95,114] (buckets {9,10,11}).
    # An out-of-scope TK flight baseline=96 (bucket 9) fully occupies
    # bucket 9's departure capacity (capacity_departure=1 there via
    # compute_residual_capacity) -- the in-scope instance is forced OUT of
    # bucket 9 even though an unconstrained objective would want t=95.
    out_of_scope = {("OB", 999, 1): 96}
    residual_dep, residual_arr = compute_residual_capacity(
        out_of_scope, bucket_size_min=10, capacity_departure=1, capacity_arrival=15,
    )
    c = _dep_candidate(1, dep_lo=95, dep_hi=114)
    model = _build([c], capacity_departure=1, residual_dep=residual_dep, residual_arr=residual_arr)
    model.objective = pyo.Objective(expr=model.t_dep["OB", 1, 1], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    # bucket 9 residual capacity = 0 (1 base - 1 out-of-scope occupant) ->
    # in-scope instance cannot use it, must land at bucket 10's floor (100).
    assert pyo.value(model.t_dep["OB", 1, 1]) == pytest.approx(100.0)


def test_f_departure_and_arrival_capacities_are_independent():
    # An IB (arrival) instance and an OB (departure) instance sharing the
    # SAME numeric bucket window must NOT compete with each other -- separate
    # z-families/capacities (departure vs arrival), per the brief's 10/15
    # split.
    c_arr = Candidate(
        od="X-Y", o="X", d="Y", gun=1, flno1=1, flno2=99999,
        r1_id=("IB", 1, 1), r2_id=("OB", 99999, 1),
        arr_time=None, dep_time=None, gap_min=100,
        arr_lo=95, arr_hi=114, dep_lo=0, dep_hi=0,
        gap_lo=-114, gap_hi=-95,
    )
    c_dep = _dep_candidate(2, dep_lo=95, dep_hi=114)
    model = _build([c_arr, c_dep], capacity_departure=1, capacity_arrival=1)
    model.objective = pyo.Objective(
        expr=model.t_arr["IB", 1, 1] + model.t_dep["OB", 2, 1], sense=pyo.minimize,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    # Both can independently claim bucket 9 (t=95) -- no cross-family
    # competition despite numerically identical bucket index.
    assert pyo.value(model.t_arr["IB", 1, 1]) == pytest.approx(95.0)
    assert pyo.value(model.t_dep["OB", 2, 1]) == pytest.approx(95.0)

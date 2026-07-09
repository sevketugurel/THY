"""Solve tests for A (rotasyon) -- aynı uçak IST->o->IST iki bacaklı görevi.

Doğruluk argümanı (ultrathink, kod öncesi): brief "Aynı uçak IST -> o -> IST
iki bacaklı bir görevi gerçekleştirir. Dönüş (inbound) IST varışı, gidişin
(outbound) IST kalkışından en az (T_OB_o + tau_o + T_IB_o) kadar sonra
olmalıdır" diyor -- KOŞULSUZ bir operasyonel kural (x_pi'ye bağlı değil, hangi
bağlantılar sunulduğundan bağımsız, sadece aynı uçağın FİZİKSEL olarak iki
yerde birden olamayacağını ifade eder). R_o = T_OB_o+T_IB_o zaten TEK bir
sağlayıcı çağrısıyla geliyor (block_times.get_rotation_constant), ayrı
T_OB/T_IB gerekmiyor:

    t_arr[IB-role, donus_flno, h] >= t_dep[OB-role, gidis_flno, h] + R_o + tau

Flight Pairs verisi flno+Pair grubu veriyor, GÜN belirtmiyor -- kısıt HER
GÜN icin, o günde HER İKİ bacağın da modelde (candidate uretiminde kullanılan
bir flight instance olarak) var olduğu durumlarda kuruluyor. Gerçek veride
Pair gruplarının çoğu (657/707) tam 2 üyeli (IST->o, o->IST); 3+ üyeli
gruplar (50/707) ara-duraklı çoklu-bacak rotasyonlar (ör. IST->MEX->CUN->IST)
olabilir -- bu M3'te yalnızca ARDIŞIK (Orig==IST) sonra (Dest==IST) bulunan
alt-çiftlere kısıt uygulanır (IST'e değmeyen ara bacaklar modelin değişken
kapsamı dışında, VARSAYIM olarak ASSUMPTIONS.md'ye işlenecek).

marker: solve (small HiGHS solve, <60s).
"""
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_operations import add_a_constraints
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300


def _rotation_candidates(dep_lo, dep_hi, dep_baseline, arr_lo, arr_hi, arr_baseline,
                          gidis_flno, donus_flno, o="ZZA", gun=1):
    # Two throwaway candidates just to get t_arr/t_dep variables created for
    # the rotation flight instances via add_flight_time_variables (which reads
    # bounds off Candidate objects) -- gap fields are irrelevant to A itself.
    c_ob = Candidate(
        od=f"IST-{o}", o="IST", d=o, gun=gun, flno1=99999, flno2=gidis_flno,
        r1_id=("IB", 99999, gun), r2_id=("OB", gidis_flno, gun),
        arr_time=None, dep_time=None, gap_min=100,
        arr_lo=0, arr_hi=0, dep_lo=dep_lo, dep_hi=dep_hi,
        gap_lo=dep_lo, gap_hi=dep_hi,
    )
    c_ib = Candidate(
        od=f"{o}-IST", o=o, d="IST", gun=gun, flno1=donus_flno, flno2=99998,
        r1_id=("IB", donus_flno, gun), r2_id=("OB", 99998, gun),
        arr_time=None, dep_time=None, gap_min=100,
        arr_lo=arr_lo, arr_hi=arr_hi, dep_lo=0, dep_hi=0,
        # gap = t_dep[OB,99998](fixed at 0) - t_arr[IB,donus] = -t_arr, so the
        # achievable gap range is the NEGATION of arr's range, not arr's range
        # itself (bug found via infeasibility diagnosis: a wrong hint here
        # corrupted derive_b_big_ms's M4, forcing t_arr=0 whenever x_ib=0 --
        # directly contradicting A's t_arr>=dep+295 requirement).
        gap_lo=-arr_hi, gap_hi=-arr_lo,
    )
    return [c_ob, c_ib]


def _build(candidates, pairs_df, r_o_lookup, tau):
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_b_constraints(model, candidates, L=L, U=U)
    add_c_constraints(model, candidates)
    add_a_constraints(model, candidates, pairs_df, r_o_lookup, tau)
    model._candidates = candidates
    return model


def _pairs_df(gidis_flno, donus_flno, o="ZZA"):
    import pandas as pd
    return pd.DataFrame([
        {"flno": gidis_flno, "orig": "IST", "dest": o, "pair": "P1"},
        {"flno": donus_flno, "orig": o, "dest": "IST", "pair": "P1"},
    ])


def test_rotation_binding_forces_minimum_gap():
    # gidis (OB) free in [0,1000]; donus (IB) free in [0,1000]. R_o=250,tau=45
    # -> min separation 295. Objective wants to MINIMIZE donus arr (adversarial:
    # would violate rotation if unconstrained) -- confirm it's forced >=295
    # after a dep of 0.
    candidates = _rotation_candidates(
        dep_lo=0, dep_hi=1000, dep_baseline=0, arr_lo=0, arr_hi=1000, arr_baseline=0,
        gidis_flno=1, donus_flno=2,
    )
    model = _build(candidates, _pairs_df(1, 2), {"ZZA": 250}, tau=45)
    model.objective = pyo.Objective(
        expr=model.t_dep["OB", 1, 1] - model.t_arr["IB", 2, 1], sense=pyo.maximize,
    )
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    dep = pyo.value(model.t_dep["OB", 1, 1])
    arr = pyo.value(model.t_arr["IB", 2, 1])
    assert arr - dep == pytest.approx(295.0)


def test_rotation_non_binding_when_gap_already_sufficient():
    # donus window already starts well after gidis window's latest possible
    # departure + R_o+tau -- constraint should not restrict anything further.
    candidates = _rotation_candidates(
        dep_lo=0, dep_hi=100, dep_baseline=0, arr_lo=1000, arr_hi=1100, arr_baseline=1000,
        gidis_flno=1, donus_flno=2,
    )
    model = _build(candidates, _pairs_df(1, 2), {"ZZA": 250}, tau=45)
    model.objective = pyo.Objective(expr=model.t_arr["IB", 2, 1], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.t_arr["IB", 2, 1]) == pytest.approx(1000.0)  # window min, unrestricted


def test_rotation_skips_station_missing_from_r_o_lookup():
    # M5 edge case (found on real full data): r_o_lookup only covers
    # stations where get_rotation_constant succeeded (main.py already
    # catches KeyError there and skips -- VARSAYIM "rotasyon verisi olmayan
    # istasyon icin A atlanir"). But add_a_constraints itself didn't apply
    # this exemption at constraint-build time -- a station present in
    # pairs_df's Flight Pairs but ABSENT from r_o_lookup crashed with a raw
    # KeyError instead of being silently skipped, both legs otherwise fully
    # in-scope.
    candidates = _rotation_candidates(
        dep_lo=0, dep_hi=1000, dep_baseline=0, arr_lo=0, arr_hi=1000, arr_baseline=0,
        gidis_flno=1, donus_flno=2,
    )
    model = _build(candidates, _pairs_df(1, 2), r_o_lookup={}, tau=45)  # ZZA missing
    model._candidates = candidates
    model.objective = pyo.Objective(expr=model.t_dep["OB", 1, 1], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    # No rotation constraint should have been built at all for this pair.
    assert len(model.ROTATION_PAIRS) == 0


def test_rotation_applies_against_out_of_scope_ib_partner_baseline():
    # M4/F edge case: donus (IB, flno=2) never became a candidate leg at all
    # (out of the model's variable scope -- e.g. no pairing survived the
    # achievable-range gate) -- it has a raw TK baseline arrival of 900
    # (epoch-min), no Pyomo t_arr variable. gidis (OB, flno=1) IS in scope,
    # free in [0,1000]. R_o=250,tau=45 -> gidis dep must be <=900-250-45=605
    # even though the rotation constraint can't reference donus as a
    # variable at all. Adversarial objective wants dep as LARGE as possible.
    c_ob = Candidate(
        od="IST-ZZA", o="IST", d="ZZA", gun=1, flno1=99999, flno2=1,
        r1_id=("IB", 99999, 1), r2_id=("OB", 1, 1),
        arr_time=None, dep_time=None, gap_min=100,
        arr_lo=0, arr_hi=0, dep_lo=0, dep_hi=1000,
        gap_lo=0, gap_hi=1000,
    )
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, [c_ob])
    add_b_constraints(model, [c_ob], L=L, U=U)
    add_c_constraints(model, [c_ob])
    add_a_constraints(
        model, [c_ob], _pairs_df(1, 2), {"ZZA": 250}, tau=45,
        out_of_scope_baselines={("IB", 2, 1): 900},
    )
    model._candidates = [c_ob]
    model.objective = pyo.Objective(expr=model.t_dep["OB", 1, 1], sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.t_dep["OB", 1, 1]) == pytest.approx(605.0)


def test_rotation_applies_against_out_of_scope_ob_partner_baseline():
    # Mirror: gidis (OB, flno=1) out of scope, raw baseline dep=100. donus
    # (IB, flno=2) in scope, free in [0,1000]. R_o=250,tau=45 -> donus arr
    # must be >=100+250+45=395. Adversarial objective wants arr as SMALL as
    # possible.
    c_ib = Candidate(
        od="ZZA-IST", o="ZZA", d="IST", gun=1, flno1=2, flno2=99998,
        r1_id=("IB", 2, 1), r2_id=("OB", 99998, 1),
        arr_time=None, dep_time=None, gap_min=100,
        arr_lo=0, arr_hi=1000, dep_lo=0, dep_hi=0,
        gap_lo=-1000, gap_hi=0,
    )
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, [c_ib])
    add_b_constraints(model, [c_ib], L=L, U=U)
    add_c_constraints(model, [c_ib])
    add_a_constraints(
        model, [c_ib], _pairs_df(1, 2), {"ZZA": 250}, tau=45,
        out_of_scope_baselines={("OB", 1, 1): 100},
    )
    model._candidates = [c_ib]
    model.objective = pyo.Objective(expr=model.t_arr["IB", 2, 1], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    assert pyo.value(model.t_arr["IB", 2, 1]) == pytest.approx(395.0)


def test_rotation_violation_caught_by_validator():
    from src.validate.independent_validator import validate_output
    import json
    from pathlib import Path
    import tempfile

    # Fixture's ROT-B is deliberately at the exact boundary (slack=0); shift
    # RB2's reported arrival 55 min earlier to create a genuine violation.
    data = {
        "objective_value": 0.0,
        "selected_connections": [],
        "adjusted_flight_times": [
            {"role": "OB", "flno": 9411, "gun": 1, "time_min": 300},
            {"role": "IB", "flno": 9401, "gun": 1, "time_min": 500},  # needs >=555
        ],
        "ranking_results": [],
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "output.json"
        path.write_text(json.dumps(data))
        fixdir = Path(__file__).parent.parent / "fixtures"
        result = validate_output(
            path, fixdir / "synthetic_od_table.xlsx", L=L, U=U,
            adjustable_window_min=180, adjustable_set="all",
            flight_pairs_path=fixdir / "synthetic_flight_pairs.xlsx", tau=45,
        )
        assert not result.is_valid
        assert any("rotation" in v.lower() or "rotasyon" in v.lower() for v in result.violations)

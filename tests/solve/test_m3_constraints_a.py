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
import datetime as dt

import pandas as pd
import pyomo.environ as pyo
import pytest

from src.candidates.generate import Candidate
from src.model.constraints_operations import add_a_constraints
from src.model.constraints_selection import add_b_constraints, add_c_constraints, add_flight_time_variables
from src.solve.runner import solve

pytestmark = pytest.mark.solve

L, U = 60, 300
ANCHOR = pd.Timestamp("2024-01-01")


def _rotation_candidates(dep_lo, dep_hi, dep_baseline, arr_lo, arr_hi, arr_baseline,
                          gidis_flno, donus_flno, o="ZZA", gun=1):
    # Two throwaway candidates just to get t_arr/t_dep variables created for
    # the rotation flight instances via add_flight_time_variables (which reads
    # bounds off Candidate objects) -- gap fields are irrelevant to A itself.
    # arr_time/dep_time (M5: needed by build_rotation_pairs's baseline-chronology
    # matching, src.model.rotation_matching) are derived from dep_baseline/
    # arr_baseline directly as minutes-of-day on the shared ANCHOR day.
    dep_ts = ANCHOR + pd.Timedelta(days=gun - 1, minutes=dep_baseline % 1440)
    arr_ts = ANCHOR + pd.Timedelta(days=gun - 1, minutes=arr_baseline % 1440)
    c_ob = Candidate(
        od=f"IST-{o}", o="IST", d=o, gun=gun, flno1=99999, flno2=gidis_flno,
        r1_id=("IB", 99999, gun), r2_id=("OB", gidis_flno, gun),
        arr_time=arr_ts, dep_time=dep_ts, gap_min=100,
        arr_lo=0, arr_hi=0, dep_lo=dep_lo, dep_hi=dep_hi,
        gap_lo=dep_lo, gap_hi=dep_hi,
    )
    c_ib = Candidate(
        od=f"{o}-IST", o=o, d="IST", gun=gun, flno1=donus_flno, flno2=99998,
        r1_id=("IB", donus_flno, gun), r2_id=("OB", 99998, gun),
        arr_time=arr_ts, dep_time=dep_ts, gap_min=100,
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


def test_rotation_kul_shaped_long_haul_matches_by_chronology_not_same_gun():
    # M5 VARSAYIM-10 real-data shape (TK174/TK175, IST-KUL, R_o~20.9h): OB
    # flies guns {1,2,3,4,6} at 15:50 (Rfix), IB flies guns {1,3,4,5,6} at
    # 11:00 (Rfix). Under the OLD "same gun" rule, gun=1's OB(15:50) would be
    # paired with gun=1's IB(11:00) -- arr BEFORE dep, massively infeasible
    # for any R_o>0. Under baseline-chronology matching, gun=1's OB instead
    # pairs with gun=3's IB (~2590min later, comfortably >= R_o+tau=1299) --
    # feasible, and every one of the 5 pairs lands on the SAME 2590min gap
    # (hand-verified, docs/decisions.md).
    R_O = 1254
    TAU = 45
    OB_TOD, IB_TOD = 950, 660  # 15:50, 11:00
    ob_guns = [1, 2, 3, 4, 6]
    ib_guns = [1, 3, 4, 5, 6]

    # NOTE: arr_lo/arr_hi/dep_lo/dep_hi are ABSOLUTE EPOCH MINUTES (like
    # everywhere else in the codebase), not bare time-of-day -- must include
    # the (gun-1)*1440 day offset or every gun's Rfix bound collapses to the
    # SAME literal tod value (a real bug caught by this test's own initial
    # failed run: t_dep/t_arr .lb all showed 950/660 regardless of gun).
    candidates = []
    for gun in ob_guns:
        ts = ANCHOR + pd.Timedelta(days=gun - 1, minutes=OB_TOD)
        epoch = (gun - 1) * 1440 + OB_TOD
        candidates.append(Candidate(
            od=f"IST-KUL", o="IST", d="KUL", gun=gun, flno1=99999, flno2=174,
            r1_id=("IB", 99999, gun), r2_id=("OB", 174, gun),
            arr_time=ts, dep_time=ts, gap_min=0,
            arr_lo=0, arr_hi=0, dep_lo=epoch, dep_hi=epoch,
            gap_lo=epoch, gap_hi=epoch,
        ))
    for gun in ib_guns:
        ts = ANCHOR + pd.Timedelta(days=gun - 1, minutes=IB_TOD)
        epoch = (gun - 1) * 1440 + IB_TOD
        candidates.append(Candidate(
            od=f"KUL-IST", o="KUL", d="IST", gun=gun, flno1=175, flno2=99998,
            r1_id=("IB", 175, gun), r2_id=("OB", 99998, gun),
            arr_time=ts, dep_time=ts, gap_min=0,
            arr_lo=epoch, arr_hi=epoch, dep_lo=0, dep_hi=0,
            gap_lo=-epoch, gap_hi=-epoch,
        ))

    pairs_df = _pairs_df(174, 175, o="KUL")
    # B/C skipped deliberately -- the throwaway partner legs' (flno1=99999,
    # flno2=99998) OWN achievable gap spans multiple days at this epoch
    # scale (Rfix, but numerically far outside [L,U]), which trips B's
    # Big-M<=1440 discipline check for a leg that's irrelevant to A itself
    # (matches the out-of-scope tests' pattern above, B/C-free).
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_a_constraints(model, candidates, pairs_df, {"KUL": R_O}, tau=TAU)
    model._candidates = candidates
    model.objective = pyo.Objective(expr=0, sense=pyo.maximize)  # feasibility-only
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"

    # Confirm the ACTUAL matching: gun=1's OB paired with gun=3's IB, not gun=1.
    assert (174, 175, 1, 3) in model.ROTATION_PAIRS
    assert (174, 175, 1, 1) not in model.ROTATION_PAIRS
    assert len(model.ROTATION_PAIRS) == 5  # all 5 OB departures matched (wraps gun6->gun1)
    assert (174, 175, 6, 1) in model.ROTATION_PAIRS  # weekly wraparound


def test_rotation_kul_shaped_constraint_still_binding():
    # Same shape, but donus (IB) is now ADJUSTABLE -- an adversarial
    # objective tries to pull IB gun=3's arrival as EARLY as possible; A
    # must still cap it at exactly dep(gun=1)+R_o+tau.
    R_O = 1254
    TAU = 45
    OB_TOD = 950
    # baseline arr (gün3, 2*1440+660=3540) sits comfortably above
    # dep+R_o+tau=950+1299=2249 already -- the window must extend BELOW
    # 2249 for a "minimize arr" objective to actually WANT to violate the
    # rotation constraint (otherwise it's non-binding by construction, not a
    # real test of bindingness). w=1350 pulls the window down to 2190<2249.
    w = 1350
    candidates = [
        Candidate(
            od="IST-KUL", o="IST", d="KUL", gun=1, flno1=99999, flno2=174,
            r1_id=("IB", 99999, 1), r2_id=("OB", 174, 1),
            arr_time=ANCHOR + pd.Timedelta(minutes=OB_TOD), dep_time=ANCHOR + pd.Timedelta(minutes=OB_TOD),
            gap_min=0, arr_lo=0, arr_hi=0, dep_lo=OB_TOD, dep_hi=OB_TOD,
            gap_lo=OB_TOD, gap_hi=OB_TOD,
        ),
        Candidate(
            od="KUL-IST", o="KUL", d="IST", gun=3, flno1=175, flno2=99998,
            r1_id=("IB", 175, 3), r2_id=("OB", 99998, 3),
            arr_time=ANCHOR + pd.Timedelta(days=2, minutes=660),
            dep_time=ANCHOR + pd.Timedelta(days=2, minutes=660), gap_min=0,
            arr_lo=2 * 1440 + 660 - w, arr_hi=2 * 1440 + 660 + w, dep_lo=0, dep_hi=0,
            gap_lo=-(2 * 1440 + 660 + w), gap_hi=-(2 * 1440 + 660 - w),
        ),
    ]
    pairs_df = _pairs_df(174, 175, o="KUL")
    # B/C skipped deliberately (same reason as the test above -- throwaway
    # partner legs' own achievable gap trips B's Big-M discipline at this
    # epoch scale, irrelevant to what A itself is being tested for here).
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_a_constraints(model, candidates, pairs_df, {"KUL": R_O}, tau=TAU)
    model._candidates = candidates
    model.objective = pyo.Objective(expr=model.t_arr["IB", 175, 3], sense=pyo.minimize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    assert result.status == "optimal"
    dep = pyo.value(model.t_dep["OB", 174, 1])
    arr = pyo.value(model.t_arr["IB", 175, 3])
    assert arr - dep == pytest.approx(R_O + TAU)


def test_rotation_exempts_pair_unreconcilable_even_at_best_case():
    # M5 VARSAYIM-11 (ASSUMPTIONS.md): even AFTER correct chronology
    # matching, 382/1571 (24.3%) of real rotation pairs remain genuinely
    # unreconcilable at their OWN best-case adjustment (single occurrence
    # each, no alternative match exists, and the achievable gap is far
    # below R_o+tau). OB Rfix gun=1 tod=500; IB Rfix gun=1 tod=510 (only
    # 10min later) -- R_o=1254,tau=45 need >=1299min, only 10 available.
    # Must be EXEMPTED (not force infeasibility, not crash) -- same spirit
    # as G's VARSAYIM-9 cluster exemption.
    ob_ts = ANCHOR + pd.Timedelta(minutes=500)
    ib_ts = ANCHOR + pd.Timedelta(minutes=510)
    c_ob = Candidate(
        od="IST-ZZA", o="IST", d="ZZA", gun=1, flno1=99999, flno2=1,
        r1_id=("IB", 99999, 1), r2_id=("OB", 1, 1),
        arr_time=ob_ts, dep_time=ob_ts, gap_min=0,
        arr_lo=0, arr_hi=0, dep_lo=500, dep_hi=500,
        gap_lo=500, gap_hi=500,
    )
    c_ib = Candidate(
        od="ZZA-IST", o="ZZA", d="IST", gun=1, flno1=2, flno2=99998,
        r1_id=("IB", 2, 1), r2_id=("OB", 99998, 1),
        arr_time=ib_ts, dep_time=ib_ts, gap_min=0,
        arr_lo=510, arr_hi=510, dep_lo=0, dep_hi=0,
        gap_lo=-510, gap_hi=-510,
    )
    candidates = [c_ob, c_ib]
    model = pyo.ConcreteModel()
    add_flight_time_variables(model, candidates)
    add_a_constraints(model, candidates, _pairs_df(1, 2), {"ZZA": 1254}, tau=45)
    model._candidates = candidates
    model.objective = pyo.Objective(expr=0, sense=pyo.maximize)
    result = solve(model, solver="highs", time_limit_sec=60, seed=42)
    # Fully-Rfix, unconstrained-by-anything, trivial-objective model can
    # report "unknown" rather than "optimal" from HiGHS -- the important
    # thing is it's NOT infeasible (no false A violation from the exempted pair).
    assert result.status != "infeasible"
    assert len(model.ROTATION_PAIRS) == 0


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
        arr_time=ANCHOR, dep_time=ANCHOR + pd.Timedelta(minutes=500), gap_min=100,
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
        arr_time=ANCHOR + pd.Timedelta(minutes=500), dep_time=ANCHOR, gap_min=100,
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


def _kul_shaped_fixture(tmp_path):
    # M5 VARSAYIM-10: self-contained KUL-shaped (long-haul, multi-day
    # rotation) od_table + flight_pairs fixture -- exercises the
    # validator's chronology-based matching independently of the shared
    # synthetic fixture (which only has same-gun/short-haul rotations).
    import openpyxl

    from src.data.loaders import load_od_table

    # R_o(KUL) resolves to ~100min from the single seed row below (ridge-pinned
    # LS with one equation). tau=45 -> required gap=145. ob at gün1 tod=1400,
    # ib at gün2 tod=105 -> baseline gap=(1440+105)-1400=145 EXACTLY (boundary,
    # matches the shared fixture's ROT-B convention) -- multi-day (gün1->gün2,
    # NOT same-gun) so this genuinely exercises the chronology matching, and
    # close enough to the boundary that a 1min legal-window shift creates a
    # real violation (unlike a same-order-of-magnitude-as-baseline gap, which
    # no legal +-180min report could ever push into violation).
    anchor = pd.Timestamp("2024-01-01")
    ob_ts = anchor + pd.Timedelta(minutes=1400)               # gün1, 23:20
    ib_ts = anchor + pd.Timedelta(days=1, minutes=105)        # gün2, 01:45

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Cr1", "Carrier Name", "Dep1", "Arr1", "FlNo1", "Arr Time",
               "Cr2", "Dep2", "Arr2", "FlNo2", "Dep Time",
               "Gate-to-Gate Uçuş Süresi", "O&D", "Gün"])
    # OB leg (IST->KUL, flno=174): a throwaway inbound partner (flno1=99999)
    # pairs with the real outbound flno2=174.
    ws.append(["TK", "Turkish Airlines", "XXX", "IST", 99999, ob_ts,
               "TK", "IST", "KUL", 174, ob_ts,
               dt.time(3, 20), "XXX-KUL", 1])
    # IB leg (KUL->IST, flno=175): real inbound flno1=175 pairs with a
    # throwaway outbound partner (flno2=99998).
    ws.append(["TK", "Turkish Airlines", "KUL", "IST", 175, ib_ts,
               "TK", "IST", "YYY", 99998, ib_ts,
               dt.time(3, 20), "KUL-YYY", 2])
    # Seed row purely so BlockTimeProvider's LS system has a VALID-gap
    # (in [L,U]) data point touching KUL at all -- rows 1/2 above both have
    # gap=0 (arr_time==dep_time, deliberately, since only their FLIGHT
    # IDENTITY matters for this test, not their own gap validity), so
    # without this row get_rotation_constant("KUL") would raise KeyError
    # and the whole rotation check would be silently skipped.
    seed_ts = anchor + pd.Timedelta(minutes=100)
    ws.append(["TK", "Turkish Airlines", "KUL", "IST", 88888, seed_ts,
               "TK", "IST", "KUL", 88889, seed_ts + pd.Timedelta(minutes=100),
               dt.time(3, 20), "KUL-KUL", 1])
    od_path = tmp_path / "od_table_kul.xlsx"
    wb.save(od_path)
    load_od_table(od_path)

    wb2 = openpyxl.Workbook()
    ws2 = wb2.active
    ws2.append(["FlNo", "Orig", "Dest", "Pair"])
    ws2.append([174, "IST", "KUL", "P1"])
    ws2.append([175, "KUL", "IST", "P1"])
    fp_path = tmp_path / "flight_pairs_kul.xlsx"
    wb2.save(fp_path)
    return od_path, fp_path


def test_validate_catches_multiday_rotation_violation(tmp_path):
    import json

    from src.validate.independent_validator import validate_output

    od_path, fp_path = _kul_shaped_fixture(tmp_path)
    # Baseline gap is deliberately at the EXACT boundary (145=R_o+tau, see
    # _kul_shaped_fixture) -- reporting IB's arrival 1min earlier (still
    # within its own +-180min legal window) creates a genuine violation of
    # the gün1(OB)<->gün2(IB) match (NOT gün1<->gün1, proving the validator's
    # independent chronology matching is what's actually being exercised).
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps({
        "objective_value": 0.0,
        "selected_connections": [],
        "adjusted_flight_times": [
            {"role": "OB", "flno": 174, "gun": 1, "time_min": 1400},
            {"role": "IB", "flno": 175, "gun": 2, "time_min": 1440 + 105 - 1},
        ],
        "ranking_results": [],
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }))
    result = validate_output(
        output_path, od_path, L=L, U=U,
        adjustable_window_min=180, adjustable_set="all",
        flight_pairs_path=fp_path, tau=45,
    )
    assert not result.is_valid
    rotation_violations = [v for v in result.violations if "rotation" in v.lower()]
    assert len(rotation_violations) == 1, result.violations
    # Confirm it correctly identifies gün1(OB) <-> gün2(IB), not gün1<->gün1.
    assert "Gün=1" in rotation_violations[0] and "Gün=2" in rotation_violations[0]


def test_validate_passes_multiday_rotation_at_boundary(tmp_path):
    import json

    from src.validate.independent_validator import validate_output

    od_path, fp_path = _kul_shaped_fixture(tmp_path)
    # Exact baseline (145=R_o+tau, non-violating boundary) reported as-is.
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps({
        "objective_value": 0.0,
        "selected_connections": [],
        "adjusted_flight_times": [
            {"role": "OB", "flno": 174, "gun": 1, "time_min": 1400},
            {"role": "IB", "flno": 175, "gun": 2, "time_min": 1440 + 105},
        ],
        "ranking_results": [],
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }))
    result = validate_output(
        output_path, od_path, L=L, U=U,
        adjustable_window_min=180, adjustable_set="all",
        flight_pairs_path=fp_path, tau=45,
    )
    assert not any("rotation" in v.lower() for v in result.violations), result.violations

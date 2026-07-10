"""Unit tests for src.validate.independent_validator.

This module must be independently verifiable of src.model.* / src.candidates.* --
it re-derives gap validity from the OUTPUT's own reported adjusted_flight_times
(never a connection's claimed gap_min display field) and checks those reported
times against a legal window independently re-derived from raw data. See plan
§1 "validate/ modelin Pyomo kodundan hiç import almayan ayrı bir mantık yolu"
(diskalifiye sigortası).

marker: unit (solver-free, pure logic).
"""
import json
from pathlib import Path

import pytest

from src.validate.independent_validator import finalize_reported_objective, recompute_objective, validate_output

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.unit

L, U = 60, 300


def _write_output(tmp_path, connections, adjusted_times):
    data = {
        "objective_value": 0.0,
        "selected_connections": connections,
        "adjusted_flight_times": adjusted_times,
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }
    path = tmp_path / "output.json"
    path.write_text(json.dumps(data))
    return path


def test_validate_passes_for_hand_verified_valid_connections(tmp_path):
    # MI1xMO2 (baseline gap=60) and NI1xNO2 (baseline gap=205) from
    # fixtures/README.md, reported at their exact baseline (Rfix) times.
    output_path = _write_output(
        tmp_path,
        connections=[
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
        ],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 795},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
        ],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert result.is_valid
    assert result.violations == []


def test_validate_catches_gap_below_l(tmp_path):
    # MI1xMO1 has baseline gap=-360 (deliberately invalid per fixtures/README.md).
    output_path = _write_output(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9111, "gun": 1, "gap_min": -360}],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9111, "gun": 1, "time_min": 480},
        ],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("gap" in v.lower() for v in result.violations)


def test_validate_ignores_claimed_gap_min_and_recomputes_from_adjusted_times(tmp_path):
    # Output CLAIMS gap_min=60 (valid) via the display field, but the reported
    # adjusted_flight_times actually give gap=-360 (MI1xMO1's real gap) --
    # validator must use the TIMES, not the claimed display value.
    output_path = _write_output(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9111, "gun": 1, "gap_min": 60}],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9111, "gun": 1, "time_min": 480},
        ],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid


def test_validate_accepts_synthesized_pairing_of_two_real_legs(tmp_path):
    # RB2(9401, inbound leg of ZZB-ZZA) and NO2(9212, outbound leg of ZZB-ZZA)
    # each individually exist as real TK flights on Gün=1, but the raw O&D
    # table never lists them PAIRED TOGETHER in one row (confirmed by
    # inspection). The model's candidate generation is a full inbound x
    # outbound cross-product (plan §4) -- a synthesized pairing of two real
    # legs is a legitimate candidate, not a fabrication. Baseline: RB2 arr=555,
    # NO2 dep=1000 -> gap=445 (invalid at baseline, but a real pairing).
    output_path = _write_output(
        tmp_path,
        connections=[{"od": "ZZB-ZZA", "flno1": 9401, "flno2": 9212, "gun": 1, "gap_min": 445}],
        adjusted_times=[
            {"role": "IB", "flno": 9401, "gun": 1, "time_min": 555},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
        ],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not any("not found" in v.lower() for v in result.violations), result.violations
    # (still correctly flagged for gap=445 > U=300, just NOT as "not found")
    assert any("gap" in v.lower() for v in result.violations)


def test_validate_catches_nonexistent_flight_reference(tmp_path):
    output_path = _write_output(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 99999, "flno2": 88888, "gun": 1, "gap_min": 100}],
        adjusted_times=[],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("not found" in v.lower() for v in result.violations)


def test_validate_catches_reported_time_outside_legal_window(tmp_path):
    # Rfix (adjustable_set defaults to "none") -- reported time must equal
    # baseline EXACTLY; a claimed deviation must be flagged.
    output_path = _write_output(
        tmp_path,
        connections=[],
        adjusted_times=[{"role": "IB", "flno": 9101, "gun": 1, "time_min": 840 + 500}],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("window" in v.lower() for v in result.violations)


def _write_output_with_ranking(tmp_path, connections, adjusted_times, ranking_results):
    data = {
        "objective_value": 0.0,
        "selected_connections": connections,
        "adjusted_flight_times": adjusted_times,
        "ranking_results": ranking_results,
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }
    path = tmp_path / "output.json"
    path.write_text(json.dumps(data))
    return path


def test_validate_passes_correctly_reported_beaten_rivals_and_rank(tmp_path):
    # MI1xMO2, J=280, correctly beats R1(300) not R2(250) -- matches
    # fixtures/README.md hand calc: N=2, beaten=[R1], rank=1.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60}],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
        ],
        ranking_results=[{"o": "ZZA", "d": "ZZB", "gun": 1, "rank": 1, "beaten_rivals": ["R1"]}],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert result.is_valid, result.violations


def test_validate_catches_fabricated_beaten_rival(tmp_path):
    # Same offered connection (only beats R1), but output FALSELY claims R2
    # (250) was also beaten -- J=280 does not beat T_comp=250.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60}],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
        ],
        ranking_results=[{"o": "ZZA", "d": "ZZB", "gun": 1, "rank": 0, "beaten_rivals": ["R1", "R2"]}],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("R2" in v and "beaten" in v.lower() for v in result.violations)


def test_validate_allows_under_claimed_beaten_rivals(tmp_path):
    # Forward-only D forcing (monotonic W(r)) can legitimately leave a
    # genuinely-beatable rival unclaimed in a flat-reward-tie scenario (e.g.
    # beating N-1 vs N rivals both land on the same clamped r=1) -- this is
    # NOT a violation (claimed subset of actual is always reward-safe, never
    # inflated). NI1xNO2 reported at arr=700,dep=820 (within each leg's
    # +-180min window of baseline 795/1000) -> gap=120, J=K_od(240)+120=360,
    # which genuinely beats ALL THREE rivals (R3=500,R4=400,R5=445) -- but
    # only R3,R5 are claimed, R4 deliberately left out.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[{"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 120}],
        adjusted_times=[
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 700},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 820},
        ],
        ranking_results=[{"o": "ZZB", "d": "ZZA", "gun": 1, "rank": 1, "beaten_rivals": ["R3", "R5"]}],
    )
    result = validate_output(
        output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U,
        adjustable_window_min=180, adjustable_set="all",
    )
    assert result.is_valid, result.violations


def test_validate_catches_rank_inconsistent_with_beaten_count(tmp_path):
    # beaten_rivals correctly lists just R1, but claimed rank doesn't match
    # N(2) - len(beaten)(1) = 1.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[{"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60}],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
        ],
        ranking_results=[{"o": "ZZA", "d": "ZZB", "gun": 1, "rank": 99, "beaten_rivals": ["R1"]}],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U)
    assert not result.is_valid
    assert any("rank" in v.lower() for v in result.violations)


def test_validate_catches_e1_imbalance(tmp_path):
    # ZZA-ZZB has 2 selected connections (MI1xMO2, MI2xMO2), ZZB-ZZA has 1
    # (NI1xNO2) -- |2-1|=1 > 0.2*3=0.6, violates E1.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
            {"od": "ZZA-ZZB", "flno1": 9102, "flno2": 9112, "gun": 1, "gap_min": 300},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
        ],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "IB", "flno": 9102, "gun": 1, "time_min": 600},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 795},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
        ],
        ranking_results=[],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U, alpha=0.20)
    assert not result.is_valid
    assert any("E1" in v for v in result.violations)


def test_validate_catches_e1_imbalance_when_one_side_has_zero_selected(tmp_path):
    # 2026-07-09 baseline autopsy finding (docs/baseline_autopsy.md #1):
    # ZZA-ZZB Gün1 has 2 STRUCTURAL candidates (MI1xMO2, MI2xMO2, per
    # fixtures/README.md ground truth) but the output selects NEITHER --
    # ZZB-ZZA Gün1 selects 1 (NI1xNO2). Old (buggy) scope built `counts`
    # only from selected_connections, so ZZA-ZZB (0 selected) was never a
    # key -- the reverse-lookup `(o,d,gun) not in counts` then skipped this
    # pair ENTIRELY, silently missing a genuine E1 violation (1-0=1 >
    # 0.2*1=0.2). The model's own add_e1_constraints scopes E1_PAIRS by
    # STRUCTURAL candidate existence (VARSAYIM-6), not selection -- the
    # validator must match.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
        ],
        adjusted_times=[
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 795},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
        ],
        ranking_results=[],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U, alpha=0.20)
    assert not result.is_valid
    assert any("E1" in v for v in result.violations)


def test_validate_e1_skips_pair_when_reverse_direction_has_no_real_flights(tmp_path):
    # Control case for the fix above: Gün=2 in this fixture only has flight
    # rows for ZZA-side/ZZB-side stations that already exist on Gün=1 (no
    # new stations), so to get a genuinely-empty reverse direction we point
    # at a (o,d) with NO raw TK rows at all in either direction: querying
    # structural-candidate existence for a nonexistent station pair must
    # return False (not crash), and since ZZA-ZZB's own reverse (ZZB-ZZA)
    # DOES exist structurally in this fixture, this test instead confirms
    # the new structural-scope lookup itself is safe for a market with zero
    # raw rows (used internally when checking (d,o,gun) for a fabricated d).
    from src.validate.independent_validator import _has_structural_candidate, _epoch_anchor
    from src.data.loaders import load_od_table
    od_table = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    tk = od_table[od_table.cr1 == "TK"]
    anchor = _epoch_anchor(tk)
    assert _has_structural_candidate(tk, "ZZA", "QQQ", 1, anchor, 0, "none", L, U) is False
    assert _has_structural_candidate(tk, "ZZA", "ZZB", 1, anchor, 0, "none", L, U) is True


def test_validate_passes_e1_balanced_market(tmp_path):
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
        ],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 795},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
        ],
        ranking_results=[],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U, alpha=0.20)
    assert not any("E1" in v for v in result.violations)


def test_validate_catches_e2_gamma_violation(tmp_path):
    # Journey constants (fixture, verified via BlockTimeProvider):
    # K_od(ZZA,ZZB)=220, K_od(ZZB,ZZA)=240. ZZA-ZZB offers gap=60 (J=280) and
    # gap=300 (J=520) -> Jbest_fwd=280. ZZB-ZZA offers gap=205 (J=445) ->
    # Jbest_bwd=445. |445-280|=165 > Gamma=30.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
            {"od": "ZZA-ZZB", "flno1": 9102, "flno2": 9112, "gun": 1, "gap_min": 300},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
        ],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "IB", "flno": 9102, "gun": 1, "time_min": 600},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 795},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
        ],
        ranking_results=[],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U, gamma=30)
    assert not result.is_valid
    assert any("E2" in v for v in result.violations)


def test_validate_e2_falls_back_to_estimated_journey_constant(tmp_path, monkeypatch):
    # 2026-07-09 baseline autopsy finding (docs/baseline_autopsy.md #2): the
    # E2 section built its OWN BlockTimeProvider and called ONLY
    # get_journey_constant (direct-median, VARSAYIM-8) -- with no fallback
    # to get_journey_constant_estimate (LS-estimate) the way the MODEL's
    # journey_constants dict does (run_full_data.py/main.py both try direct
    # then estimate). On full data 571/1329 markets only have an ESTIMATED
    # K_od -- E2 was silently skipping ALL of them (`except KeyError:
    # continue`), undercounting violations by 38 (1181 vs 1219 recomputed).
    # This forces ZZA-ZZB's DIRECT lookup to fail so only the estimate path
    # can produce a result.
    import src.validate.independent_validator as validator_mod

    real_get = validator_mod.BlockTimeProvider.get_journey_constant

    def fake_get_journey_constant(self, o, d):
        if (o, d) == ("ZZA", "ZZB"):
            raise KeyError("forced: simulate no direct baseline row for ZZA-ZZB")
        return real_get(self, o, d)

    def fake_get_journey_constant_estimate(self, o, d):
        if (o, d) == ("ZZA", "ZZB"):
            return 220.0  # same as the fixture's real direct K_od, so the hand-calc below still holds
        raise KeyError(f"no estimate stubbed for {(o, d)}")

    monkeypatch.setattr(validator_mod.BlockTimeProvider, "get_journey_constant", fake_get_journey_constant)
    monkeypatch.setattr(validator_mod.BlockTimeProvider, "get_journey_constant_estimate", fake_get_journey_constant_estimate)

    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
            {"od": "ZZA-ZZB", "flno1": 9102, "flno2": 9112, "gun": 1, "gap_min": 300},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
        ],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "IB", "flno": 9102, "gun": 1, "time_min": 600},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 795},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
        ],
        ranking_results=[],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U, gamma=30)
    assert not result.is_valid
    assert any("E2" in v for v in result.violations)


def test_validate_passes_e2_within_gamma(tmp_path):
    # gap_fwd=120 (J=220+120=340), gap_bwd=100 (J=240+100=340) -> diff=0.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 120},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 100},
        ],
        adjusted_times=[
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 800},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 920},
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 700},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 800},
        ],
        ranking_results=[],
    )
    result = validate_output(output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U, gamma=30)
    assert not any("E2" in v for v in result.violations), result.violations


def test_validate_catches_f_capacity_violation(tmp_path):
    # OB legs 9112 (baseline 900) and 9212 (baseline 1000) reported at 900
    # and 905 -- same 10-min bucket (90), capacity_departure=1 forces at
    # most one flight per bucket.
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[],
        adjusted_times=[
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 905},
        ],
        ranking_results=[],
    )
    result = validate_output(
        output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U,
        adjustable_window_min=180, adjustable_set="all",
        bucket_size_min=10, capacity_departure=1, capacity_arrival=15,
    )
    assert not result.is_valid
    assert any("F kova" in v for v in result.violations), result.violations


def test_validate_passes_f_within_capacity(tmp_path):
    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[],
        adjusted_times=[
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 905},
        ],
        ranking_results=[],
    )
    result = validate_output(
        output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U,
        adjustable_window_min=180, adjustable_set="all",
        bucket_size_min=10, capacity_departure=10, capacity_arrival=15,
    )
    assert not any("F kova" in v for v in result.violations), result.violations


def test_validate_catches_genuine_rotation_violation(tmp_path, monkeypatch):
    # RA1(OB,9311,dep baseline=200)/RA2(IB,9301,arr baseline=850) on ZZA.
    # R_o monkeypatched to 300 (tau=45, need>=345) so there's room for a
    # GENUINE-but-violatable-within-window scenario: best-case check
    # (dep_lo=20,arr_hi=1030) -> 1030>=20+345=365 -- reconcilable, NOT
    # exempt. Reported at the window EDGES (dep=380 latest, arr=670
    # earliest, both legal): 670 < 380+345=725 -- violates. Control case
    # confirming the VARSAYIM-11 exemption fix doesn't swallow real
    # violations that ARE reconcilable but weren't actually reconciled.
    import src.validate.independent_validator as validator_mod

    def fake_get_rotation_constant(self, station):
        if station == "ZZA":
            return 300.0
        raise KeyError(station)

    monkeypatch.setattr(validator_mod.BlockTimeProvider, "get_rotation_constant", fake_get_rotation_constant)

    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[],
        adjusted_times=[
            {"role": "OB", "flno": 9311, "gun": 1, "time_min": 380},
            {"role": "IB", "flno": 9301, "gun": 1, "time_min": 670},
        ],
        ranking_results=[],
    )
    result = validate_output(
        output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U,
        adjustable_window_min=180, adjustable_set="all",
        flight_pairs_path=FIXDIR / "synthetic_flight_pairs.xlsx", tau=45,
    )
    assert not result.is_valid
    assert any("rotation" in v for v in result.violations)


def test_validate_exempts_rotation_pair_unreconcilable_even_at_best_case(tmp_path, monkeypatch):
    # 2026-07-09 baseline autopsy finding (docs/baseline_autopsy.md #4): the
    # validator's rotation (A) check had NO VARSAYIM-11 exemption test at
    # all -- every matched OB/IB pair was checked UNCONDITIONALLY, meaning a
    # genuinely valid solution (which the model itself would have EXEMPTED
    # from A, per add_a_constraints' best-case-reconcilability test) could
    # get wrongly flagged. Same scenario as
    # tests/solve/test_m3_constraints_a.py::test_rotation_exempts_pair_unreconcilable_even_at_best_case
    # (R_o=1254, tau=45, only ~1030-20=1010min max achievable spread <
    # 1254+45=1299 needed) -- monkeypatched onto the real RA1/RA2 pair since
    # this 2-station fixture's LS system can't itself produce such a large
    # R_o (see fixtures/README.md degenerate-LS note).
    import src.validate.independent_validator as validator_mod

    def fake_get_rotation_constant(self, station):
        if station == "ZZA":
            return 1254.0
        raise KeyError(station)

    monkeypatch.setattr(validator_mod.BlockTimeProvider, "get_rotation_constant", fake_get_rotation_constant)

    output_path = _write_output_with_ranking(
        tmp_path,
        connections=[],
        adjusted_times=[
            {"role": "OB", "flno": 9311, "gun": 1, "time_min": 200},   # baseline, within [20,380]
            {"role": "IB", "flno": 9301, "gun": 1, "time_min": 850},   # baseline, within [670,1030]
        ],
        ranking_results=[],
    )
    result = validate_output(
        output_path, FIXDIR / "synthetic_od_table.xlsx", L=L, U=U,
        adjustable_window_min=180, adjustable_set="all",
        flight_pairs_path=FIXDIR / "synthetic_flight_pairs.xlsx", tau=45,
    )
    assert result.is_valid, result.violations
    assert not any("rotation" in v for v in result.violations)


def test_recompute_objective_matches_m2_hand_calc(tmp_path):
    # adjustable_set:none baseline scenario (fixtures/README.md M2 eki):
    # connection_reward=400.0 (200x2 days), ranking_reward=100.0 (Gün1 only,
    # Gün2 has no rival data), total=500.0.
    data = {
        "objective_value": 500.0,
        "selected_connections": [
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
            {"od": "ZZA-ZZB", "flno1": 9102, "flno2": 9112, "gun": 1, "gap_min": 300},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 2, "gap_min": 85},
            {"od": "ZZA-ZZB", "flno1": 9102, "flno2": 9112, "gun": 2, "gap_min": 300},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 2, "gap_min": 200},
        ],
        "adjusted_flight_times": [
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "IB", "flno": 9102, "gun": 1, "time_min": 600},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 795},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
            {"role": "IB", "flno": 9101, "gun": 2, "time_min": 1440 + 815},
            {"role": "IB", "flno": 9102, "gun": 2, "time_min": 1440 + 600},
            {"role": "OB", "flno": 9112, "gun": 2, "time_min": 1440 + 900},
            {"role": "IB", "flno": 9201, "gun": 2, "time_min": 1440 + 800},
            {"role": "OB", "flno": 9212, "gun": 2, "time_min": 1440 + 1000},
        ],
        "ranking_results": [],
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps(data))
    breakdown_path = tmp_path / "breakdown.json"

    total, breakdown = recompute_objective(
        output_path, FIXDIR / "synthetic_od_table.xlsx",
        FIXDIR / "synthetic_yolcu_verisi.xlsx", FIXDIR / "synthetic_change_ranking_input.xlsx",
        L=L, U=U, breakdown_path=breakdown_path,
    )

    assert total == pytest.approx(500.0)


def test_recompute_objective_falls_back_to_estimated_journey_constant(tmp_path, monkeypatch):
    # M5c §2 finding: recompute_objective's D/ranking recomputation called
    # ONLY get_journey_constant (direct-median), no estimate fallback --
    # this would raise an uncaught KeyError (crash the whole recompute, not
    # just skip one market) on any full-data market whose K_od is only
    # LS-estimated (571/1329 markets on real data). Same fix pattern as
    # independent_validator's E2 section (docs/baseline_autopsy.md #2).
    import src.validate.independent_validator as validator_mod

    real_get = validator_mod.BlockTimeProvider.get_journey_constant

    def fake_get_journey_constant(self, o, d):
        if (o, d) == ("ZZA", "ZZB"):
            raise KeyError("forced: simulate no direct baseline row for ZZA-ZZB")
        return real_get(self, o, d)

    def fake_get_journey_constant_estimate(self, o, d):
        if (o, d) == ("ZZA", "ZZB"):
            return 220.0  # matches the fixture's real direct K_od, so hand-calc still holds
        raise KeyError(f"no estimate stubbed for {(o, d)}")

    monkeypatch.setattr(validator_mod.BlockTimeProvider, "get_journey_constant", fake_get_journey_constant)
    monkeypatch.setattr(validator_mod.BlockTimeProvider, "get_journey_constant_estimate", fake_get_journey_constant_estimate)

    data = {
        "objective_value": 500.0,
        "selected_connections": [
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
            {"od": "ZZA-ZZB", "flno1": 9102, "flno2": 9112, "gun": 1, "gap_min": 300},
            {"od": "ZZB-ZZA", "flno1": 9201, "flno2": 9212, "gun": 1, "gap_min": 205},
        ],
        "adjusted_flight_times": [
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "IB", "flno": 9102, "gun": 1, "time_min": 600},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
            {"role": "IB", "flno": 9201, "gun": 1, "time_min": 795},
            {"role": "OB", "flno": 9212, "gun": 1, "time_min": 1000},
        ],
        "ranking_results": [],
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps(data))

    # Must not raise -- previously an uncaught KeyError here would crash the
    # entire recompute for a market relying on the estimate fallback.
    total, breakdown = recompute_objective(
        output_path, FIXDIR / "synthetic_od_table.xlsx",
        FIXDIR / "synthetic_yolcu_verisi.xlsx", FIXDIR / "synthetic_change_ranking_input.xlsx",
        L=L, U=U,
    )
    assert total > 0


def test_recompute_objective_passes_strict_through_to_yolcu_loader(tmp_path, monkeypatch):
    # M5d (docs/decisions.md 2026-07-10): recompute_objective previously
    # hardcoded load_yolcu_verisi's default strict=True -- would raise
    # SchemaError on full data's 3 known missing-dest rows (VARSAYIM-2).
    # Never caught before because no prior full-data run reached this code
    # path (all ended watchdog_killed first). strict must now be a real
    # pass-through parameter.
    import src.validate.independent_validator as validator_mod

    real_load = validator_mod.load_yolcu_verisi
    calls = []

    def fake_load(path, strict=True):
        calls.append(strict)
        return real_load(path, strict=strict)
    monkeypatch.setattr(validator_mod, "load_yolcu_verisi", fake_load)

    data = {
        "objective_value": 500.0,
        "selected_connections": [
            {"od": "ZZA-ZZB", "flno1": 9101, "flno2": 9112, "gun": 1, "gap_min": 60},
        ],
        "adjusted_flight_times": [
            {"role": "IB", "flno": 9101, "gun": 1, "time_min": 840},
            {"role": "OB", "flno": 9112, "gun": 1, "time_min": 900},
        ],
        "ranking_results": [],
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
    }
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps(data))

    recompute_objective(
        output_path, FIXDIR / "synthetic_od_table.xlsx",
        FIXDIR / "synthetic_yolcu_verisi.xlsx", FIXDIR / "synthetic_change_ranking_input.xlsx",
        L=L, U=U, strict=False,
    )
    assert calls == [False]

    calls.clear()
    recompute_objective(
        output_path, FIXDIR / "synthetic_od_table.xlsx",
        FIXDIR / "synthetic_yolcu_verisi.xlsx", FIXDIR / "synthetic_change_ranking_input.xlsx",
        L=L, U=U,
    )
    assert calls == [True], "default must stay strict=True -- no behavior change for existing callers"


def test_finalize_reported_objective_overwrites_with_recompute_value(tmp_path):
    # M5c §2: the OFFICIAL reported objective_value must be the
    # independently-recomputed one, never the solver's raw claim --
    # finalize_reported_objective overwrites output.json's objective_value
    # field, making "reported == recompute" true by construction.
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps({"objective_value": 500.0, "selected_connections": []}))
    ok, msg = finalize_reported_objective(
        output_path, recompute_total=500.0, solver_status="optimal", solver_objective_value=500.0,
    )
    assert ok, msg
    assert json.loads(output_path.read_text())["objective_value"] == 500.0


def test_finalize_reported_objective_requires_exact_equality_when_optimal(tmp_path):
    # A status=optimal solution's own internal accounting drifting from the
    # independently-recomputed truth is a real bug signal -- must be flagged
    # (not silently overwritten), and the file must be left UNTOUCHED. Uses
    # recompute > solver (510 vs 500) specifically so this exercises the
    # optimal-equality check, not the separate recompute>=solver floor.
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps({"objective_value": 500.0, "selected_connections": []}))
    ok, msg = finalize_reported_objective(
        output_path, recompute_total=510.0, solver_status="optimal", solver_objective_value=500.0,
    )
    assert not ok
    assert "optimal" in msg
    assert json.loads(output_path.read_text())["objective_value"] == 500.0  # untouched


def test_finalize_reported_objective_allows_recompute_ge_solver_when_time_limit(tmp_path):
    # A time_limit incumbent's own claim can legitimately be a LAZY lower
    # bound (docs/decisions.md: "gerçek gap <= solver'ın raporladığı gap") --
    # recompute finding something AT LEAST as good is fine, only strict
    # equality is waived (not the >= floor itself).
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps({"objective_value": 500.0, "selected_connections": []}))
    ok, msg = finalize_reported_objective(
        output_path, recompute_total=510.0, solver_status="time_limit", solver_objective_value=500.0,
    )
    assert ok, msg
    assert json.loads(output_path.read_text())["objective_value"] == 510.0


def test_finalize_reported_objective_flags_recompute_worse_than_solver_claim(tmp_path):
    # recompute finding LESS reward than the solver's own internal claim
    # should never happen (the solver can't validly claim a reward the
    # final times don't support) -- must be flagged regardless of status.
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps({"objective_value": 500.0, "selected_connections": []}))
    ok, msg = finalize_reported_objective(
        output_path, recompute_total=490.0, solver_status="time_limit", solver_objective_value=500.0,
    )
    assert not ok
    assert "should never happen" in msg

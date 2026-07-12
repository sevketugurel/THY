"""Kapı-D3 (docs/STATUS.md, statik HTML sonuç panosu): pure HTML-builder
function, no file I/O, no wall-clock inside the function itself (caller
supplies generated_at) -- so output is byte-deterministic for the same
inputs, which is exactly what the deterministic-output test below checks.

marker: unit (solver-free, pure logic).
"""
import pytest

from src.report.dashboard import build_dashboard_html

pytestmark = pytest.mark.unit


def _fixture_output():
    return {
        "objective_value": 668.75,
        "solver_metrics": {"status": "optimal", "solve_time_sec": 0.175},
        "selected_connections": [
            {"od": "ZZA-ZZB", "gun": 1, "flno1": 9101, "flno2": 9112, "gap_min": 84},
            {"od": "ZZB-ZZA", "gun": 1, "flno1": 9401, "flno2": 9212, "gap_min": 300},
        ],
        "ranking_results": [
            {"o": "ZZA", "d": "ZZB", "gun": 1, "rank": 1, "beaten_rivals": ["R1"]},
        ],
    }


def _full_data_output():
    return {
        "objective_value": None,
        "solver_metrics": {"status": "no_feasible_solution_found", "solve_time_sec": 0.0},
        "selected_connections": [],
    }


def _gamma_scan():
    return {
        "official_gamma": 30,
        "rows": [
            {"gamma": 30, "is_official": True, "static_infeasible_pairs": 63,
             "baseline_e2_violation_count": 1222, "baseline_e2_violation_mass_min": 70072.5,
             "independent_pair_lower_bound_min": 5055.0},
            {"gamma": 180, "is_official": False, "static_infeasible_pairs": 7,
             "baseline_e2_violation_count": 92, "baseline_e2_violation_mass_min": 8165.0,
             "independent_pair_lower_bound_min": 717.5},
        ],
        "decision": {"gamma_star": None, "fallback_tier": None, "run_campaign": False,
                     "rationale": "test rationale"},
    }


def _provenance():
    return {"FULL_OD": {"path": "data_raw/od.xlsx", "sha256": "abc123"}}


def test_build_dashboard_html_is_deterministic():
    html1 = build_dashboard_html(_fixture_output(), _full_data_output(), _gamma_scan(),
                                  _provenance(), generated_at="2026-07-12T00:00:00Z")
    html2 = build_dashboard_html(_fixture_output(), _full_data_output(), _gamma_scan(),
                                  _provenance(), generated_at="2026-07-12T00:00:00Z")
    assert html1 == html2


def test_build_dashboard_html_includes_fixture_objective_and_connections():
    html = build_dashboard_html(_fixture_output(), _full_data_output(), _gamma_scan(),
                                 _provenance(), generated_at="2026-07-12T00:00:00Z")
    assert "668.75" in html
    assert "ZZA-ZZB" in html
    assert "9101" in html
    assert "R1" in html


def test_build_dashboard_html_includes_full_data_diagnostic_no_violated_tariff():
    html = build_dashboard_html(_fixture_output(), _full_data_output(), _gamma_scan(),
                                 _provenance(), generated_at="2026-07-12T00:00:00Z")
    assert "no_feasible_solution_found" in html
    assert "ihlalli tarife" in html.lower() or "no violated" in html.lower()


def test_build_dashboard_html_includes_all_gamma_rows():
    html = build_dashboard_html(_fixture_output(), _full_data_output(), _gamma_scan(),
                                 _provenance(), generated_at="2026-07-12T00:00:00Z")
    assert "5055.0" in html or "5055" in html
    assert "717.5" in html


def test_build_dashboard_html_includes_provenance_sha256():
    html = build_dashboard_html(_fixture_output(), _full_data_output(), _gamma_scan(),
                                 _provenance(), generated_at="2026-07-12T00:00:00Z")
    assert "abc123" in html


def test_build_dashboard_html_is_self_contained_no_external_refs():
    html = build_dashboard_html(_fixture_output(), _full_data_output(), _gamma_scan(),
                                 _provenance(), generated_at="2026-07-12T00:00:00Z")
    assert "http://" not in html
    assert "https://" not in html
    assert "cdn." not in html.lower()


def test_build_dashboard_html_escapes_special_characters_in_od():
    fixture = _fixture_output()
    fixture["selected_connections"][0]["od"] = "A&B<script>"
    html = build_dashboard_html(fixture, _full_data_output(), _gamma_scan(),
                                 _provenance(), generated_at="2026-07-12T00:00:00Z")
    assert "<script>" not in html
    assert "&amp;" in html or "&lt;" in html

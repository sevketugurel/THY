import json

import pytest

from src.benchmark.writer import patch_json_field, stamp_recomputed_objective, write_benchmark_output

pytestmark = pytest.mark.unit


def _write(tmp_path, **overrides):
    p = tmp_path / "out.json"
    kwargs = dict(
        path=p,
        times={("IB", 10, 1): 600, ("OB", 20, 1): 720},
        connections=[{"od": "AAA-BBB", "flno1": 10, "flno2": 20, "gun": 1, "gap_min": 120}],
        ranking_results=[{"o": "AAA", "d": "BBB", "gun": 1, "rank": 1, "beaten_rivals": ["XX"]}],
        k_od_sources={("AAA", "BBB"): "direct"},
        status="heuristic_incumbent_with_strict_violations",
        solve_time_sec=1.5,
        diagnostics={"mode": "benchmark_full_claim", "strict_feasible": False},
    )
    kwargs.update(overrides)
    write_benchmark_output(**kwargs)
    return p


def test_schema_parity_with_strict_writer(tmp_path):
    from src.output.writer import write_output
    from src.solve.runner import SolveResult

    strict_p = tmp_path / "strict.json"
    write_output(strict_p, SolveResult(status="optimal", objective_value=1.0, selected={}, solve_time_sec=0.0))
    strict_fields = set(json.loads(strict_p.read_text()).keys())

    bench = json.loads(_write(tmp_path).read_text())
    assert strict_fields <= set(bench.keys())
    assert "diagnostics" in bench


def test_writer_is_deterministic_and_sorted(tmp_path):
    p1 = _write(tmp_path)
    content1 = p1.read_text()
    p2 = _write(tmp_path)
    assert content1 == p2.read_text()
    data = json.loads(content1)
    assert data["adjusted_flight_times"][0] == {"role": "IB", "flno": 10, "gun": 1, "time_min": 600}
    assert data["objective_value"] is None


def test_stamp_and_patch(tmp_path):
    p = _write(tmp_path)
    stamp_recomputed_objective(p, 1488074.81)
    assert json.loads(p.read_text())["objective_value"] == 1488074.81
    patch_json_field(p, ["diagnostics", "baseline_reference"], {"objective": 1.0})
    assert json.loads(p.read_text())["diagnostics"]["baseline_reference"] == {"objective": 1.0}

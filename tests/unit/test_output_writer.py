"""Unit tests for src.output.writer -- deterministic JSON output.

marker: unit (solver-free, pure IO logic).
"""
import json
from pathlib import Path

import pytest

from src.candidates.generate import Candidate
from src.output.writer import write_output
from src.solve.runner import SolveResult

pytestmark = pytest.mark.unit


def _candidate(od, flno1, flno2, gap):
    return Candidate(od=od, o=od.split("-")[0], d=od.split("-")[1], gun=1,
                      flno1=flno1, flno2=flno2, arr_time=None, dep_time=None, gap_min=gap)


def test_write_output_produces_expected_json_structure(tmp_path):
    c1 = _candidate("ZZA-ZZB", 9101, 9112, 60)
    c2 = _candidate("ZZB-ZZA", 9201, 9212, 205)
    result = SolveResult(
        status="optimal", objective_value=250.0,
        selected={c1: 1, c2: 0}, solve_time_sec=0.05,
    )
    path = tmp_path / "output.json"
    write_output(path, result)

    data = json.loads(path.read_text())
    assert data["objective_value"] == 250.0
    assert data["solver_metrics"]["status"] == "optimal"
    assert data["solver_metrics"]["solve_time_sec"] == pytest.approx(0.05)
    assert len(data["selected_connections"]) == 1
    assert data["selected_connections"][0]["od"] == "ZZA-ZZB"
    assert data["selected_connections"][0]["flno1"] == 9101
    assert data["selected_connections"][0]["flno2"] == 9112
    assert data["selected_connections"][0]["gap_min"] == 60


def test_write_output_is_deterministic(tmp_path):
    c1 = _candidate("ZZA-ZZB", 9101, 9112, 60)
    result = SolveResult(status="optimal", objective_value=100.0, selected={c1: 1}, solve_time_sec=0.01)

    path1 = tmp_path / "out1.json"
    path2 = tmp_path / "out2.json"
    write_output(path1, result)
    write_output(path2, result)

    assert path1.read_text() == path2.read_text()

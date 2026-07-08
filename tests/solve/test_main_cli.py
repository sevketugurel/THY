"""Walking-skeleton acceptance test: the literal single-command deliverable
(plan §3 M0 DoD: "python main.py --config config/standard.yaml tek komutla
koşar, pytest -m unit yeşil") run via subprocess exactly as a user would invoke it.

M1: config's adjustable_set=all is now genuinely active (free integer time
vars), so the exact M0-era hand-calc (500.0) no longer applies -- the solver
can shift times to admit MORE candidates than the fixed-baseline scenario.
This test asserts a data-derived LOWER BOUND (the fixed-time value, exactly
hand-calculated in tests/fixtures/README.md and re-verified in
tests/solve/test_m1_constraints_c.py) plus end-to-end validity; the exact
free-time optimum is not hand-calculated here on purpose (see
test_m1_constraints_c.py for the hand-calculable adjustable_set="none" case).

marker: solve (small HiGHS solve against synthetic fixture).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
pytestmark = pytest.mark.solve


def test_main_cli_runs_end_to_end_against_fixture(tmp_path):
    output_path = tmp_path / "output.json"
    result = subprocess.run(
        [sys.executable, "main.py", "--config", "src/config/standard.yaml",
         "--fixture", "--output", str(output_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "status=optimal" in result.stdout
    assert "valid=True" in result.stdout

    data = json.loads(output_path.read_text())
    # Lower bound: free time can only do at least as well as the fixed-time
    # scenario (400.0, hand-calculated in tests/fixtures/README.md).
    assert data["objective_value"] >= 400.0 - 1e-6
    assert len(data["selected_connections"]) >= 3
    assert len(data["adjusted_flight_times"]) > 0


def test_main_cli_requires_exactly_one_data_source(tmp_path):
    result = subprocess.run(
        [sys.executable, "main.py", "--config", "src/config/standard.yaml"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "exactly one" in result.stderr

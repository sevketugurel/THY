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

M5f Kapı-5 (docs/CLOSING_PLAN.md): the golden diagnostic-path test
(test_main_writes_schema_compliant_diagnostic_when_ladder_finds_nothing)
runs main.main() IN-PROCESS (not subprocess) so it can monkeypatch
main.solve_with_ladder directly -- forcing the "nothing accepted at any
ladder step" branch deterministically without needing a genuinely
unsolvable fixture (the real fixture always resolves at step1 by design).

marker: solve (small HiGHS solve against synthetic fixture).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import main as main_module
from src.solve.runner import SolveResult

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


def test_main_cli_is_deterministic_excluding_wall_clock(tmp_path):
    def run(out_path):
        subprocess.run(
            [sys.executable, "main.py", "--config", "src/config/standard.yaml",
             "--fixture", "--output", str(out_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        data = json.loads(out_path.read_text())
        del data["solver_metrics"]["solve_time_sec"]
        return data

    run1 = run(tmp_path / "out1.json")
    run2 = run(tmp_path / "out2.json")
    assert run1 == run2


def test_main_writes_schema_compliant_diagnostic_when_ladder_finds_nothing(tmp_path, monkeypatch):
    # M5f Kapı-5 golden test: "gizli test dayanıklılığı" -- if the ladder
    # exhausts every step without an accepted (validated) result, main.py
    # must NEVER leave an invalid/partial tariff at output_path. It writes
    # a schema-compliant diagnostic (objective_value: null, empty tariff,
    # terminal status) and returns a nonzero exit code.
    def fake_ladder(*args, **kwargs):
        result = SolveResult(status="no_feasible_solution_found", objective_value=None,
                              selected={}, solve_time_sec=0.0)
        return None, result, [{"step": "step3_stop_diagnose", "reason": "forced by test"}]

    monkeypatch.setattr(main_module, "solve_with_ladder", fake_ladder)
    output_path = tmp_path / "diagnostic_output.json"
    rc = main_module.main(["--config", "src/config/standard.yaml", "--fixture", "--output", str(output_path)])

    assert rc != 0
    data = json.loads(output_path.read_text())
    assert data["objective_value"] is None
    assert data["selected_connections"] == []
    assert data["adjusted_flight_times"] == []
    assert data["ranking_results"] == []
    assert data["solver_metrics"]["status"] == "no_feasible_solution_found"

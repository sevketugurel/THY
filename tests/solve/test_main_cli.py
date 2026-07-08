"""M0 walking-skeleton acceptance test: the literal single-command deliverable
(plan §3 M0 DoD: "python main.py --config config/standard.yaml tek komutla
koşar, pytest -m unit yeşil") run via subprocess exactly as a user would invoke it.

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
    # Gün1 (250.0) + Gün2 (250.0) per fixtures/README.md hand calc, doubled since
    # both days share the same valid-candidate structure.
    assert data["objective_value"] == pytest.approx(500.0)
    assert len(data["selected_connections"]) == 6


def test_main_cli_requires_exactly_one_data_source(tmp_path):
    result = subprocess.run(
        [sys.executable, "main.py", "--config", "src/config/standard.yaml"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "exactly one" in result.stderr

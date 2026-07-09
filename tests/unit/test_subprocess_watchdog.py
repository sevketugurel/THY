"""Unit tests for src.solve.subprocess_watchdog -- external wall-clock
enforcement for a single ladder step, added after finding that appsi_highs's
own time_limit does not reliably interrupt root-node cut generation on large
models (docs/decisions.md 2026-07-09). Uses tiny fake worker scripts (NOT
the real scripts/_solve_step_worker.py, which needs a real Pyomo model) so
these stay fast and deterministic.

marker: unit (real subprocesses, but sub-second fake workers -- no Pyomo/HiGHS).
"""
import pickle
import textwrap
from pathlib import Path

import pytest

from src.solve.subprocess_watchdog import solve_step_with_watchdog

pytestmark = pytest.mark.unit

_FAKE_WORKER_COMPLETES = textwrap.dedent("""
    import pickle, sys
    input_path, output_path = sys.argv[1], sys.argv[2]
    with open(input_path, "rb") as f:
        spec = pickle.load(f)
    with open(output_path, "wb") as f:
        pickle.dump({
            "status": "optimal", "objective_value": 42.0, "selected": {},
            "solve_time_sec": 0.01, "gap_values": {}, "arr_times": {}, "dep_times": {},
            "rank_values": {}, "beaten_rivals": {}, "model_stats": None,
            "build_time_sec": 0.02, "echo": spec["build_kwargs"],
        }, f)
""")

_FAKE_WORKER_HANGS = textwrap.dedent("""
    import time
    time.sleep(30)
""")


def _write_worker(tmp_path, source):
    path = tmp_path / "fake_worker.py"
    path.write_text(source)
    return path


def test_normal_completion_returns_result_and_build_time(tmp_path):
    worker = _write_worker(tmp_path, _FAKE_WORKER_COMPLETES)
    result, build_time_sec = solve_step_with_watchdog(
        build_kwargs={"candidates": [1, 2, 3]}, solve_kwargs={},
        time_limit_sec=30, watchdog_margin_sec=30, step_name="test_step",
        worker_script=worker,
    )
    assert result.status == "optimal"
    assert result.objective_value == 42.0
    assert build_time_sec == 0.02


def test_hung_subprocess_is_killed_and_reports_watchdog_killed(tmp_path):
    worker = _write_worker(tmp_path, _FAKE_WORKER_HANGS)
    result, build_time_sec = solve_step_with_watchdog(
        build_kwargs={}, solve_kwargs={},
        time_limit_sec=0.1, watchdog_margin_sec=0.1, step_name="test_step",
        sigkill_grace_sec=2, worker_script=worker,
    )
    assert result.status == "watchdog_killed"
    assert result.objective_value is None
    assert build_time_sec is None


def test_watchdog_passes_build_and_solve_kwargs_through_pickle(tmp_path):
    worker = _write_worker(tmp_path, _FAKE_WORKER_COMPLETES)
    result, _ = solve_step_with_watchdog(
        build_kwargs={"candidates": ["a", "b"], "L": 60}, solve_kwargs={"seed": 42},
        time_limit_sec=30, watchdog_margin_sec=30, step_name="test_step",
        worker_script=worker,
    )
    assert result.status == "optimal"

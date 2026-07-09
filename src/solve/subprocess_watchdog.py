"""External wall-clock watchdog for solving ONE ladder step in its own OS
process. See docs/decisions.md 2026-07-09 "appsi_highs time_limit kok-dugum
cut turlarini KESEMIYOR": HiGHS's own time_limit cannot reliably interrupt
root-node cut generation on large models (observed: a 600s configured limit
overran to 1282.9s+ with zero incumbent on a 605K-row presolved model) --
a solver-internal timeout alone is not trustworthy for enforcing a hard
wall-clock budget. This module spawns scripts/_solve_step_worker.py as a
subprocess that builds+solves the model, and SIGTERM/SIGKILLs it externally
if it overruns time_limit_sec by more than watchdog_margin_sec.
"""
import pickle
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from src.solve.runner import SolveResult

WORKER_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "_solve_step_worker.py"
SIGKILL_GRACE_SEC = 15


def solve_step_with_watchdog(
    build_kwargs: dict, solve_kwargs: dict, time_limit_sec: float,
    watchdog_margin_sec: float = 60, step_name: str = "step",
    sigkill_grace_sec: float = SIGKILL_GRACE_SEC, worker_script=WORKER_SCRIPT,
) -> tuple:
    """Returns (SolveResult, build_time_sec_or_None). build_time_sec is None
    when the subprocess was killed before it could report back (the
    ladder's caller should treat that as "unknown", not zero)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "input.pkl"
        output_path = Path(tmpdir) / "output.pkl"
        with open(input_path, "wb") as f:
            pickle.dump({"build_kwargs": build_kwargs, "solve_kwargs": solve_kwargs}, f)

        hard_limit = time_limit_sec + watchdog_margin_sec
        proc = subprocess.Popen([sys.executable, "-u", str(worker_script), str(input_path), str(output_path)])
        t0 = time.time()
        try:
            proc.wait(timeout=hard_limit)
        except subprocess.TimeoutExpired:
            print(
                f"[watchdog] {step_name}: subprocess exceeded {hard_limit:.0f}s "
                f"(time_limit={time_limit_sec}s + margin={watchdog_margin_sec}s) -- sending SIGTERM",
                flush=True,
            )
            proc.terminate()
            try:
                proc.wait(timeout=sigkill_grace_sec)
            except subprocess.TimeoutExpired:
                print(
                    f"[watchdog] {step_name}: SIGTERM ignored after {sigkill_grace_sec}s -- sending SIGKILL",
                    flush=True,
                )
                proc.kill()
                proc.wait(timeout=sigkill_grace_sec)
        wall_time_sec = time.time() - t0

        if output_path.exists():
            with open(output_path, "rb") as f:
                payload = pickle.load(f)
            result = SolveResult(
                status=payload["status"], objective_value=payload["objective_value"],
                selected=payload["selected"], solve_time_sec=payload["solve_time_sec"],
                gap_values=payload["gap_values"], arr_times=payload["arr_times"],
                dep_times=payload["dep_times"], rank_values=payload["rank_values"],
                beaten_rivals=payload["beaten_rivals"], model_stats=payload["model_stats"],
            )
            return result, payload.get("build_time_sec")

        return (
            SolveResult(status="watchdog_killed", objective_value=None, selected={}, solve_time_sec=wall_time_sec),
            None,
        )

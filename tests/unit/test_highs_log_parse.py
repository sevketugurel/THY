"""Unit tests for src.solve.runner.parse_highs_log -- best-effort extraction of
model size (rows/cols/nonzeros/binary) from HiGHS's own log text, so M5's full-data
runs can report presolve stats without re-deriving them from the Pyomo model
(which would only give pre-presolve size, not what HiGHS actually branches on).

marker: unit (pure string parsing, no solver call).
"""
import pytest

from src.solve.runner import parse_highs_log

pytestmark = pytest.mark.unit

_SAMPLE_LOG = """MIP has 18118 rows; 40200 cols; 120000 nonzeros; 40200 integer variables (40200 binary)
Coefficient ranges:
  Matrix  [1e+00, 1e+00]
Presolving model
9000 rows, 20000 cols, 60000 nonzeros 0s
Presolve reductions: rows 9000(-9118); columns 20000(-20200); nonzeros 60000(-60000)

Solving report
  Status            Optimal
  Primal bound      668.75
  Dual bound        668.75
  Gap               0% (tolerance: 0.01%)
"""


def test_parses_original_and_presolved_size():
    stats = parse_highs_log(_SAMPLE_LOG)
    assert stats["orig_rows"] == 18118
    assert stats["orig_cols"] == 40200
    assert stats["orig_nonzeros"] == 120000
    assert stats["orig_binary"] == 40200
    assert stats["presolved_rows"] == 9000
    assert stats["presolved_cols"] == 20000
    assert stats["presolved_nonzeros"] == 60000


def test_parses_final_gap_pct():
    stats = parse_highs_log(_SAMPLE_LOG)
    assert stats["final_gap_pct"] == 0.0


def test_missing_lines_yield_none_not_crash():
    stats = parse_highs_log("some unrelated solver chatter\nwith no recognizable lines\n")
    assert stats["orig_rows"] is None
    assert stats["presolved_rows"] is None
    assert stats["final_gap_pct"] is None


def test_empty_string_yields_all_none():
    stats = parse_highs_log("")
    assert all(v is None for v in stats.values())


def test_nonzero_gap_parsed():
    log = "  Gap               4.32% (tolerance: 5%)\n"
    stats = parse_highs_log(log)
    assert stats["final_gap_pct"] == 4.32

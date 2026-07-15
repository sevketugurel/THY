"""Tests for benchmark baseline time maps and seed-delta rules."""

import json

import pandas as pd
import pytest

from src.benchmark.times import apply_seed_deltas, build_baseline_times, load_seed_deltas

pytestmark = pytest.mark.unit


ANCHOR = pd.Timestamp(2026, 3, 1, 0, 0)


def _tk():
    return pd.DataFrame([
        {
            "flno1": 10,
            "flno2": 20,
            "gun": 1,
            "arr_time": pd.Timestamp(2026, 3, 1, 10, 0),
            "dep_time": pd.Timestamp(2026, 3, 1, 12, 0),
            "dep1": "AAA",
            "arr2": "BBB",
            "cr1": "TK",
        },
        {
            "flno1": 10,
            "flno2": 21,
            "gun": 1,
            "arr_time": pd.Timestamp(2026, 3, 1, 10, 5),
            "dep_time": pd.Timestamp(2026, 3, 1, 13, 0),
            "dep1": "AAA",
            "arr2": "CCC",
            "cr1": "TK",
        },
    ])


def test_baseline_times_first_occurrence_wins():
    times = build_baseline_times(_tk(), ANCHOR)
    assert times[("IB", 10, 1)] == 600
    assert times[("OB", 20, 1)] == 720
    assert times[("OB", 21, 1)] == 780


def test_apply_deltas_happy_path_and_rules():
    baseline = {("IB", 10, 1): 600, ("OB", 20, 1): 720}
    deltas = [
        {"role": "IB", "flno": 10, "gun": 1, "delta_min": -30},
        {"role": "OB", "flno": 99, "gun": 1, "delta_min": 10},
        {"role": "OB", "flno": 20, "gun": 1, "delta_min": 500},
    ]
    times, stats = apply_seed_deltas(baseline, deltas, adjustable_window_min=180)
    assert times[("IB", 10, 1)] == 570
    assert times[("OB", 20, 1)] == 720
    assert stats == {"applied": 1, "skipped_missing_flight": 1, "fallback_window_exceeded": 1}


def test_load_seed_deltas_missing_and_corrupt(tmp_path):
    deltas, note = load_seed_deltas(tmp_path / "missing.json")
    assert deltas == []
    assert "not found" in note

    bad = tmp_path / "bad.json"
    bad.write_text("{bad json")
    deltas, note = load_seed_deltas(bad)
    assert deltas == []
    assert "unreadable" in note

    malformed = tmp_path / "malformed.json"
    malformed.write_text(json.dumps({"deltas": [{"role": "IB", "flno": 1}]}))
    deltas, note = load_seed_deltas(malformed)
    assert deltas == []
    assert "malformed" in note


def test_load_seed_deltas_ok(tmp_path):
    p = tmp_path / "seed.json"
    p.write_text(json.dumps({"deltas": [{"role": "IB", "flno": 10, "gun": 1, "delta_min": -30}]}))
    deltas, note = load_seed_deltas(p)
    assert note == "ok"
    assert len(deltas) == 1

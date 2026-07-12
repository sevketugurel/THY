"""M5i (spec docs/superpowers/specs/2026-07-12-residual-repair-design.md §3.3):
output-şemalı JSON'dan referans nokta yükleme -- saf IO, solver yok (marker yok = unit)."""
import json
from pathlib import Path

import pytest

from src.candidates.generate import Candidate
from src.repair.reference import load_reference_point, resolve_reference_path

L, U = 60, 300


def _candidate(o, d, flno1, flno2, gap_lo, gap_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=max(gap_lo, min(gap_hi, 0)), arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )


def _write_output_json(path, entries):
    path.write_text(json.dumps({"adjusted_flight_times": entries, "selected_connections": []}))


def test_loads_arr_dep_split_by_role(tmp_path):
    c = _candidate("ZZG", "ZZH", 201, 301, 50, 150)
    f = tmp_path / "ref.json"
    _write_output_json(f, [
        {"role": "IB", "flno": 201, "gun": 1, "time_min": 1000},
        {"role": "OB", "flno": 301, "gun": 1, "time_min": 1130},
    ])
    arr, dep = load_reference_point(f, [c])
    assert arr[("IB", 201, 1)] == 1000
    assert dep[("OB", 301, 1)] == 1130


def test_missing_instance_raises_assertion(tmp_path):
    c = _candidate("ZZG", "ZZH", 201, 301, 50, 150)
    f = tmp_path / "ref.json"
    _write_output_json(f, [{"role": "IB", "flno": 201, "gun": 1, "time_min": 1000}])  # OB eksik
    with pytest.raises(AssertionError, match="missing dep"):
        load_reference_point(f, [c])


def test_resolve_reference_path_default_when_none():
    default = Path("runs/warm_start_elastic_output.json")
    assert resolve_reference_path(None, default) == default
    assert resolve_reference_path("runs/x.json", default) == Path("runs/x.json")

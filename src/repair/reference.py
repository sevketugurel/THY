"""M5i RCR Engine (spec docs/superpowers/specs/2026-07-12-residual-repair-design.md
§3.3): output-şemalı bir JSON'dan (adjusted_flight_times) referans nokta yükleme --
scripts/run_lns.py'nin eski _load_starting_reference'ının ve conflict-deactivation
script'inin _load_reference'ının ortak saf çekirdeği. src.model'e bağımlılık YOK."""
import json
from pathlib import Path


def resolve_reference_path(cli_value, default_path: Path) -> Path:
    """--reference verilmezse eski davranış (default_path) bire bir korunur."""
    return Path(cli_value) if cli_value else Path(default_path)


def load_reference_point(path, candidates):
    """(arr_times, dep_times) döndürür; anahtar ("IB"|"OB", flno, gun).
    Dosya, her candidate'ın r1_id/r2_id'sini kapsamak ZORUNDA (bu repo'nun
    writer'ları her zaman tam kapsar) -- eksikte AssertionError."""
    data = json.loads(Path(path).read_text())
    arr_times, dep_times = {}, {}
    for e in data["adjusted_flight_times"]:
        key = (e["role"], e["flno"], e["gun"])
        if e["role"] == "IB":
            arr_times[key] = e["time_min"]
        else:
            dep_times[key] = e["time_min"]
    arr_ids = {c.r1_id for c in candidates}
    dep_ids = {c.r2_id for c in candidates}
    missing_arr = arr_ids - set(arr_times)
    missing_dep = dep_ids - set(dep_times)
    assert not missing_arr, f"reference missing arr instances: {sorted(missing_arr)[:5]}"
    assert not missing_dep, f"reference missing dep instances: {sorted(missing_dep)[:5]}"
    return arr_times, dep_times

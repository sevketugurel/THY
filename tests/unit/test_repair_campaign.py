"""M5i RCR Engine kampanya karar mantığı (spec §4) -- saf Python, solver yok."""
import os
import time

from src.candidates.generate import Candidate
from src.model.deactivation import market_direction_index
from src.repair.campaign import (
    adaptive_k, count_violation_families, escalation_decision, newest_file_since,
    pick_round_kills, should_smoke_validate, split_slack,
)

L, U = 60, 300


def _candidate(o, d, flno1, flno2, gap_lo, gap_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=max(gap_lo, min(gap_hi, 0)), arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )


def _ctx():
    cands = [
        _candidate("ZZG", "ZZH", 201, 301, 50, 350),   # killable
        _candidate("ZZH", "ZZG", 202, 302, 50, 350),   # killable
        _candidate("ZZI", "ZZJ", 203, 303, 100, 200),  # unkillable
        _candidate("ZZJ", "ZZI", 204, 304, 100, 200),  # unkillable
        _candidate("ZZK", "ZZL", 205, 305, 50, 350),   # killable
        _candidate("ZZL", "ZZK", 206, 306, 100, 200),  # unkillable
    ]
    index = market_direction_index(cands)
    pair_slack = {
        ("ZZG", "ZZH", 1): {"e1": 0.0, "e2": 300.0, "total": 300.0},
        ("ZZI", "ZZJ", 1): {"e1": 0.0, "e2": 200.0, "total": 200.0},  # both-unkillable
        ("ZZK", "ZZL", 1): {"e1": 0.0, "e2": 100.0, "total": 100.0},
    }
    contributions = {("ZZG", "ZZH", 1): 10.0, ("ZZH", "ZZG", 1): 999.0}
    return cands, index, pair_slack, contributions


# --- pick_round_kills ---

def test_picks_cheaper_killable_side_worst_first():
    cands, index, ps, contrib = _ctx()
    kills, eq = pick_round_kills(ps, index, cands, contrib, already_killed=set(), k=10, L=L, U=U)
    assert kills[0] == ("ZZG", "ZZH", 1)          # 10.0 < 999.0
    assert ("ZZK", "ZZL", 1) in kills             # tek killable yön o
    assert eq == [("ZZI", "ZZJ", 1)]              # both-unkillable -> equalization-only


def test_k_limit_and_already_killed_skip():
    cands, index, ps, contrib = _ctx()
    kills, _ = pick_round_kills(ps, index, cands, contrib, already_killed=set(), k=1, L=L, U=U)
    assert len(kills) == 1 and kills[0] == ("ZZG", "ZZH", 1)
    kills2, _ = pick_round_kills(ps, index, cands, contrib,
                                 already_killed={("ZZG", "ZZH", 1)}, k=10, L=L, U=U)
    assert ("ZZG", "ZZH", 1) not in kills2 and ("ZZH", "ZZG", 1) not in kills2


# --- escalation_decision (spec §4.5, üç dal) ---

def test_escalation_three_branches():
    assert escalation_decision(10944.0, 10000.0, mechanics_sound=True) == "continue-A"   # >=%5
    assert escalation_decision(10944.0, 10800.0, mechanics_sound=True) == "switch-B"     # 0<x<%5
    assert escalation_decision(10944.0, 10944.0, mechanics_sound=True) == "switch-B"     # =0, sağlam
    assert escalation_decision(10944.0, 10944.0, mechanics_sound=False) == "early-stop"  # =0, bozuk


# --- adaptive_k (spec §4.4) ---

def test_adaptive_k_growth_and_cap():
    assert adaptive_k(30, 10000.0, 9000.0) == 60      # %10 >= %8 -> iki kat
    assert adaptive_k(30, 10000.0, 9500.0) == 30      # %5 < %8 -> sabit
    assert adaptive_k(80, 10000.0, 9000.0) == 100     # tavan
    assert adaptive_k(30, 0.0, 0.0) == 30             # sıfır bölme koruması


# --- smoke eşiği + slack dökümü + ihlal aileleri ---

def test_should_smoke_validate_same_8pct_rule():
    assert should_smoke_validate(10000.0, 9100.0) is True
    assert should_smoke_validate(10000.0, 9500.0) is False


def test_split_slack_pending_vs_open():
    _, _, ps, _ = _ctx()
    pending, open_ = split_slack(ps, killed={("ZZH", "ZZG", 1)})  # ZZG-ZZH çiftinin bwd'si
    assert pending == 300.0 and open_ == 300.0


def test_count_violation_families():
    v = ["E1 AAA-BBB Gün=1: ...", "E2 CCC-DDD Gün=2: ...", "E2 X-Y Gün=3: ...", "rank claim ..."]
    assert count_violation_families(v) == {"E1": 1, "E2": 2, "other": 1}


def test_newest_file_since(tmp_path):
    old = tmp_path / "lns_summary_a.log.json"
    old.write_text("{}")
    t = time.time() + 1
    new = tmp_path / "lns_summary_b.log.json"
    new.write_text("{}")
    os.utime(old, (t - 100, t - 100))
    os.utime(new, (t + 100, t + 100))
    assert newest_file_since(tmp_path, "lns_summary_*.log.json", t) == new
    assert newest_file_since(tmp_path, "lns_summary_*.log.json", t + 200) is None

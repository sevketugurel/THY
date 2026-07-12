"""M5i RCR Engine Adım-0 (spec §3.1): residual çift kayıtları + özet -- saf Python, solver yok."""
from src.candidates.generate import Candidate
from src.model.deactivation import market_direction_index
from src.repair.diagnosis import build_residual_records, summarize_records

L, U = 60, 300


def _candidate(o, d, flno1, flno2, gap_lo, gap_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=max(gap_lo, min(gap_hi, 0)), arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )


def _fixture():
    # Çift 1: ZZG-ZZH -- fwd killable (aralık pencereyi taşıyor), bwd unkillable (tam pencere içi)
    # Çift 2: ZZI-ZZJ -- iki yön de unkillable (both_unkillable)
    cands = [
        _candidate("ZZG", "ZZH", 201, 301, 50, 350),   # killable
        _candidate("ZZH", "ZZG", 202, 302, 100, 200),  # unkillable (⊆ [60,300])
        _candidate("ZZI", "ZZJ", 203, 303, 70, 80),    # unkillable
        _candidate("ZZJ", "ZZI", 204, 304, 90, 90),    # unkillable + forced-on (tekil, pencere içi)
    ]
    index = market_direction_index(cands)
    pair_slack = {
        ("ZZG", "ZZH", 1): {"e1": 0.0, "e2": 100.0, "total": 100.0},
        ("ZZI", "ZZJ", 1): {"e1": 0.4, "e2": 0.0, "total": 0.4},
        ("ZZK", "ZZL", 1): {"e1": 0.0, "e2": 0.0, "total": 0.0},  # ihlalsiz -- kayda girmez
    }
    contributions = {("ZZG", "ZZH", 1): 500.0, ("ZZH", "ZZG", 1): 40.0}
    selected_counts = {("ZZG", "ZZH", 1): 1, ("ZZH", "ZZG", 1): 1,
                       ("ZZI", "ZZJ", 1): 1, ("ZZJ", "ZZI", 1): 1}
    rho = {("ZZG", "ZZH"): 10, ("ZZH", "ZZG"): 12, ("ZZI", "ZZJ"): 5, ("ZZJ", "ZZI"): 5}
    return cands, index, pair_slack, contributions, selected_counts, rho


def test_records_sorted_by_total_desc_and_zero_slack_excluded():
    cands, index, ps, contrib, sel, rho = _fixture()
    records = build_residual_records(ps, index, cands, contrib, sel, rho, L, U)
    assert [r["pair"] for r in records] == [["ZZG", "ZZH", 1], ["ZZI", "ZZJ", 1]]


def test_killability_and_forced_on_flags():
    cands, index, ps, contrib, sel, rho = _fixture()
    records = build_residual_records(ps, index, cands, contrib, sel, rho, L, U)
    r1 = records[0]
    assert r1["directions"]["fwd"]["killable"] is True
    assert r1["directions"]["bwd"]["killable"] is False
    assert r1["both_unkillable"] is False
    r2 = records[1]
    assert r2["both_unkillable"] is True
    assert r2["directions"]["bwd"]["has_forced_on"] is True


def test_contribution_lookup_defaults_to_zero():
    cands, index, ps, contrib, sel, rho = _fixture()
    records = build_residual_records(ps, index, cands, contrib, sel, rho, L, U)
    assert records[1]["directions"]["fwd"]["reward_contribution"] == 0.0


def test_summary_counts_and_c1_loss():
    cands, index, ps, contrib, sel, rho = _fixture()
    records = build_residual_records(ps, index, cands, contrib, sel, rho, L, U)
    s = summarize_records(records)
    assert s["n_violated_pairs"] == 2
    assert s["n_both_unkillable"] == 1
    assert s["n_killable_coverable"] == 1
    # C1 kaybı = her çiftte min(katkı): min(500,40) + min(0,0) = 40
    assert s["c1_reward_loss_estimate"] == 40.0
    assert s["n_forced_on_directions"] == 1
    assert s["top_stations"][0][1] >= 1  # istasyon sayımları mevcut

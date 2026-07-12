"""M5i RCR Engine Adım-0 teşhis mantığı (spec §3.1) -- saf Python, IO yok, solver yok.
Her pozitif-slack (o,d,gun) çifti için killability/ödül-katkı kaydı üretir;
scripts/diagnose_residual_repair.py bunları full-data girdileriyle çağırır."""
from src.model.deactivation import is_direction_killable


def _direction_record(direction, direction_index, candidates, contributions,
                      selected_counts, rho, L, U):
    idxs = direction_index.get(direction, [])
    dir_cands = [candidates[i] for i in idxs]
    return {
        "direction": list(direction),
        "killable": bool(dir_cands) and is_direction_killable(dir_cands, L, U),
        "n_candidates": len(idxs),
        "n_selected": selected_counts.get(direction, 0),
        "has_forced_on": any(c.gap_lo == c.gap_hi and L <= c.gap_lo <= U for c in dir_cands),
        "rho": rho.get((direction[0], direction[1]), 0),
        "reward_contribution": contributions.get(direction, 0.0),
    }


def build_residual_records(pair_slack, direction_index, candidates, contributions,
                           selected_counts, rho, L, U):
    """compute_pair_slack çıktısındaki her pozitif-total çift için kayıt;
    total'e göre azalan sıralı. contributions: recompute_objective breakdown'ının
    markets listesinden {(o,d,gun): connection_component+ranking_component} --
    kaydı olmayan yön 0.0 (o yönde bugün ödül yok => kapatması bedava)."""
    records = []
    for (o, d, gun), s in pair_slack.items():
        if s["total"] <= 0:
            continue
        fwd_rec = _direction_record((o, d, gun), direction_index, candidates,
                                    contributions, selected_counts, rho, L, U)
        bwd_rec = _direction_record((d, o, gun), direction_index, candidates,
                                    contributions, selected_counts, rho, L, U)
        records.append({
            "pair": [o, d, gun],
            "e1": s["e1"], "e2": s["e2"], "total": s["total"],
            "directions": {"fwd": fwd_rec, "bwd": bwd_rec},
            "both_unkillable": not (fwd_rec["killable"] or bwd_rec["killable"]),
        })
    records.sort(key=lambda r: (-r["total"], r["pair"]))
    return records


def summarize_records(records):
    """Spec §3.1 toplamları -- Adım-0 konsol özeti + JSON'un summary alanı."""
    n_pairs = len(records)
    n_both_unkillable = sum(1 for r in records if r["both_unkillable"])
    c1_loss = sum(min(r["directions"]["fwd"]["reward_contribution"],
                      r["directions"]["bwd"]["reward_contribution"]) for r in records)
    stations = {}
    for r in records:
        for st in (r["pair"][0], r["pair"][1]):
            stations[st] = stations.get(st, 0) + 1
    return {
        "n_violated_pairs": n_pairs,
        "n_both_unkillable": n_both_unkillable,
        "n_killable_coverable": n_pairs - n_both_unkillable,
        "killable_cover_ratio": ((n_pairs - n_both_unkillable) / n_pairs) if n_pairs else 1.0,
        "n_forced_on_directions": sum(
            1 for r in records for t in ("fwd", "bwd") if r["directions"][t]["has_forced_on"]),
        "c1_reward_loss_estimate": c1_loss,
        "top_stations": sorted(stations.items(), key=lambda kv: (-kv[1], kv[0]))[:10],
    }

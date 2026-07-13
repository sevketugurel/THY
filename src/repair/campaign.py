"""M5i RCR Engine kampanya karar mantığı (spec §4) -- saf Python, IO/solver yok.
scripts/run_residual_repair.py orkestratörü bu fonksiyonları çağırır;
üç dallı eskalasyon (§4.5), adaptif K (§4.4), smoke eşiği (§4.7),
worst-K kill seçimi (§4.1) ve tur-logu yardımcıları burada test edilir."""
from pathlib import Path

from src.model.deactivation import is_direction_killable


def order_residual_kill_candidates(pair_slack, direction_index, candidates,
                                   contributions, already_killed, L, U):
    """Gece-4 probe modu (2026-07-13): her açık ihlalli çift için EN UCUZ
    killable yönü seç, çiftleri (reward_loss ASC, pair_slack DESC, yön)
    sırasında listele -- 'önce en ucuz gerçekleşebilir kill' hipotezi
    (worst-first'ün 4 probe'da primal aramayı kırdığı gece bulgusunun tersi).
    Returns [{"direction","pair","reward_loss","pair_slack"}]; both-unkillable
    ve bir ucu zaten kapatılmış çiftler listede YOK."""
    entries = []
    for (o, d, gun), s in pair_slack.items():
        if s["total"] <= 0:
            continue
        fwd, bwd = (o, d, gun), (d, o, gun)
        if fwd in already_killed or bwd in already_killed:
            continue
        options = []
        for dirn in (fwd, bwd):
            dir_cands = [candidates[i] for i in direction_index.get(dirn, [])]
            if dir_cands and is_direction_killable(dir_cands, L, U):
                options.append((contributions.get(dirn, 0.0), len(dir_cands), dirn))
        if not options:
            continue
        options.sort()
        cost, _n, dirn = options[0]
        entries.append({"direction": dirn, "pair": fwd,
                        "reward_loss": cost, "pair_slack": s["total"]})
    entries.sort(key=lambda e: (e["reward_loss"], -e["pair_slack"], e["direction"]))
    return entries


def pick_round_kills(pair_slack, direction_index, candidates, contributions,
                     already_killed, k, L, U, ordering="worst-slack"):
    """Spec §4.1 adım 2: her çiftte killable yönlerden düşük
    reward_contribution'lı olanı kapat. Both-unkillable çiftler K'ya
    SAYILMAZ (equalization_only). Bir ucu zaten kapatılmış çiftler atlanır.

    ordering (gece-4): "worst-slack" = çiftler total slack DESC (spec'in
    orijinali); "cheapest" = order_residual_kill_candidates sırası
    (reward_loss ASC, slack DESC) -- worst-first'ün primal aramayı kırdığı
    gece bulgusundan sonra eklendi."""
    if ordering not in ("worst-slack", "cheapest"):
        raise ValueError(f"pick_round_kills: unknown ordering {ordering!r}")
    kills, equalization_only = [], []
    if ordering == "cheapest":
        entries = order_residual_kill_candidates(
            pair_slack, direction_index, candidates, contributions,
            already_killed, L, U)
        kills = [e["direction"] for e in entries[:k]]
        covered_pairs = {e["pair"] for e in entries}
        for (o, d, gun), s in sorted(pair_slack.items()):
            if s["total"] <= 0:
                continue
            fwd, bwd = (o, d, gun), (d, o, gun)
            if fwd in already_killed or bwd in already_killed:
                continue
            if fwd not in covered_pairs:
                equalization_only.append(fwd)
        return kills, equalization_only
    ordered = sorted(((key, s) for key, s in pair_slack.items() if s["total"] > 0),
                     key=lambda kv: (-kv[1]["total"], kv[0]))
    for (o, d, gun), _s in ordered:
        if len(kills) >= k:
            break
        fwd, bwd = (o, d, gun), (d, o, gun)
        if fwd in already_killed or bwd in already_killed:
            continue
        options = []
        for dirn in (fwd, bwd):
            dir_cands = [candidates[i] for i in direction_index.get(dirn, [])]
            if dir_cands and is_direction_killable(dir_cands, L, U):
                options.append((contributions.get(dirn, 0.0), len(dir_cands), dirn))
        if not options:
            equalization_only.append(fwd)
            continue
        options.sort()
        kills.append(options[0][2])
    return kills, equalization_only


def escalation_decision(sigma_start, sigma_now, mechanics_sound, threshold_pct=0.05):
    """Spec §4.5: ilk 2 tur sonunda üç dal."""
    drop = sigma_start - sigma_now
    if drop >= threshold_pct * sigma_start:
        return "continue-A"
    if drop > 0:
        return "switch-B"
    return "switch-B" if mechanics_sound else "early-stop"


def adaptive_k(current_k, sigma_before, sigma_after, cap=100, growth_threshold_pct=0.08):
    """Spec §4.4: tur düşüşü mevcut Σslack'in >=%8'i ise K iki katına (tavan)."""
    if sigma_before <= 0:
        return current_k
    if (sigma_before - sigma_after) >= growth_threshold_pct * sigma_before:
        return min(cap, current_k * 2)
    return current_k


def should_smoke_validate(sigma_before, sigma_after, threshold_pct=0.08):
    """Spec §4.7 (kullanıcı düzeltmesi #2): §4.4 ile AYNI %8 eşiği."""
    return sigma_before > 0 and (sigma_before - sigma_after) >= threshold_pct * sigma_before


def split_slack(pair_slack, killed):
    """Spec §4.2: kapatılmış-ama-henüz-itilmemiş çiftlerdeki slack vs açık."""
    pending = open_ = 0.0
    for (o, d, gun), s in pair_slack.items():
        if (o, d, gun) in killed or (d, o, gun) in killed:
            pending += s["total"]
        else:
            open_ += s["total"]
    return pending, open_


def count_violation_families(violations):
    """Validator ihlal string'lerini ailelere say (smoke log formatı için)."""
    counts = {"E1": 0, "E2": 0, "other": 0}
    for v in violations:
        if v.startswith("E1 "):
            counts["E1"] += 1
        elif v.startswith("E2 "):
            counts["E2"] += 1
        else:
            counts["other"] += 1
    return counts


def newest_file_since(directory, glob_pattern, since_epoch):
    """run_lns'in kendi <ts>'li özet dosyasını keşif: since_epoch'tan yeni,
    en yeni mtime'lı eşleşme (yoksa None)."""
    matches = [p for p in Path(directory).glob(glob_pattern) if p.stat().st_mtime > since_epoch]
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None

#!/usr/bin/env python3
"""M5i RCR Engine kampanya orkestratörü (spec docs/superpowers/specs/
2026-07-12-residual-repair-design.md §3.4 + §4): A modu turları (worst-K kill +
40dk LNS) -> ilk 2 tur sonunda üç dallı eskalasyon (§4.5) -> gerekirse B modu
(tam killable cover + warm_start_elastic + kalan bütçe LNS). Keep-best persist;
Σslack=0'da strict validate; valid=True'da DUR ve RAPORLA --
outputs/full_data_output.json ASLA yazılmaz (spec §0.5).

Kullanım:
  .venv/bin/python3 -u scripts/run_residual_repair.py --dry-run   # solver'sız plan kontrolü
  nohup .venv/bin/python3 -u scripts/run_residual_repair.py > runs/residual_repair_console.log 2>&1 &
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.config.paths import FULL_FP, FULL_OD, FULL_YV
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table, load_yolcu_verisi
from src.data.provenance import file_provenance
from src.model.deactivation import market_direction_index
from src.model.lns import compute_gamma_infeasible_pairs, compute_pair_slack
from src.repair.campaign import (
    adaptive_k, count_violation_families, escalation_decision, newest_file_since,
    pick_round_kills, should_smoke_validate, split_slack,
)
from src.repair.reference import load_reference_point
from src.validate.independent_validator import validate_output

PY = sys.executable
SIGMA_ZERO_EPS = 1e-6


def _now():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _measure(candidates, journey_constants, partial_path, L, U, alpha, gamma, gamma_inf):
    arr, dep = load_reference_point(partial_path, candidates)
    ps = compute_pair_slack(candidates, journey_constants, arr, dep, L, U, alpha, gamma,
                            gamma_infeasible_pairs=gamma_inf)
    sigma = sum(v["total"] for v in ps.values())
    n_e1 = sum(1 for v in ps.values() if v["e1"] > 0)
    n_e2 = sum(1 for v in ps.values() if v["e2"] > 0)
    return ps, sigma, n_e1, n_e2


def _run_lns_round(reference, directions_file, wall_sec, out_prefix, seed):
    """run_lns subprocess'i; (summary_dict|None, console_log_path) döner."""
    t_start = time.time()
    cmd = [PY, "-u", "scripts/run_lns.py",
           "--reference", str(reference),
           "--deactivation-file", str(directions_file),
           "--selection", "component", "--builder", "fix",
           "--max-wall-sec", str(wall_sec), "--seed", str(seed),
           "--output", f"{out_prefix}_lns_output.json"]
    log_path = Path(f"{out_prefix}_lns_console.log")
    print(f"[campaign] LNS: {' '.join(cmd)}", flush=True)
    try:
        with open(log_path, "w") as fh:
            subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                           timeout=wall_sec + 900, check=False)
    except subprocess.TimeoutExpired:
        print("[campaign] LNS subprocess dış zaman aşımı (round failed sayılır)", flush=True)
    summary_path = newest_file_since("runs", "lns_summary_*.log.json", t_start)
    if summary_path is None:
        return None, log_path
    return json.loads(summary_path.read_text()), log_path


def _run_elastic_step(directions_file, campaign_dir, n_round):
    """M5i gece-2 düzeltmesi (docs/decisions.md 2026-07-13): kill'ler yalnız
    TAM serbestlikte gerçekleşebiliyor -- G gün-kümesi + A rotasyon zarfı,
    per-component LNS'te donuk komşular pencere-dışına itişe izin vermiyor
    (round-1/2 otopsisi: opportunistic fix'e rağmen 20/20 infeasible; kanıt
    runs/residual_repair_campaign_20260712T205104Z/round1_lns_console.log).
    Proven M5h deseni tur-içine alındı: her tur önce mini-elastik (tüm ağ
    serbest, kill'leri gerçekleştirir), sonra LNS o noktadan cilalar.

    Returns kalıcı kopyanın yolu (campaign_dir/roundN_elastic_output.json)
    ya da None (watchdog/çökme -- taze çıktı üretilmedi)."""
    out_log = campaign_dir / f"round{n_round}_elastic_console.log"
    # Gece-3 ayarı (2026-07-13): 506/491 kill probe'ları dual~0 + SIFIR
    # incumbent imzasıyla tıkandı (çözüm LP'de var, primal arama bulamıyor)
    # -- effort 0.3->0.5 (M5h deactivation scriptinin default'u) + 900->1200s.
    cmd = [PY, "-u", "scripts/warm_start_elastic.py",
           "--deactivation-file", str(directions_file),
           "--time-limit-sec", "1200", "--max-improving-sols", "1",
           "--mip-heuristic-effort", "0.5"]
    print(f"[campaign] elastik: {' '.join(cmd)}", flush=True)
    t_start = time.time()
    try:
        with open(out_log, "w") as fh:
            subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                           timeout=2700, check=False)
    except subprocess.TimeoutExpired:
        print("[campaign] elastik adım dış zaman aşımı", flush=True)
        return None
    wse_out = Path("runs/warm_start_elastic_output.json")
    if not (wse_out.exists() and wse_out.stat().st_mtime > t_start):
        return None  # taze çıktı yok (watchdog_killed, sıfır incumbent)
    dst = campaign_dir / f"round{n_round}_elastic_output.json"
    shutil.copy2(wse_out, dst)  # sonraki turun overwrite'ından koru
    return dst


def _strict_validate(partial_path, config):
    return validate_output(
        Path(partial_path), FULL_OD, L=config["L"], U=config["U"],
        adjustable_window_min=config["adjustable_window_min"], adjustable_set=config["adjustable_set"],
        flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
        alpha=config["alpha"], gamma=config["gamma"],
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], e1_activation=config["e1_activation"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", default="runs/lns_best_partial_20260712T150223Z.json")
    parser.add_argument("--base-deactivation", default="runs/conflict_deactivation_level04_directions.json")
    parser.add_argument("--diagnosis", default="runs/residual_repair_diagnosis.json")
    parser.add_argument("--budget-sec", type=float, default=14400.0)
    parser.add_argument("--round-wall-sec", type=float, default=2400.0)
    parser.add_argument("--k", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true",
                         help="Solver yok: tur-1 kill planı + bütçe aritmetiği yazdırılır, çıkılır.")
    args = parser.parse_args()

    assert Path(args.diagnosis).exists(), \
        "Adım-0 zorunlu önkoşul (spec §0.1): önce scripts/diagnose_residual_repair.py koş"

    t0 = time.time()
    deadline = t0 + args.budget_sec
    campaign_dir = Path(f"runs/residual_repair_campaign_{_now()}")
    campaign_dir.mkdir(parents=True, exist_ok=True)

    # --- paylaşılan preprocessing bloğu (run_conflict_deactivation_feasibility.py ile aynı) ---
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U, alpha, gamma = config["L"], config["U"], config["alpha"], config["gamma"]

    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FULL_YV, strict=False)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    anchor = compute_epoch_anchor(tk)

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=L, U=U, gun=gun, adjustable_window_min=config["adjustable_window_min"],
            adjustable_set=config["adjustable_set"], epoch_anchor=anchor,
        ))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    provider = BlockTimeProvider(tk, L=L, U=U)
    journey_constants = {}
    dropped_markets = set()
    for c in candidates:
        market = (c.o, c.d)
        if market in journey_constants or market in dropped_markets:
            continue
        try:
            journey_constants[market] = provider.get_journey_constant(c.o, c.d)
        except KeyError:
            try:
                journey_constants[market] = provider.get_journey_constant_estimate(c.o, c.d)
            except KeyError:
                dropped_markets.add(market)
    candidates = [c for c in candidates if (c.o, c.d) in journey_constants]
    # --- preprocessing sonu ---

    direction_index = market_direction_index(candidates)
    gamma_inf = compute_gamma_infeasible_pairs(candidates, journey_constants, L, U, gamma)

    diagnosis = json.loads(Path(args.diagnosis).read_text())
    contributions = {}
    for r in diagnosis["records"]:
        for tag in ("fwd", "bwd"):
            d = r["directions"][tag]
            contributions[tuple(d["direction"])] = d["reward_contribution"]

    base_killed = {tuple(d) for d in json.loads(Path(args.base_deactivation).read_text())}
    best_partial = args.reference
    best_killed = set(base_killed)
    _, best_sigma, n_e1, n_e2 = _measure(candidates, journey_constants, best_partial,
                                         L, U, alpha, gamma, gamma_inf)
    sigma_campaign_start = best_sigma
    print(f"[campaign] start: Sigma={best_sigma:.2f} (E1={n_e1}, E2={n_e2}) "
          f"base_killed={len(base_killed)} budget={args.budget_sec:.0f}s", flush=True)

    campaign_log = {"started_utc": datetime.now(timezone.utc).isoformat(),
                    "data_provenance": {"FULL_OD": file_provenance(FULL_OD)},
                    "sigma_start": best_sigma, "rounds": []}

    def _persist_log():
        (campaign_dir / "campaign_log.json").write_text(
            json.dumps(campaign_log, indent=2, ensure_ascii=False))

    def _final_report(reason):
        campaign_log["finished_utc"] = datetime.now(timezone.utc).isoformat()
        campaign_log["finish_reason"] = reason
        campaign_log["sigma_final_best"] = best_sigma
        campaign_log["best_partial"] = str(best_partial)
        campaign_log["killed_total"] = len(best_killed)
        campaign_log["reward_loss_estimate_total"] = sum(
            contributions.get(d, 0.0) for d in best_killed - base_killed)
        _persist_log()
        (campaign_dir / "campaign_summary.json").write_text(
            json.dumps({k: v for k, v in campaign_log.items() if k != "rounds"},
                       indent=2, ensure_ascii=False))
        print(f"[campaign] BİTTİ ({reason}): Sigma {sigma_campaign_start:.2f} -> {best_sigma:.2f}, "
              f"best={best_partial}, kampanya-kill=+{len(best_killed)-len(base_killed)}, "
              f"log={campaign_dir}", flush=True)

    mode = "A"
    k = args.k
    n_round = 0
    mechanics = []  # her tur: (kill_uygulandi: bool, iter_kostu: bool)

    def _escalation_check():
        """Spec §4.5: 2 tamamlanmış A-turu sonunda üç dallı karar.
        Returns 'stop' | 'switch-B' | None."""
        mech_sound = all(m[0] for m in mechanics) and any(m[1] for m in mechanics)
        decision = escalation_decision(sigma_campaign_start, best_sigma, mech_sound)
        print(f"[campaign] eskalasyon (2 tur sonu): {decision} "
              f"(Sigma {sigma_campaign_start:.2f}->{best_sigma:.2f}, "
              f"mekanik={'sağlam' if mech_sound else 'bozuk'})", flush=True)
        if decision == "early-stop":
            return "stop"
        if decision == "switch-B":
            return "switch-B"
        return None

    while True:
        remaining = deadline - time.time()
        if remaining < 2100 + args.round_wall_sec + 300:
            _final_report("budget_exhausted")
            return

        n_round += 1
        pair_slack, sigma_before, n_e1, n_e2 = _measure(
            candidates, journey_constants, best_partial, L, U, alpha, gamma, gamma_inf)

        round_k = k if mode == "A" else 10**9  # B modu: tüm killable-coverable (spec §4.6)
        kills, eq_only = pick_round_kills(pair_slack, direction_index, candidates,
                                          contributions, best_killed, round_k, L, U)

        round_killed = best_killed | set(kills)
        directions_file = Path(f"runs/residual_repair_round{n_round}_directions.json")
        directions_file.write_text(json.dumps(sorted([list(d) for d in round_killed])))
        print(f"[campaign] round {n_round} ({mode}): +{len(kills)} kill "
              f"(toplam {len(round_killed)}), equalization-only={len(eq_only)}, K={round_k}", flush=True)

        if args.dry_run:
            print(f"[campaign] DRY-RUN kills[:10]={kills[:10]}", flush=True)
            print(f"[campaign] DRY-RUN eq_only[:5]={eq_only[:5]}", flush=True)
            n_rounds_fit = int(args.budget_sec // (args.round_wall_sec + 300))
            print(f"[campaign] DRY-RUN: bütçe {args.budget_sec:.0f}s, tur {args.round_wall_sec:.0f}s "
                  f"-> ~{n_rounds_fit} tur sığar", flush=True)
            return

        out_prefix = campaign_dir / f"round{n_round}"
        round_rec = {"round": n_round, "mode": mode, "k": round_k if mode == "A" else "ALL",
                     "kills_added": len(kills), "equalization_only": len(eq_only),
                     "sigma_before": sigma_before}

        # HER turda önce mini-elastik: kill'leri tam serbestlikte gerçekleştir
        # (gece-2 düzeltmesi -- gerekçe _run_elastic_step docstring'inde).
        elastic_path = _run_elastic_step(directions_file, campaign_dir, n_round)
        if elastic_path is None:
            mechanics.append((False, False))
            if mode == "B":
                mode = "A"  # B'nin tam-cover elastiği tıkandı -- A'ya dön (level07 kliği)
            k = max(1, k // 2)  # gece-3: floor 10->1, kliği ince tarayabilsin
            round_rec.update({"status": "elastic-failed",
                              "next_repair_decision": f"revert+K->{k}",
                              "validator_status": "not-run",
                              "wall_sec": round(time.time() - t0, 1)})
            print(f"[campaign] round {n_round}: elastik adım BAŞARISIZ -- "
                  f"kill'ler geri alındı, K={k}", flush=True)
            (campaign_dir / f"round_{n_round}.json").write_text(
                json.dumps(round_rec, indent=2, ensure_ascii=False))
            campaign_log["rounds"].append(round_rec)
            _persist_log()
            if n_round == 2 and mode == "A":
                verdict = _escalation_check()
                if verdict == "stop":
                    _final_report("early_stop_mechanics")
                    return
                if verdict == "switch-B":
                    mode = "B"
            continue

        _, s_el, _, _ = _measure(candidates, journey_constants, elastic_path,
                                 L, U, alpha, gamma, gamma_inf)
        round_rec["sigma_after_elastic"] = s_el
        print(f"[campaign] round {n_round}: elastik nokta Sigma={s_el:.2f} "
              f"(best={best_sigma:.2f})", flush=True)
        if s_el < best_sigma - 1e-9:
            best_partial, best_sigma, best_killed = str(elastic_path), s_el, round_killed
            if best_sigma <= SIGMA_ZERO_EPS:
                v = _strict_validate(best_partial, config)
                round_rec["validator_status"] = f"strict:{'valid' if v.is_valid else 'INVALID'}"
                campaign_log["rounds"].append(round_rec)
                (campaign_dir / f"round_{n_round}.json").write_text(
                    json.dumps(round_rec, indent=2, ensure_ascii=False))
                if v.is_valid:
                    _final_report("SIGMA_ZERO_VALID -- outputs/ YAZILMADI, kullanıcı onayı bekleniyor")
                else:
                    for viol in v.violations[:15]:
                        print(f"  [violation] {viol}", flush=True)
                    _final_report("SIGMA_ZERO_BUT_INVALID -- anomali, insan incelemesi gerekli")
                return

        lns_wall = args.round_wall_sec if mode == "A" else max(600.0, deadline - time.time() - 900)
        # LNS referansı HER ZAMAN bu turun elastik noktası: kill-tutarlı tek nokta o
        summary, _console = _run_lns_round(elastic_path, directions_file,
                                           lns_wall, out_prefix, args.seed)
        if summary is None:
            mechanics.append((len(kills) > 0, False))
            round_rec.update({"status": "failed", "next_repair_decision": "revert+continue",
                              "validator_status": "not-run"})
            print(f"[campaign] round {n_round} FAILED (özet yok) -- referans korunur", flush=True)
        elif not summary.get("partial_output_path"):
            # LNS koştu ama hiç iyileşme üretmedi (best-partial dosyası yok) --
            # bu mekanik arıza DEĞİL (round-1 otopsisi: 20 iterasyon gerçekten
            # koştu); keep-best gereği referans + kill seti korunur.
            mechanics.append((len(kills) > 0, summary.get("n_iterations", 0) > 0))
            round_rec.update({"status": "ok-no-improve",
                              "sigma_slack": sigma_before,
                              "lns_summary_n_iterations": summary.get("n_iterations"),
                              "next_repair_decision": "revert",
                              "validator_status": "not-run",
                              "wall_sec": round(time.time() - t0, 1)})
            print(f"[campaign] round {n_round}: iyileşme yok "
                  f"({summary.get('n_iterations')} iterasyon) -- referans korunur", flush=True)
        else:
            new_partial = summary["partial_output_path"]
            ps_new, sigma_after, n_e1_a, n_e2_a = _measure(
                candidates, journey_constants, new_partial, L, U, alpha, gamma, gamma_inf)
            pending, open_ = split_slack(ps_new, round_killed)
            improved = sigma_after < best_sigma - 1e-9
            mechanics.append((len(kills) > 0, summary.get("n_iterations", 0) > 0))

            validator_status = "not-run"
            if improved and should_smoke_validate(sigma_before, sigma_after):
                v = _strict_validate(new_partial, config)
                fam = count_violation_families(v.violations)
                validator_status = ("smoke:valid" if v.is_valid else
                                    f"smoke:invalid(E1={fam['E1']},E2={fam['E2']},other={fam['other']})")
                if fam["other"] > 0:
                    print(f"[campaign] UYARI: E1/E2 dışı {fam['other']} ihlal!", flush=True)

            if improved:
                old_before = best_sigma
                best_partial, best_sigma, best_killed = new_partial, sigma_after, round_killed
                if mode == "A":
                    k = adaptive_k(k, old_before, sigma_after)
                decision = "adopt"
            else:
                decision = "revert"

            round_rec.update({
                "status": "ok", "sigma_slack": sigma_after,
                "sigma_slack_killed_pending": pending, "sigma_slack_open": open_,
                "e1_pairs_violated": n_e1_a, "e2_pairs_violated": n_e2_a,
                "killed_direction_count_round": len(kills),
                "killed_direction_count_total": len(best_killed),
                "reward_loss_estimate_total": sum(
                    contributions.get(d, 0.0) for d in best_killed - base_killed),
                "validator_status": validator_status,
                "partial_output_path": new_partial,
                "lns_summary_n_iterations": summary.get("n_iterations"),
                "next_repair_decision": decision, "wall_sec": round(time.time() - t0, 1),
            })
            print(f"[campaign] round {n_round}: Sigma {sigma_before:.2f} -> {sigma_after:.2f} "
                  f"({decision}); best={best_sigma:.2f}; pending={pending:.1f} open={open_:.1f}", flush=True)

            # Σslack=0 -> strict validate -> valid=True'da DUR (spec §4.7)
            if best_sigma <= SIGMA_ZERO_EPS:
                v = _strict_validate(best_partial, config)
                round_rec["validator_status"] = f"strict:{'valid' if v.is_valid else 'INVALID'}"
                campaign_log["rounds"].append(round_rec)
                (campaign_dir / f"round_{n_round}.json").write_text(
                    json.dumps(round_rec, indent=2, ensure_ascii=False))
                if v.is_valid:
                    _final_report("SIGMA_ZERO_VALID -- outputs/ YAZILMADI, kullanıcı onayı bekleniyor")
                else:
                    for viol in v.violations[:15]:
                        print(f"  [violation] {viol}", flush=True)
                    _final_report("SIGMA_ZERO_BUT_INVALID -- anomali, insan incelemesi gerekli")
                return

        (campaign_dir / f"round_{n_round}.json").write_text(
            json.dumps(round_rec, indent=2, ensure_ascii=False))
        campaign_log["rounds"].append(round_rec)
        _persist_log()

        # Spec §4.5: ilk 2 tur sonunda üç dallı karar (yalnız A modunda)
        if mode == "A" and n_round == 2:
            verdict = _escalation_check()
            if verdict == "stop":
                _final_report("early_stop_mechanics")
                return
            if verdict == "switch-B":
                mode = "B"


if __name__ == "__main__":
    main()

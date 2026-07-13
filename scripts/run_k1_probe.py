#!/usr/bin/env python3
"""M5i RCR Engine — K=1 AYRIM PROBE'u (gece-4, 2026-07-13, kullanıcı direktifi).

Soru: "Tek bir doğru direction kapatmak bile solver tarafından
gerçekleştirilebiliyor mu?" — K=30/15/10 elastik denemelerinin dördü de
dual~0.009 + SIFIR incumbent verdi (çözüm LP'de var, primal bulamıyor);
bu probe sayı-kliği ile toksik-yön hipotezini AYIRIR.

Protokol:
  - level04 base (476 yön) üstüne HER SEFERİNDE +1 yeni direction.
  - Adaylar cheapest-first: reward_loss ASC, pair_slack DESC
    (src.repair.campaign.order_residual_kill_candidates).
  - Her deneme: warm_start_elastic KISA limitle (default 750s; level04'ün
    kanıtlı incumbent süresi 534s + pay), PROVEN config (effort default 0.3).
  - İncumbent üretenler incremental keep-best ile birikir: sonraki deneme
    base + BİRİKMİŞ çalışanlar + yeni aday koşar (birikmiş set her adımda
    yeniden doğrulanmış olur).
  - İlk `--fail-streak-stop` denemede SIFIR başarı -> "K1_ALL_FAIL" ile dur
    (kullanıcı madde 4: honest direction-kill hattının net teşhisi).
  - outputs/ ASLA yazılmaz; LNS yok (probe saf elastik-realizasyon testi).

Kullanım: .venv/bin/python3 -u scripts/run_k1_probe.py [--max-attempts 20]
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
from src.config.paths import FULL_OD, FULL_YV
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table, load_yolcu_verisi
from src.data.provenance import file_provenance
from src.model.deactivation import market_direction_index
from src.model.lns import compute_gamma_infeasible_pairs, compute_pair_slack
from src.repair.campaign import newest_file_since, order_residual_kill_candidates
from src.repair.reference import load_reference_point

PY = sys.executable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", default="runs/lns_best_partial_20260712T150223Z.json")
    parser.add_argument("--base-deactivation", default="runs/conflict_deactivation_level04_directions.json")
    parser.add_argument("--diagnosis", default="runs/residual_repair_diagnosis.json")
    parser.add_argument("--max-attempts", type=int, default=20)
    parser.add_argument("--fail-streak-stop", type=int, default=10,
                         help="ilk N denemede SIFIR başarı varsa K1_ALL_FAIL ile dur")
    parser.add_argument("--time-limit-sec", type=float, default=750.0,
                         help="warm_start_elastic ana solve limiti (level04 kanıtı 534s + pay)")
    parser.add_argument("--max-wall-sec", type=float, default=21600.0)
    args = parser.parse_args()

    assert Path(args.diagnosis).exists(), "Adım-0 önkoşulu: önce diagnose_residual_repair.py"

    t0 = time.time()
    deadline = t0 + args.max_wall_sec
    probe_dir = Path(f"runs/k1_probe_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    probe_dir.mkdir(parents=True, exist_ok=True)

    # --- paylaşılan preprocessing bloğu (diagnose/orkestratör ile aynı) ---
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

    def _sigma_of(path):
        arr, dep = load_reference_point(path, candidates)
        ps = compute_pair_slack(candidates, journey_constants, arr, dep, L, U, alpha, gamma,
                                gamma_infeasible_pairs=gamma_inf)
        return sum(v["total"] for v in ps.values()), ps

    sigma_ref, pair_slack_ref = _sigma_of(args.reference)
    print(f"[k1probe] referans Sigma={sigma_ref:.2f} ({args.reference})", flush=True)

    diagnosis = json.loads(Path(args.diagnosis).read_text())
    contributions = {}
    for r in diagnosis["records"]:
        for tag in ("fwd", "bwd"):
            d = r["directions"][tag]
            contributions[tuple(d["direction"])] = d["reward_contribution"]

    base_killed = {tuple(d) for d in json.loads(Path(args.base_deactivation).read_text())}
    ordered = order_residual_kill_candidates(
        pair_slack_ref, direction_index, candidates, contributions, base_killed, L, U)
    print(f"[k1probe] {len(ordered)} aday yön (cheapest-first); ilk 5: "
          f"{[(e['direction'], round(e['reward_loss'], 1), e['pair_slack']) for e in ordered[:5]]}",
          flush=True)

    working = []            # incumbent üreten yönler (incremental birikir)
    last_good_sigma = None  # son başarılı elastik noktanın Sigma'sı
    attempts = []
    probe_log_path = probe_dir / "probe_log.json"

    def _persist(conclusion=None):
        payload = {
            "started_utc": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
            "reference": args.reference, "sigma_reference": sigma_ref,
            "base_deactivation": args.base_deactivation, "n_base_killed": len(base_killed),
            "time_limit_sec": args.time_limit_sec,
            "data_provenance": {"FULL_OD": file_provenance(FULL_OD)},
            "attempts": attempts,
            "working_directions": [list(d) for d in working],
            "conclusion": conclusion,
        }
        probe_log_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    for n, entry in enumerate(ordered[:args.max_attempts], start=1):
        if time.time() + args.time_limit_sec + 600 > deadline:
            _persist("WALL_BUDGET")
            print("[k1probe] duvar bütçesi doldu", flush=True)
            break

        cand_dir = entry["direction"]
        kill_set = sorted(base_killed | set(working) | {cand_dir})
        directions_file = probe_dir / f"attempt{n}_directions.json"
        directions_file.write_text(json.dumps([list(d) for d in kill_set]))

        print(f"[k1probe] attempt {n}/{min(args.max_attempts, len(ordered))}: "
              f"+{cand_dir} (reward_loss={entry['reward_loss']:.1f}, "
              f"pair_slack={entry['pair_slack']}, working={len(working)}, "
              f"toplam kill={len(kill_set)})", flush=True)

        t_start = time.time()
        cmd = [PY, "-u", "scripts/warm_start_elastic.py",
               "--deactivation-file", str(directions_file),
               "--time-limit-sec", str(args.time_limit_sec), "--max-improving-sols", "1"]
        try:
            with open(probe_dir / f"attempt{n}_console.log", "w") as fh:
                subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                               timeout=args.time_limit_sec + 1500, check=False)
        except subprocess.TimeoutExpired:
            print(f"[k1probe] attempt {n}: dış zaman aşımı", flush=True)

        wse_out = Path("runs/warm_start_elastic_output.json")
        incumbent = wse_out.exists() and wse_out.stat().st_mtime > t_start
        status, solve_wall = "unknown", None
        log_json = newest_file_since("runs", "warm_start_elastic_*.log.json", t_start)
        if log_json:
            try:
                lj = json.loads(Path(log_json).read_text())
                status, solve_wall = lj.get("status"), lj.get("solve_wall_sec")
            except (json.JSONDecodeError, OSError):
                pass

        record = {
            "attempt": n, "direction": list(cand_dir),
            "pair": [entry["pair"][0], entry["pair"][1], entry["pair"][2]],
            "stations": [cand_dir[0], cand_dir[1]],
            "reward_loss": entry["reward_loss"], "pair_slack": entry["pair_slack"],
            "n_kills_total": len(kill_set),
            "sigma_before": last_good_sigma if last_good_sigma is not None else sigma_ref,
            "solver_status": status, "incumbent": bool(incumbent),
            "solve_wall_sec": solve_wall,
            "attempt_wall_sec": round(time.time() - t_start, 1),
        }

        if incumbent:
            dst = probe_dir / f"attempt{n}_elastic_output.json"
            shutil.copy2(wse_out, dst)
            s_after, _ = _sigma_of(dst)
            record["sigma_after"] = s_after
            working.append(cand_dir)
            last_good_sigma = s_after
            print(f"[k1probe] attempt {n}: INCUMBENT status={status} "
                  f"Sigma={s_after:.2f} -- yön birikime alındı "
                  f"(working={len(working)})", flush=True)
        else:
            record["sigma_after"] = None
            print(f"[k1probe] attempt {n}: incumbent YOK (status={status}) -- "
                  f"yön reddedildi", flush=True)

        attempts.append(record)
        (probe_dir / f"attempt_{n}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False))
        _persist()

        n_success = sum(1 for a in attempts if a["incumbent"])
        if n_success == 0 and len(attempts) >= args.fail_streak_stop:
            _persist("K1_ALL_FAIL")
            print(f"[k1probe] SONUÇ: ilk {len(attempts)} denemede SIFIR incumbent -- "
                  f"K=1 bile gerçekleştirilemiyor, honest direction-kill hattı "
                  f"NET TEŞHİSLE duruyor (kullanıcı madde 4)", flush=True)
            return

    n_success = sum(1 for a in attempts if a["incumbent"])
    conclusion = f"DONE: {n_success}/{len(attempts)} incumbent"
    _persist(conclusion)
    if working:
        acc = probe_dir / "accumulated_directions.json"
        acc.write_text(json.dumps([list(d) for d in sorted(base_killed | set(working))]))
        print(f"[k1probe] BİRİKMİŞ ÇALIŞAN SET: {acc} "
              f"(base {len(base_killed)} + working {len(working)})", flush=True)
    print(f"[k1probe] BİTTİ: {conclusion}; son Sigma="
          f"{last_good_sigma if last_good_sigma is not None else 'N/A'}; "
          f"log={probe_log_path}", flush=True)


if __name__ == "__main__":
    main()

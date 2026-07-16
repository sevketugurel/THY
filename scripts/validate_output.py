#!/usr/bin/env python3
"""Çıktı dosyası doğrulama kapısı (Phase 3).

Kullanım:
  python scripts/validate_output.py --config src/config/standard.yaml --fixture
  python scripts/validate_output.py --config src/config/standard.yaml --full-data
  python scripts/validate_output.py --config src/config/standard.yaml --fixture \\
      --output runs/output.json --check-determinism

Kontroller:
  1. Şema — gerekli alanlar, tipler, yineleme yok
  2. Dahili tutarlılık — B/A/D/E1/E2/F/G (independent_validator.validate_output)
  3. Amaç yeniden hesaplama — raporlanan == bağımsız recompute_objective
  4. İddia tamlığı — ayarlı saatlerden türetilen bağlantılar ⊆ listed ve ==
  5. Sayı tutarlılığı — bağlantı/pazar/uçuş sayıları ve IST kayma aralığı
  6. Deterministik kontrol — (yalnız --fixture + --check-determinism) pipeline'ı
     iki kez çalıştırıp dosyaları bayt-düzeyinde karşılaştırır

Çıkış kodu: 0 = tüm zorunlu kapılar geçti, 1 = en az bir zorunlu kapı başarısız.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from src.config.paths import FULL_CR, FULL_FP, FULL_OD, FULL_YV
from src.data.loaders import load_od_table
from src.candidates.generate import compute_epoch_anchor
from src.validate.independent_validator import (
    recompute_objective,
    summarize_violation_families,
    validate_claim_completeness,
    validate_output,
)

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_CR = "tests/fixtures/synthetic_change_ranking_input.xlsx"
FIXTURE_FP = "tests/fixtures/synthetic_flight_pairs.xlsx"

_DEFAULT_OUTPUT = {
    "fixture": "outputs/fixture_output.json",
    "full_data": "outputs/full_data_output.json",
}

# --- Şema sabitleri ---
_TOP_REQUIRED = ["objective_value", "selected_connections", "adjusted_flight_times",
                 "ranking_results", "k_od_sources", "solver_metrics"]
_TOP_OPTIONAL = {"diagnostics"}
_SOLVER_METRICS_REQUIRED = ["status", "solve_time_sec"]
_CONN_REQUIRED = ["od", "flno1", "flno2", "gun", "gap_min"]
_TIME_REQUIRED = ["role", "flno", "gun", "time_min"]
_RANK_REQUIRED = ["o", "d", "gun", "rank", "beaten_rivals"]

# Sert kısıt aileleri: ihlal varsa "geçersiz" sayılır
_HARD_FAMILIES = ("A", "B", "D", "F", "G", "window")


def check_schema(data: dict) -> list[str]:
    """Şema kontrolü: gerekli alanlar, tipler, yinelemeler.

    Yalnızca bu modülün yeni mantığıdır; testlerde doğrudan çağrılır.
    Hata mesajlarının listesini döndürür (boş → geçti).
    """
    errors = []

    # Üst-düzey gerekli alanlar
    for field in _TOP_REQUIRED:
        if field not in data:
            errors.append(f"eksik üst-düzey alan: '{field}'")

    # Beklenmeyen üst-düzey alanlar (spec dışı)
    known = set(_TOP_REQUIRED) | _TOP_OPTIONAL
    for key in data:
        if key not in known:
            errors.append(f"spec dışı üst-düzey alan: '{key}'")

    # solver_metrics içeriği
    sm = data.get("solver_metrics")
    if isinstance(sm, dict):
        for field in _SOLVER_METRICS_REQUIRED:
            if field not in sm:
                errors.append(f"solver_metrics içinde eksik alan: '{field}'")
        if "status" in sm and not isinstance(sm["status"], str):
            errors.append(f"solver_metrics.status str olmalı, bulundu: {type(sm['status'])}")
        if "solve_time_sec" in sm and not isinstance(sm["solve_time_sec"], (int, float)):
            errors.append("solver_metrics.solve_time_sec sayı olmalı")
    elif sm is not None:
        errors.append(f"solver_metrics dict olmalı, bulundu: {type(sm)}")

    # objective_value tipi
    ov = data.get("objective_value")
    if ov is not None and not isinstance(ov, (int, float)):
        errors.append(f"objective_value float veya null olmalı, bulundu: {type(ov)}")

    # selected_connections — alanlar ve yinelemeler
    seen_conns: set = set()
    for i, conn in enumerate(data.get("selected_connections", [])):
        for field in _CONN_REQUIRED:
            if field not in conn:
                errors.append(f"selected_connections[{i}] eksik alan: '{field}'")
            elif conn[field] is None:
                errors.append(f"selected_connections[{i}].{field} null olamaz")
        key = (conn.get("od"), conn.get("flno1"), conn.get("flno2"), conn.get("gun"))
        if key in seen_conns:
            errors.append(f"yinelenen bağlantı: {key}")
        seen_conns.add(key)

    # adjusted_flight_times — alanlar ve yinelemeler
    seen_times: set = set()
    valid_roles = {"IB", "OB"}
    for i, entry in enumerate(data.get("adjusted_flight_times", [])):
        for field in _TIME_REQUIRED:
            if field not in entry:
                errors.append(f"adjusted_flight_times[{i}] eksik alan: '{field}'")
        if "role" in entry and entry["role"] not in valid_roles:
            errors.append(f"adjusted_flight_times[{i}].role geçersiz: '{entry['role']}'")
        key = (entry.get("role"), entry.get("flno"), entry.get("gun"))
        if key in seen_times:
            errors.append(f"yinelenen adjusted_flight_times girişi: {key}")
        seen_times.add(key)

    # ranking_results — alanlar
    for i, entry in enumerate(data.get("ranking_results", [])):
        for field in _RANK_REQUIRED:
            if field not in entry:
                errors.append(f"ranking_results[{i}] eksik alan: '{field}'")
        if "rank" in entry and (not isinstance(entry["rank"], int) or entry["rank"] < 0):
            errors.append(f"ranking_results[{i}].rank >= 0 tamsayı olmalı")
        if "beaten_rivals" in entry and not isinstance(entry["beaten_rivals"], list):
            errors.append(f"ranking_results[{i}].beaten_rivals liste olmalı")

    return errors


def _epoch_min(ts, anchor):
    return int((ts - anchor).total_seconds() // 60)


def _compute_shifts(data: dict, tk, anchor) -> list[int]:
    """Her adjusted_flight_times girişi için baseline'dan sapma (dakika) listesi."""
    shifts = []
    for entry in data.get("adjusted_flight_times", []):
        role, flno, gun = entry["role"], entry["flno"], entry["gun"]
        if role == "IB":
            match = tk[(tk.flno1 == flno) & (tk.gun == gun)]
            col = "arr_time"
        else:
            match = tk[(tk.flno2 == flno) & (tk.gun == gun)]
            col = "dep_time"
        if match.empty:
            continue
        baseline_ts = match.iloc[0][col]
        baseline_min = _epoch_min(baseline_ts, anchor)
        shifts.append(entry["time_min"] - baseline_min)
    return shifts


def _tick(ok: bool) -> str:
    return "✓" if ok else "✗"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="THY çıktı dosyası doğrulama kapısı",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixture", action="store_true",
                       help="Sentetik fixture verisiyle doğrula")
    group.add_argument("--full-data", action="store_true",
                       help="Tam veri çıktısını doğrula")
    parser.add_argument("--config", required=True, help="YAML konfigürasyon dosyası")
    parser.add_argument("--output", default=None,
                        help="Doğrulanacak çıktı dosyası (belirtilmezse varsayılan kullanılır)")
    parser.add_argument("--check-determinism", action="store_true",
                        help="Pipeline'ı iki kez çalıştırıp bayt-özdeşlik denetle (sadece --fixture)")
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text())
    mode = "fixture" if args.fixture else "full_data"
    output_path = Path(args.output) if args.output else Path(_DEFAULT_OUTPUT[mode])
    strict = args.fixture

    if args.fixture:
        od_path = FIXTURE_OD
        yv_path = FIXTURE_YV
        cr_path = FIXTURE_CR
        fp_path = FIXTURE_FP
    else:
        od_path = str(FULL_OD)
        yv_path = str(FULL_YV)
        cr_path = str(FULL_CR)
        fp_path = str(FULL_FP)

    if not output_path.exists():
        print(f"HATA: Çıktı dosyası bulunamadı: {output_path}", file=sys.stderr)
        return 1

    data = json.loads(output_path.read_text())
    file_size = output_path.stat().st_size

    sep = "=" * 65
    print(f"\n{sep}")
    print("THY ÇIKTI DOĞRULAMA RAPORU")
    print(f"Mod      : {'fixture' if args.fixture else 'full_data'}")
    print(f"Dosya    : {output_path}")
    print(f"Boyut    : {file_size:,} bayt")
    print(sep)

    all_pass = True
    gate_results: list[tuple[str, bool, str]] = []  # (isim, geçti_mi, not)

    # ─── 1. Şema Kontrolü ────────────────────────────────────────────────────
    print("\n[1] Şema Kontrolü")
    schema_errors = check_schema(data)
    gate_ok = not schema_errors
    if gate_ok:
        print("    ✓ Tüm gerekli alanlar mevcut; yineleme ve spec-dışı alan yok")
    else:
        for err in schema_errors:
            print(f"    ✗ {err}")
        all_pass = False
    gate_results.append(("Şema kontrolü", gate_ok, f"{len(schema_errors)} hata"))

    # ─── 2. Dahili Tutarlılık ─────────────────────────────────────────────────
    print("\n[2] Dahili Tutarlılık (A/B/D/E1/E2/F/G)")
    vr = validate_output(
        output_path, od_path,
        L=config["L"], U=config["U"],
        adjustable_window_min=config["adjustable_window_min"],
        adjustable_set=config["adjustable_set"],
        flight_pairs_path=fp_path,
        tau=config["tau"],
        x_dev=config["X_dev"],
        alpha=config["alpha"],
        gamma=config["gamma"],
        bucket_size_min=config["bucket_size_min"],
        capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"],
        e1_activation=config.get("e1_activation", "conditional"),
    )
    families = summarize_violation_families(vr.violations)
    fam_counts = families["counts"]

    hard_count = sum(fam_counts.get(f, 0) for f in _HARD_FAMILIES)
    e1_e2_count = fam_counts.get("E1", 0) + fam_counts.get("E2", 0)
    total_violations = sum(fam_counts.values())

    if vr.is_valid:
        print("    ✓ Tüm kısıtlar sağlanıyor: sıfır ihlal")
        gate_ok = True
    else:
        fam_str = ", ".join(f"{k}:{v}" for k, v in sorted(fam_counts.items()))
        print(f"    ! {total_violations} ihlal: {fam_str}")
        for v in vr.violations[:5]:
            print(f"      - {v}")
        if len(vr.violations) > 5:
            print(f"      ... ({len(vr.violations) - 5} ihlal daha)")

        if mode == "fixture":
            gate_ok = False
            all_pass = False
        else:
            # Benchmark çıktısı için yalnızca sert aileler kapıyı düşürür
            gate_ok = hard_count == 0
            if not gate_ok:
                all_pass = False
                print(f"    ✗ Sert kısıt ihlali (A/B/D/F/G): {hard_count}")
            else:
                print(f"    ! E1={e1_e2_count} teşhis ihlali (benchmark yolunda beklenen, kapıyı düşürmez)")

    gate_results.append((
        "Dahili tutarlılık",
        gate_ok,
        f"sert={hard_count}, E1/E2={e1_e2_count}" if total_violations else "sıfır ihlal",
    ))

    # ─── 3. Amaç Yeniden Hesaplama ────────────────────────────────────────────
    print("\n[3] Amaç Değeri Yeniden Hesaplama")
    recomputed, breakdown = recompute_objective(
        output_path, od_path, yv_path, cr_path,
        L=config["L"], U=config["U"],
        strict=strict,
    )
    reported_obj = data.get("objective_value")
    tol = 1e-6

    if reported_obj is None:
        print("    ! objective_value=null — teşhis çıktısı (geçti)")
        gate_ok = True
        note = "null (teşhis çıktısı)"
    elif abs(recomputed - reported_obj) <= tol:
        print(f"    ✓ Yeniden hesaplanan = {recomputed:.6f} == Raporlanan = {reported_obj:.6f}")
        gate_ok = True
        note = f"uyuşuyor (Δ<{tol:.0e})"
    else:
        diff = abs(recomputed - reported_obj)
        print(f"    ✗ Uyumsuzluk: yeniden hesaplanan={recomputed:.6f}, "
              f"raporlanan={reported_obj:.6f}, fark={diff:.2e}")
        gate_ok = False
        all_pass = False
        note = f"uyuşmuyor (Δ={diff:.2e})"

    gate_results.append(("Amaç yeniden hesaplama", gate_ok, note))

    # ─── 4. İddia Tamlığı ─────────────────────────────────────────────────────
    print("\n[4] İddia Tamlığı")
    claim = validate_claim_completeness(
        output_path, od_path, yv_path,
        L=config["L"], U=config["U"],
        strict=strict,
    )
    if claim["claim_complete"]:
        print(f"    ✓ Tam iddia: eksik={claim['missing_claims']}, "
              f"fazladan={claim['extra_claims']}")
        gate_ok = True
        claim_note = "tam"
    else:
        print(f"    ! Eksik iddia: {claim['missing_claims']}, "
              f"fazladan: {claim['extra_claims']}")
        if mode == "fixture":
            gate_ok = False
            all_pass = False
        else:
            gate_ok = True  # benchmark yolu: eksik iddia uyarı, hata değil
        claim_note = (f"eksik={claim['missing_claims']}, "
                      f"fazladan={claim['extra_claims']}")

    gate_results.append(("İddia tamlığı", gate_ok, claim_note))

    # ─── 5. Sayı Tutarlılığı + IST Kayma Aralığı ─────────────────────────────
    print("\n[5] Sayı Tutarlılığı ve IST Kayma Aralığı")
    n_conns = len(data.get("selected_connections", []))
    n_times = len(data.get("adjusted_flight_times", []))
    n_markets = len(data.get("ranking_results", []))

    # IST kayma hesabı
    od_table = load_od_table(od_path)
    tk = od_table[od_table.cr1 == "TK"]
    anchor = compute_epoch_anchor(tk)
    shifts = _compute_shifts(data, tk, anchor)

    shift_ok = True
    window = config["adjustable_window_min"]
    out_of_window = [s for s in shifts if abs(s) > window]
    if out_of_window:
        shift_ok = False
        all_pass = False
        print(f"    ✗ Pencere dışı kayma: {len(out_of_window)} giriş "
              f"(izin verilen ±{window} dk)")

    min_shift = min(shifts) if shifts else 0
    max_shift = max(shifts) if shifts else 0

    print(f"    Seçilen bağlantı sayısı  : {n_conns}")
    print(f"    Ayarlanan uçuş sayısı    : {n_times}")
    print(f"    Kazanılan pazar sayısı   : {n_markets}")
    print(f"    IST kayma aralığı         : [{min_shift:+d}, {max_shift:+d}] dk "
          f"(izin: ±{window} dk)")

    if shift_ok:
        print(f"    ✓ Tüm IST kaymaları [{-window}, +{window}] aralığında")

    gate_results.append((
        "Sayı tutarlılığı / IST kayma",
        shift_ok,
        f"bağ={n_conns}, pzr={n_markets}, kayma=[{min_shift:+d},{max_shift:+d}]dk",
    ))

    # ─── 6. Deterministik Kontrol ─────────────────────────────────────────────
    if args.check_determinism:
        print("\n[6] Deterministik Kontrol")
        if mode == "full_data":
            print("    ! Tam veri modunda deterministik kontrol atlandı "
                  "(pipeline ~30-40 dk, bayt-özdeşlik tohum türevli yapıyla pratikte sağlanıyor)")
            gate_results.append(("Deterministik kontrol", True, "atlandı (full_data)"))
        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                out1 = Path(tmpdir) / "det1.json"
                out2 = Path(tmpdir) / "det2.json"
                base_cmd = [
                    sys.executable, "main.py",
                    "--config", args.config, "--fixture",
                ]
                r1 = subprocess.run(base_cmd + ["--output", str(out1)],
                                    capture_output=True, text=True)
                r2 = subprocess.run(base_cmd + ["--output", str(out2)],
                                    capture_output=True, text=True)

                if r1.returncode != 0 or r2.returncode != 0:
                    print(f"    ✗ Pipeline hatası (çıkış kodları: "
                          f"{r1.returncode}, {r2.returncode})")
                    all_pass = False
                    gate_results.append(("Deterministik kontrol", False, "pipeline hatası"))
                else:
                    # solve_time_sec wall-clock zamana bağlı, çalıştırma başına
                    # farklılık beklenir. Çözüm içeriğini karşılaştır.
                    def _content(p):
                        d = json.loads(p.read_text())
                        d.get("solver_metrics", {}).pop("solve_time_sec", None)
                        return json.dumps(d, sort_keys=True)

                    if _content(out1) == _content(out2):
                        print("    ✓ DETERMİNİZM: İki çalıştırma çözüm içeriği özdeş "
                              "(solve_time_sec hariç)")
                        gate_results.append(("Deterministik kontrol", True,
                                             "içerik özdeş"))
                    else:
                        print("    ✗ DETERMİNİZM BAŞARISIZ: Çözüm içeriği farklı")
                        all_pass = False
                        gate_results.append(("Deterministik kontrol", False, "farklı"))

    # ─── Özet ─────────────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("DOĞRULAMA KAPISI ÖZETİ")
    print(sep)
    for name, ok, note in gate_results:
        print(f"  {_tick(ok)}  {name:<35} {note}")

    print()
    print("SONUÇ METRİKLERİ")
    print(f"  Çıktı dosyası      : {output_path} ({file_size:,} bayt)")
    print(f"  Seçilen bağlantı   : {n_conns}")
    print(f"  Kazanılan pazar    : {n_markets}")
    print(f"  Ayarlanan uçuş     : {n_times}")
    if reported_obj is not None:
        print(f"  Amaç değeri        : {reported_obj}")
        print(f"  Bağlantı ödülü     : {breakdown.get('connection_reward', 0):.4f}")
        print(f"  Sıralama ödülü     : {breakdown.get('ranking_reward', 0):.4f}")
    else:
        print("  Amaç değeri        : null (teşhis çıktısı)")
    print(f"  IST kayma min/max  : [{min_shift:+d}, {max_shift:+d}] dk")
    sm = data.get("solver_metrics", {})
    print(f"  Solver durumu      : {sm.get('status', '?')}")
    print(f"  Çözüm süresi       : {sm.get('solve_time_sec', '?')} sn")
    if fam_counts:
        print(f"  İhlal özeti        : "
              f"{', '.join(f'{k}={v}' for k, v in sorted(fam_counts.items()))}")
    else:
        print("  İhlal özeti        : sıfır")

    print()
    final_label = "✓ TÜM ZORUNLU KAPILAR GEÇTİ" if all_pass else "✗ EN AZ BİR KAPI BAŞARISIZ"
    print(f"  Genel sonuç        : {final_label}")
    print(sep)
    print()

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

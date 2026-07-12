#!/usr/bin/env python3
"""Kapı-6 (docs/CLOSING_PLAN.md, M5f): teslim paketleyici. Paketlemeden ÖNCE
fixture CLI'ı ve tam test suite'ini ZORUNLU olarak koşar -- ikisinden biri
başarısız olursa paketleme İPTAL edilir (sıfır-olmayan exit code, zip
oluşturulmaz). Bu, "ihlalli/bozuk bir teslim asla paketlenemez" garantisinin
son, mekanik kapısı.

Paketlenen içerik (kaynak kodu + dokümantasyon, YARIŞMA VERİSİ HARİÇ --
data_raw/ ve runs/*.json zaten .gitignore'da, bu script AYRICA dışlar):
main.py, requirements.txt, README.md, CLAUDE.md, ASSUMPTIONS.md, KURULUM.md,
run.sh, Dockerfile, docker-compose.yml, .dockerignore, pytest.ini,
conftest.py, src/, tests/, scripts/, docs/ (model.pdf + report.pdf +
TESLIM_BEKLENTILERI.md dahil, docs/ altında oldukları için otomatik),
tests/fixtures/ (sentetik veri, paylaşılabilir), outputs/ (Kapı-D0/D3:
fixture_output.json + full_data_output.json + GAMMA_SENSITIVITY_STATIC_SCAN.json
+ dashboard.html -- resmî Γ=30 çıktısı hangisi olduğu KURULUM.md/README.md'de
açıkça not edilir, ihlalli bir tarife BURAYA ASLA konmaz).

Kullanım: .venv/bin/python3 -u scripts/package_submission.py [--skip-tests]
(--skip-tests yalnızca hızlı yerel deneme için -- gerçek bir v1.0-submission
paketi İÇİN KULLANILMAMALI, DoD bunu gerektirir.)
"""
import argparse
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INCLUDE_PATHS = [
    "main.py", "requirements.txt", "README.md", "CLAUDE.md", "ASSUMPTIONS.md",
    "KURULUM.md", "run.sh",
    "Dockerfile", "docker-compose.yml", ".dockerignore",
    "pytest.ini", "conftest.py",
    "src", "tests", "scripts", "docs", "outputs",
]

EXCLUDE_SUFFIXES = (".pyc",)
EXCLUDE_DIR_NAMES = {"__pycache__", ".pytest_cache", "data_raw", ".venv"}


def _run_fixture_cli() -> bool:
    print("[package] running fixture CLI (668.75/valid=True gate)...", flush=True)
    result = subprocess.run(
        [sys.executable, "main.py", "--config", "src/config/standard.yaml", "--fixture"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    print(result.stdout, end="")
    if result.returncode != 0 or "status=optimal" not in result.stdout or "valid=True" not in result.stdout:
        print(f"[package] FIXTURE CLI GATE FAILED (returncode={result.returncode}) -- ABORTING PACKAGE", flush=True)
        print(result.stderr, file=sys.stderr)
        return False
    print("[package] fixture CLI gate PASSED.", flush=True)
    return True


def _run_full_test_suite() -> bool:
    print("[package] running full test suite (python -m pytest)...", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT, capture_output=True, text=True, timeout=1800,
    )
    print(result.stdout[-4000:], end="")
    if result.returncode != 0:
        print(f"[package] TEST SUITE GATE FAILED (returncode={result.returncode}) -- ABORTING PACKAGE", flush=True)
        print(result.stderr[-2000:], file=sys.stderr)
        return False
    print("[package] test suite gate PASSED.", flush=True)
    return True


def _iter_files():
    for rel in INCLUDE_PATHS:
        p = ROOT / rel
        if p.is_file():
            yield p
            continue
        if not p.is_dir():
            continue
        for f in p.rglob("*"):
            if not f.is_file():
                continue
            if any(part in EXCLUDE_DIR_NAMES for part in f.relative_to(ROOT).parts):
                continue
            if f.suffix in EXCLUDE_SUFFIXES:
                continue
            yield f


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true",
                         help="DEV ONLY -- skips the mandatory fixture+suite gates. "
                              "Never use for a real v1.0-submission package.")
    parser.add_argument("--output", default=None,
                         help="zip path (default: runs/thy_submission_<timestamp>.zip)")
    args = parser.parse_args(argv)

    if not args.skip_tests:
        if not _run_fixture_cli():
            return 1
        if not _run_full_test_suite():
            return 1
    else:
        print("[package] WARNING: --skip-tests set -- mandatory gates BYPASSED, "
              "this package is NOT submission-grade.", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = Path(args.output) if args.output else ROOT / "runs" / f"thy_submission_{stamp}.zip"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    n_files = 0
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in _iter_files():
            zf.write(f, arcname=f.relative_to(ROOT))
            n_files += 1

    print(f"[package] wrote {n_files} files to {output_path} "
          f"({output_path.stat().st_size / 1024:.0f} KiB)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

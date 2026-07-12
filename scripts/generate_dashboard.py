#!/usr/bin/env python3
"""Kapı-D3: statik HTML sonuç panosu üretici. stdlib + pandas dışında hiçbir
bağımlılık yok, CDN/framework/server YOK -- tek kendi kendine yeten HTML
dosyası (`src/report/dashboard.py::build_dashboard_html`, TDD ile 7 test).

Girdi: outputs/fixture_output.json, outputs/full_data_output.json,
outputs/GAMMA_SENSITIVITY_STATIC_SCAN.json (yoksa runs/ eşdeğerlerine
düşer) + `data_raw/`nin 4 dosyasının sha256'sı (mevcutsa).

Kullanım: .venv/bin/python3 -u scripts/generate_dashboard.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.paths import FULL_CR, FULL_FP, FULL_OD, FULL_YV
from src.data.provenance import file_provenance
from src.report.dashboard import build_dashboard_html


def _load_first_existing(*candidates: Path) -> dict:
    for p in candidates:
        if p.exists():
            return json.loads(p.read_text())
    raise FileNotFoundError(f"none of {candidates} exist")


def main():
    root = Path(__file__).resolve().parent.parent

    fixture_output = _load_first_existing(
        root / "outputs" / "fixture_output.json", root / "runs" / "output.json",
    )
    full_data_output = _load_first_existing(
        root / "outputs" / "full_data_output.json",
        root / "runs" / "rehearsal" / "full_data_kapi10.json",
    )
    gamma_scan = _load_first_existing(
        root / "outputs" / "GAMMA_SENSITIVITY_STATIC_SCAN.json",
        root / "runs" / "gamma_sensitivity_scan.json",
    )

    provenance = {}
    for name, path in (("O&D", FULL_OD), ("Yolcu Verisi", FULL_YV),
                        ("Change Ranking", FULL_CR), ("Flight Pairs", FULL_FP)):
        try:
            provenance[name] = file_provenance(path)
        except FileNotFoundError:
            provenance[name] = {"path": path, "sha256": "(data_raw/ mevcut değil -- yarışma verisi repo'ya dahil değil)"}

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    html = build_dashboard_html(fixture_output, full_data_output, gamma_scan, provenance, generated_at)

    out_path = root / "runs" / "dashboard.html"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"[dashboard] wrote {out_path} ({len(html)} bytes)")
    return out_path


if __name__ == "__main__":
    main()

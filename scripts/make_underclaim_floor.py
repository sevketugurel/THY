#!/usr/bin/env python3
"""M5i RCR Engine C1 (spec §3.2): under-claim floor SİGORTA artefaktı -- solver YOK.

Akış: diagnosis records -> her ihlalli çiftte düşük-katkılı yönü düşür ->
recompute_objective ile objective'i yeniden yaz -> strict validate_output ->
runs/underclaim_floor_output.json + sidecar not. outputs/'a ASLA yazmaz
(spec §0.5); teslim paketine ana çözüm olarak GİRMEZ (spec §0.1).

Kullanım: .venv/bin/python3 -u scripts/make_underclaim_floor.py
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.config.paths import FULL_CR, FULL_FP, FULL_OD, FULL_YV
from src.data.provenance import file_provenance
from src.repair.underclaim import choose_directions_to_drop, drop_directions
from src.validate.independent_validator import recompute_objective, validate_output

RISK_PARAGRAPH = (
    "Bu çıktı bir UNDER-CLAIM FLOOR sigortasıdır (spec 2026-07-12-residual-repair-design.md "
    "§3.2): ihlalli her (o,d,gun) çiftinin bir yönünün bağlantıları LİSTEDEN düşürülmüştür; "
    "uçuş zamanları DEĞİŞMEMİŞTİR ve düşürülen bağlantılar tarifede fiziksel olarak uçmaya "
    "devam eder. docs/model.md'nin B semantiği ('uygun olan sunulmak zorunda', çift yönlü "
    "reifikasyon) ile bilinçli çelişir; validator'ın seçim-bazlı E1/E2 aktivasyonu sayesinde "
    "geçer. Organizatör değerlendirmeyi zamanlardan türetirse bu çıktı ONLARIN gözünde "
    "ihlallidir. Teslim paketine ancak açık dipnotla, ana çözüm OLMADAN girebilir."
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--partial", default="runs/lns_best_partial_20260712T150223Z.json")
    parser.add_argument("--diagnosis", default="runs/residual_repair_diagnosis.json")
    parser.add_argument("--out", default="runs/underclaim_floor_output.json")
    parser.add_argument("--note", default="runs/underclaim_floor_note.json")
    args = parser.parse_args()

    out_path, note_path = Path(args.out), Path(args.note)
    assert "outputs" not in out_path.parts and "outputs" not in note_path.parts, \
        "spec §0.5: C1 outputs/ dizinine yazamaz"
    assert Path(args.diagnosis).exists(), \
        "Adım-0 zorunlu önkoşul (spec §0.1): önce scripts/diagnose_residual_repair.py koş"

    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]

    diagnosis = json.loads(Path(args.diagnosis).read_text())
    records = diagnosis["records"]
    drops = choose_directions_to_drop(records)
    print(f"[underclaim] {len(records)} ihlalli çift -> {len(drops)} yön düşürülecek", flush=True)

    data = json.loads(Path(args.partial).read_text())
    new_data, n_conn, n_rank = drop_directions(data, drops)
    print(f"[underclaim] {n_conn} bağlantı + {n_rank} ranking girdisi düştü "
          f"({len(new_data['selected_connections'])} bağlantı kaldı)", flush=True)

    out_path.write_text(json.dumps(new_data, indent=1, ensure_ascii=False))
    recompute_total, _ = recompute_objective(
        out_path, FULL_OD, FULL_YV, FULL_CR, L=L, U=U, strict=False,
        breakdown_path=out_path.with_suffix(".objective_breakdown.json"),
    )
    new_data["objective_value"] = recompute_total
    out_path.write_text(json.dumps(new_data, indent=1, ensure_ascii=False))
    print(f"[underclaim] objective (bağımsız recompute) = {recompute_total:.2f} "
          f"(referans: {diagnosis['reference_objective_recompute_total']:.2f})", flush=True)

    validation = validate_output(
        out_path, FULL_OD, L=L, U=U,
        adjustable_window_min=config["adjustable_window_min"], adjustable_set=config["adjustable_set"],
        flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
        alpha=config["alpha"], gamma=config["gamma"],
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], e1_activation=config["e1_activation"],
    )
    print(f"[underclaim] validator: is_valid={validation.is_valid} "
          f"n_violations={len(validation.violations)}", flush=True)
    if not validation.is_valid:
        for v in validation.violations[:10]:
            print(f"  [violation] {v}", flush=True)

    note = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_partial": args.partial,
        "n_pairs_broken": len(records),
        "n_directions_dropped": len(drops),
        "n_connections_dropped": n_conn,
        "objective_before_recompute": diagnosis["reference_objective_recompute_total"],
        "objective_after_recompute": recompute_total,
        "reward_loss": diagnosis["reference_objective_recompute_total"] - recompute_total,
        "validator_is_valid": validation.is_valid,
        "n_violations": len(validation.violations),
        "violations_head": validation.violations[:20],
        "risk_paragraph": RISK_PARAGRAPH,
        "data_provenance": {"FULL_OD": file_provenance(FULL_OD)},
    }
    note_path.write_text(json.dumps(note, indent=2, ensure_ascii=False))
    print(f"[underclaim] SİGORTA ARTEFAKTI: {out_path} (+not: {note_path}) -- "
          f"outputs/ dizinine YAZILMADI (spec §0.5)", flush=True)


if __name__ == "__main__":
    main()

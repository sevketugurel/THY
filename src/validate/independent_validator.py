"""Independent feasibility validator -- deliberately does not import src.model.*
or src.candidates.*. Re-derives gap validity from raw arr_time/dep_time directly,
never trusting a value the solver output already claims (disqualification
insurance, plan §1/§5).

M0 scope: only the B-style gap-window check (Modul-3 kapi 1). Rotation (A), ranking
(D), balance (E), capacity (F), regularity (G) checks land alongside their
constraint groups in M2-M4.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from src.data.loaders import load_od_table


@dataclass
class ValidationResult:
    is_valid: bool
    violations: list = field(default_factory=list)


def validate_output(output_path: Path, od_table_path: Path, L: int, U: int) -> ValidationResult:
    data = json.loads(Path(output_path).read_text())
    od_table = load_od_table(od_table_path)
    tk = od_table[od_table.cr1 == "TK"]

    violations = []
    for conn in data["selected_connections"]:
        o, d = conn["od"].split("-")
        match = tk[
            (tk.dep1 == o) & (tk.arr2 == d)
            & (tk.flno1 == conn["flno1"]) & (tk.flno2 == conn["flno2"])
            & (tk.gun == conn["gun"])
        ]
        if match.empty:
            violations.append(
                f"connection {conn['od']} FlNo1={conn['flno1']} FlNo2={conn['flno2']} "
                f"Gün={conn['gun']}: not found in raw O&D table"
            )
            continue

        row = match.iloc[0]
        actual_gap = int((row.dep_time - row.arr_time).total_seconds() // 60)
        if not (L <= actual_gap <= U):
            violations.append(
                f"connection {conn['od']} FlNo1={conn['flno1']} FlNo2={conn['flno2']} "
                f"Gün={conn['gun']}: gap={actual_gap}min outside [{L},{U}]"
            )

    return ValidationResult(is_valid=not violations, violations=violations)

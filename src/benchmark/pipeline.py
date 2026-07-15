"""Benchmark-safe production pipeline.

FLOOR writes a schema-compliant, claim-complete output immediately, but remains
an emergency fallback. Production selection prefers claim-complete candidates
with cleaner hard-family diagnostics before comparing objective values.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

from src.benchmark.claim import build_full_claim, derive_market_universe, derive_ranking_from_claim
from src.benchmark.times import apply_seed_deltas, build_baseline_times, load_seed_deltas
from src.benchmark.writer import patch_json_field, stamp_recomputed_objective, write_benchmark_output
from src.output.writer import write_output
from src.solve.ladder import solve_with_ladder
from src.validate.independent_validator import (
    finalize_reported_objective,
    recompute_objective,
    summarize_violation_families,
    validate_claim_completeness,
    validate_output,
)

_INTERPRETATION = "strict_A_G_checked; E1_E2_reported_as_diagnostics"
_BASE_NOTE = (
    "E1/E2 strict okuması altında yayınlanan baseline tarifesi de ihlallidir; "
    "bkz. docs/report.md"
)
_HARD_FAMILIES = ("A", "B", "D", "F", "G")
_E_FAMILIES = ("E1", "E2")


@dataclass
class Assessment:
    stage: str
    status: str
    objective: float
    n_strict_violations: int
    strict_feasible: bool
    claim: dict
    families: dict

    @property
    def hard_family_violations(self) -> int:
        counts = self.families["counts"]
        return sum(counts.get(family, 0) for family in _HARD_FAMILIES)

    @property
    def e1_e2_violations(self) -> int:
        counts = self.families["counts"]
        return sum(counts.get(family, 0) for family in _E_FAMILIES)


@dataclass
class _Ctx:
    od_path: object
    yv_path: object
    cr_path: object
    fp_path: object
    config: dict
    od_table: object
    tk: object
    market_k_od: dict
    sources: dict
    dropped: list
    yolcu_strict: bool


def _status_for(stage: str, n_violations: int) -> str:
    if n_violations == 0:
        return "baseline_floor" if stage == "baseline_floor" else "strict_feasible_incumbent"
    return f"{stage}_with_strict_violations"


def _selection_key(assessment: Assessment):
    if not assessment.claim["claim_complete"]:
        return (1, float("inf"), float("inf"), float("-inf"))
    return (
        0,
        assessment.hard_family_violations,
        assessment.e1_e2_violations,
        -assessment.objective,
    )


def _is_better(candidate: Assessment, incumbent: Assessment) -> bool:
    return _selection_key(candidate) < _selection_key(incumbent)


def _validate_strict(ctx: _Ctx, path):
    cfg = ctx.config
    return validate_output(
        path,
        ctx.od_path,
        L=cfg["L"],
        U=cfg["U"],
        adjustable_window_min=cfg["adjustable_window_min"],
        adjustable_set=cfg["adjustable_set"],
        flight_pairs_path=ctx.fp_path,
        tau=cfg["tau"],
        x_dev=cfg["X_dev"],
        alpha=cfg["alpha"],
        gamma=cfg["gamma"],
        bucket_size_min=cfg["bucket_size_min"],
        capacity_departure=cfg["capacity_departure"],
        capacity_arrival=cfg["capacity_arrival"],
        e1_activation=cfg.get("e1_activation", "conditional"),
    )


def _assess_and_write(ctx: _Ctx, path, times, stage, seed_block, baseline_reference, elapsed_sec):
    cfg = ctx.config
    connections = build_full_claim(ctx.tk, ctx.market_k_od, times, L=cfg["L"], U=cfg["U"])
    ranking = derive_ranking_from_claim(ctx.od_table, ctx.market_k_od, connections)

    write_benchmark_output(
        path,
        times,
        connections,
        ranking,
        ctx.sources,
        status="provisional",
        solve_time_sec=elapsed_sec,
        diagnostics={},
    )
    total, _ = recompute_objective(
        path,
        ctx.od_path,
        ctx.yv_path,
        ctx.cr_path,
        L=cfg["L"],
        U=cfg["U"],
        strict=ctx.yolcu_strict,
    )
    claim = validate_claim_completeness(
        path,
        ctx.od_path,
        ctx.yv_path,
        L=cfg["L"],
        U=cfg["U"],
        strict=ctx.yolcu_strict,
    )
    validation = _validate_strict(ctx, path)
    families = summarize_violation_families(validation.violations)
    n_violations = sum(families["counts"].values())
    status = _status_for(stage, n_violations)
    diagnostics = {
        "mode": "benchmark_full_claim",
        "strict_feasible": n_violations == 0,
        "constraint_interpretation": _INTERPRETATION,
        "claim_complete": claim["claim_complete"],
        "missing_claims": claim["missing_claims"],
        "extra_claims": claim["extra_claims"],
        "claim_check": {
            "missing_claims": claim["missing_claims"],
            "extra_claims": claim["extra_claims"],
        },
        "seed": seed_block,
        "strict_violations": {
            "total": n_violations,
            "total_pairs": n_violations,
            "by_family": families["counts"],
            "examples": families["examples"],
        },
        "selection_priority": {
            "hard_family_violations": sum(families["counts"].get(f, 0) for f in _HARD_FAMILIES),
            "e1_e2_violations": sum(families["counts"].get(f, 0) for f in _E_FAMILIES),
            "objective": total,
        },
        "dropped_markets_no_k_od": len(ctx.dropped),
        "baseline_reference": baseline_reference,
        "note": _BASE_NOTE,
    }
    write_benchmark_output(
        path,
        times,
        connections,
        ranking,
        ctx.sources,
        status=status,
        solve_time_sec=elapsed_sec,
        diagnostics=diagnostics,
    )
    stamp_recomputed_objective(path, total)
    return Assessment(stage, status, total, n_violations, n_violations == 0, claim, families)


def run_benchmark_pipeline(
    *,
    output_path,
    od_path,
    yv_path,
    cr_path,
    fp_path,
    config,
    od_table,
    tk,
    provider,
    rho,
    anchor,
    candidates,
    journey_constants,
    rival_data,
    b_od_data,
    ranking_table,
    pairs_df,
    r_o_lookup,
    monotonic,
    seed_deltas_path,
    time_budget_sec,
    improve_enabled=True,
    yolcu_strict=False,
    ladder_fn=solve_with_ladder,
    now_fn=time.time,
) -> int:
    t0 = now_fn()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    market_k_od, dropped, sources = derive_market_universe(tk, rho, provider)
    if dropped:
        suffix = "..." if len(dropped) > 5 else ""
        print(
            f"[benchmark] K_od türetilemeyen {len(dropped)} pazar claim evreni dışında: "
            f"{dropped[:5]}{suffix}",
            flush=True,
        )
    ctx = _Ctx(
        od_path=od_path,
        yv_path=yv_path,
        cr_path=cr_path,
        fp_path=fp_path,
        config=config,
        od_table=od_table,
        tk=tk,
        market_k_od=market_k_od,
        sources=sources,
        dropped=dropped,
        yolcu_strict=yolcu_strict,
    )
    baseline_times = build_baseline_times(tk, anchor)

    floor = _assess_and_write(
        ctx,
        output_path,
        baseline_times,
        "baseline_floor",
        seed_block={"file": None, "note": "floor: ham baseline saatleri"},
        baseline_reference=None,
        elapsed_sec=now_fn() - t0,
    )
    best_ref = {
        "objective": floor.objective,
        "strict_violations_total": floor.n_strict_violations,
        "hard_family_violations": floor.hard_family_violations,
        "e1_e2_violations": floor.e1_e2_violations,
        "selection_note": "floor is emergency fallback; final selection minimizes hard-family violations first",
    }
    patch_json_field(output_path, ["diagnostics", "baseline_reference"], best_ref)
    best = floor
    print(
        f"[benchmark] floor yazıldı: objective={floor.objective} "
        f"strict_violations={floor.n_strict_violations}",
        flush=True,
    )

    try:
        deltas, note = load_seed_deltas(seed_deltas_path)
        if deltas:
            seed_times, stats = apply_seed_deltas(
                baseline_times,
                deltas,
                config["adjustable_window_min"],
            )
            tmp_seed = output_path.with_name(output_path.stem + ".seed_attempt.json")
            seed_block = {"file": str(seed_deltas_path), **stats, "note": note}
            attempt = _assess_and_write(
                ctx,
                tmp_seed,
                seed_times,
                "heuristic_incumbent",
                seed_block=seed_block,
                baseline_reference=best_ref,
                elapsed_sec=now_fn() - t0,
            )
            if _is_better(attempt, best):
                output_path.write_text(tmp_seed.read_text())
                best = attempt
                print(
                    f"[benchmark] seed kabul: objective={attempt.objective} "
                    f"hard_violations={attempt.hard_family_violations} "
                    f"e1_e2_violations={attempt.e1_e2_violations} applied={stats['applied']}",
                    flush=True,
                )
            else:
                print(
                    f"[benchmark] seed reddedildi (claim_complete={attempt.claim['claim_complete']}, "
                    f"hard={attempt.hard_family_violations}, e1_e2={attempt.e1_e2_violations}, "
                    f"objective={attempt.objective}; incumbent hard={best.hard_family_violations}, "
                    f"e1_e2={best.e1_e2_violations}, objective={best.objective})",
                    flush=True,
                )
        else:
            print(f"[benchmark] seed yok/okunamadı ({note}) — floor ile devam", flush=True)
    except Exception as exc:
        print(f"[benchmark] seed aşaması hata verdi, floor korunuyor: {exc}", flush=True)

    try:
        remaining = time_budget_sec - (now_fn() - t0)
        if improve_enabled and candidates and remaining > 90:
            cfg = config
            tmp_improve = output_path.with_name(output_path.stem + ".improve_attempt.json")

            def _improve_validate_fn(step_candidates, result) -> bool:
                write_output(tmp_improve, result, k_od_sources=None)
                total_i, _ = recompute_objective(
                    tmp_improve,
                    od_path,
                    yv_path,
                    cr_path,
                    L=cfg["L"],
                    U=cfg["U"],
                    strict=yolcu_strict,
                )
                reconciliation_ok, reconciliation_msg = finalize_reported_objective(
                    tmp_improve,
                    total_i,
                    result.status,
                    result.objective_value,
                )
                if not reconciliation_ok:
                    print(f"[benchmark] improve reconciliation failure: {reconciliation_msg}", flush=True)
                    return False
                validation = _validate_strict(ctx, tmp_improve)
                for violation in validation.violations[:5]:
                    print(f"  [benchmark] improve aday ihlali: {violation}", flush=True)
                return validation.is_valid

            _, result, ladder_log = ladder_fn(
                candidates_full=candidates,
                rho=rho,
                journey_constants=journey_constants,
                rival_data=rival_data,
                b_od_data=b_od_data,
                ranking_table=ranking_table,
                pairs_df=pairs_df,
                r_o_lookup=r_o_lookup,
                tau=cfg["tau"],
                x_dev=cfg["X_dev"],
                epoch_anchor=anchor,
                alpha=cfg["alpha"],
                gamma=cfg["gamma"],
                tk_rows=tk,
                bucket_size_min=cfg["bucket_size_min"],
                capacity_departure=cfg["capacity_departure"],
                capacity_arrival=cfg["capacity_arrival"],
                L=cfg["L"],
                U=cfg["U"],
                monotonic=monotonic,
                step1_time_limit_sec=max(60, remaining - cfg.get("watchdog_margin_sec", 60)),
                seed=cfg["seed"],
                solver=cfg["solver"],
                validate_fn=_improve_validate_fn,
                e1_activation=cfg.get("e1_activation", "conditional"),
                enable_elastic_fallback=False,
                step2_k_schedule=(),
                use_subprocess_watchdog=True,
                watchdog_margin_sec=cfg.get("watchdog_margin_sec", 60),
            )
            for entry in ladder_log:
                print(f"  [benchmark] improve ladder: {entry}", flush=True)
            accepted = result.status in ("optimal", "time_limit") and result.objective_value is not None
            if accepted:
                data_i = json.loads(tmp_improve.read_text())
                claim_i = validate_claim_completeness(
                    tmp_improve,
                    od_path,
                    yv_path,
                    L=cfg["L"],
                    U=cfg["U"],
                    strict=yolcu_strict,
                )
                improve_assessment = Assessment(
                    "improved_incumbent",
                    "strict_feasible_incumbent",
                    data_i["objective_value"],
                    0,
                    True,
                    claim_i,
                    {"counts": {}, "examples": {}},
                )
                if _is_better(improve_assessment, best):
                    data_i["solver_metrics"]["status"] = "strict_feasible_incumbent"
                    data_i["diagnostics"] = {
                        "mode": "benchmark_full_claim",
                        "strict_feasible": True,
                        "constraint_interpretation": _INTERPRETATION,
                        "claim_complete": True,
                        "missing_claims": 0,
                        "extra_claims": 0,
                        "claim_check": {"missing_claims": 0, "extra_claims": 0},
                        "seed": {"file": None, "note": "improve: strict tam-MIP incumbent"},
                        "strict_violations": {
                            "total": 0,
                            "total_pairs": 0,
                            "by_family": {},
                            "examples": {},
                        },
                        "selection_priority": {
                            "hard_family_violations": 0,
                            "e1_e2_violations": 0,
                            "objective": data_i["objective_value"],
                        },
                        "dropped_markets_no_k_od": len(dropped),
                        "baseline_reference": best_ref,
                        "note": _BASE_NOTE,
                    }
                    output_path.write_text(json.dumps(data_i, indent=2, sort_keys=True) + "\n")
                    best = improve_assessment
                    print(
                        f"[benchmark] improve kabul: strict_feasible_incumbent objective={best.objective}",
                        flush=True,
                    )
                else:
                    print(
                        f"[benchmark] improve incumbent reddedildi (claim_complete="
                        f"{claim_i['claim_complete']}, objective={data_i['objective_value']} "
                        f"<= {best.objective})",
                        flush=True,
                    )
            else:
                print(
                    f"[benchmark] improve incumbent bulamadı (status={result.status}) — mevcut en iyi korunuyor",
                    flush=True,
                )
        else:
            print(
                f"[benchmark] improve atlandı (enabled={improve_enabled}, "
                f"kalan={max(0.0, remaining):.0f}s, n_candidates={len(candidates)})",
                flush=True,
            )
    except Exception as exc:
        print(f"[benchmark] improve aşaması hata verdi, mevcut en iyi korunuyor: {exc}", flush=True)

    families_txt = ",".join(f"{k}:{v}" for k, v in sorted(best.families["counts"].items())) or "none"
    print(
        f"status={best.status} objective={best.objective} "
        f"claim_complete={best.claim['claim_complete']} "
        f"strict_feasible={best.strict_feasible} violations={families_txt}"
    )
    return 0

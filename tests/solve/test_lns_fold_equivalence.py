"""M5d LNS fold-redesign (plan: .claude/plans/a-evet-ama-iki-tingly-canyon.md,
adım 9): SERT KAPI. Fold-tabanlı build_elastic_feasibility_model_folded'ın
fix-tabanlı build_elastic_feasibility_model + fix_reference_except_free ile
AYNI Σslack'i (bağımsız compute_pair_slack recompute'uyla, her modelin
KENDİ objective_value'suyla DEĞİL) ürettiği ve GERÇEKTEN daha küçük
(satırların <%20'si) olduğu kanıtlanmadan, fold'lu builder hiçbir gerçek
LNS koşusuna bağlanmaz.

Gerçek fixture verisi kullanılır (tests/fixtures/synthetic_*.xlsx) --
A+G+F'in kendi optimal çözümünden bir referans nokta türetilir, sonra TEK
bir serbest-küme seçimi (IB 9101 gün1 + OB 9311 gün1) üç aileyi BİRDEN
kasıtlı olarak "karışık" hale getirir:
  (a) E2: pazar (ZZA,ZZB,1)'in bir adayı (IB9101/OB9112) serbest arr,
      donuk dep -- karışık aday; ters yön (ZZB,ZZA,1) de OB9311'i
      paylaştığı için karışık.
  (b) A: ROT-A rotasyon çifti (OB9311 kalkış, IB9301 varış) -- OB9311
      serbest, IB9301 donuk -- karışık rotasyon çifti (partial_pair).
  (c) G: MI1(9101, IB) çok-günlü kümesi -- gün1 serbest, gün2 donuk --
      karışık cluster (zaten test_constraints_operations_g_folded.py'de
      izole test edildi, burada TAM BUILDER üzerinden entegrasyonu
      doğrulanıyor).

marker: solve (small HiGHS solve, <60s -- fixture ölçeğinde mip_gap=0.0
ile kanıtlanmış optimal hâlâ hızlı).
"""
from pathlib import Path

import pyomo.environ as pyo
import pytest
import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_flight_pairs, load_od_table, load_yolcu_verisi
from src.model.build import (
    build_core_feasibility_model, build_elastic_feasibility_model, build_elastic_feasibility_model_folded,
)
from src.model.constraints_elastic import add_elastic_feasibility_objective
from src.model.deviation_objective import add_min_deviation_objective
from src.model.lns import compute_pair_slack, fix_reference_except_free
from src.model.partition import partition_by_freedom
from src.solve.runner import solve

FIXDIR = Path(__file__).parent.parent / "fixtures"
pytestmark = pytest.mark.solve

PROVEN_OPTIMAL_KWARGS = dict(solver="highs", time_limit_sec=60, seed=42, mip_gap=0.0)


def _fixture_ingredients():
    config = yaml.safe_load(Path("src/config/standard.yaml").read_text())
    L, U = config["L"], config["U"]

    od_table = load_od_table(FIXDIR / "synthetic_od_table.xlsx")
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXDIR / "synthetic_yolcu_verisi.xlsx", strict=True)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    pairs_df = load_flight_pairs(FIXDIR / "synthetic_flight_pairs.xlsx")

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
    for c in candidates:
        market = (c.o, c.d)
        if market not in journey_constants:
            journey_constants[market] = provider.get_journey_constant(c.o, c.d)

    rotation_stations = set(row["dest"] for row in pairs_df.to_dict("records") if row["orig"] == "IST")
    r_o_lookup = {}
    for station in rotation_stations:
        try:
            r_o_lookup[station] = provider.get_rotation_constant(station)
        except KeyError:
            continue

    return config, L, U, tk, candidates, journey_constants, pairs_df, r_o_lookup, anchor


def _all_bounds(candidates):
    arr_bounds, dep_bounds = {}, {}
    for c in candidates:
        arr_bounds.setdefault(c.r1_id, (c.arr_lo, c.arr_hi))
        dep_bounds.setdefault(c.r2_id, (c.dep_lo, c.dep_hi))
    return arr_bounds, dep_bounds


def _model_row_count(model):
    return sum(1 for _ in model.component_data_objects(pyo.Constraint, active=True))


def test_folded_matches_fix_based_and_is_genuinely_smaller():
    config, L, U, tk, candidates, journey_constants, pairs_df, r_o_lookup, anchor = _fixture_ingredients()

    core_model = build_core_feasibility_model(
        candidates, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, tk_rows=tk, bucket_size_min=config["bucket_size_min"],
        capacity_departure=config["capacity_departure"], capacity_arrival=config["capacity_arrival"],
    )
    add_min_deviation_objective(core_model)
    core_result = solve(core_model, **PROVEN_OPTIMAL_KWARGS)
    assert core_result.status == "optimal"
    reference_arr, reference_dep = core_result.arr_times, core_result.dep_times

    # Deliberately mixed free set touching E2 (ZZA-ZZB market's candidates
    # share these legs), A (ROT-A rotation pair), and G (MI1's multi-day
    # cluster) all at once -- see module docstring.
    free_arr = {("IB", 9101, 1)}
    free_dep = {("OB", 9311, 1)}

    arr_bounds, dep_bounds = _all_bounds(candidates)
    assert set(reference_arr) == set(arr_bounds), "reference_arr must cover the full instance universe"
    assert set(reference_dep) == set(dep_bounds)
    partition = partition_by_freedom(candidates, free_arr, free_dep, reference_arr, reference_dep, L, U)

    # FIX-based.
    fixed_model = build_elastic_feasibility_model(
        candidates, journey_constants, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], L=L, U=U,
    )
    fix_reference_except_free(fixed_model, reference_arr, reference_dep, free_arr, free_dep)
    add_elastic_feasibility_objective(fixed_model, epsilon=0.0)
    fixed_result = solve(fixed_model, **PROVEN_OPTIMAL_KWARGS)
    assert fixed_result.status == "optimal"
    fixed_rows = _model_row_count(fixed_model)

    # FOLD-based.
    folded_model = build_elastic_feasibility_model_folded(
        candidates, journey_constants, pairs_df, r_o_lookup, tau=config["tau"], x_dev=config["X_dev"],
        epoch_anchor=anchor, alpha=config["alpha"], gamma=config["gamma"], tk_rows=tk,
        bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
        capacity_arrival=config["capacity_arrival"], partition=partition, L=L, U=U,
    )
    add_elastic_feasibility_objective(folded_model, epsilon=0.0)
    folded_result = solve(folded_model, **PROVEN_OPTIMAL_KWARGS)
    assert folded_result.status == "optimal"
    folded_rows = _model_row_count(folded_model)

    # (1) Equivalence -- independent recompute over the FULL merged point
    # (free + frozen instances), NOT each model's own objective_value.
    # compute_pair_slack already covers every pair directly from raw
    # arr/dep times, regardless of whether the folded model gave a pair a
    # real Var/row -- so no separate addition of
    # _e1_frozen_slack_total/_e2_frozen_slack_total is needed (or correct)
    # here; that would double-count what's already in the raw recompute.
    fixed_slack = compute_pair_slack(
        candidates, journey_constants, fixed_result.arr_times, fixed_result.dep_times,
        L, U, config["alpha"], config["gamma"],
    )
    folded_full_arr = {**reference_arr, **folded_result.arr_times}
    folded_full_dep = {**reference_dep, **folded_result.dep_times}
    folded_slack = compute_pair_slack(
        candidates, journey_constants, folded_full_arr, folded_full_dep, L, U, config["alpha"], config["gamma"],
    )
    fixed_total = sum(v["total"] for v in fixed_slack.values())
    folded_total = sum(v["total"] for v in folded_slack.values())
    assert folded_total == pytest.approx(fixed_total, abs=1e-6)

    # (1b) Bonus check: the frozen-constant bookkeeping fields ARE correct
    # for their actual purpose -- making the folded model's OWN (smaller,
    # Var-only) objective_value comparable to the fix-based model's by
    # adding back what never became a Var/row in the folded model.
    e1_frozen = getattr(folded_model, "_e1_frozen_slack_total", 0.0)
    e2_frozen = getattr(folded_model, "_e2_frozen_slack_total", 0.0)
    assert folded_result.objective_value + e1_frozen + e2_frozen == pytest.approx(fixed_result.objective_value)

    # (2) Genuinely smaller -- not just equivalent, the whole point of the
    # fold is to shrink the model (user's explicit acceptance threshold).
    assert folded_rows < 0.20 * fixed_rows, (
        f"folded model ({folded_rows} rows) must be under 20% of fix-based ({fixed_rows} rows) "
        f"-- otherwise the fold 'worked' but didn't achieve its actual purpose"
    )

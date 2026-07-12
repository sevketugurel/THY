# Residual Conflict Repair Engine — Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 10944-Σslack partial'ından başlayarak, hedefli yön-kapatma turlarıyla (A→B eskalasyonlu, 4h bütçe) full-data'da İLK strict-valid çıktıyı aramak; paralelde C1 under-claim sigorta artefaktı üretmek.

**Architecture:** Saf-Python karar mantığı yeni `src/repair/` modülünde (repo'nun `src/report/` deseni), üç ince script `scripts/`'te; solve'lar mevcut `run_lns.py`/`warm_start_elastic.py` subprocess'leri. Model çekirdeği (`src/model/`, `src/validate/`) READ-ONLY.

**Tech Stack:** Python 3.14 (`.venv`), pandas, mevcut `compute_pair_slack`/`deactivation`/`independent_validator` API'leri. Solver çağrıları yalnız subprocess üzerinden.

**Spec:** `docs/superpowers/specs/2026-07-12-residual-repair-design.md` (normatif — çelişkide spec kazanır).

## Global Constraints

- Testler her zaman `.venv/bin/python3 -m pytest` ile (kullanıcı tercihi).
- `src/config/standard.yaml` değiştirilmez (spec §4: hiçbir düğme değişmez).
- `outputs/` dizinine HİÇBİR script yazmaz (spec §0.5) — kampanya valid=True bulsa bile durur ve raporlar.
- `src/model/`, `src/validate/`, `src/candidates/`, `src/data/` dosyaları değiştirilmez; yalnız import edilir.
- Dosya adları spec-exact: `runs/residual_repair_diagnosis.json`, `runs/underclaim_floor_output.json`, `runs/underclaim_floor_note.json`, `runs/residual_repair_round<N>_directions.json`, `runs/residual_repair_campaign_<ts>/`.
- Kampanya referansı: `runs/lns_best_partial_20260712T150223Z.json`; taban kapatma seti: `runs/conflict_deactivation_level04_directions.json`.
- Seed=42; tüm eşitlik-kırıcılar deterministik.
- Docstring'ler Türkçe, repo üslubunda, spec bölüm referanslı.
- Her task sonunda commit; commit mesajı sonunda `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Dosya Haritası

| Dosya | Sorumluluk |
|---|---|
| `src/repair/__init__.py` (yeni) | boş paket dosyası |
| `src/repair/reference.py` (yeni) | output-şemalı JSON'dan referans nokta yükleme |
| `src/repair/diagnosis.py` (yeni) | Adım-0 kayıt/özet üretimi (saf fonksiyonlar) |
| `src/repair/underclaim.py` (yeni) | C1 yön seçimi + bağlantı düşürme (saf fonksiyonlar) |
| `src/repair/campaign.py` (yeni) | tur kararları: worst-K kill seçimi, eskalasyon, adaptif K, smoke eşiği, slack dökümü, yardımcılar |
| `scripts/run_lns.py` (değişiklik) | `--reference` bayrağı (`:72-93` loader delegasyonu, `:281` çağrı, argparse) |
| `scripts/diagnose_residual_repair.py` (yeni) | Adım-0 IO/orkestrasyon |
| `scripts/make_underclaim_floor.py` (yeni) | C1 IO/orkestrasyon |
| `scripts/run_residual_repair.py` (yeni) | kampanya orkestratörü (subprocess + loglama) |
| `tests/unit/test_repair_reference.py` (yeni) | reference.py 1:1 |
| `tests/unit/test_repair_diagnosis.py` (yeni) | diagnosis.py 1:1 |
| `tests/unit/test_repair_underclaim.py` (yeni) | underclaim.py 1:1 |
| `tests/unit/test_repair_campaign.py` (yeni) | campaign.py 1:1 |

## Paylaşılan bilgi (görevler bunu varsayar)

**Candidate test yardımcısı** — `tests/unit/test_deactivation.py:16-22`'deki desenle birebir; her yeni test dosyasının başına kopyalanır:

```python
from src.candidates.generate import Candidate

L, U = 60, 300


def _candidate(o, d, flno1, flno2, gap_lo, gap_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=max(gap_lo, min(gap_hi, 0)), arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )
```

**Full-data preprocessing bloğu** — `scripts/run_conflict_deactivation_feasibility.py:146-178`'den kopya; her yeni script'te aynen kullanılır (repo deseni: her kampanya scripti kendi kopyasını taşır):

```python
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
```

Gerekli importlar (aynı script dosyasından): `yaml`, `from src.candidates.generate import compute_epoch_anchor, generate_candidates`, `from src.config.paths import FULL_CR, FULL_FP, FULL_OD, FULL_YV`, `from src.data.block_times import BlockTimeProvider`, `from src.data.loaders import load_od_table, load_yolcu_verisi`, `from src.data.provenance import file_provenance`.

**Kullanılan mevcut API'ler (imzalar):**

```python
# src/model/lns.py
compute_pair_slack(candidates, journey_constants, arr_times, dep_times, L, U, alpha, gamma,
                   e1_activation="conditional", gamma_infeasible_pairs=None)
# -> {(o,d,gun): {"e1": float, "e2": float, "total": float}}  (çift TEK anahtar altında)
compute_gamma_infeasible_pairs(candidates, journey_constants, L, U, gamma)  # -> set

# src/model/deactivation.py
market_direction_index(candidates)          # -> {(o,d,gun): [candidate index]}
is_direction_killable(direction_candidates, L, U)  # -> bool (D2)

# src/validate/independent_validator.py
recompute_objective(output_path, od_table_path, yolcu_path, ranking_path, L, U,
                    breakdown_path=None, strict=True)  # -> (total, breakdown_dict)
# breakdown: {"claimed_objective_value","connection_reward","ranking_reward","total",
#             "markets":[{"o","d","gun","count","rank","connection_component","ranking_component"}]}
validate_output(output_path, od_table_path, L, U, adjustable_window_min, adjustable_set,
                flight_pairs_path, tau, x_dev, alpha, gamma, bucket_size_min,
                capacity_departure, capacity_arrival, e1_activation)  # -> .is_valid, .violations

# Output-şema JSON alanları (runs/lns_best_partial_*.json):
# adjusted_flight_times: [{"role","flno","gun","time_min"}]
# selected_connections:  [{"od","flno1","flno2","gap_min","gun"}]
# ranking_results: []  (LNS partial'larında BOŞ — post-hoc sentez yapılmadı)
# objective_value: float
# Kapatma dosyası formatı: JSON list of [o, d, gun]  (run_lns.py:313 tuple'a çevirir)
```

**validate_output tam çağrı kalıbı** (D7'den, `scripts/run_conflict_deactivation_feasibility.py:340-347`):

```python
validation = validate_output(
    output_path, FULL_OD, L=L, U=U,
    adjustable_window_min=config["adjustable_window_min"], adjustable_set=config["adjustable_set"],
    flight_pairs_path=FULL_FP, tau=config["tau"], x_dev=config["X_dev"],
    alpha=config["alpha"], gamma=config["gamma"],
    bucket_size_min=config["bucket_size_min"], capacity_departure=config["capacity_departure"],
    capacity_arrival=config["capacity_arrival"], e1_activation=config["e1_activation"],
)
```

---

### Task 1: `src/repair/reference.py` + `run_lns.py --reference` bayrağı

**Files:**
- Create: `src/repair/__init__.py`, `src/repair/reference.py`
- Modify: `scripts/run_lns.py` (`:72-93` civarı loader, argparse bloğu `:208` sonrası, çağrı `:281`)
- Test: `tests/unit/test_repair_reference.py`

**Interfaces:**
- Produces: `load_reference_point(path, candidates) -> (arr_times: dict, dep_times: dict)` (anahtar `("IB"|"OB", flno, gun)`); `resolve_reference_path(cli_value, default_path) -> Path`. Task 3/5/7 bunları kullanır; `run_lns.py --reference <path>` bayrağı Task 7'nin subprocess çağrısında kullanılır.

- [ ] **Step 1: Failing test yaz**

```python
# tests/unit/test_repair_reference.py
"""M5i (spec docs/superpowers/specs/2026-07-12-residual-repair-design.md §3.3):
output-şemalı JSON'dan referans nokta yükleme -- saf IO, solver yok (marker yok = unit)."""
import json
from pathlib import Path

import pytest

from src.candidates.generate import Candidate
from src.repair.reference import load_reference_point, resolve_reference_path

L, U = 60, 300


def _candidate(o, d, flno1, flno2, gap_lo, gap_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=max(gap_lo, min(gap_hi, 0)), arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )


def _write_output_json(path, entries):
    path.write_text(json.dumps({"adjusted_flight_times": entries, "selected_connections": []}))


def test_loads_arr_dep_split_by_role(tmp_path):
    c = _candidate("ZZG", "ZZH", 201, 301, 50, 150)
    f = tmp_path / "ref.json"
    _write_output_json(f, [
        {"role": "IB", "flno": 201, "gun": 1, "time_min": 1000},
        {"role": "OB", "flno": 301, "gun": 1, "time_min": 1130},
    ])
    arr, dep = load_reference_point(f, [c])
    assert arr[("IB", 201, 1)] == 1000
    assert dep[("OB", 301, 1)] == 1130


def test_missing_instance_raises_assertion(tmp_path):
    c = _candidate("ZZG", "ZZH", 201, 301, 50, 150)
    f = tmp_path / "ref.json"
    _write_output_json(f, [{"role": "IB", "flno": 201, "gun": 1, "time_min": 1000}])  # OB eksik
    with pytest.raises(AssertionError, match="missing dep"):
        load_reference_point(f, [c])


def test_resolve_reference_path_default_when_none():
    default = Path("runs/warm_start_elastic_output.json")
    assert resolve_reference_path(None, default) == default
    assert resolve_reference_path("runs/x.json", default) == Path("runs/x.json")
```

- [ ] **Step 2: Testin FAIL ettiğini gör**

Run: `.venv/bin/python3 -m pytest tests/unit/test_repair_reference.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.repair'`

- [ ] **Step 3: Minimal implementasyon**

```python
# src/repair/__init__.py  (boş dosya)
```

```python
# src/repair/reference.py
"""M5i residual-repair (spec docs/superpowers/specs/2026-07-12-residual-repair-design.md
§3.3): output-şemalı bir JSON'dan (adjusted_flight_times) referans nokta yükleme --
scripts/run_lns.py'nin eski _load_starting_reference'ının ve conflict-deactivation
script'inin _load_reference'ının ortak saf çekirdeği. src.model'e bağımlılık YOK."""
import json
from pathlib import Path


def resolve_reference_path(cli_value, default_path: Path) -> Path:
    """--reference verilmezse eski davranış (default_path) bire bir korunur."""
    return Path(cli_value) if cli_value else Path(default_path)


def load_reference_point(path, candidates):
    """(arr_times, dep_times) döndürür; anahtar ("IB"|"OB", flno, gun).
    Dosya, her candidate'ın r1_id/r2_id'sini kapsamak ZORUNDA (bu repo'nun
    writer'ları her zaman tam kapsar) -- eksikte AssertionError."""
    data = json.loads(Path(path).read_text())
    arr_times, dep_times = {}, {}
    for e in data["adjusted_flight_times"]:
        key = (e["role"], e["flno"], e["gun"])
        if e["role"] == "IB":
            arr_times[key] = e["time_min"]
        else:
            dep_times[key] = e["time_min"]
    arr_ids = {c.r1_id for c in candidates}
    dep_ids = {c.r2_id for c in candidates}
    missing_arr = arr_ids - set(arr_times)
    missing_dep = dep_ids - set(dep_times)
    assert not missing_arr, f"reference missing arr instances: {sorted(missing_arr)[:5]}"
    assert not missing_dep, f"reference missing dep instances: {sorted(missing_dep)[:5]}"
    return arr_times, dep_times
```

- [ ] **Step 4: Testin PASS ettiğini gör**

Run: `.venv/bin/python3 -m pytest tests/unit/test_repair_reference.py -v`
Expected: 3 passed

- [ ] **Step 5: `run_lns.py`'yi bağla**

Üç düzenleme:

(a) Dosya başındaki import bloğuna (mevcut `from src.model.lns import ...` satırlarının yanına):

```python
from src.repair.reference import load_reference_point, resolve_reference_path
```

(b) `run_lns.py:77-93`'teki `_load_starting_reference` fonksiyonunun TAMAMINI sil (gövdesi artık `load_reference_point`'te). `STARTING_INCUMBENT` sabiti (`:72`) KALIR.

(c) Argparse bloğuna (`--deactivation-file`'ın hemen altına):

```python
    parser.add_argument("--reference", default=None,
                         help="M5i (spec 2026-07-12-residual-repair-design.md §3.3): output-şemalı JSON'dan "
                              "başlangıç referansı yükle; verilmezse eski davranış "
                              "(runs/warm_start_elastic_output.json) bire bir korunur.")
```

(d) `:281`'deki çağrıyı değiştir:

```python
    reference_arr, reference_dep = _load_starting_reference(candidates)
```
→
```python
    reference_path = resolve_reference_path(args.reference, STARTING_INCUMBENT)
    print(f"[run_lns] starting reference: {reference_path}", flush=True)
    reference_arr, reference_dep = load_reference_point(reference_path, candidates)
```

- [ ] **Step 6: Tüm unit suite yeşil mi + bayrak görünüyor mu**

Run: `.venv/bin/python3 -m pytest tests/unit -q && .venv/bin/python3 scripts/run_lns.py --help | grep -A2 reference`
Expected: tüm testler passed; help çıktısında `--reference` görünür.

- [ ] **Step 7: Commit**

```bash
git add src/repair/__init__.py src/repair/reference.py tests/unit/test_repair_reference.py scripts/run_lns.py
git commit -m "M5i Task1: src/repair/reference.py + run_lns --reference bayrağı (TDD)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `src/repair/diagnosis.py` — Adım-0 kayıt/özet mantığı

**Files:**
- Create: `src/repair/diagnosis.py`
- Test: `tests/unit/test_repair_diagnosis.py`

**Interfaces:**
- Consumes: `is_direction_killable`, `market_direction_index` (mevcut), `compute_pair_slack` çıktı şeması.
- Produces: `build_residual_records(pair_slack, direction_index, candidates, contributions, selected_counts, rho, L, U) -> list[dict]` (total-desc sıralı) ve `summarize_records(records) -> dict`. Task 3/5 bunları kullanır. Kayıt şeması aşağıdaki koddaki gibi — `directions.fwd/bwd.{direction,killable,n_candidates,n_selected,has_forced_on,rho,reward_contribution}` + `both_unkillable`.

- [ ] **Step 1: Failing test yaz**

```python
# tests/unit/test_repair_diagnosis.py
"""M5i Adım-0 (spec §3.1): residual çift kayıtları + özet -- saf Python, solver yok."""
from src.candidates.generate import Candidate
from src.model.deactivation import market_direction_index
from src.repair.diagnosis import build_residual_records, summarize_records

L, U = 60, 300


def _candidate(o, d, flno1, flno2, gap_lo, gap_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=max(gap_lo, min(gap_hi, 0)), arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )


def _fixture():
    # Çift 1: ZZG-ZZH -- fwd killable (aralık pencereyi taşıyor), bwd unkillable (tam pencere içi)
    # Çift 2: ZZI-ZZJ -- iki yön de unkillable (both_unkillable)
    cands = [
        _candidate("ZZG", "ZZH", 201, 301, 50, 350),   # killable
        _candidate("ZZH", "ZZG", 202, 302, 100, 200),  # unkillable (⊆ [60,300])
        _candidate("ZZI", "ZZJ", 203, 303, 70, 80),    # unkillable
        _candidate("ZZJ", "ZZI", 204, 304, 90, 90),    # unkillable + forced-on (tekil, pencere içi)
    ]
    index = market_direction_index(cands)
    pair_slack = {
        ("ZZG", "ZZH", 1): {"e1": 0.0, "e2": 100.0, "total": 100.0},
        ("ZZI", "ZZJ", 1): {"e1": 0.4, "e2": 0.0, "total": 0.4},
        ("ZZK", "ZZL", 1): {"e1": 0.0, "e2": 0.0, "total": 0.0},  # ihlalsiz -- kayda girmez
    }
    contributions = {("ZZG", "ZZH", 1): 500.0, ("ZZH", "ZZG", 1): 40.0}
    selected_counts = {("ZZG", "ZZH", 1): 1, ("ZZH", "ZZG", 1): 1,
                       ("ZZI", "ZZJ", 1): 1, ("ZZJ", "ZZI", 1): 1}
    rho = {("ZZG", "ZZH"): 10, ("ZZH", "ZZG"): 12, ("ZZI", "ZZJ"): 5, ("ZZJ", "ZZI"): 5}
    return cands, index, pair_slack, contributions, selected_counts, rho


def test_records_sorted_by_total_desc_and_zero_slack_excluded():
    cands, index, ps, contrib, sel, rho = _fixture()
    records = build_residual_records(ps, index, cands, contrib, sel, rho, L, U)
    assert [r["pair"] for r in records] == [["ZZG", "ZZH", 1], ["ZZI", "ZZJ", 1]]


def test_killability_and_forced_on_flags():
    cands, index, ps, contrib, sel, rho = _fixture()
    records = build_residual_records(ps, index, cands, contrib, sel, rho, L, U)
    r1 = records[0]
    assert r1["directions"]["fwd"]["killable"] is True
    assert r1["directions"]["bwd"]["killable"] is False
    assert r1["both_unkillable"] is False
    r2 = records[1]
    assert r2["both_unkillable"] is True
    assert r2["directions"]["bwd"]["has_forced_on"] is True


def test_contribution_lookup_defaults_to_zero():
    cands, index, ps, contrib, sel, rho = _fixture()
    records = build_residual_records(ps, index, cands, contrib, sel, rho, L, U)
    assert records[1]["directions"]["fwd"]["reward_contribution"] == 0.0


def test_summary_counts_and_c1_loss():
    cands, index, ps, contrib, sel, rho = _fixture()
    records = build_residual_records(ps, index, cands, contrib, sel, rho, L, U)
    s = summarize_records(records)
    assert s["n_violated_pairs"] == 2
    assert s["n_both_unkillable"] == 1
    assert s["n_killable_coverable"] == 1
    # C1 kaybı = her çiftte min(katkı): min(500,40) + min(0,0) = 40
    assert s["c1_reward_loss_estimate"] == 40.0
    assert s["n_forced_on_directions"] == 1
    assert ("ZZG", 1) in s["top_stations"] or ["ZZG", 1] in [list(x) for x in s["top_stations"]]
```

- [ ] **Step 2: FAIL gör**

Run: `.venv/bin/python3 -m pytest tests/unit/test_repair_diagnosis.py -v`
Expected: FAIL — `No module named 'src.repair.diagnosis'`

- [ ] **Step 3: Minimal implementasyon**

```python
# src/repair/diagnosis.py
"""M5i Adım-0 teşhis mantığı (spec §3.1) -- saf Python, IO yok, solver yok.
Her pozitif-slack (o,d,gun) çifti için killability/ödül-katkı kaydı üretir;
scripts/diagnose_residual_repair.py bunları full-data girdileriyle çağırır."""
from src.model.deactivation import is_direction_killable


def _direction_record(direction, direction_index, candidates, contributions,
                      selected_counts, rho, L, U):
    idxs = direction_index.get(direction, [])
    dir_cands = [candidates[i] for i in idxs]
    return {
        "direction": list(direction),
        "killable": bool(dir_cands) and is_direction_killable(dir_cands, L, U),
        "n_candidates": len(idxs),
        "n_selected": selected_counts.get(direction, 0),
        "has_forced_on": any(c.gap_lo == c.gap_hi and L <= c.gap_lo <= U for c in dir_cands),
        "rho": rho.get((direction[0], direction[1]), 0),
        "reward_contribution": contributions.get(direction, 0.0),
    }


def build_residual_records(pair_slack, direction_index, candidates, contributions,
                           selected_counts, rho, L, U):
    """compute_pair_slack çıktısındaki her pozitif-total çift için kayıt;
    total'e göre azalan sıralı. contributions: recompute_objective breakdown'ının
    markets listesinden {(o,d,gun): connection_component+ranking_component} --
    kaydı olmayan yön 0.0 (o yönde bugün ödül yok => kapatması bedava)."""
    records = []
    for (o, d, gun), s in pair_slack.items():
        if s["total"] <= 0:
            continue
        fwd_rec = _direction_record((o, d, gun), direction_index, candidates,
                                    contributions, selected_counts, rho, L, U)
        bwd_rec = _direction_record((d, o, gun), direction_index, candidates,
                                    contributions, selected_counts, rho, L, U)
        records.append({
            "pair": [o, d, gun],
            "e1": s["e1"], "e2": s["e2"], "total": s["total"],
            "directions": {"fwd": fwd_rec, "bwd": bwd_rec},
            "both_unkillable": not (fwd_rec["killable"] or bwd_rec["killable"]),
        })
    records.sort(key=lambda r: (-r["total"], r["pair"]))
    return records


def summarize_records(records):
    """Spec §3.1 toplamları -- Adım-0 konsol özeti + JSON'un summary alanı."""
    n_pairs = len(records)
    n_both_unkillable = sum(1 for r in records if r["both_unkillable"])
    c1_loss = sum(min(r["directions"]["fwd"]["reward_contribution"],
                      r["directions"]["bwd"]["reward_contribution"]) for r in records)
    stations = {}
    for r in records:
        for st in (r["pair"][0], r["pair"][1]):
            stations[st] = stations.get(st, 0) + 1
    return {
        "n_violated_pairs": n_pairs,
        "n_both_unkillable": n_both_unkillable,
        "n_killable_coverable": n_pairs - n_both_unkillable,
        "killable_cover_ratio": ((n_pairs - n_both_unkillable) / n_pairs) if n_pairs else 1.0,
        "n_forced_on_directions": sum(
            1 for r in records for t in ("fwd", "bwd") if r["directions"][t]["has_forced_on"]),
        "c1_reward_loss_estimate": c1_loss,
        "top_stations": sorted(stations.items(), key=lambda kv: (-kv[1], kv[0]))[:10],
    }
```

- [ ] **Step 4: PASS gör**

Run: `.venv/bin/python3 -m pytest tests/unit/test_repair_diagnosis.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/repair/diagnosis.py tests/unit/test_repair_diagnosis.py
git commit -m "M5i Task2: Adım-0 teşhis mantığı (kayıt+özet, TDD)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `scripts/diagnose_residual_repair.py` — Adım-0 script'i + gerçek koşu

**Files:**
- Create: `scripts/diagnose_residual_repair.py`
- (Test yok — tüm mantık Task 2'de test edildi; bu dosya ince IO.)

**Interfaces:**
- Consumes: Task 1 `load_reference_point`, Task 2 `build_residual_records/summarize_records`, paylaşılan preprocessing bloğu, `recompute_objective`.
- Produces: `runs/residual_repair_diagnosis.json` — şema: `{"generated_utc", "partial", "data_provenance", "reference_objective_recompute_total", "summary": <summarize_records>, "records": <build_residual_records>}`. Task 5 (`--diagnosis`) ve kullanıcı raporu bunu tüketir.

- [ ] **Step 1: Script'i yaz**

```python
#!/usr/bin/env python3
"""M5i Adım-0 (spec docs/superpowers/specs/2026-07-12-residual-repair-design.md §3.1):
residual-repair fizibilite teşhisi -- SOLVER YOK, salt-okunur. Kampanyanın ve C1'in
zorunlu önkoşulu: killability, both-unkillable sayısı, yön-başına gerçek ödül katkısı
(recompute_objective breakdown'ından), C1 kayıp tahmini, istasyon kümeleri.

Kullanım: .venv/bin/python3 -u scripts/diagnose_residual_repair.py [--partial ...] [--out ...]
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.config.paths import FULL_CR, FULL_OD, FULL_YV
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table, load_yolcu_verisi
from src.data.provenance import file_provenance
from src.model.deactivation import market_direction_index
from src.model.lns import compute_gamma_infeasible_pairs, compute_pair_slack
from src.repair.diagnosis import build_residual_records, summarize_records
from src.repair.reference import load_reference_point
from src.validate.independent_validator import recompute_objective

DEFAULT_PARTIAL = "runs/lns_best_partial_20260712T150223Z.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--partial", default=DEFAULT_PARTIAL)
    parser.add_argument("--out", default="runs/residual_repair_diagnosis.json")
    args = parser.parse_args()

    t0 = time.time()
    # --- paylaşılan preprocessing bloğu (plan "Paylaşılan bilgi" bölümünden AYNEN) ---
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

    print(f"[diagnose] preprocessing {time.time()-t0:.1f}s, n_candidates={len(candidates)}", flush=True)

    arr, dep = load_reference_point(args.partial, candidates)
    gamma_inf = compute_gamma_infeasible_pairs(candidates, journey_constants, L, U, gamma)
    pair_slack = compute_pair_slack(candidates, journey_constants, arr, dep, L, U, alpha, gamma,
                                    gamma_infeasible_pairs=gamma_inf)
    sigma = sum(v["total"] for v in pair_slack.values())
    print(f"[diagnose] Sigma-slack={sigma:.2f} at {args.partial}", flush=True)

    # Yön-başına seçili bağlantı sayısı (B semantiği: seçim=pencere-içi gap)
    selected_counts = {}
    for c in candidates:
        gap = dep[c.r2_id] - arr[c.r1_id]
        if L <= gap <= U:
            key = (c.o, c.d, c.gun)
            selected_counts[key] = selected_counts.get(key, 0) + 1

    # Yön-başına gerçek ödül katkısı: bağımsız recompute breakdown'ından
    breakdown_path = Path(args.out).with_suffix(".breakdown.json")
    recompute_total, breakdown = recompute_objective(
        Path(args.partial), FULL_OD, FULL_YV, FULL_CR, L=L, U=U,
        strict=False, breakdown_path=breakdown_path,
    )
    contributions = {
        (m["o"], m["d"], m["gun"]): m["connection_component"] + m["ranking_component"]
        for m in breakdown["markets"]
    }
    print(f"[diagnose] reference recompute objective={recompute_total:.2f}", flush=True)

    direction_index = market_direction_index(candidates)
    records = build_residual_records(pair_slack, direction_index, candidates,
                                     contributions, selected_counts, rho, L, U)
    summary = summarize_records(records)
    summary["sigma_slack"] = sigma
    summary["n_gamma_exempt_pairs"] = len(gamma_inf)

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "partial": args.partial,
        "data_provenance": {"FULL_OD": file_provenance(FULL_OD)},
        "reference_objective_recompute_total": recompute_total,
        "summary": summary,
        "records": records,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    print(f"[diagnose] written: {args.out} ({time.time()-t0:.1f}s total)", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Unit suite hâlâ yeşil**

Run: `.venv/bin/python3 -m pytest tests/unit -q`
Expected: tümü passed (script import edilmiyor, regresyon yok).

- [ ] **Step 3: Gerçek koşu (Adım-0 — kampanya önkoşulu)**

Run: `.venv/bin/python3 -u scripts/diagnose_residual_repair.py`
Expected: ~1-3dk; konsolda `Sigma-slack=10944.00` (referansla tutarlı), summary JSON'u (n_violated_pairs≈327, n_both_unkillable=?, c1_reward_loss_estimate=?, top_stations başında VCE bekleniyor); `runs/residual_repair_diagnosis.json` yazıldı.
**Bu adımın çıktı özeti kullanıcı raporuna girer (spec: Adım-0 zorunlu, kullanıcı görmek istiyor).** `recompute_objective` breakdown'ında `m["gun"]` alanının varlığı burada doğal olarak doğrulanır (markets listesi o/d/gun taşıyor — beklenen); tutarsızlık çıkarsa DUR ve raporla.

- [ ] **Step 4: Commit**

```bash
git add scripts/diagnose_residual_repair.py
git commit -m "M5i Task3: Adım-0 teşhis scripti + full-data koşusu

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `src/repair/underclaim.py` — C1 mantığı

**Files:**
- Create: `src/repair/underclaim.py`
- Test: `tests/unit/test_repair_underclaim.py`

**Interfaces:**
- Consumes: Task 2'nin kayıt şeması (`records`).
- Produces: `choose_directions_to_drop(records) -> list[tuple]`; `drop_directions(data, directions) -> (new_data, n_conn_dropped, n_rank_dropped)`. Task 5 kullanır.

- [ ] **Step 1: Failing test yaz**

```python
# tests/unit/test_repair_underclaim.py
"""M5i C1 (spec §3.2): under-claim floor mantığı -- saf Python, IO/solver yok."""
from src.repair.underclaim import choose_directions_to_drop, drop_directions


def _record(o, d, gun, fwd_contrib, bwd_contrib, fwd_sel=2, bwd_sel=2):
    return {
        "pair": [o, d, gun], "e1": 0.0, "e2": 50.0, "total": 50.0,
        "directions": {
            "fwd": {"direction": [o, d, gun], "killable": True, "n_candidates": 3,
                    "n_selected": fwd_sel, "has_forced_on": False, "rho": 1,
                    "reward_contribution": fwd_contrib},
            "bwd": {"direction": [d, o, gun], "killable": True, "n_candidates": 3,
                    "n_selected": bwd_sel, "has_forced_on": False, "rho": 1,
                    "reward_contribution": bwd_contrib},
        },
        "both_unkillable": False,
    }


def test_chooses_lower_contribution_side_per_pair():
    records = [_record("AAA", "BBB", 1, 500.0, 40.0), _record("CCC", "DDD", 2, 10.0, 90.0)]
    drops = choose_directions_to_drop(records)
    assert drops == [("BBB", "AAA", 1), ("CCC", "DDD", 2)]


def test_tie_breaks_on_fewer_selected_then_tuple():
    r = _record("AAA", "BBB", 1, 100.0, 100.0, fwd_sel=1, bwd_sel=5)
    assert choose_directions_to_drop([r]) == [("AAA", "BBB", 1)]
    r2 = _record("AAA", "BBB", 1, 100.0, 100.0, fwd_sel=2, bwd_sel=2)
    assert choose_directions_to_drop([r2]) == [("AAA", "BBB", 1)]  # tuple sırası


def test_drop_directions_filters_connections_and_rankings_only():
    data = {
        "adjusted_flight_times": [{"role": "IB", "flno": 1, "gun": 1, "time_min": 100}],
        "selected_connections": [
            {"od": "AAA-BBB", "flno1": 1, "flno2": 2, "gap_min": 90, "gun": 1},
            {"od": "BBB-AAA", "flno1": 3, "flno2": 4, "gap_min": 90, "gun": 1},
            {"od": "AAA-BBB", "flno1": 5, "flno2": 6, "gap_min": 90, "gun": 2},  # farklı gün -- kalır
        ],
        "ranking_results": [{"od": "AAA-BBB", "gun": 1, "rank": 1, "beaten_rivals": []}],
        "objective_value": 123.0,
    }
    new_data, n_conn, n_rank = drop_directions(data, [("AAA", "BBB", 1)])
    assert n_conn == 1 and n_rank == 1
    assert len(new_data["selected_connections"]) == 2
    assert all(not (c["od"] == "AAA-BBB" and c["gun"] == 1)
               for c in new_data["selected_connections"])
    assert new_data["ranking_results"] == []
    assert new_data["adjusted_flight_times"] == data["adjusted_flight_times"]  # DOKUNULMAZ
    assert data["selected_connections"][0]["od"] == "AAA-BBB"  # girdi mutate edilmedi
```

- [ ] **Step 2: FAIL gör**

Run: `.venv/bin/python3 -m pytest tests/unit/test_repair_underclaim.py -v`
Expected: FAIL — `No module named 'src.repair.underclaim'`

- [ ] **Step 3: Minimal implementasyon**

```python
# src/repair/underclaim.py
"""M5i C1 under-claim floor mantığı (spec §3.2) -- SİGORTA ARTEFAKTI üretimi.

UYARI (spec §0.1/§8): bu mekanizma docs/model.md'nin B semantiğiyle ("uygun
olan sunulmak zorunda", çift yönlü reifikasyon) bilinçli olarak çelişir --
validator'ın seçim-bazlı E1/E2 aktivasyonundan yararlanır. Teslim paketine
ana çözüm olarak GİRMEZ; scripts/make_underclaim_floor.py sidecar notunda
risk paragrafı zorunludur."""


def choose_directions_to_drop(records):
    """Her ihlalli çift için DÜŞÜK reward_contribution'lı yönü seç.
    Eşitlik kırıcı: önce daha az n_selected, sonra yön tuple'ı (determinizm).
    records: build_residual_records çıktısı (JSON round-trip'i de kabul)."""
    drops = []
    for r in records:
        options = []
        for tag in ("fwd", "bwd"):
            d = r["directions"][tag]
            options.append((d["reward_contribution"], d["n_selected"], tuple(d["direction"])))
        options.sort()
        drops.append(options[0][2])
    return drops


def drop_directions(data, directions):
    """Output-şemalı dict'ten verilen yönlerin selected_connections +
    ranking_results girdilerini düşürür. adjusted_flight_times'a DOKUNMAZ
    (zamanlar aynen uçar -- under-claim'in tanımı). Girdiyi mutate etmez.
    Returns (new_data, n_connections_dropped, n_ranking_dropped)."""
    dirset = {tuple(d) for d in directions}

    def _hit(od_str, gun):
        o, d = od_str.split("-")
        return (o, d, gun) in dirset

    new_sc, n_conn = [], 0
    for conn in data["selected_connections"]:
        if _hit(conn["od"], conn["gun"]):
            n_conn += 1
        else:
            new_sc.append(conn)

    new_rr, n_rank = [], 0
    for entry in data.get("ranking_results", []):
        if "od" in entry and "gun" in entry and _hit(entry["od"], entry["gun"]):
            n_rank += 1
        else:
            new_rr.append(entry)

    new_data = dict(data)
    new_data["selected_connections"] = new_sc
    new_data["ranking_results"] = new_rr
    return new_data, n_conn, n_rank
```

- [ ] **Step 4: PASS gör**

Run: `.venv/bin/python3 -m pytest tests/unit/test_repair_underclaim.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/repair/underclaim.py tests/unit/test_repair_underclaim.py
git commit -m "M5i Task4: C1 under-claim mantığı (yön seçimi + düşürme, TDD)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `scripts/make_underclaim_floor.py` — C1 script'i + gerçek koşu

**Files:**
- Create: `scripts/make_underclaim_floor.py`

**Interfaces:**
- Consumes: Task 3 çıktısı `runs/residual_repair_diagnosis.json` (yoksa HATA — Adım-0 önkoşulu), Task 4 fonksiyonları, `recompute_objective`, `validate_output` (D7 kalıbı).
- Produces: `runs/underclaim_floor_output.json` (objective_value = bağımsız recompute), `runs/underclaim_floor_note.json` (sidecar), `runs/underclaim_floor_output.objective_breakdown.json`.

- [ ] **Step 1: Script'i yaz**

```python
#!/usr/bin/env python3
"""M5i C1 (spec §3.2): under-claim floor SİGORTA artefaktı -- solver YOK.

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
```

- [ ] **Step 2: Unit suite yeşil**

Run: `.venv/bin/python3 -m pytest tests/unit -q`
Expected: tümü passed.

- [ ] **Step 3: Gerçek koşu (C1 sigortası)**

Run: `.venv/bin/python3 -u scripts/make_underclaim_floor.py`
Expected: ~1-2dk; `is_valid=True` bekleniyor (zamanlar elastik-feasible noktadan, A/G/F değişmedi; E1/E2 seçim-bazlı muafiyet). objective_before/after + reward_loss konsolda.
**valid=False çıkarsa: DUR, ihlal ailelerini raporla (spec §3.2) — kampanyaya bu bulguyla devam kararı kullanıcıda değil, plan gereği kampanya yine başlar ama C1 bulgusu sabah raporuna girer.**

- [ ] **Step 4: Commit**

```bash
git add scripts/make_underclaim_floor.py
git commit -m "M5i Task5: C1 under-claim floor scripti + sigorta artefaktı koşusu

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: `src/repair/campaign.py` — tur kararları

**Files:**
- Create: `src/repair/campaign.py`
- Test: `tests/unit/test_repair_campaign.py`

**Interfaces:**
- Consumes: `is_direction_killable`, `compute_pair_slack` çıktı şeması.
- Produces (Task 7 bunları kullanır):
  - `pick_round_kills(pair_slack, direction_index, candidates, contributions, already_killed, k, L, U) -> (kills: list[tuple], equalization_only: list[tuple])`
  - `escalation_decision(sigma_start, sigma_now, mechanics_sound, threshold_pct=0.05) -> "continue-A"|"switch-B"|"early-stop"`
  - `adaptive_k(current_k, sigma_before, sigma_after, cap=100, growth_threshold_pct=0.08) -> int`
  - `should_smoke_validate(sigma_before, sigma_after, threshold_pct=0.08) -> bool`
  - `split_slack(pair_slack, killed: set) -> (pending_total, open_total)`
  - `count_violation_families(violations) -> {"E1": int, "E2": int, "other": int}`
  - `newest_file_since(directory, glob_pattern, since_epoch) -> Path|None`

- [ ] **Step 1: Failing test yaz**

```python
# tests/unit/test_repair_campaign.py
"""M5i kampanya karar mantığı (spec §4) -- saf Python, solver yok."""
import time

from src.candidates.generate import Candidate
from src.model.deactivation import market_direction_index
from src.repair.campaign import (
    adaptive_k, count_violation_families, escalation_decision, newest_file_since,
    pick_round_kills, should_smoke_validate, split_slack,
)

L, U = 60, 300


def _candidate(o, d, flno1, flno2, gap_lo, gap_hi, gun=1):
    return Candidate(
        od=f"{o}-{d}", o=o, d=d, gun=gun, flno1=flno1, flno2=flno2,
        r1_id=("IB", flno1, gun), r2_id=("OB", flno2, gun), arr_time=None, dep_time=None,
        gap_min=max(gap_lo, min(gap_hi, 0)), arr_lo=0, arr_hi=200, dep_lo=0, dep_hi=500,
        gap_lo=gap_lo, gap_hi=gap_hi,
    )


def _ctx():
    cands = [
        _candidate("ZZG", "ZZH", 201, 301, 50, 350),   # killable
        _candidate("ZZH", "ZZG", 202, 302, 50, 350),   # killable
        _candidate("ZZI", "ZZJ", 203, 303, 100, 200),  # unkillable
        _candidate("ZZJ", "ZZI", 204, 304, 100, 200),  # unkillable
        _candidate("ZZK", "ZZL", 205, 305, 50, 350),   # killable
        _candidate("ZZL", "ZZK", 206, 306, 100, 200),  # unkillable
    ]
    index = market_direction_index(cands)
    pair_slack = {
        ("ZZG", "ZZH", 1): {"e1": 0.0, "e2": 300.0, "total": 300.0},
        ("ZZI", "ZZJ", 1): {"e1": 0.0, "e2": 200.0, "total": 200.0},  # both-unkillable
        ("ZZK", "ZZL", 1): {"e1": 0.0, "e2": 100.0, "total": 100.0},
    }
    contributions = {("ZZG", "ZZH", 1): 10.0, ("ZZH", "ZZG", 1): 999.0}
    return cands, index, pair_slack, contributions


# --- pick_round_kills ---

def test_picks_cheaper_killable_side_worst_first():
    cands, index, ps, contrib = _ctx()
    kills, eq = pick_round_kills(ps, index, cands, contrib, already_killed=set(), k=10, L=L, U=U)
    assert kills[0] == ("ZZG", "ZZH", 1)          # 10.0 < 999.0
    assert ("ZZK", "ZZL", 1) in kills             # tek killable yön o
    assert eq == [("ZZI", "ZZJ", 1)]              # both-unkillable -> equalization-only


def test_k_limit_and_already_killed_skip():
    cands, index, ps, contrib = _ctx()
    kills, _ = pick_round_kills(ps, index, cands, contrib, already_killed=set(), k=1, L=L, U=U)
    assert len(kills) == 1 and kills[0] == ("ZZG", "ZZH", 1)
    kills2, _ = pick_round_kills(ps, index, cands, contrib,
                                 already_killed={("ZZG", "ZZH", 1)}, k=10, L=L, U=U)
    assert ("ZZG", "ZZH", 1) not in kills2 and ("ZZH", "ZZG", 1) not in kills2


# --- escalation_decision (spec §4.5, üç dal) ---

def test_escalation_three_branches():
    assert escalation_decision(10944.0, 10000.0, mechanics_sound=True) == "continue-A"   # >=%5
    assert escalation_decision(10944.0, 10800.0, mechanics_sound=True) == "switch-B"     # 0<x<%5
    assert escalation_decision(10944.0, 10944.0, mechanics_sound=True) == "switch-B"     # =0, sağlam
    assert escalation_decision(10944.0, 10944.0, mechanics_sound=False) == "early-stop"  # =0, bozuk


# --- adaptive_k (spec §4.4) ---

def test_adaptive_k_growth_and_cap():
    assert adaptive_k(30, 10000.0, 9000.0) == 60      # %10 >= %8 -> iki kat
    assert adaptive_k(30, 10000.0, 9500.0) == 30      # %5 < %8 -> sabit
    assert adaptive_k(80, 10000.0, 9000.0) == 100     # tavan
    assert adaptive_k(30, 0.0, 0.0) == 30             # sıfır bölme koruması


# --- smoke eşiği + slack dökümü + ihlal aileleri ---

def test_should_smoke_validate_same_8pct_rule():
    assert should_smoke_validate(10000.0, 9100.0) is True
    assert should_smoke_validate(10000.0, 9500.0) is False


def test_split_slack_pending_vs_open():
    _, _, ps, _ = _ctx()
    pending, open_ = split_slack(ps, killed={("ZZH", "ZZG", 1)})  # ZZG-ZZH çiftinin bwd'si
    assert pending == 300.0 and open_ == 300.0


def test_count_violation_families():
    v = ["E1 AAA-BBB Gün=1: ...", "E2 CCC-DDD Gün=2: ...", "E2 X-Y Gün=3: ...", "rank claim ..."]
    assert count_violation_families(v) == {"E1": 1, "E2": 2, "other": 1}


def test_newest_file_since(tmp_path):
    old = tmp_path / "lns_summary_a.log.json"; old.write_text("{}")
    t = time.time() + 1
    new = tmp_path / "lns_summary_b.log.json"; new.write_text("{}")
    import os
    os.utime(old, (t - 100, t - 100)); os.utime(new, (t + 100, t + 100))
    assert newest_file_since(tmp_path, "lns_summary_*.log.json", t) == new
    assert newest_file_since(tmp_path, "lns_summary_*.log.json", t + 200) is None
```

- [ ] **Step 2: FAIL gör**

Run: `.venv/bin/python3 -m pytest tests/unit/test_repair_campaign.py -v`
Expected: FAIL — `No module named 'src.repair.campaign'`

- [ ] **Step 3: Minimal implementasyon**

```python
# src/repair/campaign.py
"""M5i kampanya karar mantığı (spec §4) -- saf Python, IO/solver yok.
scripts/run_residual_repair.py orkestratörü bu fonksiyonları çağırır;
üç dallı eskalasyon (§4.5), adaptif K (§4.4), smoke eşiği (§4.7),
worst-K kill seçimi (§4.1) ve tur-logu yardımcıları burada test edilir."""
from pathlib import Path

from src.model.deactivation import is_direction_killable


def pick_round_kills(pair_slack, direction_index, candidates, contributions,
                     already_killed, k, L, U):
    """Spec §4.1 adım 2: worst-K çift (total desc); her çiftte killable
    yönlerden düşük reward_contribution'lı olanı kapat. Both-unkillable
    çiftler K'ya SAYILMAZ (equalization_only). Bir ucu zaten kapatılmış
    çiftler atlanır (kill gerçekleşmeyi bekliyor -- LNS itecek)."""
    kills, equalization_only = [], []
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
```

- [ ] **Step 4: PASS gör**

Run: `.venv/bin/python3 -m pytest tests/unit/test_repair_campaign.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/repair/campaign.py tests/unit/test_repair_campaign.py
git commit -m "M5i Task6: kampanya karar mantığı (worst-K kill, eskalasyon, adaptif K, smoke, TDD)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: `scripts/run_residual_repair.py` — orkestratör

**Files:**
- Create: `scripts/run_residual_repair.py`

**Interfaces:**
- Consumes: Task 1 `--reference` bayrağı + `load_reference_point`; Task 6'nın tüm fonksiyonları; Task 3 diagnosis JSON'u (contributions kaynağı); `compute_pair_slack`, `compute_gamma_infeasible_pairs`, `market_direction_index`; subprocess olarak `scripts/run_lns.py` ve `scripts/warm_start_elastic.py`.
- Produces: `runs/residual_repair_campaign_<ts>/round_<N>.json`, `campaign_log.json`, `campaign_summary.json`; `runs/residual_repair_round<N>_directions.json`; konsol kampanya raporu.

- [ ] **Step 1: Script'i yaz**

```python
#!/usr/bin/env python3
"""M5i kampanya orkestratörü (spec docs/superpowers/specs/2026-07-12-residual-repair-design.md
§3.4 + §4): A modu turları (worst-K kill + 40dk LNS) -> ilk 2 tur sonunda üç dallı
eskalasyon (§4.5) -> gerekirse B modu (tam killable cover + warm_start_elastic + kalan
bütçe LNS). Keep-best persist; Σslack=0'da strict validate; valid=True'da DUR ve RAPORLA
-- outputs/full_data_output.json ASLA yazılmaz (spec §0.5).

Kullanım:
  .venv/bin/python3 -u scripts/run_residual_repair.py --dry-run   # solver'sız plan kontrolü
  nohup .venv/bin/python3 -u scripts/run_residual_repair.py > runs/residual_repair_console.log 2>&1 &
"""
import argparse
import json
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

    # --- paylaşılan preprocessing bloğu (plan "Paylaşılan bilgi" bölümünden AYNEN) ---
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
              f"best={best_partial}, kills(+{len(best_killed)-len(base_killed)}), "
              f"log={campaign_dir}", flush=True)

    mode = "A"
    k = args.k
    n_round = 0
    mechanics = []  # (kills_uygulandı: bool, iter_kosdu: bool) her tur

    while True:
        remaining = deadline - time.time()
        if remaining < args.round_wall_sec + 300:
            _final_report("budget_exhausted")
            return

        n_round += 1
        pair_slack, sigma_before, n_e1, n_e2 = _measure(
            candidates, journey_constants, best_partial, L, U, alpha, gamma, gamma_inf)

        if mode == "A":
            kills, eq_only = pick_round_kills(pair_slack, direction_index, candidates,
                                              contributions, best_killed, k, L, U)
        else:  # B modu: tüm killable-coverable residual (spec §4.6)
            kills, eq_only = pick_round_kills(pair_slack, direction_index, candidates,
                                              contributions, best_killed, 10**9, L, U)

        round_killed = best_killed | set(kills)
        directions_file = Path(f"runs/residual_repair_round{n_round}_directions.json")
        directions_file.write_text(json.dumps(sorted([list(d) for d in round_killed])))
        print(f"[campaign] round {n_round} ({mode}): +{len(kills)} kill "
              f"(toplam {len(round_killed)}), equalization-only={len(eq_only)}, K={k}", flush=True)

        if args.dry_run:
            print(f"[campaign] DRY-RUN: kills={kills[:10]}... eq_only={eq_only[:5]}...", flush=True)
            print(f"[campaign] DRY-RUN: bütçe {args.budget_sec:.0f}s, tur {args.round_wall_sec:.0f}s "
                  f"-> ~{int(args.budget_sec // (args.round_wall_sec + 300))} tur sığar", flush=True)
            return

        out_prefix = campaign_dir / f"round{n_round}"

        if mode == "B":
            # B modu: önce warm_start_elastic (900s), watchdog'a takılırsa atla (spec §4.6)
            wse_cmd = [PY, "-u", "scripts/warm_start_elastic.py",
                       "--deactivation-file", str(directions_file),
                       "--time-limit-sec", "900", "--max-improving-sols", "1"]
            print(f"[campaign] B: {' '.join(wse_cmd)}", flush=True)
            t_wse = time.time()
            try:
                with open(campaign_dir / "B_wse_console.log", "w") as fh:
                    subprocess.run(wse_cmd, stdout=fh, stderr=subprocess.STDOUT,
                                   timeout=900 + 120 + 900 + 300, check=False)
            except subprocess.TimeoutExpired:
                print("[campaign] B: warm_start_elastic dış zaman aşımı -- atlanıyor", flush=True)
            wse_out = Path("runs/warm_start_elastic_output.json")
            if wse_out.exists() and wse_out.stat().st_mtime > t_wse:
                _, s_wse, _, _ = _measure(candidates, journey_constants, wse_out,
                                          L, U, alpha, gamma, gamma_inf)
                print(f"[campaign] B: elastik nokta Sigma={s_wse:.2f}", flush=True)
                if s_wse < best_sigma - 1e-9:
                    best_partial, best_sigma, best_killed = str(wse_out), s_wse, round_killed
            lns_wall = max(600.0, deadline - time.time() - 600)
        else:
            lns_wall = args.round_wall_sec

        summary, console_log = _run_lns_round(best_partial, directions_file,
                                              lns_wall, out_prefix, args.seed)

        round_rec = {"round": n_round, "mode": mode, "k": k,
                     "kills_added": len(kills), "equalization_only": len(eq_only),
                     "sigma_before": sigma_before}
        if summary is None or not summary.get("partial_output_path"):
            mechanics.append((len(kills) > 0, False))
            round_rec.update({"status": "failed", "next_repair_decision": "revert+continue",
                              "validator_status": "not-run"})
            print(f"[campaign] round {n_round} FAILED (özet yok) -- referans korunur", flush=True)
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
                best_partial, best_sigma, best_killed = new_partial, sigma_after, round_killed
                k = adaptive_k(k, sigma_before, sigma_after)
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
            mech_sound = all(m[0] for m in mechanics) and any(m[1] for m in mechanics)
            decision = escalation_decision(sigma_campaign_start, best_sigma, mech_sound)
            print(f"[campaign] eskalasyon kararı (2 tur sonu): {decision} "
                  f"(Sigma {sigma_campaign_start:.2f}->{best_sigma:.2f}, mekanik={'sağlam' if mech_sound else 'bozuk'})",
                  flush=True)
            if decision == "early-stop":
                _final_report("early_stop_mechanics")
                return
            if decision == "switch-B":
                mode = "B"


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Unit suite yeşil + dry-run**

Run: `.venv/bin/python3 -m pytest tests/unit -q`
Expected: tümü passed.

Run: `.venv/bin/python3 -u scripts/run_residual_repair.py --dry-run`
Expected: ~1-2dk; `round 1 (A): +30 kill ...` satırı, kills önizlemesi, bütçe aritmetiği (`~5 tur sığar`), solver koşusu YOK, çıkış temiz. `runs/residual_repair_round1_directions.json` üretilir (dry-run kalıntısı — sorun değil, gerçek koşu kendi round dosyalarını yeniden yazar).

- [ ] **Step 3: Commit**

```bash
git add scripts/run_residual_repair.py
git commit -m "M5i Task7: kampanya orkestratörü (A->B eskalasyon, keep-best, smoke, dur-koşulları)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Kampanya yürütme (runbook — kod yok)

**Files:** yok (yürütme + raporlama).

- [ ] **Step 1: Son kapı — tam suite**

Run: `.venv/bin/python3 -m pytest tests/unit -q`
Expected: tümü passed (solve testlerine gerek yok — model koduna dokunulmadı).

- [ ] **Step 2: Kampanyayı arkaplanda başlat**

```bash
nohup .venv/bin/python3 -u scripts/run_residual_repair.py > runs/residual_repair_console.log 2>&1 &
echo $! > runs/residual_repair.pid
```

- [ ] **Step 3: İzleme**

Periyodik (ör. 20-30dk arayla): `tail -20 runs/residual_repair_console.log` + en yeni `runs/residual_repair_campaign_*/campaign_log.json`. İlk 2 tur (~80-90dk) sonunda eskalasyon kararı loglanacak.

- [ ] **Step 4: Kullanıcı raporu (kampanya bittiğinde ya da valid=True'da HEMEN)**

Rapor içeriği (spec §0.5 + kullanıcının bütçe-cevabındaki liste):
- Adım-0 özeti (both-unkillable oranı, C1 kayıp tahmini, VCE kümesi)
- C1 sonucu (valid mi, objective before/after, kayıp; sigorta konumu hatırlatması)
- Kampanya: tur tablosu (Σslack yörüngesi, kill sayıları, kararlar), final Σslack, en iyi partial yolu, ödül-kaybı tahmini, eskalasyon kararı ve gerekçesi
- valid=True bulunduysa: **`outputs/full_data_output.json` YAZILMADI** — yazma kararı kullanıcıda
- Sabah önerisi: devam/uzatma/B-tekrarı/folded-kill desteği/SCIP opsiyonu

---

## Plan öz-denetimi (yazım sonrası yapıldı)

- **Spec kapsaması:** §3.1→Task 2+3, §3.2→Task 4+5, §3.3→Task 1, §3.4+§4→Task 6+7, §4.5 üç dal→`escalation_decision`+testleri, §4.6 B-Plan-B→`_run` B dalı (watchdog atlanır), §4.7 smoke→`should_smoke_validate`+orkestratör, §4.8→Task 7 sabit `--builder fix` + round-1 fallback NOT'u (aşağıda), §5 hata→round-failed/revert yolları, §6 test→dört unit dosyası. Eksik: §4.8'in round-1 folded-fallback'i orkestratöre OTOMASYON olarak konmadı — bilinçli: tek seferlik manuel teşhis komutu (`run_lns --reference <best> --builder folded --max-wall-sec 2400`, deactivation-file OLMADAN) Task 8 izleme adımında gerekirse elle koşulur; otomasyonu YAGNI.
- **Placeholder taraması:** temiz — her adımda tam kod/komut/beklenen çıktı var.
- **Tip tutarlılığı:** `load_reference_point(path, candidates)` Task 1/3/7'de aynı; kayıt şeması Task 2 üretir, Task 4/5/7 tüketir (`directions.fwd/bwd.direction/reward_contribution/n_selected`); kapatma dosyası formatı (list of [o,d,gun]) run_lns.py:313 ile uyumlu; `contributions` anahtarı her yerde `(o,d,gun)` tuple.

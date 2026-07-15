# Benchmark-Safe Üretim Yolu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `main.py --full-data` her koşulda şema-uyumlu, tam-iddia (claim-complete), recompute-objective'li bir incumbent yazar (beklenen ≈1.488M) ve strict E1/E2 ihlallerini açık teşhis olarak raporlar; asla null/exit-1 dönmez.

**Architecture:** Yeni `src/benchmark/` modülü (times/claim/writer/pipeline): baseline FLOOR hemen yazılır → seed-delta overlay uygulanıp daha iyiyse üzerine yazılır → kalan bütçede mevcut strict tam-MIP (ladder, elastic kapalı) denenir ve yalnız strict-clean + claim-complete + daha-yüksek-recompute incumbent terfi eder. Eski strict merdiven `--strict-gate` bayrağı arkasında AYNEN korunur; `--fixture` yoluna sıfır dokunuş.

**Tech Stack:** Python 3.14 (proje venv'i), pandas, Pyomo/HiGHS (yalnız improve aşaması), pytest. Spec: `docs/superpowers/specs/2026-07-15-benchmark-safe-pipeline-design.md`.

## Global Constraints

- **Terminoloji (spec §0, P0):** strict validator-clean OLMAYAN hiçbir çıktı/log/doküman/test adında "geçerli tarife", "valid solution", `valid=True`, "validator-clean", "feasible solution" KULLANILAMAZ. Benchmark CLI özet satırında `valid=` alt dizisi geçemez (Task 5'te regresyon testi var). `--fixture` ve `--strict-gate` yolları gerçekten validator-clean olduğundan oradaki mevcut `valid=True` metni DEĞİŞMEZ.
- **exit 0 = yalnız dosya-üretim garantisi** (fizibilite garantisi değil); FLOOR yazıldıktan sonra hiçbir istisna exit≠0 üretemez. Veri dosyaları eksik/okunamazsa exit≠0 serbesttir.
- **`objective_value`'ya asla solver sayısı yazılmaz** — her zaman `recompute_objective` sonucu yazılır.
- **Validator bağımsızlığı:** `src/validate/independent_validator.py` HİÇBİR koşulda `src.model`, `src.candidates` veya `src.benchmark` import ETMEZ — yeni claim-completeness kontrolü kasıtlı bağımsız yeniden-uygulamadır (mevcut desen).
- **Fixture invariantı:** `python main.py --config src/config/standard.yaml --fixture` çıktısı 668.75 / `valid=True` / exit 0 olarak DEĞİŞMEDEN kalır.
- **Test komutu:** her zaman `source .venv/bin/activate` sonrası `python -m pytest` (kullanıcı tercihi). Solve testleri <60sn.
- **TDD:** her task kırmızı→yeşil→commit. Docs ilgili kodla AYNI commit'te.
- **Dur-ve-sor kapıları (Task 8):** (a) full-data recompute ≠ 1488074.8064039326 (±1e-6); (b) E1/E2 dışı ailede >0 strict ihlal; (c) seed `fallback_window_exceeded > 0`. Bunlardan biri tetiklenirse kullanıcıya dönülür, outputs/ YENİLENMEZ.
- Teslim: 2026-07-16 17:00. Task sırası = öncelik sırası; Task 8'den sonra süre daralırsa Task 9-10 improve-ayarlarından önce gelir (improve zaten config kill-switch'li).

---

### Task 1: `src/benchmark/times.py` — baseline haritası + seed-delta overlay

**Files:**
- Create: `src/benchmark/__init__.py` (boş)
- Create: `src/benchmark/times.py`
- Test: `tests/unit/test_benchmark_times.py`

**Interfaces:**
- Consumes: pandas DataFrame `tk` (kolonlar: flno1, flno2, gun, arr_time, dep_time — mevcut loader çıktısı), `anchor` (pd.Timestamp, `compute_epoch_anchor` sözleşmesi).
- Produces: `build_baseline_times(tk, anchor) -> dict[(role:str, flno:int, gun:int), int]`; `load_seed_deltas(path) -> tuple[list, str]`; `apply_seed_deltas(baseline_times, deltas, adjustable_window_min) -> tuple[dict, dict]` (stats anahtarları: `applied`, `skipped_missing_flight`, `fallback_window_exceeded`).

- [ ] **Step 1: Failing testleri yaz**

```python
# tests/unit/test_benchmark_times.py
"""src/benchmark/times.py testleri — spec §3.2 kuralları (a)/(b)/(c)."""
import json

import pandas as pd
import pytest

from src.benchmark.times import apply_seed_deltas, build_baseline_times, load_seed_deltas

pytestmark = pytest.mark.unit


def _tk():
    # 2 satır; ikinci satır AYNI (flno1=10,gun=1) bacağını farklı arr_time ile
    # tekrarlar -- build_baseline_times İLK görüleni tutmalı (validator'ın
    # match.iloc[0] davranışıyla aynı sözleşme).
    return pd.DataFrame([
        {"flno1": 10, "flno2": 20, "gun": 1,
         "arr_time": pd.Timestamp(2026, 3, 1, 10, 0), "dep_time": pd.Timestamp(2026, 3, 1, 12, 0),
         "dep1": "AAA", "arr2": "BBB", "cr1": "TK"},
        {"flno1": 10, "flno2": 21, "gun": 1,
         "arr_time": pd.Timestamp(2026, 3, 1, 10, 5), "dep_time": pd.Timestamp(2026, 3, 1, 13, 0),
         "dep1": "AAA", "arr2": "CCC", "cr1": "TK"},
    ])


ANCHOR = pd.Timestamp(2026, 3, 1, 0, 0)


def test_baseline_times_first_occurrence_wins():
    times = build_baseline_times(_tk(), ANCHOR)
    assert times[("IB", 10, 1)] == 600      # 10:00, İLK satır (10:05 değil)
    assert times[("OB", 20, 1)] == 720      # 12:00
    assert times[("OB", 21, 1)] == 780      # 13:00


def test_apply_deltas_happy_path_and_rules():
    baseline = {("IB", 10, 1): 600, ("OB", 20, 1): 720}
    deltas = [
        {"role": "IB", "flno": 10, "gun": 1, "delta_min": -30},   # uygulanır
        {"role": "OB", "flno": 99, "gun": 1, "delta_min": 10},    # uçuş yok -> atla
        {"role": "OB", "flno": 20, "gun": 1, "delta_min": 500},   # |500|>180 -> baseline'da kal
    ]
    times, stats = apply_seed_deltas(baseline, deltas, adjustable_window_min=180)
    assert times[("IB", 10, 1)] == 570
    assert times[("OB", 20, 1)] == 720
    assert stats == {"applied": 1, "skipped_missing_flight": 1, "fallback_window_exceeded": 1}


def test_load_seed_deltas_missing_and_corrupt(tmp_path):
    deltas, note = load_seed_deltas(tmp_path / "yok.json")
    assert deltas == [] and "not found" in note

    bad = tmp_path / "bozuk.json"
    bad.write_text("{bozuk json")
    deltas, note = load_seed_deltas(bad)
    assert deltas == [] and "unreadable" in note

    eksik = tmp_path / "eksik.json"
    eksik.write_text(json.dumps({"deltas": [{"role": "IB", "flno": 1}]}))
    deltas, note = load_seed_deltas(eksik)
    assert deltas == [] and "malformed" in note


def test_load_seed_deltas_ok(tmp_path):
    p = tmp_path / "seed.json"
    p.write_text(json.dumps({"deltas": [{"role": "IB", "flno": 10, "gun": 1, "delta_min": -30}]}))
    deltas, note = load_seed_deltas(p)
    assert note == "ok" and len(deltas) == 1
```

- [ ] **Step 2: Kırmızıyı doğrula**

Run: `source .venv/bin/activate && python -m pytest tests/unit/test_benchmark_times.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.benchmark'`

- [ ] **Step 3: Implementasyon**

```python
# src/benchmark/times.py
"""Benchmark pipeline zaman haritaları: her TK bacağı için baseline + seed-delta
overlay (spec §3.2). Üretim tarafıdır -- validator (src.validate) buradan HİÇBİR
ŞEY import edemez (bağımsızlık kuralı)."""
import json
from pathlib import Path


def epoch_min(ts, anchor) -> int:
    return int((ts - anchor).total_seconds() // 60)


def build_baseline_times(tk, anchor) -> dict:
    """(role, flno, gun) -> epoch dakika. IB=arr_time (IST varış),
    OB=dep_time (IST kalkış). Aynı bacak birden çok satırda görünür (her satır
    bir itinerary) -- İLK görülen tutulur, validator'ın match.iloc[0]
    davranışıyla aynı sözleşme."""
    times = {}
    for row in tk.itertuples():
        arr_key = ("IB", int(row.flno1), int(row.gun))
        if arr_key not in times:
            times[arr_key] = epoch_min(row.arr_time, anchor)
        dep_key = ("OB", int(row.flno2), int(row.gun))
        if dep_key not in times:
            times[dep_key] = epoch_min(row.dep_time, anchor)
    return times


def load_seed_deltas(path) -> tuple:
    """(deltas, note) döner; dosya yok/bozuk/eksik-anahtar -> ([], neden) --
    pipeline seed'siz devam eder (spec §3.2 kural c), ASLA raise etmez."""
    p = Path(path)
    if not p.exists():
        return [], f"seed file not found: {p}"
    try:
        data = json.loads(p.read_text())
        deltas = data["deltas"]
        for d in deltas:
            if not all(k in d for k in ("role", "flno", "gun", "delta_min")):
                return [], "seed file malformed: delta entry missing keys"
        return deltas, "ok"
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return [], f"seed file unreadable: {exc}"


def apply_seed_deltas(baseline_times: dict, deltas: list, adjustable_window_min: int) -> tuple:
    """Overlay kuralları (spec §3.2): (a) uçuş baseline'da yoksa atla;
    (b) |delta| pencereyi aşarsa baseline'da bırak (bağımsız pencere bekçisi);
    her ikisi de sayaçlanır."""
    times = dict(baseline_times)
    stats = {"applied": 0, "skipped_missing_flight": 0, "fallback_window_exceeded": 0}
    for d in deltas:
        key = (d["role"], int(d["flno"]), int(d["gun"]))
        if key not in baseline_times:
            stats["skipped_missing_flight"] += 1
            continue
        if abs(int(d["delta_min"])) > adjustable_window_min:
            stats["fallback_window_exceeded"] += 1
            continue
        times[key] = baseline_times[key] + int(d["delta_min"])
        stats["applied"] += 1
    return times, stats
```

`src/benchmark/__init__.py`: boş dosya.

- [ ] **Step 4: Yeşili doğrula**

Run: `python -m pytest tests/unit/test_benchmark_times.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/benchmark/ tests/unit/test_benchmark_times.py
git commit -m "Benchmark Task1: baseline zaman haritası + seed-delta overlay (TDD)"
```

---

### Task 2: `src/benchmark/claim.py` — pazar evreni + tam-iddia + ranking türetme

**Files:**
- Create: `src/benchmark/claim.py`
- Test: `tests/unit/test_benchmark_claim.py`

**Interfaces:**
- Consumes: Task 1'in `build_baseline_times`; `src.data.competitors.derive_rival_best_times`; `src.data.block_times.BlockTimeProvider` (get_journey_constant / get_journey_constant_estimate, KeyError sözleşmesi).
- Produces: `derive_market_universe(tk, rho, provider) -> tuple[dict[(o,d), float], list[(o,d)], dict[(o,d), str]]` (market_k_od, dropped, sources); `build_full_claim(tk, market_k_od, times, L, U) -> list[dict]` (od/flno1/flno2/gun/gap_min, sıralı); `derive_ranking_from_claim(od_table, market_k_od, connections) -> list[dict]` (o/d/gun/rank/beaten_rivals, sıralı).

- [ ] **Step 1: Failing testleri yaz**

```python
# tests/unit/test_benchmark_claim.py
"""Tam-iddia türetme testleri (spec §3.3). Anahtar test: fixture eşdeğerliği --
B çift-yönlü reifikasyon olduğundan, çözülmüş saatlerden türetilen tam-iddia
kümesi modelin seçtiği x kümesiyle BİREBİR aynı olmak ZORUNDA."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.benchmark.claim import build_full_claim, derive_market_universe, derive_ranking_from_claim
from src.benchmark.times import build_baseline_times
from src.candidates.generate import compute_epoch_anchor
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_od_table, load_yolcu_verisi

pytestmark = pytest.mark.unit

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_OUTPUT = "outputs/fixture_output.json"


def test_build_full_claim_gap_window():
    tk = pd.DataFrame([
        {"flno1": 10, "flno2": 20, "gun": 1,
         "arr_time": pd.Timestamp(2026, 3, 1, 10, 0), "dep_time": pd.Timestamp(2026, 3, 1, 12, 0),
         "dep1": "AAA", "arr2": "BBB", "cr1": "TK"},
        {"flno1": 11, "flno2": 20, "gun": 1,
         "arr_time": pd.Timestamp(2026, 3, 1, 11, 30), "dep_time": pd.Timestamp(2026, 3, 1, 12, 0),
         "dep1": "AAA", "arr2": "BBB", "cr1": "TK"},
    ])
    times = build_baseline_times(tk, pd.Timestamp(2026, 3, 1))
    market_k_od = {("AAA", "BBB"): 100.0}
    claim = build_full_claim(tk, market_k_od, times, L=60, U=300)
    # 10->20 gap=120 (girer); 11->20 gap=30 (<60, girmez)
    assert [(c["flno1"], c["flno2"], c["gap_min"]) for c in claim] == [(10, 20, 120)]


def test_full_claim_matches_fixture_models_selection():
    """EŞDEĞERLİK ÇAPASI: modelin x'leri == saatlerden türetilen tam-iddia."""
    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    anchor = compute_epoch_anchor(tk)
    data = json.loads(Path(FIXTURE_OUTPUT).read_text())

    times = build_baseline_times(tk, anchor)
    times.update({(e["role"], e["flno"], e["gun"]): e["time_min"]
                  for e in data["adjusted_flight_times"]})

    yolcu = load_yolcu_verisi(FIXTURE_YV)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    provider = BlockTimeProvider(tk, L=60, U=300)
    market_k_od, dropped, sources = derive_market_universe(tk, rho, provider)

    claim = build_full_claim(tk, market_k_od, times, L=60, U=300)
    derived = {(c["od"], c["flno1"], c["flno2"], c["gun"]) for c in claim}
    listed = {(c["od"], c["flno1"], c["flno2"], c["gun"]) for c in data["selected_connections"]}
    assert derived == listed


def test_derive_ranking_passes_independent_d_check(tmp_path):
    """Türetilen ranking, bağımsız validator'ın D-check'inden sıfır ihlalle
    geçmeli. (Fixture dosyasındaki ranking_results ile ALAN-ALANA eşitlik
    ARANMAZ: W'nun düz/berabere segmentinde model meşru under-claim yapabilir
    -- bkz. validator'ın under-claim toleransı; bizim türetmemiz TAM actual
    beaten kümesini iddia eder, bu da D-check'in her iki kuralını yapısal
    olarak sağlar.)"""
    from src.validate.independent_validator import validate_output

    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXTURE_YV)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    provider = BlockTimeProvider(tk, L=60, U=300)
    market_k_od, _, _ = derive_market_universe(tk, rho, provider)
    data = json.loads(Path(FIXTURE_OUTPUT).read_text())

    data["ranking_results"] = derive_ranking_from_claim(
        od_table, market_k_od, data["selected_connections"])
    p = tmp_path / "out.json"
    p.write_text(json.dumps(data))
    res = validate_output(
        p, FIXTURE_OD, L=60, U=300, adjustable_window_min=180, adjustable_set="all",
        flight_pairs_path="tests/fixtures/synthetic_flight_pairs.xlsx",
        tau=45, x_dev=15, alpha=0.20, gamma=30,
        bucket_size_min=10, capacity_departure=10, capacity_arrival=15)
    ranking_viols = [v for v in res.violations if v.startswith("ranking_results")]
    assert ranking_viols == []
```

- [ ] **Step 2: Kırmızıyı doğrula**

Run: `python -m pytest tests/unit/test_benchmark_claim.py -q`
Expected: FAIL — `cannot import name 'build_full_claim'`

- [ ] **Step 3: Implementasyon**

```python
# src/benchmark/claim.py
"""Tam-iddia (claim-complete) türetme: final saatlerden TÜM uygun bağlantılar +
ranking (spec §3.3). Pazar mantığı recompute_objective'inkiyle BİLEREK aynı
(bkz. o fonksiyonun VARSAYIM-8 fallback zinciri) -- ama buradan validator'a
kod AKMAZ: validator kendi bağımsız kopyasını taşır (Task 3), fixture
eşdeğerlik testi ikisini çapraz bağlar."""
from src.data.competitors import derive_rival_best_times


def derive_market_universe(tk, rho, provider):
    """Claim evreni = rho-pazarları ∩ K_od-türetilebilir (direct ya da
    LS-estimate; VARSAYIM-8 + VARSAYIM-18). K_od'suz pazar listeye giremez:
    recompute_objective'in fallback zinciri LS-estimate'te de başarısız olan
    bir pazar bağlantısında KeyError ile çökerdi (main.py'nin dropped_markets
    mantığının claim karşılığı). Döner: (market_k_od, dropped, sources)."""
    market_k_od, dropped, sources = {}, [], {}
    for (o, d) in sorted(rho):
        try:
            market_k_od[(o, d)] = provider.get_journey_constant(o, d)
            sources[(o, d)] = "direct"
        except KeyError:
            try:
                market_k_od[(o, d)] = provider.get_journey_constant_estimate(o, d)
                sources[(o, d)] = "estimated"
            except KeyError:
                dropped.append((o, d))
    return market_k_od, dropped, sources


def build_full_claim(tk, market_k_od: dict, times: dict, L: int, U: int) -> list:
    """Her (o,d) evren-pazarı x gün için inbound(dep1==o) x outbound(arr2==d)
    tam cross-product; final gap [L,U] içindeyse HER bağlantı listeye girer
    (budanmış aday listesi DEĞİL -- bütünlük tanımı gereği taze türetme).
    Bağlantı-varlık sözleşmesi validator'ınkiyle aynı: her bacak AYRI var
    olmalı, (flno1,flno2) çiftinin ham satırı ŞART DEĞİL."""
    connections = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        day = tk[tk["gun"] == gun]
        inbound_by_o, outbound_by_d = {}, {}
        for row in day.itertuples():
            inbound_by_o.setdefault(row.dep1, set()).add(int(row.flno1))
            outbound_by_d.setdefault(row.arr2, set()).add(int(row.flno2))
        for (o, d) in market_k_od:
            for f1 in sorted(inbound_by_o.get(o, ())):
                t_arr = times.get(("IB", f1, gun))
                if t_arr is None:
                    continue
                for f2 in sorted(outbound_by_d.get(d, ())):
                    t_dep = times.get(("OB", f2, gun))
                    if t_dep is None:
                        continue
                    gap = t_dep - t_arr
                    if L <= gap <= U:
                        connections.append({
                            "od": f"{o}-{d}", "flno1": f1, "flno2": f2,
                            "gun": gun, "gap_min": gap,
                        })
    connections.sort(key=lambda c: (c["od"], c["flno1"], c["flno2"], c["gun"]))
    return connections


def derive_ranking_from_claim(od_table, market_k_od: dict, connections: list) -> list:
    """recompute_objective'in beaten/rank mantığının üretim-tarafı karşılığı:
    journeys = K_od + gap; beaten = {rakip: herhangi bir j <= T_comp};
    rank = max(1, N - |beaten|) (rank-onehot clamp sözleşmesi)."""
    gaps_by_market = {}
    for c in connections:
        o, d = c["od"].split("-")
        gaps_by_market.setdefault((o, d, c["gun"]), []).append(c["gap_min"])
    results = []
    for (o, d, gun), gaps in sorted(gaps_by_market.items()):
        rivals = derive_rival_best_times(od_table, o, d, gun)
        if not rivals:
            continue
        k_od = market_k_od[(o, d)]
        journeys = [k_od + g for g in gaps]
        beaten = sorted(k for k, tc in rivals.items() if any(j <= tc for j in journeys))
        rank = max(1, len(rivals) - len(beaten))
        results.append({"o": o, "d": d, "gun": gun, "rank": rank, "beaten_rivals": beaten})
    return results
```

- [ ] **Step 4: Yeşili doğrula**

Run: `python -m pytest tests/unit/test_benchmark_claim.py -q`
Expected: 3 passed. **Eşdeğerlik testi FAIL ederse DUR:** bu, ya claim
türetmesinde bir bug ya da gerçek bir evren-farkı bulgusudur — geçici olarak
gevşetilmez, nedeni bulunur (fixture'da hangi bağlantı fark ediyor yazdırılıp
incelenir), gerekirse kullanıcıya sorulur.

- [ ] **Step 5: Commit**

```bash
git add src/benchmark/claim.py tests/unit/test_benchmark_claim.py
git commit -m "Benchmark Task2: tam-iddia türetme + fixture eşdeğerlik çapası (TDD)"
```

---

### Task 3: Validator iki modu — claim-completeness (EŞİTLİK) + aile özeti

**Files:**
- Modify: `src/validate/independent_validator.py` (dosya sonuna iki yeni fonksiyon — mevcut `validate_output`/`recompute_objective`/`finalize_reported_objective` DEĞİŞMEZ)
- Test: `tests/unit/test_claim_completeness.py`

**Interfaces:**
- Produces: `validate_claim_completeness(output_path, od_table_path, yolcu_path, L, U, strict=True) -> dict` (anahtarlar: `missing`, `extra`, `missing_claims`, `extra_claims`, `claim_complete`); `summarize_violation_families(violations: list[str]) -> dict` (anahtarlar: `counts`, `examples` — aile başına ilk 10 ham mesaj).
- Consumes: output JSON şeması (selected_connections/adjusted_flight_times), mevcut loader'lar + BlockTimeProvider (dosyada zaten import'lu).

- [ ] **Step 1: Failing testleri yaz**

```python
# tests/unit/test_claim_completeness.py
"""Spec §5: claim_complete EŞİTLİK kontrolü (P1 revizyonu) -- underclaim DA
overclaim DA yakalanır; overclaim kritik çünkü recompute listeden beslenir."""
import json
from pathlib import Path

import pytest

from src.validate.independent_validator import summarize_violation_families, validate_claim_completeness

pytestmark = pytest.mark.unit

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_OUTPUT = "outputs/fixture_output.json"


def _load_fixture_output():
    return json.loads(Path(FIXTURE_OUTPUT).read_text())


def test_untampered_fixture_output_is_claim_complete(tmp_path):
    p = tmp_path / "out.json"
    p.write_text(json.dumps(_load_fixture_output()))
    res = validate_claim_completeness(p, FIXTURE_OD, FIXTURE_YV, L=60, U=300)
    assert res["claim_complete"] is True
    assert res["missing_claims"] == 0 and res["extra_claims"] == 0


def test_missing_claim_detected(tmp_path):
    data = _load_fixture_output()
    data["selected_connections"].pop(0)          # kasıtlı underclaim
    p = tmp_path / "out.json"
    p.write_text(json.dumps(data))
    res = validate_claim_completeness(p, FIXTURE_OD, FIXTURE_YV, L=60, U=300)
    assert res["missing_claims"] == 1 and res["claim_complete"] is False


def test_extra_claim_detected(tmp_path):
    data = _load_fixture_output()
    fake = dict(data["selected_connections"][0])
    fake["flno2"] = 99999                        # saatlerin desteklemediği bağlantı
    data["selected_connections"].append(fake)    # kasıtlı overclaim
    p = tmp_path / "out.json"
    p.write_text(json.dumps(data))
    res = validate_claim_completeness(p, FIXTURE_OD, FIXTURE_YV, L=60, U=300)
    assert res["extra_claims"] == 1 and res["claim_complete"] is False


def test_summarize_violation_families_prefix_classifier():
    violations = [
        "E1 AAA-BBB Gün=1: |n_fwd(2)-n_bwd(0)| exceeds alpha(0.2)*(n_fwd+n_bwd)",
        "E2 AAA-BBB Gün=1: |Jbest_fwd(500)-Jbest_bwd(400)| exceeds Gamma(30)",
        "E2 CCC-DDD Gün=2: |Jbest_fwd(700)-Jbest_bwd(500)| exceeds Gamma(30)",
        "rotation FlNo(OB)=5 Gün=1 FlNo(IB)=6 Gün=1: IST arrival 100 < required minimum 200 (dep 10 + R_o(X)=45 + tau=45)",
        "F kova(departure) bucket=12: 11 uçuş, kalan kapasite 10 (taban=10, kapsam-dışı işgal=0)",
        "regularity (x_dev) role=IB FlNo=7 küme=[1, 2]: gün-içi spread=40min exceeds X_dev=15 (day-normalized times={1: 0, 2: 40})",
        "connection AAA-BBB FlNo1=1 FlNo2=2 Gün=1: gap=30min outside [60,300]",
        "bilinmeyen bir mesaj",
    ]
    fam = summarize_violation_families(violations)
    assert fam["counts"] == {"E1": 1, "E2": 2, "A": 1, "F": 1, "G": 1, "B": 1, "other": 1}
    assert fam["examples"]["E2"][0].startswith("E2 AAA-BBB")
    assert len(fam["examples"]["E2"]) == 2
```

- [ ] **Step 2: Kırmızıyı doğrula**

Run: `python -m pytest tests/unit/test_claim_completeness.py -q`
Expected: FAIL — `cannot import name 'validate_claim_completeness'`

- [ ] **Step 3: Implementasyon** (dosya sonuna ekle)

```python
# src/validate/independent_validator.py — dosya SONUNA eklenecek iki fonksiyon


_FAMILY_PREFIXES = [
    ("rotation ", "A"), ("connection ", "B"), ("E1 ", "E1"), ("E2 ", "E2"),
    ("F kova", "F"), ("regularity (x_dev)", "G"),
    ("adjusted_flight_times entry", "window"), ("ranking_results ", "D"),
]


def summarize_violation_families(violations: list) -> dict:
    """Aile-bazlı sayaç + aile başına ilk 10 ham örnek mesaj (spec §4
    diagnostics beslemesi). Sınıflandırma validate_output'un KENDİ mesaj
    önekleriyle yapılır -- önek değişirse test_claim_completeness'ın
    classifier testi kırılır (bilinçli bağ, sessiz kayma yok)."""
    counts, examples = {}, {}
    for v in violations:
        fam = next((f for p, f in _FAMILY_PREFIXES if v.startswith(p)), "other")
        counts[fam] = counts.get(fam, 0) + 1
        bucket = examples.setdefault(fam, [])
        if len(bucket) < 10:
            bucket.append(v)
    return {"counts": counts, "examples": examples}


def validate_claim_completeness(
    output_path: Path, od_table_path: Path, yolcu_path: Path, L: int, U: int,
    strict: bool = True,
) -> dict:
    """Tam-iddia EŞİTLİK kontrolü (spec §5, P1): output'un KENDİ saatlerinden
    bağımsızca türetilen uygun-bağlantı kümesi == listelenen küme. missing
    (underclaim) DA extra (overclaim) DA ihlal -- overclaim kritik:
    recompute_objective listelenen kümeden beslenir, fazladan bağlantı
    objective'i ŞİŞİRİR ve strict-check'ler yalnız raporlandığı için başka
    hiçbir kapı bunu yakalamaz. Evren: rho-pazarları ∩ K_od-türetilebilir
    (VARSAYIM-8/18). src.benchmark'tan import YOK -- kasıtlı bağımsız
    yeniden-uygulama (bu dosyanın yerleşik deseni)."""
    data = json.loads(Path(output_path).read_text())
    od_table = load_od_table(od_table_path)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(yolcu_path, strict=strict)
    provider = BlockTimeProvider(tk, L=L, U=U)

    scorable = set()
    for r in yolcu.itertuples():
        o, d = r.orig, r.dest
        try:
            provider.get_journey_constant(o, d)
        except KeyError:
            try:
                provider.get_journey_constant_estimate(o, d)
            except KeyError:
                continue
        scorable.add((o, d))

    reported_times = {
        (e["role"], e["flno"], e["gun"]): e["time_min"]
        for e in data.get("adjusted_flight_times", [])
    }

    derived = set()
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        day = tk[tk["gun"] == gun]
        inbound_by_o, outbound_by_d = {}, {}
        for row in day.itertuples():
            inbound_by_o.setdefault(row.dep1, set()).add(int(row.flno1))
            outbound_by_d.setdefault(row.arr2, set()).add(int(row.flno2))
        for (o, d) in scorable:
            for f1 in inbound_by_o.get(o, ()):
                t_arr = reported_times.get(("IB", f1, gun))
                if t_arr is None:
                    continue
                for f2 in outbound_by_d.get(d, ()):
                    t_dep = reported_times.get(("OB", f2, gun))
                    if t_dep is None:
                        continue
                    if L <= t_dep - t_arr <= U:
                        derived.add((f"{o}-{d}", f1, f2, gun))

    listed = {(c["od"], c["flno1"], c["flno2"], c["gun"]) for c in data["selected_connections"]}
    missing = sorted(derived - listed)
    extra = sorted(listed - derived)
    return {
        "missing": [list(m) for m in missing], "extra": [list(e) for e in extra],
        "missing_claims": len(missing), "extra_claims": len(extra),
        "claim_complete": not missing and not extra,
    }
```

- [ ] **Step 4: Yeşili doğrula + tam suite regresyonu**

Run: `python -m pytest tests/unit/test_claim_completeness.py -q && python -m pytest -m unit -q`
Expected: yeni 4 test dahil tüm unit yeşil (mevcut validator testlerinde sıfır kırılma).

- [ ] **Step 5: Commit**

```bash
git add src/validate/independent_validator.py tests/unit/test_claim_completeness.py
git commit -m "Benchmark Task3: validator'a claim-completeness EŞİTLİK modu + aile özeti (TDD)"
```

---

### Task 4: `src/benchmark/writer.py` — diagnostics'li şema-uyumlu yazıcı

**Files:**
- Create: `src/benchmark/writer.py`
- Test: `tests/unit/test_benchmark_writer.py`

**Interfaces:**
- Produces: `write_benchmark_output(path, times, connections, ranking_results, k_od_sources, status, solve_time_sec, diagnostics) -> None`; `stamp_recomputed_objective(path, total) -> None`; `patch_json_field(path, keys: list, value) -> None`.
- Şema sözleşmesi: `src/output/writer.py::write_output`'un ürettiği üst-düzey alanların TAMAMI + `diagnostics` (parite testi ile bağlanır).

- [ ] **Step 1: Failing testleri yaz**

```python
# tests/unit/test_benchmark_writer.py
import json
from pathlib import Path

import pytest

from src.benchmark.writer import patch_json_field, stamp_recomputed_objective, write_benchmark_output

pytestmark = pytest.mark.unit


def _write(tmp_path, **overrides):
    p = tmp_path / "out.json"
    kwargs = dict(
        path=p,
        times={("IB", 10, 1): 600, ("OB", 20, 1): 720},
        connections=[{"od": "AAA-BBB", "flno1": 10, "flno2": 20, "gun": 1, "gap_min": 120}],
        ranking_results=[{"o": "AAA", "d": "BBB", "gun": 1, "rank": 1, "beaten_rivals": ["XX"]}],
        k_od_sources={("AAA", "BBB"): "direct"},
        status="heuristic_incumbent_with_strict_violations",
        solve_time_sec=1.5,
        diagnostics={"mode": "benchmark_full_claim", "strict_feasible": False},
    )
    kwargs.update(overrides)
    write_benchmark_output(**kwargs)
    return p


def test_schema_parity_with_strict_writer(tmp_path):
    """write_output'un ürettiği TÜM üst-düzey alanlar benchmark yazıcısında da
    olmalı (şema-uyumluluk) + diagnostics EK alan."""
    from src.output.writer import write_output
    from src.solve.runner import SolveResult

    strict_p = tmp_path / "strict.json"
    write_output(strict_p, SolveResult(status="optimal", objective_value=1.0, selected={}, solve_time_sec=0.0))
    strict_fields = set(json.loads(strict_p.read_text()).keys())

    bench = json.loads(_write(tmp_path).read_text())
    assert strict_fields <= set(bench.keys())
    assert "diagnostics" in bench


def test_writer_is_deterministic_and_sorted(tmp_path):
    p1 = _write(tmp_path)
    content1 = p1.read_text()
    p2 = _write(tmp_path)
    assert content1 == p2.read_text()
    data = json.loads(content1)
    assert data["adjusted_flight_times"][0] == {"role": "IB", "flno": 10, "gun": 1, "time_min": 600}
    assert data["objective_value"] is None  # stamp'ten önce her zaman None


def test_stamp_and_patch(tmp_path):
    p = _write(tmp_path)
    stamp_recomputed_objective(p, 1488074.81)
    assert json.loads(p.read_text())["objective_value"] == 1488074.81
    patch_json_field(p, ["diagnostics", "baseline_reference"], {"objective": 1.0})
    assert json.loads(p.read_text())["diagnostics"]["baseline_reference"] == {"objective": 1.0}
```

- [ ] **Step 2: Kırmızıyı doğrula**

Run: `python -m pytest tests/unit/test_benchmark_writer.py -q`
Expected: FAIL — modül yok

- [ ] **Step 3: Implementasyon**

```python
# src/benchmark/writer.py
"""Benchmark çıktı yazıcısı: write_output'un şemasıyla alan-parite (test
bağlı) + diagnostics bloğu. objective_value ASLA burada hesaplanmaz --
önce None yazılır, recompute sonrası stamp_recomputed_objective doldurur
(spec: 'objective yalnız recompute'tan yazılır')."""
import json
from pathlib import Path


def write_benchmark_output(path, times: dict, connections: list, ranking_results: list,
                           k_od_sources: dict, status: str, solve_time_sec: float,
                           diagnostics: dict) -> None:
    adjusted = [
        {"role": r, "flno": f, "gun": g, "time_min": t}
        for (r, f, g), t in times.items()
    ]
    adjusted.sort(key=lambda e: (e["role"], e["flno"], e["gun"]))
    k_od_source_list = sorted(
        ({"o": o, "d": d, "source": s} for (o, d), s in (k_od_sources or {}).items()),
        key=lambda e: (e["o"], e["d"]),
    )
    data = {
        "objective_value": None,
        "selected_connections": connections,
        "adjusted_flight_times": adjusted,
        "ranking_results": ranking_results,
        "k_od_sources": k_od_source_list,
        "solver_metrics": {"status": status, "solve_time_sec": solve_time_sec},
        "diagnostics": diagnostics,
    }
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def stamp_recomputed_objective(path, total: float) -> None:
    patch_json_field(path, ["objective_value"], total)


def patch_json_field(path, keys: list, value) -> None:
    data = json.loads(Path(path).read_text())
    node = data
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
```

- [ ] **Step 4: Yeşili doğrula**

Run: `python -m pytest tests/unit/test_benchmark_writer.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/benchmark/writer.py tests/unit/test_benchmark_writer.py
git commit -m "Benchmark Task4: diagnostics'li şema-parite yazıcı (TDD)"
```

---

### Task 5: `src/benchmark/pipeline.py` — floor → seed → improve orkestrasyonu

**Files:**
- Create: `src/benchmark/pipeline.py`
- Test: `tests/unit/test_benchmark_pipeline.py` (solver'sız, monkeypatch'li)
- Test: `tests/solve/test_benchmark_pipeline_fixture.py` (gerçek HiGHS, fixture ölçeği, <60sn)

**Interfaces:**
- Consumes: Task 1-4'ün tüm fonksiyonları; `src.solve.ladder.solve_with_ladder` (imza main.py:162-176'daki çağrıyla aynı); `src.output.writer.write_output`; validator üçlüsü + Task 3 fonksiyonları.
- Produces: `run_benchmark_pipeline(**kwargs) -> int` (aşağıdaki tam imza) ve `Assessment` dataclass'ı. main.py Task 6'da bunu çağırır.

- [ ] **Step 1: Failing testleri yaz**

```python
# tests/unit/test_benchmark_pipeline.py
"""Pipeline sözleşme testleri (solver YOK): exit-0 dosya-üretim garantisi,
terminoloji yasağı, seed kabul/red kapıları, improve çökmesine dayanıklılık."""
import json
from pathlib import Path

import pytest

from src.benchmark.pipeline import run_benchmark_pipeline
from src.candidates.generate import compute_epoch_anchor
from src.data.block_times import BlockTimeProvider
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi

pytestmark = pytest.mark.unit

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_CR = "tests/fixtures/synthetic_change_ranking_input.xlsx"
FIXTURE_FP = "tests/fixtures/synthetic_flight_pairs.xlsx"

CONFIG = {
    "L": 60, "U": 300, "tau": 45, "X_dev": 15, "alpha": 0.20, "gamma": 30,
    "bucket_size_min": 10, "capacity_departure": 10, "capacity_arrival": 15,
    "adjustable_window_min": 180, "adjustable_set": "all",
    "e1_activation": "conditional", "seed": 42, "solver": "highs",
    "watchdog_margin_sec": 60,
}


def _pipeline_kwargs(tmp_path, **overrides):
    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXTURE_YV)
    kwargs = dict(
        output_path=tmp_path / "output.json",
        od_path=FIXTURE_OD, yv_path=FIXTURE_YV, cr_path=FIXTURE_CR, fp_path=FIXTURE_FP,
        config=CONFIG, od_table=od_table, tk=tk,
        provider=BlockTimeProvider(tk, L=60, U=300),
        rho={(r.orig, r.dest): r.rho for r in yolcu.itertuples()},
        anchor=compute_epoch_anchor(tk),
        candidates=[], journey_constants={}, rival_data={}, b_od_data={},
        ranking_table=load_change_ranking(FIXTURE_CR),
        pairs_df=load_flight_pairs(FIXTURE_FP), r_o_lookup={}, monotonic=True,
        seed_deltas_path=tmp_path / "seed_yok.json",
        time_budget_sec=600, improve_enabled=False, yolcu_strict=True,
    )
    kwargs.update(overrides)
    return kwargs


def test_floor_written_and_exit_zero_without_seed(tmp_path, capsys):
    rc = run_benchmark_pipeline(**_pipeline_kwargs(tmp_path))
    assert rc == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert data["objective_value"] is not None and data["objective_value"] > 0
    assert data["diagnostics"]["claim_complete"] is True
    assert data["diagnostics"]["constraint_interpretation"] == "strict_A_G_checked; E1_E2_reported_as_diagnostics"
    assert "baseline_floor" in data["solver_metrics"]["status"]
    out = capsys.readouterr().out
    assert "valid=" not in out            # P0 terminoloji yasağı


def test_corrupt_seed_falls_back_to_floor(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text("{bozuk")
    rc = run_benchmark_pipeline(**_pipeline_kwargs(tmp_path, seed_deltas_path=seed))
    assert rc == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert "baseline_floor" in data["solver_metrics"]["status"]


def test_seed_with_zero_deltas_not_promoted(tmp_path):
    # delta'sız seed => seed saatleri == floor saatleri => objective eşit,
    # "daha yüksek" şartı sağlanmaz => floor kalır (kabul kapısı testi).
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"deltas": []}))
    rc = run_benchmark_pipeline(**_pipeline_kwargs(tmp_path, seed_deltas_path=seed))
    assert rc == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert "baseline_floor" in data["solver_metrics"]["status"]


def test_improve_crash_keeps_best_and_exit_zero(tmp_path):
    def boom_ladder(**kwargs):
        raise RuntimeError("solver çöktü")
    rc = run_benchmark_pipeline(**_pipeline_kwargs(
        tmp_path, improve_enabled=True, candidates=["sahte-aday"], ladder_fn=boom_ladder))
    assert rc == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert data["objective_value"] is not None
```

- [ ] **Step 2: Kırmızıyı doğrula**

Run: `python -m pytest tests/unit/test_benchmark_pipeline.py -q`
Expected: FAIL — modül yok

- [ ] **Step 3: Implementasyon**

```python
# src/benchmark/pipeline.py
"""Benchmark-safe üretim yolu orkestrasyonu (spec §3.1):
FLOOR (baseline, hemen yaz) -> SEED (delta overlay, iyiyse terfi) ->
IMPROVE (strict tam-MIP denemesi; yalnız strict-clean + claim-complete +
daha-yüksek-recompute terfi eder). exit 0 = dosya-üretim garantisi (spec §0);
FLOOR yazıldıktan sonra hiçbir istisna exit'i bozamaz."""
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
_BASE_NOTE = ("E1/E2 strict okuması altında yayınlanan baseline tarifesi de "
              "ihlallidir; bkz. docs/report.md")


@dataclass
class Assessment:
    stage: str
    status: str
    objective: float
    n_strict_violations: int
    strict_feasible: bool
    claim: dict
    families: dict


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


def _status_for(stage: str, n_viol: int) -> str:
    if n_viol == 0:
        return "baseline_floor" if stage == "baseline_floor" else "strict_feasible_incumbent"
    return f"{stage}_with_strict_violations"


def _validate_strict(ctx, path):
    cfg = ctx.config
    return validate_output(
        path, ctx.od_path, L=cfg["L"], U=cfg["U"],
        adjustable_window_min=cfg["adjustable_window_min"], adjustable_set=cfg["adjustable_set"],
        flight_pairs_path=ctx.fp_path, tau=cfg["tau"], x_dev=cfg["X_dev"],
        alpha=cfg["alpha"], gamma=cfg["gamma"], bucket_size_min=cfg["bucket_size_min"],
        capacity_departure=cfg["capacity_departure"], capacity_arrival=cfg["capacity_arrival"],
        e1_activation=cfg.get("e1_activation", "conditional"),
    )


def _assess_and_write(ctx, path, times, stage, seed_block, baseline_reference, elapsed_sec):
    """Tek noktadan değerlendirme: yaz -> recompute -> claim-eşitlik ->
    strict teşhis -> diagnostics'li nihai yazım. objective yalnız recompute'tan."""
    cfg = ctx.config
    connections = build_full_claim(ctx.tk, ctx.market_k_od, times, L=cfg["L"], U=cfg["U"])
    ranking = derive_ranking_from_claim(ctx.od_table, ctx.market_k_od, connections)

    write_benchmark_output(path, times, connections, ranking, ctx.sources,
                           status="provisional", solve_time_sec=elapsed_sec, diagnostics={})
    total, _ = recompute_objective(path, ctx.od_path, ctx.yv_path, ctx.cr_path,
                                   L=cfg["L"], U=cfg["U"], strict=ctx.yolcu_strict)
    claim = validate_claim_completeness(path, ctx.od_path, ctx.yv_path,
                                        L=cfg["L"], U=cfg["U"], strict=ctx.yolcu_strict)
    validation = _validate_strict(ctx, path)
    families = summarize_violation_families(validation.violations)
    n_viol = sum(families["counts"].values())
    status = _status_for(stage, n_viol)

    diagnostics = {
        "mode": "benchmark_full_claim",
        "strict_feasible": n_viol == 0,
        "constraint_interpretation": _INTERPRETATION,
        "claim_complete": claim["claim_complete"],
        "claim_check": {"missing_claims": claim["missing_claims"],
                        "extra_claims": claim["extra_claims"]},
        "seed": seed_block,
        "strict_violations": {"total": n_viol, "by_family": families["counts"],
                              "examples": families["examples"]},
        "dropped_markets_no_k_od": len(ctx.dropped),
        "baseline_reference": baseline_reference,
        "note": _BASE_NOTE,
    }
    write_benchmark_output(path, times, connections, ranking, ctx.sources,
                           status=status, solve_time_sec=elapsed_sec, diagnostics=diagnostics)
    stamp_recomputed_objective(path, total)
    return Assessment(stage, status, total, n_viol, n_viol == 0, claim, families)


def run_benchmark_pipeline(
    *, output_path, od_path, yv_path, cr_path, fp_path, config, od_table, tk,
    provider, rho, anchor, candidates, journey_constants, rival_data, b_od_data,
    ranking_table, pairs_df, r_o_lookup, monotonic, seed_deltas_path,
    time_budget_sec, improve_enabled=True, yolcu_strict=False,
    ladder_fn=solve_with_ladder, now_fn=time.time,
) -> int:
    t0 = now_fn()
    output_path = Path(output_path)
    market_k_od, dropped, sources = derive_market_universe(tk, rho, provider)
    if dropped:
        print(f"[benchmark] K_od türetilemeyen {len(dropped)} pazar claim evreni dışında "
              f"(VARSAYIM-8/18): {dropped[:5]}{'...' if len(dropped) > 5 else ''}", flush=True)
    ctx = _Ctx(od_path=od_path, yv_path=yv_path, cr_path=cr_path, fp_path=fp_path,
               config=config, od_table=od_table, tk=tk, market_k_od=market_k_od,
               sources=sources, dropped=dropped, yolcu_strict=yolcu_strict)
    baseline_times = build_baseline_times(tk, anchor)

    # ---- FLOOR: bu yazımdan sonra exit 0 dosya-üretim garantisi yürürlükte
    floor = _assess_and_write(ctx, output_path, baseline_times, "baseline_floor",
                              seed_block={"file": None, "note": "floor: ham baseline saatleri"},
                              baseline_reference=None, elapsed_sec=now_fn() - t0)
    best_ref = {"objective": floor.objective,
                "strict_violations_total": floor.n_strict_violations}
    patch_json_field(output_path, ["diagnostics", "baseline_reference"], best_ref)
    best = floor
    print(f"[benchmark] floor yazıldı: objective={floor.objective} "
          f"strict_violations={floor.n_strict_violations}", flush=True)

    # ---- SEED (spec §3.2; her hata floor'u korur)
    try:
        deltas, note = load_seed_deltas(seed_deltas_path)
        if deltas:
            seed_times, stats = apply_seed_deltas(
                baseline_times, deltas, config["adjustable_window_min"])
            tmp_s = output_path.with_name(output_path.stem + ".seed_attempt.json")
            seed_block = {"file": str(seed_deltas_path), **stats, "note": note}
            attempt = _assess_and_write(ctx, tmp_s, seed_times, "heuristic_incumbent",
                                        seed_block=seed_block, baseline_reference=best_ref,
                                        elapsed_sec=now_fn() - t0)
            if attempt.claim["claim_complete"] and attempt.objective > best.objective:
                output_path.write_text(tmp_s.read_text())
                best = attempt
                print(f"[benchmark] seed kabul: objective={attempt.objective} "
                      f"strict_violations={attempt.n_strict_violations} "
                      f"applied={stats['applied']}", flush=True)
            else:
                print(f"[benchmark] seed reddedildi (claim_complete="
                      f"{attempt.claim['claim_complete']}, objective={attempt.objective} "
                      f"<= floor {best.objective}) — floor korunuyor", flush=True)
        else:
            print(f"[benchmark] seed yok/okunamadı ({note}) — floor ile devam", flush=True)
    except Exception as exc:  # dosya-üretim garantisi: floor dosyada
        print(f"[benchmark] seed aşaması hata verdi, floor korunuyor: {exc}", flush=True)

    # ---- IMPROVE (spec §3.4; kesilebilir, her hata mevcut en iyiyi korur)
    try:
        remaining = time_budget_sec - (now_fn() - t0)
        if improve_enabled and candidates and remaining > 90:
            cfg = config
            tmp_i = output_path.with_name(output_path.stem + ".improve_attempt.json")

            def _improve_validate_fn(step_candidates, result) -> bool:
                write_output(tmp_i, result, k_od_sources=None)
                total_i, _ = recompute_objective(tmp_i, od_path, yv_path, cr_path,
                                                 L=cfg["L"], U=cfg["U"], strict=yolcu_strict)
                ok, msg = finalize_reported_objective(
                    tmp_i, total_i, result.status, result.objective_value)
                if not ok:
                    print(f"[benchmark] improve reconciliation FAILURE: {msg}", flush=True)
                    return False
                v = _validate_strict(ctx, tmp_i)
                for viol in v.violations[:5]:
                    print(f"  [benchmark] improve aday ihlali: {viol}", flush=True)
                return v.is_valid

            _, result, ladder_log = ladder_fn(
                candidates_full=candidates, rho=rho, journey_constants=journey_constants,
                rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
                pairs_df=pairs_df, r_o_lookup=r_o_lookup, tau=cfg["tau"], x_dev=cfg["X_dev"],
                epoch_anchor=anchor, alpha=cfg["alpha"], gamma=cfg["gamma"], tk_rows=tk,
                bucket_size_min=cfg["bucket_size_min"],
                capacity_departure=cfg["capacity_departure"],
                capacity_arrival=cfg["capacity_arrival"], L=cfg["L"], U=cfg["U"],
                monotonic=monotonic,
                step1_time_limit_sec=max(60, remaining - cfg.get("watchdog_margin_sec", 60)),
                seed=cfg["seed"], solver=cfg["solver"], validate_fn=_improve_validate_fn,
                e1_activation=cfg.get("e1_activation", "conditional"),
                enable_elastic_fallback=False, step2_k_schedule=(),
                use_subprocess_watchdog=True,
                watchdog_margin_sec=cfg.get("watchdog_margin_sec", 60),
            )
            for entry in ladder_log:
                print(f"  [benchmark] improve ladder: {entry}", flush=True)
            accepted = result.status in ("optimal", "time_limit") and result.objective_value is not None
            if accepted:
                data_i = json.loads(tmp_i.read_text())
                claim_i = validate_claim_completeness(tmp_i, od_path, yv_path,
                                                      L=cfg["L"], U=cfg["U"], strict=yolcu_strict)
                if claim_i["claim_complete"] and data_i["objective_value"] > best.objective:
                    data_i["solver_metrics"]["status"] = "strict_feasible_incumbent"
                    data_i["diagnostics"] = {
                        "mode": "benchmark_full_claim",
                        "strict_feasible": True,
                        "constraint_interpretation": _INTERPRETATION,
                        "claim_complete": True,
                        "claim_check": {"missing_claims": 0, "extra_claims": 0},
                        "seed": {"file": None, "note": "improve: strict tam-MIP incumbent'ı"},
                        "strict_violations": {"total": 0, "by_family": {}, "examples": {}},
                        "dropped_markets_no_k_od": len(dropped),
                        "baseline_reference": best_ref,
                        "note": _BASE_NOTE,
                    }
                    output_path.write_text(json.dumps(data_i, indent=2, sort_keys=True) + "\n")
                    best = Assessment("improved_incumbent", "strict_feasible_incumbent",
                                      data_i["objective_value"], 0, True, claim_i,
                                      {"counts": {}, "examples": {}})
                    print(f"[benchmark] improve KABUL: strict_feasible_incumbent "
                          f"objective={best.objective}", flush=True)
                else:
                    print(f"[benchmark] improve incumbent'ı reddedildi (claim_complete="
                          f"{claim_i['claim_complete']}, objective={data_i['objective_value']} "
                          f"<= {best.objective})", flush=True)
            else:
                print(f"[benchmark] improve incumbent bulamadı (status={result.status}) — "
                      f"beklenen davranış, mevcut en iyi korunuyor", flush=True)
        else:
            print(f"[benchmark] improve atlandı (enabled={improve_enabled}, "
                  f"kalan={max(0.0, remaining):.0f}s, n_candidates={len(candidates)})", flush=True)
    except Exception as exc:
        print(f"[benchmark] improve aşaması hata verdi, mevcut en iyi korunuyor: {exc}", flush=True)

    families_txt = ",".join(f"{k}:{v}" for k, v in sorted(best.families["counts"].items())) or "none"
    print(f"status={best.status} objective={best.objective} "
          f"claim_complete={best.claim['claim_complete']} "
          f"strict_feasible={best.strict_feasible} violations={families_txt}")
    return 0
```

- [ ] **Step 4: Unit yeşili doğrula**

Run: `python -m pytest tests/unit/test_benchmark_pipeline.py -q`
Expected: 4 passed. (Not: fixture baseline'ı strict-clean çıkarsa
`baseline_floor`, değilse `baseline_floor_with_strict_violations` — testler bu
yüzden `"baseline_floor" in status` ile kontrol ediyor, ikisi de meşru.)

- [ ] **Step 5: Solve e2e testini yaz (gerçek HiGHS, fixture)**

```python
# tests/solve/test_benchmark_pipeline_fixture.py
"""Benchmark pipeline'ın fixture verisiyle uçtan uca vitrini: improve aşaması
fixture'da strict-clean optimal bulur -> status=strict_feasible_incumbent,
objective=668.75 (bruteforce-oracle'lı bilinen değer)."""
import json

import pytest

from src.benchmark.pipeline import run_benchmark_pipeline
from src.candidates.generate import compute_epoch_anchor, generate_candidates
from src.data.block_times import BlockTimeProvider
from src.data.competitors import derive_rival_best_times
from src.data.loaders import load_change_ranking, load_flight_pairs, load_od_table, load_yolcu_verisi
from src.data.ranking import compute_baseline_best_journey, derive_b_od, is_ranking_monotonic

pytestmark = pytest.mark.solve

FIXTURE_OD = "tests/fixtures/synthetic_od_table.xlsx"
FIXTURE_YV = "tests/fixtures/synthetic_yolcu_verisi.xlsx"
FIXTURE_CR = "tests/fixtures/synthetic_change_ranking_input.xlsx"
FIXTURE_FP = "tests/fixtures/synthetic_flight_pairs.xlsx"

CONFIG = {
    "L": 60, "U": 300, "tau": 45, "X_dev": 15, "alpha": 0.20, "gamma": 30,
    "bucket_size_min": 10, "capacity_departure": 10, "capacity_arrival": 15,
    "adjustable_window_min": 180, "adjustable_set": "all",
    "e1_activation": "conditional", "seed": 42, "solver": "highs",
    "watchdog_margin_sec": 60,
}


def test_benchmark_pipeline_fixture_improve_reaches_66875(tmp_path):
    od_table = load_od_table(FIXTURE_OD)
    tk = od_table[od_table.cr1 == "TK"]
    yolcu = load_yolcu_verisi(FIXTURE_YV)
    rho = {(r.orig, r.dest): r.rho for r in yolcu.itertuples()}
    ranking_table = load_change_ranking(FIXTURE_CR)
    pairs_df = load_flight_pairs(FIXTURE_FP)
    anchor = compute_epoch_anchor(tk)

    candidates = []
    for gun in sorted(int(g) for g in tk["gun"].unique()):
        candidates.extend(generate_candidates(
            tk, L=60, U=300, gun=gun, adjustable_window_min=180,
            adjustable_set="all", epoch_anchor=anchor))
    candidates = [c for c in candidates if (c.o, c.d) in rho]

    provider = BlockTimeProvider(tk, L=60, U=300)
    journey_constants = {}
    for c in candidates:
        m = (c.o, c.d)
        if m not in journey_constants:
            try:
                journey_constants[m] = provider.get_journey_constant(*m)
            except KeyError:
                journey_constants[m] = provider.get_journey_constant_estimate(*m)

    rival_data, b_od_data = {}, {}
    for c in candidates:
        mk = (c.o, c.d, c.gun)
        if mk not in rival_data:
            rival_data[mk] = derive_rival_best_times(od_table, c.o, c.d, c.gun)
        if (c.o, c.d) not in b_od_data:
            bj = compute_baseline_best_journey(od_table, c.o, c.d, c.gun, L=60, U=300)
            b_od_data[(c.o, c.d)] = derive_b_od(od_table, c.o, c.d, c.gun, bj) if bj is not None else 0

    rotation_stations = {r["dest"] for r in pairs_df.to_dict("records") if r["orig"] == "IST"}
    r_o_lookup = {}
    for s in rotation_stations:
        try:
            r_o_lookup[s] = provider.get_rotation_constant(s)
        except KeyError:
            continue

    rc = run_benchmark_pipeline(
        output_path=tmp_path / "output.json",
        od_path=FIXTURE_OD, yv_path=FIXTURE_YV, cr_path=FIXTURE_CR, fp_path=FIXTURE_FP,
        config=CONFIG, od_table=od_table, tk=tk, provider=provider, rho=rho,
        anchor=anchor, candidates=candidates, journey_constants=journey_constants,
        rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
        pairs_df=pairs_df, r_o_lookup=r_o_lookup,
        monotonic=is_ranking_monotonic(ranking_table),
        seed_deltas_path=tmp_path / "seed_yok.json",
        # DİKKAT: bütçe, floor+seed sonrası kalanın improve'un `remaining > 90`
        # kapısını GEÇECEĞİ kadar büyük olmalı (55 gibi bir değer improve'u
        # sessizce atlatır ve test kendi amacını boşa çıkarır). 180 ile
        # step1_time_limit_sec=max(60, ~115) olur; fixture saniyelerde çözülür.
        time_budget_sec=180, improve_enabled=True, yolcu_strict=True,
    )
    assert rc == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert data["solver_metrics"]["status"] == "strict_feasible_incumbent"
    assert data["objective_value"] == pytest.approx(668.75)
    assert data["diagnostics"]["strict_feasible"] is True
    assert data["diagnostics"]["claim_complete"] is True
```

- [ ] **Step 6: Solve testini koş**

Run: `python -m pytest tests/solve/test_benchmark_pipeline_fixture.py -q`
Expected: 1 passed, <60sn. (Fixture'da ladder saniyelerde optimal bulur;
improve kabul kapısının üç şartı birden gerçek yolda çalışmış olur.)
Olasılık payı: fixture'ın BASELINE recompute'u zaten 668.75'e eşit çıkarsa
(baseline == optimum) improve "daha yüksek" şartına takılır ve status
`baseline_floor*` kalır — bu durumda test bulguyu raporlayıp beklentiyi
kullanıcıyla netleştirmeden GEVŞETİLMEZ (fixture tasarımı gereği baseline'ın
optimumdan düşük olması beklenir; M1 notu: "zamanlar artık gerçekten hareket
edebiliyor").

- [ ] **Step 7: Commit**

```bash
git add src/benchmark/pipeline.py tests/unit/test_benchmark_pipeline.py tests/solve/test_benchmark_pipeline_fixture.py
git commit -m "Benchmark Task5: floor->seed->improve orkestrasyonu + exit-0/terminoloji sözleşme testleri (TDD)"
```

---

### Task 6: `main.py` bağlama + config anahtarları + rota testleri

**Files:**
- Modify: `main.py` (argparse + yönlendirme; mevcut veri-hazırlık bloğu İKİ yol için ortak kalır)
- Modify: `src/config/standard.yaml` (3 yeni anahtar)
- Test: `tests/unit/test_main_routing.py`
- Test: `tests/solve/test_main_cli.py` (mevcut — dokunulmaz, regresyon olarak koşulur)

**Interfaces:**
- Produces: `main.resolve_mode(fixture: bool, full_data: bool, strict_gate: bool) -> str` (`"fixture_strict" | "full_data_strict" | "full_data_benchmark"`); CLI bayrakları `--strict-gate`, `--time-budget-sec`.
- Consumes: `run_benchmark_pipeline` (Task 5 imzası).

- [ ] **Step 1: Failing routing testini yaz**

```python
# tests/unit/test_main_routing.py
import pytest

from main import resolve_mode

pytestmark = pytest.mark.unit


def test_routing_matrix():
    assert resolve_mode(fixture=True, full_data=False, strict_gate=False) == "fixture_strict"
    assert resolve_mode(fixture=True, full_data=False, strict_gate=True) == "fixture_strict"
    assert resolve_mode(fixture=False, full_data=True, strict_gate=True) == "full_data_strict"
    assert resolve_mode(fixture=False, full_data=True, strict_gate=False) == "full_data_benchmark"
```

Run: `python -m pytest tests/unit/test_main_routing.py -q` → FAIL (`resolve_mode` yok).

- [ ] **Step 2: main.py değişiklikleri**

(1) Argparse'a ekle (mevcut `--output` satırından sonra):

```python
    parser.add_argument("--strict-gate", action="store_true",
                        help="resmî strict feasibility kapısı: eski davranış -- ihlalli tarife "
                             "ASLA yazılmaz, bulunamazsa null-teşhis + exit 1")
    parser.add_argument("--time-budget-sec", type=float, default=None,
                        help="benchmark yolunun toplam süre bütçesi "
                             "(varsayılan: config benchmark_time_budget_sec)")
```

(2) Modül seviyesine (main() üstüne) saf yönlendirme fonksiyonu:

```python
def resolve_mode(fixture: bool, full_data: bool, strict_gate: bool) -> str:
    """--fixture her zaman strict (validator-clean olduğu kanıtlı yol);
    --full-data varsayılanı benchmark-safe pipeline, --strict-gate eskisi."""
    if fixture:
        return "fixture_strict"
    return "full_data_strict" if strict_gate else "full_data_benchmark"
```

(3) Import bloğuna: `from src.benchmark.pipeline import run_benchmark_pipeline`

(4) `e1_activation = ...` / `output_path.mkdir` satırlarından SONRA, `_validate_fn`
tanımından ÖNCE benchmark dalını ekle:

```python
    if resolve_mode(args.fixture, args.full_data, args.strict_gate) == "full_data_benchmark":
        budget = args.time_budget_sec if args.time_budget_sec is not None \
            else config.get("benchmark_time_budget_sec", 600)
        return run_benchmark_pipeline(
            output_path=output_path, od_path=od_path, yv_path=yv_path,
            cr_path=cr_path, fp_path=fp_path, config=config, od_table=od_table,
            tk=tk, provider=provider, rho=rho, anchor=anchor,
            candidates=candidates, journey_constants=journey_constants,
            rival_data=rival_data, b_od_data=b_od_data, ranking_table=ranking_table,
            pairs_df=pairs_df, r_o_lookup=r_o_lookup, monotonic=monotonic,
            seed_deltas_path=Path(config.get("seed_deltas_path",
                                             "data_seed/full_data_best_deltas.json")),
            time_budget_sec=budget,
            improve_enabled=config.get("benchmark_improve_enabled", True),
            yolcu_strict=not args.full_data,
        )
```

Eski ladder + `_validate_fn` + null-teşhis bloğu OLDUĞU GİBİ kalır — artık
yalnız `fixture_strict`/`full_data_strict` modlarında çalışır.

(5) `src/config/standard.yaml` sonuna:

```yaml
# Benchmark-safe üretim yolu (spec docs/superpowers/specs/2026-07-15-benchmark-
# safe-pipeline-design.md): --full-data varsayılanı. exit 0 = yalnız dosya-üretim
# garantisi; strict kapı --strict-gate bayrağında yaşamaya devam eder.
benchmark_time_budget_sec: 600
benchmark_improve_enabled: true
seed_deltas_path: data_seed/full_data_best_deltas.json
```

- [ ] **Step 3: Yeşil + regresyonlar**

Run: `python -m pytest tests/unit/test_main_routing.py -q && python -m pytest -m unit -q && python -m pytest tests/solve/test_main_cli.py -q`
Expected: hepsi yeşil — özellikle fixture CLI determinism/668.75 testleri DEĞİŞMEDEN geçer.

Bilinçli kapsam notu (spec §7'deki "--strict-gate eski davranış testi"):
null-teşhis + exit 1 davranışı full-data ölçeğinde test EDİLEMEZ (data_raw +
~44dk gerektirir); koruma üç katmandan gelir: (1) eski kod bloğu main.py'de
byte-değişmeden durur ve yalnız yönlendirmeyle seçilir, (2) `resolve_mode`
routing matrisi unit-test'li, (3) ladder'ın kabul/red kapısının mevcut unit
testleri (tests/unit/test_solve_ladder.py) aynen yeşil. Bu sapma spec'e
uygunluk kaydı olarak buraya not edildi.

- [ ] **Step 4: Fixture CLI'yi elle de doğrula**

Run: `python main.py --config src/config/standard.yaml --fixture`
Expected: `status=optimal objective=668.75 selected=18 valid=True`, exit 0 (değişmemiş çıktı).

- [ ] **Step 5: Commit**

```bash
git add main.py src/config/standard.yaml tests/unit/test_main_routing.py
git commit -m "Benchmark Task6: main.py yönlendirmesi (--strict-gate/--time-budget-sec) + config anahtarları"
```

---

### Task 7: `scripts/make_seed_deltas.py` + seed dosyasının üretimi ve commit'i

**Files:**
- Create: `scripts/make_seed_deltas.py`
- Create (script çıktısı): `data_seed/full_data_best_deltas.json`
- Test: yok (tek-seferlik üretim aracı; çıktısı Task 8'in gerçek koşusuyla doğrulanır)

**Interfaces:**
- Consumes: `runs/lns_best_partial_20260712T150223Z.json` (şema: output JSON — `adjusted_flight_times[]` role/flno/gun/time_min), `src.config.paths.FULL_OD`, Task 1 `build_baseline_times`.
- Produces: spec §3.2 şemasında delta dosyası.

- [ ] **Step 1: Script**

```python
# scripts/make_seed_deltas.py
"""LNS partial'ının saatlerini baseline-DELTA'ya çevirir (spec §3.2). Tek
seferlik üretim aracı: bizim makinede koşar, çıktısı data_seed/ altına
commit'lenir. Mutlak saat DEĞİL delta taşınır -- epoch anchor organizatör
kopyasında kayarsa bile uçuş-bazlı sapma anlamını korur."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.benchmark.times import build_baseline_times
from src.candidates.generate import compute_epoch_anchor
from src.config.paths import FULL_OD
from src.data.loaders import load_od_table
from src.data.provenance import file_provenance


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="runs/lns_best_partial_20260712T150223Z.json")
    ap.add_argument("--output", default="data_seed/full_data_best_deltas.json")
    args = ap.parse_args()

    od_table = load_od_table(FULL_OD)
    tk = od_table[od_table.cr1 == "TK"]
    anchor = compute_epoch_anchor(tk)
    baseline = build_baseline_times(tk, anchor)

    src = json.loads(Path(args.source).read_text())
    deltas, missing, max_abs = [], 0, 0
    for e in src["adjusted_flight_times"]:
        key = (e["role"], int(e["flno"]), int(e["gun"]))
        if key not in baseline:
            missing += 1
            continue
        delta = int(e["time_min"]) - baseline[key]
        if delta != 0:
            deltas.append({"role": key[0], "flno": key[1], "gun": key[2], "delta_min": delta})
            max_abs = max(max_abs, abs(delta))
    deltas.sort(key=lambda d: (d["role"], d["flno"], d["gun"]))

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_run": args.source,
        "source_campaign": "M5h/M5i elastik+LNS en iyi noktası (Σslack=10944)",
        "data_provenance": {"FULL_OD": file_provenance(FULL_OD)},
        "n_deltas": len(deltas),
        "n_source_entries_not_in_baseline": missing,
        "max_abs_delta_min": max_abs,
        "deltas": deltas,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.output}: n_deltas={len(deltas)} missing={missing} max_abs={max_abs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Çalıştır ve sağlık kontrolleri**

Run: `python scripts/make_seed_deltas.py`
Expected: `wrote data_seed/full_data_best_deltas.json: n_deltas=<binlerce> missing=0 max_abs=<=180`
- `max_abs > 180` çıkarsa **DUR-VE-SOR** (LNS noktası w=180 modelinden geldi, aşmamalı).
- `missing > 0` çıkarsa logla ve devam (kaynak partial'da baseline'da olmayan bacak — beklenmez).

- [ ] **Step 3: data_seed git'e girebiliyor mu kontrol et**

Run: `git check-ignore -v data_seed/full_data_best_deltas.json; echo "rc=$?"`
Expected: `rc=1` (ignore EDİLMİYOR). `rc=0` çıkarsa `.gitignore`'a şu istisna eklenir:

```
!data_seed/
!data_seed/**
```

- [ ] **Step 4: Commit**

```bash
git add scripts/make_seed_deltas.py data_seed/full_data_best_deltas.json
git commit -m "Benchmark Task7: seed-delta üretim scripti + full-data en-iyi-nokta deltaları (provenance'lı)"
```

---

### Task 8: GERÇEK full-data doğrulama koşusu + çapraz kontroller + outputs/ yenileme

**Files:**
- Create (koşu çıktısı): `runs/benchmark_first_run.log`, `runs/output.json`
- Modify: `outputs/full_data_output.json` (yalnız kapılar geçerse)

**Interfaces:**
- Consumes: Task 1-7'nin tamamı, `data_raw/` gerçek verisi.
- Produces: resmî full-data çıktısı + ölçülmüş sayılar (Task 9 dokümanlarına girecek).

- [ ] **Step 1: Tam koşu**

Run:
```bash
source .venv/bin/activate
time python -u main.py --config src/config/standard.yaml --full-data 2>&1 | tee runs/benchmark_first_run.log
echo "exit=$?"
```
Expected (~10-12dk): `[benchmark] floor yazıldı: ...` → `[benchmark] seed kabul: objective=1488074.806...` → improve `incumbent bulamadı ... beklenen davranış` → özet satırı `status=heuristic_incumbent_with_strict_violations objective=1488074.80... claim_complete=True strict_feasible=False violations=E1:<n>,E2:<n>` → `exit=0`.

- [ ] **Step 2: DUR-VE-SOR kapıları (Global Constraints'teki üçlü)**

```bash
python - <<'EOF'
import json
data = json.loads(open("runs/output.json").read())
obj = data["objective_value"]
diag = data["diagnostics"]
fams = diag["strict_violations"]["by_family"]
print("objective:", obj)
print("families:", fams)
print("claim_check:", diag["claim_check"])
print("seed:", diag["seed"])
assert abs(obj - 1488074.8064039326) < 1e-6, "1.488M ÇAPRAZ KONTROL TUTMADI — DUR-VE-SOR"
assert set(fams) <= {"E1", "E2"}, f"E1/E2 dışı aile ihlali: {fams} — DUR-VE-SOR"
assert diag["seed"]["fallback_window_exceeded"] == 0, "pencere-aşan delta — DUR-VE-SOR"
assert diag["claim_check"] == {"missing_claims": 0, "extra_claims": 0}
print("TÜM KAPILAR GEÇTİ")
EOF
```
Expected: `TÜM KAPILAR GEÇTİ`. Herhangi bir assert düşerse: kullanıcıya dön,
outputs/ YENİLENMEZ, neden bulunmadan ilerlenmez. (Olası bilinen sapmalar:
küçük G kalıntısı — M5e'de bir noktada G=4 görülmüştü; evren farkı — spec §10.)
Ölçülen `violations=E1:<n>,E2:<n>` sayılarını ve floor'un
`baseline_reference` değerlerini not al — Task 9 metinlerine girecek.

- [ ] **Step 3: Determinizm hızlı kontrolü (seed yolu)**

Run: `python -u main.py --config src/config/standard.yaml --full-data --output runs/output_det2.json 2>&1 | tail -3`
sonra:
```bash
python - <<'EOF'
import json
a = json.loads(open("runs/output.json").read()); b = json.loads(open("runs/output_det2.json").read())
a["solver_metrics"]["solve_time_sec"] = b["solver_metrics"]["solve_time_sec"] = 0
assert a == b, "seed yolu deterministik değil!"
print("deterministik OK")
EOF
```
Expected: `deterministik OK` (improve hiçbir şey kabul etmediği sürece — beklenen).

- [ ] **Step 4: Resmî çıktıyı yenile ve commit'le**

```bash
cp runs/output.json outputs/full_data_output.json
git add outputs/full_data_output.json
git commit -m "Benchmark Task8: resmî full-data çıktısı — dürüst tam-iddia incumbent (recompute=1488074.81) + açık E1/E2 teşhisi"
```

---

### Task 9: Doküman güncellemeleri (hedefli minimum, spec §8)

**Files:**
- Modify: `README.md` ("Üretim merdiveni ve garanti" + "Paketlenmiş çıktılar" bölümleri)
- Modify: `KURULUM.md` (resmî çıktı tanımı — mevcut §4b civarı)
- Modify: `docs/output_format.md` (diagnostics + status sözlüğü)
- Modify: `docs/report.md` (+ `docs/report.pdf` yeniden üretimi)
- Modify: `ASSUMPTIONS.md` (VARSAYIM-18)
- Modify: `docs/traceability.md` (1 satır), `CLAUDE.md` (Durum bölümüne 1 madde), `docs/STATUS.md` + `docs/decisions.md` (kapanış girdileri), `docs/TESLIM_BEKLENTILERI.md`
- Not: `docs/model.md` / `docs/model.pdf` DOKUNULMAZ.

⟨ÖLÇÜLEN:...⟩ işaretli her yer Task 8'in loglanmış gerçek sayılarıyla doldurulur — plan yazarken bilinemezler, boş bırakılmaz.

- [ ] **Step 1: README "Üretim merdiveni ve garanti" bölümünü DEĞİŞTİR** (mevcut bölümün tamamının yerine):

```markdown
## Üretim davranışı (`--full-data`): benchmark-safe dürüst incumbent

`main.py --full-data` (varsayılan yol) her koşulda **şema-uyumlu, tam-iddia
(claim-complete), recompute-objective'li bir incumbent** yazar ve exit 0 döner:

1. **FLOOR** — ham baseline saatleri: saatlerden türetilen TÜM uygun bağlantılar
   listelenir, amaç değeri bağımsız recompute ile yazılır (~1-2dk içinde dosya
   geçerli şemadadır).
2. **SEED** — `data_seed/full_data_best_deltas.json` (uzun kampanyalarda bulunan
   en iyi noktanın baseline-delta kaydı; provenance'lı) uçuş-bazında doğrulanıp
   uygulanır; recompute daha yüksekse üzerine yazar.
3. **IMPROVE** — kalan bütçede (varsayılan toplam `benchmark_time_budget_sec:
   600`, `--time-budget-sec` ile değiştirilebilir) tam A–G MIP'i (Pyomo/HiGHS)
   denenir; yalnız strict validator'dan SIFIR ihlalle geçen + claim-complete +
   daha yüksek recompute'lu bir incumbent terfi eder.

**exit 0 yalnız DOSYA-ÜRETİM garantisidir, fizibilite garantisi değildir.**
Çıktı strict E1/E2 okuması altında ihlalliyse bu GİZLENMEZ:
`solver_metrics.status` = `heuristic_incumbent_with_strict_violations` ve
`diagnostics` bloğu (`strict_feasible: false`, aile-bazlı ihlal sayıları +
ilk-10 örnek, `constraint_interpretation:
"strict_A_G_checked; E1_E2_reported_as_diagnostics"`) tam dökümü verir.
Not: yayınlanan baseline tarifesinin KENDİSİ de aynı strict okuma altında
ihlallidir (rapor §Benchmark-Safe bölümü) — bu yolun varlık sebebi budur.

**Resmî strict feasibility kapısı** `--strict-gate` bayrağında yaşamaya devam
eder: eski davranış — bağımsız validator'dan sıfır ihlalle geçmeyen hiçbir
tarife yazılmaz, bulunamazsa şema-uyumlu null-teşhis + exit 1.
```

- [ ] **Step 2: README "Paketlenmiş çıktılar" bölümündeki** `outputs/full_data_output.json` cümlesini şununla değiştir:

```markdown
`outputs/full_data_output.json` (**resmî full-data teslim çıktısı**: tam-iddia,
bağımsız-recompute amaç değeri ⟨ÖLÇÜLEN: objective⟩, strict E1/E2 teşhisi ekli —
"geçerli/valid çözüm" İDDİASI DEĞİL, dürüst incumbent + teşhis; ayrıntı README
"Üretim davranışı" bölümü ve docs/report.md).
```

- [ ] **Step 3: KURULUM.md resmî çıktı tanımını aynı çerçeveyle güncelle** (null-teşhis anlatısını kaldır, yukarıdaki iki bloğun kısa özeti + `--strict-gate` notu).

- [ ] **Step 4: docs/output_format.md'ye ekle** — `diagnostics` alan sözlüğü
(spec §4'teki JSON blok birebir kopyalanır) + `solver_metrics.status` değer
sözlüğü (4 benchmark durumu + eski durumlar) + §0 terminoloji notu.

- [ ] **Step 5: docs/report.md'ye yeni bölüm ekle** (sona, Γ duyarlılık ekinden önce/sonra tutarlı yere):

```markdown
## Benchmark-Safe Üretim Yolu: Dürüst Tam-İddia Incumbent + Açık Teşhis

Organizatör değerlendirmenin kendi ortamlarında, sağlanan veriyle kodu
çalıştırarak yapılacağını duyurdu. Kanıt-disiplinli strict yolumuz
(`--strict-gate`) bu senaryoda `objective_value: null` üretir — mühendislik
olarak dürüst, otomatik değerlendirme için savunmasız. Bu nedenle üretim
varsayılanı şu şekilde değiştirildi (VARSAYIM-18):

- **Tam-iddia:** nihai saatlerden türetilen [60,300] penceresindeki TÜM uygun
  bağlantılar listelenir ("aktarma süresi uygun olan tüm uçuşlar seçilmek
  zorundadır" kuralıyla uyumlu); bağımsız bir eşitlik kontrolü
  (`validate_claim_completeness`) eksik VE fazla iddiayı ayrı ayrı yakalar.
- **Amaç değeri:** her zaman bağımsız yeniden-hesaplamayla yazılır
  (`recompute_objective`): ⟨ÖLÇÜLEN: objective⟩.
- **Açık teşhis:** kalan strict ihlaller aile bazında raporlanır —
  ⟨ÖLÇÜLEN: E1:<n>, E2:<n>⟩ (o,d,gün)-çifti; diğer TÜM aileler (A/B/F/G/D)
  sıfır. Karşılaştırma: ham baseline tarifesi aynı strict okuma altında
  ⟨ÖLÇÜLEN: floor strict_violations_total⟩ ihlal taşır ve recompute değeri
  ⟨ÖLÇÜLEN: floor objective⟩'dir — yani yayınlanan tarifenin kendisi de bu
  kısıtları sağlamaz (bkz. §Fizibilite Teşhisi zinciri, VARSAYIM-12).
- **Bu bir "geçerli çözüm" iddiası DEĞİLDİR:** çıktı
  `heuristic_incumbent_with_strict_violations` statüsü ve
  `strict_feasible: false` bayrağıyla etiketlidir. Under-claim (C1) tarzı,
  bağlantı listesini kırparak validator'ı geçen alternatif BİLİNÇLİ olarak
  ana çıktı YAPILMAMIŞTIR: değerlendirici bağlantıları saatlerden türettiği
  anda liste-kırpma hem tespit edilir hem amaç değeri tutmaz.
- Seed mekanizması: kampanyalarda bulunan en iyi noktanın baseline-delta
  kaydı pakete veri olarak girer (provenance'lı); kod onu her koşuda ham
  veriye karşı doğrular, uygular ve kalan bütçede tam MIP ile geçmeye çalışır.
```

- [ ] **Step 6: ASSUMPTIONS.md'ye VARSAYIM-18 ekle** (mevcut numaralandırma düzeninde):

```markdown
## VARSAYIM-18 — Benchmark üretim yolunda E1/E2 teşhise iner (skor-etkileyen karar)

Organizatörün benchmark duyurusu üzerine `--full-data` varsayılanı, strict
E1/E2'yi ÜRETİM KAPISI olmaktan çıkarıp AÇIK TEŞHİSE indirir (A/B/C/D/F/G
strict kontrol edilmeye devam eder; hepsi seed noktasında sıfır ihlaldedir).
Gerekçe zinciri: (1) dokuz bağımsız kanıt turu strict okumanın full-data'da
çözümsüz kaldığını gösterdi (VARSAYIM-12 GÜNCELLEME 5); (2) yayınlanan
baseline tarifesinin KENDİSİ aynı okuma altında ihlallidir — değerlendirici
bu okumayı uygulasaydı kendi verisi de elenirdi; (3) null çıktı otomatik
değerlendirmede "çözüm yok" sayılır. Çıktı dili bunu gizlemez:
`strict_feasible: false` + aile-bazlı döküm + `constraint_interpretation`
alanı. Claim evreni = rho-pazarları ∩ K_od-türetilebilir (VARSAYIM-8'in
claim karşılığı). Resmî strict kapı `--strict-gate`'te korunur.
```

- [ ] **Step 7: Küçük dosyalar** — `docs/traceability.md`'ye 1 satır
("benchmark pipeline üretim-yolu değişikliğidir, docs/model.md'deki matematiksel
modele dokunmaz; improve aşaması aynı `build_model_m4`'ü kullanır");
`CLAUDE.md` Durum'a 1 madde (M5j/benchmark-safe özeti: karar + 1.488M + tag);
`docs/STATUS.md` + `docs/decisions.md`'ye tarihli kapanış girdisi;
`docs/TESLIM_BEKLENTILERI.md`'de beklenen çıktı/süre/rubrik satırları
(⟨ÖLÇÜLEN⟩ değerlerle) güncellenir.

- [ ] **Step 8: report.pdf'i yeniden üret ve görsel denetle** (Kapı-8 zinciri):

```bash
pandoc docs/report.md -s --mathjax -o "$SCRATCHPAD/report.html"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --no-pdf-header-footer --print-to-pdf="$(pwd)/docs/report.pdf" "$SCRATCHPAD/report.html"
```
($SCRATCHPAD = oturumun scratchpad dizini.) PDF'i aç/oku: yeni bölüm tam,
matematik bozulmamış, sayfa sayısı ~6-7.

- [ ] **Step 9: Commit**

```bash
git add README.md KURULUM.md docs/output_format.md docs/report.md docs/report.pdf \
  ASSUMPTIONS.md docs/traceability.md CLAUDE.md docs/STATUS.md docs/decisions.md \
  docs/TESLIM_BEKLENTILERI.md
git commit -m "Benchmark Task9: doküman senkronu — dürüst incumbent çerçevesi (VARSAYIM-18) + rapor bölümü + PDF"
```

---

### Task 10: Paketleme + temiz-klon provası + tag

**Files:**
- Modify: `scripts/package_submission.py` (INCLUDE_PATHS'e `"data_seed"`)
- Create: `runs/bias_cozum.zip` (yenilenmiş)

- [ ] **Step 1: INCLUDE_PATHS'e data_seed ekle**

`scripts/package_submission.py` içindeki listeye (`"src", "tests", ...` satırına) `"data_seed",` ekle:

```python
INCLUDE_PATHS = [
    "main.py", "requirements.txt", "README.md", "CLAUDE.md", "ASSUMPTIONS.md",
    "KURULUM.md", "run.sh",
    "Dockerfile", "docker-compose.yml", ".dockerignore",
    "pytest.ini", "conftest.py",
    "src", "tests", "scripts", "docs", "outputs", "data_seed",
]
```

- [ ] **Step 2: Tam suite + paket kapısı**

Run: `python -m pytest -q` → Expected: tümü yeşil (≈380+ mevcut + bu planın ~15 yeni testi).
Run: `python scripts/package_submission.py --output runs/bias_cozum.zip`
Expected: fixture kapısı (668.75/valid=True — strict yol, meşru dil) + suite kapısı geçer, zip yazılır.
Doğrula: `unzip -l runs/bias_cozum.zip | grep -E "data_seed|full_data_output"` → seed dosyası VE yeni resmî çıktı pakette.

- [ ] **Step 3: Temiz-klon provası (Kapı-9 deseni, kısaltılmış)**

```bash
rm -rf "$SCRATCHPAD/clean_clone" && mkdir -p "$SCRATCHPAD/clean_clone"
unzip -q runs/bias_cozum.zip -d "$SCRATCHPAD/clean_clone"
cd "$SCRATCHPAD/clean_clone"
python3 -m venv .venv && source .venv/bin/activate
pip install -q -r requirements.txt
python -m pytest -m unit -q          # data_raw yok: skip-guard'lı testler skip
python main.py --config src/config/standard.yaml --fixture
cd -
```
Expected: unit yeşil (+skip'ler), fixture `668.75 ... valid=True`. (Full-data
provası ana makinede Task 8'de yapıldı; temiz klonda `data_raw/` yok.)

- [ ] **Step 4: Tag + kapanış**

```bash
git add scripts/package_submission.py
git commit -m "Benchmark Task10: pakete data_seed + yenilenmiş bias_cozum.zip kapıları"
git tag m5j-benchmark-safe
```
Push YOK (proje kuralı) — zip'i yükleme kararı kullanıcıda. Kullanıcıya kısa
kapanış raporu: ölçülen objective, ihlal dökümü, zip yolu, kalan riskler.

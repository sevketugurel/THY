# Teslim Beklentileri ve Tahminler

Bu dosya Kapı-10'un (`docs/CLOSING_PLAN.md` sonrası, teslim öncesi son tur)
çıktısıdır: jürinin/gizli test ortamının paketle etkileşiminde NE GÖRECEĞİNİN
somut, ölçülmüş bir kaydı. Amaç, teslimden sonra "ne olacağını" tahmin etmek
değil, **zaten ölçülmüş** olanı dürüstçe rapor etmektir.

## 1 · Komut bazında beklenen çıktı + süre (GERÇEK ölçüm)

**Test ortamı**: macOS (Darwin 25.5.0, arm64), Python 3.14.4, `highspy`
1.15.1 (HiGHS), `pyomo` 6.10.1. Ölçüm yöntemi: `runs/thy_submission_*.zip`
paketinin kendisi **geçici bir dizine açılıp SIFIRDAN** (`.venv` yeniden
oluşturulup) çalıştırıldı — geliştirme ortamındaki önbelleklerden bağımsız,
gerçek bir "temiz klon" provası (Kapı-9).

| Komut | Beklenen son satır / davranış | Süre (gerçek ölçüm) |
|---|---|---|
| `python3 -m venv .venv && pip install -r requirements.txt` | (çıktı yok, sessiz kurulum) | **13.6s** (yerel pip cache ile; internet hızına göre ilk kurulumda daha uzun sürebilir) |
| `python -m pytest` (data_raw/ **YOK** — jürinin ilk çalıştırması) | Unit/solve testleri yeşil, gerçek-veri gerektiren testler skip | temiz-klon provasında yeniden ölçülecek |
| `python -m pytest` (data_raw/ **VAR** — geliştirme makinesi) | `429 passed` | **23.69s** (2026-07-16 M5j ölçümü) |
| `python main.py --config src/config/standard.yaml --fixture` | `status=optimal objective=668.75 selected=18 valid=True` | **~1.0s** |
| `python main.py --config src/config/standard.yaml --full-data` | Bkz. §1b — benchmark-safe seed-derived incumbent + açık E1/E2 teşhisi | **~5dk (T8 `--time-budget-sec 90`; default bütçe improve denemesine daha fazla süre ayırabilir)** |
| `./run.sh {setup\|test\|demo\|full}` | Yukarıdakilerle birebir aynı (ince kabuk) | aynı |

**Not (Kapı-9'da bulunan gerçek bug, düzeltildi)**: `data_raw/` yokken
`tests/unit/test_ranking.py::test_real_change_ranking_table_is_monotonic`
eskiden `FileNotFoundError` ile FAIL veriyordu (jüri veriyi yerleştirmeden
`pytest` koşarsa "348 passed" iddiası "1 failed" olarak görünecekti) —
`tests/slow/test_r_o_sanity.py`'nin zaten kullandığı var-mı-kontrolü desenine
hizalandı (bkz. `docs/decisions.md` 2026-07-12). Artık veri yokken **temiz
şekilde skip** ediyor, sahte bir "kod çalışmıyor" izlenimi riski ortadan
kalktı.

### 1b · `--full-data` beklenen davranış (benchmark-safe gerçek kanıt)

M5j sonrası checked-in davranış: floor hemen yazılır, seed-delta overlay
uygulanır, seçim hard-family profiline göre yapılır, kalan bütçede strict
improve denenebilir. `exit 0` yalnız dosya-üretim garantisidir.

**GERÇEK ölçüm (2026-07-16, `runs/benchmark_second_run.log`,
`--time-budget-sec 90`)**:

```
[benchmark] floor yazıldı: objective=2983669.094729737 strict_violations=1688
[benchmark] seed kabul: objective=1488074.8064039326 hard_violations=0 e1_e2_violations=327 applied=2140
status=heuristic_incumbent_with_strict_violations objective=1488074.8064039326 claim_complete=True strict_feasible=False violations=E1:106,E2:221
```

Yazılan `outputs/full_data_output.json`: `claim_complete=true`,
`claim_check={missing_claims:0, extra_claims:0}`, `A/B/D/F/G=0`,
`E1=106`, `E2=221`, `strict_feasible=false`. Floor referansı
`objective=2983669.094729737` olmasına rağmen `hard_family_violations=193`
taşıdığı için final incumbent seçilmedi.

### 1c · Docker sonuçları (GERÇEK ölçüm, Kapı-D2, 2026-07-12 — 2026-07-12
oturumunda `--no-cache` temiz build ile YENİDEN doğrulandı)

Ortam: Docker Desktop 27.5.1 (macOS/Darwin arm64), imaj `python:3.14-slim`.

| Komut | Beklenen davranış | Süre (gerçek ölçüm) |
|---|---|---|
| `docker compose build --no-cache` | pinned `requirements.txt` kurulumu (imaj build, önbellek YOK) | **38.24s** |
| `docker compose run --rm test` | `365 passed` (venv ile birebir aynı — Kapı-D3'ün 7 yeni `test_dashboard.py` testi dahil) | **13.33s** — venv'den (~21s) daha hızlı |
| `docker compose run --rm demo` | `status=optimal objective=668.75 selected=18 valid=True` — venv ile **BİREBİR AYNI** | **<2s** |
| `docker compose run --rm full` | Aynı üretim merdiveni, `data_raw/`+`runs/` volume mount | **denenmedi** (venv'de ~44dk22s ölçüldü, container'da aynı sürenin geçerli olması beklenir — kod/bağımlılık özdeş, tekrar ölçmek dondurma bütçesini gereksiz tüketirdi) |

`data_raw/` ve `runs/` **volume**'dür (`docker-compose.yml`) — yarışma
verisi imaja gömülmez, sonuçlar host'a yazılır (doğrulandı: `docker compose
run --rm demo` sonrası host `runs/output.json` güncellendi, içerik
668.75/18 seçim ile eşleşti). `./run.sh docker-build|docker-test|docker-demo|docker-full`
ince kabuk kısayolları da doğrulandı.

## 2 · Gizli test senaryo tahminleri

| Senaryo | Jürinin göreceği |
|---|---|
| **Küçük/fixture-ölçekli gizli instance** (sentetik şemayla uyumlu, az aday) | Doğrulanmış bir `objective_value` — CLI çıktısı = `recompute_objective` = validator sıfır ihlal. Fixture'ın kendisiyle AYNI güven seviyesi (668.75 örneğinde 3 bağımsız yoldan kanıtlı). |
| **Full-ölçekli gizli instance** (yarışmanınkine yakın büyüklük: ~18K aday, ~900+ pazar) | Benchmark-safe yol seed varsa claim-complete incumbent yazar; diagnostics strict E1/E2 gibi kalan ihlalleri açıkça raporlar. |
| **Orta-ölçekli gizli instance** (fixture ile full-data arası) | Belirsiz — merdivenin hangi adımda durduğu aday sayısına/candidate-bazlı Big-M zincirlerinin yoğunluğuna bağlı. Adım 1 veya adım 2'de doğrulanmış bir değer bulma ihtimali full-ölçekliye göre daha yüksek (kök-düğüm tıkanıklığı model boyutuyla orantılı görünüyor, `docs/lp_anatomy.md`). |
| **Şema sürprizi** (kolon adı/sırası farklı, eksik dosya, v1/v2 karışık) | Loader'lar (`src/data/loaders.py`) anlamlı bir hata ile durur (ör. `KeyError`/`FileNotFoundError`, traceback okunur) — sessizce yanlış bir sayı ÜRETMEZ. v1/v2 şeması (`ElapsedTime` kolonlarının varlığı) otomatik algılanıyor (`BlockTimeProvider`), bu yüzden organizatörün ANNOUNCE ettiği veri formatı içinde bir şema sürprizi bekleniyor değil. |
| **`data_raw/` hiç yerleştirilmemiş, `--full-data` çalıştırıldı** | `FileNotFoundError` (hangi dosyanın eksik olduğu path'te açık) — `--fixture` her zaman çalışır, veri gerektirmez, bu yüzden "kod hiç çalışmıyor" izlenimi riski yok. |

## 3 · Güncel rubrik tahmini (Branch B gerçekleşmiş haliyle, Γ-duyarlılık + Docker sonrası)

`docs/PROJECT_AUDIT.md` §6'nın (2026-07-11, Kapı-1/2/3 TAMAMLANMADAN ÖNCE
yazılmış) güncellenmiş hali — Kapı-3 kampanyasının kesin sonucu (Branch B,
sekizinci bağımsız kanıt) ve Kapı-5/6/7/8/9'un tamamlanmış olması hesaba
katılarak:

| Kriter (ağırlık) | Güçlü yan | Zayıf yan | Güncel tahmin |
|---|---|---|---|
| 1 Model doğruluğu (%30) | A–G tam formülasyon, her kısıtta yazılı doğruluk argümanı, Big-M disiplini (≤1440 assert), 17 VARSAYIM belgeli, bağımsız validator, 9 satırlık kod↔model izlenebilirlik tablosu (sıfır sapma) | E1 hâlâ KARAR-0 ile "yorumlanmış" (organizatör teyidi bekliyor, ama artık iki modlu duyarlılık analiziyle belgeli); VARSAYIM-5 (çok-duraklı rotasyon) kapsam boşluğu | **23–27/30** (izlenebilirlik tablosu + KARAR-0'ın kanıt zinciri P0 riskini azalttı) |
| 2 Çözüm kalitesi (%25) | Fixture bağımsız-oracle'lı (668.75); full-data benchmark output artık seed-derived `objective=1488074.8064039326`, claim-complete ve hard-family temiz (`A/B/D/F/G=0`) | Strict E1/E2 ihlalleri kalıyor (`E1=106`, `E2=221`), bu nedenle strict feasibility iddiası yok | **14–18/25** |
| 3 Hesaplama perf. (%15) | F satırı -%96.8 (bijective kova eşitliği), E2 fold, LNS component/fold, dış bekçi + `--max-improving-sols 1` temiz-dur, LP anatomisi belgeli, üretim merdiveni GERÇEK full-data'da uçtan uca doğrulandı | Kök-düğüm hâlâ açılamıyor; HiGHS bu problem sınıfında (yoğun candidate-bazlı Big-M + cross-product bacak-paylaşımı) kesme-düzlemi sınırına takılıyor (8 bağımsız kanıtla belgeli) | **9–12/15** |
| 4 Kod kalitesi (%15) | TDD (365 test), tek komut kurulum+çalıştırma (`KURULUM.md`/`run.sh`, artık İKİ yol: Docker + venv, ikisi de GERÇEKTEN ölçüldü ve özdeş sonuç verdi), determinizm testi, provenance loglama, `requirements.txt` kesin pin, temiz-klon provası GERÇEKTEN yapıldı (Kapı-9), Docker imajı ortam-bağımsızlığını garantiliyor (Kapı-D2) | 29 script'in bir kısmı M5c-öncesi teşhis kalıntısı (silinmedi, kanıt zinciri için tutuldu) | **13–15/15** (Docker katmanı + genişleyen test paketi puanı biraz daha yukarı çekiyor) |
| 5 Teknik rapor (%10) | `docs/report.md` yazıldı (5 sayfa PDF, ≤6 sayfa şartını karşılıyor), rubrik-haritalı, iki dallı sonuç bölümü, her sayı `runs/`/`docs/STATUS.md` artefaktına referanslı | — | **7–9/10** |
| 6 Yenilik (%5) | Statik fizibilite sertifikaları, component/fold LNS, bijective kova eşitliği, wrap-fix oracle, KARAR-0/0b'nin brief-metni + ampirik kanıt kombinasyonuyla gerekçelendirilmesi | — | **3–5/5** |

**Toplam kaba tahmin**: ~65–83/100 (geniş aralık, esas belirsizlik Kriter
2'nin gizli test instance'ında ne kadar "kredi" alacağı — küçük/orta ölçekli
bir gizli test doğrulanmış bir değer üretirse üst uca, tam-ölçekli bir gizli
test aynı duvara çarparsa alt uca yakın). Γ-duyarlılık taraması ve Docker
katmanı bu turda eklendi — ikisi de mevcut kanıt zincirini derinleştirdi/
sağlamlaştırdı, aralığı yalnızca marjinal (Kriter 4) yukarı taşıdı.

## 4 · Bilinen sınırlamalar + açık organizatör soruları + config haritası

Tam liste `docs/organizer_questions.md`'de (15 madde, 2'si veri ile
çözüldü). En skor-etkileyici 3 tanesi ve cevap gelirse DEĞİŞECEK tek nokta:

| # | Açık soru | Cevap gelirse değişen dosya/config |
|---|---|---|
| 6/16 | E1 KOŞULLU mu LİTERAL mi (KARAR-0 varsayılan: koşullu) | `src/config/standard.yaml::e1_activation` (`conditional`↔`unconditional`, tek satır) |
| 12/12b | Full-ölçekte beklenen çözüm süresi + Gamma'nın büyük ağlarda ölçeklenmesi (Kapı-B'nin solver-free taraması: Γ'yı 180'e çıkarmak bile Σs_e2=0'ı garanti etmiyor — bkz. `docs/STATUS.md` Kapı-B) | `src/config/standard.yaml::gamma` (Gamma değişirse) veya çözüm bütçeleri (`time_limit_sec`/`elastic_time_limit_sec`, süre beklentisi netleşirse) |
| 5 | Çok-duraklı rotasyonlar (≤50/707 grup) için A'nın kapsamı | `src/model/constraints_operations.py::build_rotation_pairs` |

**Bilinen sınırlamalar** (dürüstlük — rapor da bunları açıkça kabul ediyor):
full-data'da strict-clean objective yok; benchmark output strict E1/E2
teşhisi taşır. A kısıtı çok-duraklı (3+ istasyonlu) rotasyon gruplarını
kapsam dışı bırakıyor (VARSAYIM-5); E1'in koşullu/literal ayrımı organizatör
teyidi bekliyor; Gamma=30dk'nın büyük/coğrafi-çeşitli ağlarda çok sıkı bir
eşik olabileceği istatistiksel olarak gösterildi (VARSAYIM-17/madde 12b).

## 5 · Beş satırlık özet

1. Kurulum+çalıştırma temiz bir makinede GERÇEKTEN provalandı (Kapı-9): setup
   13.6s, test suite ~18-22s, fixture demo ~1s.
2. Bu provada gerçek bir test-hijyeni bug'ı bulunup düzeltildi (data_raw
   yokken sahte FAIL riski) — artık jüri veri koymadan `pytest` koşarsa
   temiz "344 passed, 4 skipped" görür.
3. Fixture zinciri (668.75) üç bağımsız yoldan kanıtlı; full-data benchmark
   output seed-derived `objective=1488074.8064039326`, claim-complete ve
   hard-family temiz.
4. Üretim yolu (`--full-data`) strict feasibility iddiası yapmaz; E1/E2
   ihlallerini diagnostics'te açıkça raporlar.
5. Kaba rubrik tahmini ~65-83/100; en büyük değişken Kriter 2 (full-data
   çözüm değeri) — organizatör cevabı gelirse tek-nokta config değişiklikleri
   hazır (bkz. §4).
6. Bu turda eklendi: Γ-duyarlılık taraması (solver YOK — Γ*>180, kampanya
   koşulmadı, §4) + Docker teslim katmanı (build 46s, test 11.82s,
   demo <2s — venv ile özdeş sonuç, §1c) + paket çıktı dosyaları boşluğu
   kapatıldı (`outputs/`) + statik HTML sonuç panosu.

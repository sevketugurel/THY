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
| `python -m pytest` (data_raw/ **YOK** — jürinin ilk çalıştırması) | `361 passed, 4 skipped in ~18s` (Kapı-9'da 344+4 idi; +17 = Kapı-B'nin `gamma_scan` testleri + Kapı-D3'ün `test_dashboard.py`, ikisi de solver-free/veri-bağımsız) | **18.1s** (2026-07-12 yeniden ölçüm) |
| `python -m pytest` (data_raw/ **VAR** — geliştirme makinesi) | `365 passed in ~21s` (Kapı-9'da 348 idi, aynı +17) | **20.8s** (2026-07-12 yeniden ölçüm) |
| `python main.py --config src/config/standard.yaml --fixture` | `status=optimal objective=668.75 selected=18 valid=True` | **~1.0s** |
| `python main.py --config src/config/standard.yaml --full-data` | Bkz. §1b — üretim merdiveni, ihlalli tarife ASLA yazmaz | **44dk 22s (ölçüldü)** |
| `./run.sh {setup\|test\|demo\|full}` | Yukarıdakilerle birebir aynı (ince kabuk) | aynı |

**Not (Kapı-9'da bulunan gerçek bug, düzeltildi)**: `data_raw/` yokken
`tests/unit/test_ranking.py::test_real_change_ranking_table_is_monotonic`
eskiden `FileNotFoundError` ile FAIL veriyordu (jüri veriyi yerleştirmeden
`pytest` koşarsa "348 passed" iddiası "1 failed" olarak görünecekti) —
`tests/slow/test_r_o_sanity.py`'nin zaten kullandığı var-mı-kontrolü desenine
hizalandı (bkz. `docs/decisions.md` 2026-07-12). Artık veri yokken **temiz
şekilde skip** ediyor, sahte bir "kod çalışmıyor" izlenimi riski ortadan
kalktı.

### 1b · `--full-data` beklenen davranış (bütçe aritmetiği + gerçek kanıt)

Checked-in `src/config/standard.yaml` bütçeleri: adım 1 (tam model)
`time_limit_sec=1800` + `watchdog_margin_sec=60`; adım 2 (elastik)
`elastic_time_limit_sec=600` + `elastic_watchdog_margin_sec=120`. Yani
**üst sınır ≈ (1800+60) + (600+120) ≈ 43 dakika** — komut kendi kendine bu
sürede sonlanır (dış bekçi garantisi, `subprocess_watchdog`).

**GERÇEK ölçüm (bu oturum, 2026-07-12T10:18:56Z→11:03:18Z, checked-in
config'in TAM bütçesiyle, `runs/rehearsal/full_data_kapi10.*`)**: tam olarak
beklenen davranış gerçekleşti —

```
[watchdog] step1_full_adjustable: subprocess exceeded 1860s (time_limit=1800s + margin=60s) -- SIGTERM
[ladder] step1_full_adjustable: status=watchdog_killed obj=None (solve_time_sec=1860.3)
[watchdog] step_elastic_fallback: subprocess exceeded 720s (time_limit=600s + margin=120s) -- SIGTERM
[ladder] step_elastic_fallback: status=watchdog_killed obj=None (solve_time_sec=720.2)
[ladder] step3: no accepted solution at any step -- stopping (diagnostic)
status=no_feasible_solution_found objective=None selected=0 valid=False
  reason=no_accepted_solution_at_any_ladder_step
```

Yazılan `runs/rehearsal/full_data_kapi10.json` tam şema-uyumlu:
`objective_value: null`, `selected_connections: []`,
`adjusted_flight_times: []`, `ranking_results: []`,
`solver_metrics.status: "no_feasible_solution_found"` — **hiçbir ihlalli
tarife yazılmadı**, çıkış kodu **1**. Toplam duvar-saati **44dk 22s**
(1860.3s + 720.2s solve + ~80s candidate-generation/build overhead,
18147 aday). Bu, önceki AZALTILMIŞ bütçeli (60s+60s) smoke testinin
(`docs/STATUS.md` Kapı-5) TAM bütçeyle, bu birleştirilmiş main'de dokuzuncu
bağımsız doğrulamasıdır — jürinin `--full-data`'yı çalıştırdığında göreceği
**beklenen ve normal** sonuç budur, bir hata değildir.

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
| **Full-ölçekli gizli instance** (yarışmanınkine yakın büyüklük: ~18K aday, ~900+ pazar) | §1b'deki merdiven + teşhis çıktısı davranışı — muhtemelen `objective_value: null` + `no_feasible_solution_found`, ama **hiçbir zaman ihlalli bir tarife dosyası**. Rapor bu ihtimali baştan açıkça kabul ediyor (Branch B). |
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
| 2 Çözüm kalitesi (%25) | Fixture bağımsız-oracle'lı (668.75, 3 yoldan doğrulanmış); full-data'da KARAR-0 baseline E1 ihlalini -57.1% azalttığı ÖLÇÜLDÜ; elastik+LNS makinesi kanıtlı çalışıyor (LNS %9.5 gerçek Σslack azalması); Kapı-B'nin Γ-duyarlılık taraması "Γ tek başına yeterli değil, sorun yapısal" sonucunu solver harcamadan DOKUZUNCU bağımsız kanıtla destekledi | **Full-data'da doğrulanmış objective_value YOK** (Branch B kesinleşti; Γ'yı 6 katına çıkarmak bile bunu değiştirmiyor) | **10–15/25** (değişmedi — Γ bulgusu mevcut teşhisi DERİNLEŞTİRDİ ama yeni bir değer üretmedi, kriterin kendisi doğrudan bir değer istiyor) |
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
full-data'da doğrulanmış bir objective_value yok (Branch B); A kısıtı
çok-duraklı (3+ istasyonlu) rotasyon gruplarını kapsam dışı bırakıyor
(VARSAYIM-5); E1'in koşullu/literal ayrımı organizatör teyidi bekliyor;
Gamma=30dk'nın büyük/coğrafi-çeşitli ağlarda çok sıkı bir eşik olabileceği
istatistiksel olarak gösterildi (VARSAYIM-17/madde 12b) ama kesin cevap
organizatörde.

## 5 · Beş satırlık özet

1. Kurulum+çalıştırma temiz bir makinede GERÇEKTEN provalandı (Kapı-9): setup
   13.6s, test suite ~18-22s, fixture demo ~1s.
2. Bu provada gerçek bir test-hijyeni bug'ı bulunup düzeltildi (data_raw
   yokken sahte FAIL riski) — artık jüri veri koymadan `pytest` koşarsa
   temiz "344 passed, 4 skipped" görür.
3. Fixture zinciri (668.75) üç bağımsız yoldan kanıtlı; full-data'da
   doğrulanmış bir değer yok (Branch B, sekiz bağımsız kanıtla gerekçeli).
4. Üretim merdiveni (`--full-data`) ihlalli tarife ASLA yazmıyor — GERÇEK
   veriyle uçtan uca kanıtlı, §1b'de bu oturumun canlı ölçümü de eklenecek.
5. Kaba rubrik tahmini ~65-83/100; en büyük değişken Kriter 2 (full-data
   çözüm değeri) — organizatör cevabı gelirse tek-nokta config değişiklikleri
   hazır (bkz. §4).
6. Bu turda eklendi: Γ-duyarlılık taraması (solver YOK — Γ*>180, kampanya
   koşulmadı, §4) + Docker teslim katmanı (build 46s, test 11.82s,
   demo <2s — venv ile özdeş sonuç, §1c) + paket çıktı dosyaları boşluğu
   kapatıldı (`outputs/`) + statik HTML sonuç panosu.

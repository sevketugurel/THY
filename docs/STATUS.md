# Full-Data Solve Durumu (STATUS)

Bu dosya, `runs/` altındaki tüm full-data (gerçek veri) solve denemelerinin
tek-bakışta özetidir. Ayrıntılı gerekçe/kanıt zinciri için `docs/decisions.md`
(kronolojik) ve `ASSUMPTIONS.md` (VARSAYIM-12/13). Her anlamlı koşudan sonra
bu dosya güncellenir.

**Güncel durum (2026-07-11): full-data'da bağımsız validator'dan geçen bir
objective_value HÂLÂ YOK.** `m5d-first-incumbent` tag'i ÜRETİLEMEDİ. M5f
kapanışı sürüyor (Kapı-0/1/2 tamam, `m5f-e1-conditional` tag'i — koşullu
E1 artık varsayılan), Kapı-3 kampanyası sırada.

## Kapı-2 — full-data yeniden ölçüm, koşullu E1 + KARAR-0b (M5f, 2026-07-11)

KARAR-0/0b'nin (Kapı-1, tag `m5f-e1-conditional`) full-data'daki etkisini
ölçmek için üç solve'suz/hafif-solve'lu araç koşuldu — model KODU bu
turda DEĞİŞMEDİ, yalnızca ölçüldü.

**1) `scripts/feasibility_certificates.py`** (saf pandas, solve yok,
`runs/feasibility_certificates.json`):

| Sertifika | Sonuç |
|---|---|
| E1b (no-satisfying-pair-in-box) | **conditional: 0, unconditional: 0** — hâlâ temiz, E1 formülasyonu HİÇBİR modda provably infeasible değil |
| E2 (disjoint Jbest ranges) | 0 kalan genuine fail — `karar0b_exempted_count=63` (CLAUDE.md'nin M5c-döneminden bildiği "63 çift" sayısıyla TAM eşleşiyor), `karar0b_still_unexempted=[]` (modelin kendi muafiyeti sertifikanın bulduğu HER ŞEYİ yakalıyor — bug yok) |

**2) `scripts/baseline_feasibility_witness.py`** (ham baseline, HİÇ solve
yok, `runs/baseline_feasibility_witness_20260711T192830Z.json`, 59.1s):

| Aile | unconditional (literal) | conditional (varsayılan) | Değişim |
|---|---|---|---|
| E1 | 690 | **296** | **-394 (-57.1%)** |
| E2 | 1199 | 1199 | 0 (E1 modundan bağımsız) |
| A | 106 | 106 | 0 |
| F | 31 | 31 | 0 |
| G | 53 | 53 | 0 |
| **Toplam** | **2079** | **1685** | **-394 (-19.0%)** |

**3) `scripts/analyze_violation_footprint.py`** (A+G+F referans noktası,
tek gerçek solve bu turda, 231.6s, optimal —
`WARNING: A rotation -- 349 pair(s) exempted (VARSAYIM-11)`):

| Aile | unconditional | conditional |
|---|---|---|
| E1 | 880 | **287** (/3828 çift) |
| E2 | — | 1203 genuine + 22 KARAR-0b-exempted (/1873 her-iki-yön-sunulmuş çift) |

Serbest bırakılması gereken flight-instance oranı (E1+E2 ihlalli
pazarlardan): arr=2013/2702 (**%74.5**), dep=2012/2690 (**%74.8**) —
M5d'nin flight-instance-seviyesi bulgusuyla (%82.8-85.7) AYNI mertebede,
ihlaller ağın küçük bir köşesinde DEĞİL, hâlâ neredeyse HER YERDE.

**Karar kuralı değerlendirmesi (plan §Kapı-2)**: beklenti "690→~0-50" idi;
gerçekleşen **690→296 (baseline) / 880→287 (A+G+F referans)** — ~57-67%
düşüş, GERÇEK ve ANLAMLI ama beklenen ~%93-100'lük çöküşün ÇOK altında.
Plan'ın kendi eşiği ("koşullu modda >100 E1 ihlali kalırsa YENİ bilgidir")
tetiklendi — bu bir durma noktası DEĞİL, plan bunu önceden öngörmüş:
Kapı-3'e AYNEN devam edilir, yalnızca plato beklentisi buna göre
kalibre edilir (Σslack≈0'a E1 TEK BAŞINA ulaştırmayacak, E2'nin 1203
genuine ihlali ve A/F/G'nin değişmeyen kütlesi hâlâ baskın kalıyor).
Net okuma: KARAR-0 gerçek ve ölçülebilir bir iyileşme (tek-yön-sıfır
artefaktının ~57-67%'si temizlendi) ama full-data'nın temel zorluğunu TEK
BAŞINA çözmüyor — E2/A/F/G'nin kendi kütlesi ve ağ-çapına-yayılmış
(%74.5-74.8) ihlal ayak izi hâlâ Kapı-3'ün gerçek işi.

## M5e Bölüm 3 — son kampanya (v2 veri), Adım a+b+e

| Adım | Script | Sonuç |
|---|---|---|
| a) Elastik+warm-start | `scripts/warm_start_elastic.py` | 1. deneme (600s+120s) `watchdog_killed`; 2. deneme (900s, `--max-improving-sols 1`) **43.2s'de gerçek incumbent**, elastik-obj=369921.70, warm-start log-kanıtlı |
| b) LNS component/fold | `scripts/run_lns.py --builder folded --selection component` | Σslack 69559.20→**62821.90** (%9.68 azalma), 23 iterasyonda plato (kriter b) — **v1'in adım-13 sonucuyla (68865.62→62487.27, %9.28) neredeyse birebir aynı büyüklük mertebesi** |
| e) Kabul-edilebilirlik dökümü | `validate_output`+`recompute_objective` (partial best point) | 1763 strict ihlal (E1=645, E2=1114, G=4); E1 fazlalık oranı medyan/p90/max **hepsi 0.800** (çoğu ihlal tek-yönlü sıfır-karşı-aday durumu); E2 fazlalık dakika medyan=37.5/p90=125.0/max=425.0; reward-recompute=2959336.81 (BİLGİ AMAÇLI — strict-feasible DEĞİL, teslim edilemez) |

**Kriter (a) [Σslack≈0] YİNE tetiklenmedi.** Daha da önemlisi: LNS'in
component-bazlı denemesinde 23 iterasyonun büyük kısmı (iter 6-17, 19-23)
**gerçek `status=infeasible`** verdi (zaman-aşımı DEĞİL, HiGHS'in kendi
infeasibility sertifikası) — v1'in adım-13'te bulduğu "6/9 bileşen
dondurulmuş çevrede GERÇEKTEN infeasible" bulgusunun **v2 veriyle ÜÇÜNCÜ
bağımsız doğrulaması**. Bu, full-data'daki yapısal zorluğun LS-tahmin
kaynaklı bir blok-süresi hatası OLMADIĞINI güçlü şekilde gösteriyor — daha
doğru (Elapsed-türevli) K_od/R_o ile bile aynı örüntü aynen tekrarlanıyor.

Tag `m5e-first-incumbent` HENÜZ ÜRETİLEMEDİ (Σslack sıfıra inmedi).

## M5e Bölüm 3d — pencere deneyi (adjustable_window_min=360), SONUÇSUZ (standart bütçeyle)

`--adjustable-window-min` CLI override'ı `warm_start_elastic.py` ve
`run_lns.py`'ye eklendi (`generate_candidates`'in zaten kapsamlı TDD'li
window-mantığına ince bir argparse katmanı — yeni bağımsız test
gerekmedi). Big-M>1440 riski (VARSAYIM-3'ün 720 geçmişi) `src/model/big_m.py::MAX_ALLOWED_BIG_M`
runtime assert'iyle korunuyor — 360'ta bu assert HİÇ tetiklenmedi.

**Bulgu**: window=360'ta aday sayısı 18147→**26258 (+44.7%)**. `warm_start_elastic.py`'nin
Adım A'sı (A+G+F referans) kendi İÇ 600s+120s bekçisiyle (script'in
`--time-limit-sec`'i yalnızca Adım B'yi kapsıyor, Adım A hardcoded) **720.2s'de
`watchdog_killed`** — window=180'de AYNI adım güvenilir şekilde ~235s'de
`optimal` veriyordu. Adım B'ye hiç ulaşılamadı (script "ABORT -- no usable
A+G+F point" ile erken çıkıyor). **Sonuç**: pencere genişletmenin "ucuz"
olacağı varsayımı YANLIŞ ÇIKTI — aday sayısındaki %44.7'lik artış, en kolay
alt-problemi (A+G+F ALONE, window=180'de M5d'nin en güvenilir adımı) bile
standart bütçenin dışına itiyor. Big-M güvenlik sınırı sorun DEĞİLDİ; asıl
darboğaz aday-sayısı patlaması.

Bu noktada kullanıcıya durumla birlikte danışılıyor: (a) yalnızca Adım A
için ayrı/daha büyük bir bütçe denensin mi, (b) 360'ı burada bırakıp 720'yi
mi (daha riskli) denemeli, yoksa (c) pencere deneyi burada kapatılıp mevcut
window=180 sonucu (Adım a+b+e, yukarıda) kampanyanın son noktası mı kabul
edilmeli.

## DATA v2 EPOCH (M5e, 2026-07-11) — yeniden ölçüm, v1 ↔ v2 yan yana

Organizatörün 2026-07-09 veri paketi (`ElapsedTime1`/`ElapsedTime2`/`ML2`,
wrap-fix) entegre edildi (tag `m5e-data-v2`, bkz. Bölüm 1). Bu tablo,
AYNI güncel kod üzerinde v1 (arşivlenmiş, `data_raw/_organizer_source_package/
O&D Rakip Bağlantı Tablosu.xlsx`, byte-özdeş eski `data_raw` dosyası) ile v2
(şu anki `data_raw/`) arasındaki farkı izole ediyor — kod-düzeltmesi
kaynaklı kayma ile veri-kaynaklı kaymayı KARIŞTIRMIYOR (2026-07-09'un
orijinal 2048-ihlal ölçümü, M5b/M5c validator düzeltmelerinden ÖNCEydi;
buradaki v1 sütunu bugünkü kodla YENİDEN ölçüldü).

| Kalem | v1 (bugünkü kodla yeniden ölçüldü) | v2 | Değişim | Kaynak |
|---|---|---|---|---|
| Baseline ihlal — toplam | 2137 | 2102 | **-35 (-1.6%)** | `scripts/baseline_feasibility_witness.py` |
| Baseline ihlal — A | 144 | 106 | **-38 (-26.4%)** | aynı |
| Baseline ihlal — E1 | 690 | 690 | 0 (beklenen — E1 blok-süresine bağlı değil) | aynı |
| Baseline ihlal — E2 | 1219 | 1222 | +3 (küçük) | aynı |
| Baseline ihlal — F | 31 | 31 | 0 (beklenen — kapasiteye bağlı değil) | aynı |
| Baseline ihlal — G | 53 | 53 | 0 (beklenen — güne bağlı değil) | aynı |
| Gamma-infeasible pair sayısı | 76 | 63 | **-13 (-17.1%)**, ama TEK-YÖNLÜ DEĞİL: 57 ortak, 19 yalnızca v1'de, 6 yeni v2'de | `compute_gamma_infeasible_pairs` (scratch script, `docs/decisions.md`) |
| A uzlaştırılamaz çift (VARSAYIM-11 exemption) | 382 | 349 | **-33 (-8.6%)** | `scripts/run_core_feasibility.py` (WARNING log) |
| Statik E1/E2 sertifikaları (a/b/e2) | 0/0/0 (temiz) | 0/0/0 (temiz) | değişmedi — hâlâ provably-infeasible DEĞİL | `scripts/feasibility_certificates.py` |
| A+G+F referans (min_total_deviation_min) | 4233.0 (205.7s) | **4551.0 (238.5s)** | +318.0 (+7.5%) — daha az exemption = daha çok gerçek kısıt | `scripts/run_core_feasibility.py` |
| K_od kaynak (805 TK-gözlemli pazar) | 780 direkt / 25 LS-tahmini | 780 direkt (aynı filtre) / 25→**25/25 artık DOĞRUDAN** (VARSAYIM-15) | LS hatası medyan=1.28dk/p90=6.72dk/max=124.11dk | `scripts/validate_block_times_v2.py`, `docs/block_time_cross_validation.md` |
| n_candidates (rho-filtreli) | 18118 | 18147 | +29 (K_od kapsamı genişledi) | aynı script'ler |
| Elastik Σslack tabanı | 68865.62 (v1, 2026-07-10, 5 denemenin 2'si `time_limit`) | **69559.20** (E1=667/1225 pair ihlalli) | +693.58 (+1.0%) — pratikte AYNI mertebe | `scripts/warm_start_elastic.py` + `scripts/run_lns.py --max-iterations 0` |
| LNS bağlı-bileşen sayısı (violated-fixable, gamma-infeasible hariç) | 9 | **7** (boyutlar: 217,235,235,239,240,243,247 — hepsi büyük, tek-pair mikro-bileşen yok) | -2 bileşen, benzer toplam ölçek | `src/model/lns.py::build_pair_adjacency`+`connected_components` |

**Not (elastik Σslack v2 tabanı)**: v1'in kendi geçmişi bu adımın flaky
olduğunu gösteriyor (600s+120s bütçeyle 5 denemenin 3'ü `watchdog_killed`,
yalnızca 2'si gerçek incumbent verdi). v2'de aynı bütçeyle ilk deneme
`watchdog_killed` (720.2s, incumbent yok, ama warm-start log-kanıtlı kabul
edildi); `--max-improving-sols 1` "temiz-dur" hilesiyle 900s bütçeli ikinci
deneme **43.2s'de gerçek incumbent verdi** (`status=time_limit`,
elastik-obj=369921.70, 1892 strict ihlal — E1=667/E2=1225, v1'in Phase-2
seed'iyle [1879 ihlal] aynı büyüklük mertebesi). Bağımsız Σslack recompute
(`run_lns.py --max-iterations 0`, gerçek slack formülüyle, elastik amaç
fonksiyonunun ε·deviation terimini İÇERMEZ): **69559.20** — v1'in
68865.62'sine göre pratik olarak AYNI (%1.0 fark), gamma-infeasible pair
sayısı (63) yukarıdaki satırla BİREBİR tutarlı (çapraz-kontrol geçti).

**Dur-ve-sor değerlendirmesi**: yukarıdaki hiçbir kalem v1'e göre BÜYÜK
yapısal bir çelişki göstermiyor — tüm değişimler küçük-orta büyüklükte
(%1.6-%26.4 aralığında) ve YÖNÜ beklenen (K_od/R_o iyileşmesi → A ve
Gamma-infeasible azalıyor; E1/F/G değişmiyor çünkü blok-süresine
bağlı değiller). Bölüm 3'e geçiş için engel YOK.

## Bu oturumun (M5d Adım 1+2) koşuları

| Tarih (UTC) | Script | Amaç | Sonuç | objective | valid |
|---|---|---|---|---|---|
| 2026-07-10T21:15:54 | `run_full_data.py` (900s+120s) | Jbest fix TEK BAŞINA, K-subset/fold/warm-start YOK, full-adjustable | `watchdog_killed`, `Nodes=0`, 1019.3s | — | — |
| 2026-07-10T21:40:39 | `run_local_branching.py --k 200` | A+G+F referans + `build_model_m4` + Big-M local-branching (k=200) | `watchdog_killed`, `Nodes=0`, 720.2s (presolve/probing 3765/278163 binary'de kaldı) | — | — |
| 2026-07-10T21:X (analyze_violation_footprint.py, solve yok) | — | Aynı referans noktada E1/E2 ihlallerini kapsayan uçuş-instance ayak izi | arr %85.7 (2311/2697), dep %82.8 (2225/2688) serbest gerekir — 4536 örnek | — | — |

**Sonuç**: Jbest fix'in TEK BAŞINA yeterli olmadığı doğrulandı. k=200
local-branching aynı kök-düğüm-donma semptomunu gösterdi; ayak-izi analizi
bunun NEDEN beklenir olduğunu gösteriyor (ihlaller ağın ~%85'ine yayılmış,
mütevazı bir k ile kapsanamaz). Üçüncü kör bir k denemesi çalıştırılmadı —
plandaki "3 ardışık başarısız koşu → dur" eşiği + yeni sistemik bulgu
birlikte tetiklendi, kullanıcıya soruldu.

## Önceki turların (M5/M5c) özet koşuları

| Tarih (UTC) | Script | Sonuç | Not |
|---|---|---|---|
| 2026-07-09T09:30–20:50 (5 koşu) | `run_full_data.py` | çoğunlukla `infeasible`/`?` | M5'in ilk ladder denemeleri, VARSAYIM-9/10/11 öncesi/sırası |
| 2026-07-09T16:19:27 | `run_full_data.py` | `infeasible` | VARSAYIM-12'nin orijinal K-subset merdiveni koşusu (K=50/100/200/400 hepsi infeasible) |
| 2026-07-10T07:58:11 | `run_min_deviation.py` | `watchdog_killed` | min-sapma amaç fonksiyonu denemesi (M5c) |
| 2026-07-10T07:16–09:10 (3 koşu) | `run_full_data.py` | `infeasible`/`watchdog_killed` | F bijective-fix + E2-fold sıkılaştırma turu (M5c) — **Jbest fix'inden ÖNCEKİ son full_data_run** |
| 2026-07-10T10:24–10:48 | `run_feasibility_only.py` | `watchdog_killed` | `build_feasibility_model` (C/D yok) denemesi (M5c) |
| 2026-07-10T11:57:09 | `run_core_feasibility.py` | **optimal**, 205.7s, gap=1.13% | A+G+F ALONE full-data'da temiz çözüldü (min_total_deviation=4233.0) — M5d'nin referans noktası kaynağı |
| 2026-07-10T12:12:33 | `run_elastic_feasibility.py` | `watchdog_killed` | elastik (slack) model warm-start OLMADAN full-data'da hiç incumbent bulamadı |
| 2026-07-10T18:49:48 | `derive_warm_start.py` | valid=False | ilk warm-start türetme denemesi |
| 2026-07-10T19:09–20:38 (5 koşu) | `warm_start_elastic.py` | 3× `watchdog_killed`, 2× `time_limit` (obj=388889.16) | warm-start borusu proven (log-kanıtlı kabul), ama incumbent STRICT validator'dan geçmiyor (1879 ihlal) — Phase-2 seed, "ilk doğrulanmış değer" DEĞİL |

## Kullanıcı redirect'i (2026-07-11): kapanış yok, Fix-and-Optimize LNS

Yukarıdaki "Sıradaki adım" sorusu kullanıcıya soruldu; kullanıcı kapanışı
reddetti ve ayrıntılı bir LNS (Large Neighborhood Search) protokolü verdi.
Sonuç: **İLK GERÇEK slack azalması elde edildi** (ayrıntı: `docs/decisions.md`
2026-07-11 girdisi):

- `src/model/lns.py` + `scripts/run_lns.py`/`_lns_step_worker.py` yazıldı
  (TDD, 262 test yeşil). Mekanik: referans noktadan (mevcut elastik
  incumbent) en kötü m pair'i seç, o pair'lerin uçuş-instance'larını
  serbest bırak, GERİ KALANINI GERÇEKTEN `.fix()`'le (Big-M göstergesi
  DEĞİL), warm-start'la (`derive_and_set_warm_start`) yeniden çöz.
- İlk smoke-test (epsilon=1e-6, filtre yok): AYNI eski semptom (`Nodes=0`,
  gerçek slack hiç değişmedi).
- Kök neden bulundu: worst-slack seçimi, 1214 E2-ihlalli pair'in yalnızca
  19'unu oluşturan GERÇEKTEN düzeltilemez (journey_constant asimetrisi
  Gamma'yı en-iyi-durumda bile aşıyor) pair'leri EN ÖNCE seçiyordu — bunlardan
  biri bile serbest kümedeyse tüm alt-solve tıkanıyor. `compute_gamma_infeasible_pairs`
  ile bunlar kalıcı olarak hariç tutuldu. Ayrıca epsilon=1e-6→0 (deviation
  tie-breaker) kök-düğüm donmasına katkıda bulunuyormuş (nedeni tam
  açıklanamadı, ampirik).
- **Doğrulama testi (30 en-kötü E1-only pair, 182 serbest örnek, epsilon=0,
  filtre uygulanmış): `status=optimal` (kesilmeden!), Σslack 68865.62→45455.37
  — 23,410 puanlık kanıtlı azalma.** Kontrol (aynı ölçek ama filtresiz):
  220s'de hâlâ tamamlanmadı — filtre zorunlu, tek başına epsilon=0 yetmiyor.

## LNS tam-bütçeli koşular (2 bağımsız run, ikisi de plato ile durdu)

| Koşu | İterasyon | Süre | Sigma-slack başlangıç→son | Azalma | Çıktı |
|---|---|---|---|---|---|
| 1 (persistence fix ÖNCESİ) | 51 | ~85dk | 68865.62→49086.73 | %28.7 | kaybedildi (bug) |
| 2 (persistence fix SONRASI) | 61 | ~100dk | 68865.62→50204.06 | %27.1 | `runs/lns_best_partial_20260711T010508Z.json` |

**Kalan slack dökümü (koşu 2, final nokta)**: toplam 50204.06 — %9.4
(4707.34, 34 pair) `compute_gamma_infeasible_pairs`'ın kalıcı-hariç
tuttuğu, VERİ-KAYNAKLI (K_od asimetrisi, hiçbir zamanlama seçimiyle
düzeltilemez) 76 pair'den; **%90.6 (45496.72, 1490 pair) GERÇEKTEN
düzeltilebilir ama LNS'in henüz ULAŞAMADIĞI pair'lerden** — veri/yorum
sorunu değil, mevcut arama stratejisi/bütçe sınırı. İki bağımsız koşunun
neredeyse aynı yüzdede (%27-29) platoya girmesi: mekanizma kanıtlı
çalışıyor, ama mevcut m-tuning/randomize + 240s/iterasyon bütçesiyle bu
noktanın ötesine geçemiyor.

**Kullanıcıya soruldu, otonom devam edilmedi**: farklı hedefleme
stratejisi (örn. en-yüksek-ROI/en-kolay-düzeltilebilir pair'leri önceliklendir,
worst-slack yerine), daha uzun iterasyon bütçesi, ya da paralel
Gurobi/SCIP hattı.

## M5d LNS Yeniden Tasarımı (2026-07-11) — bağlantılı-bileşen + fold

Kullanıcı platonun İKİ bağımsız nedenini belirledi (worst-first hedefleme
+ fix-sonra-presolve maliyeti) ve iki yükseltmeyi BİRLİKTE istedi. Plan:
`.claude/plans/a-evet-ama-iki-tingly-canyon.md`. Ayrıntı: `docs/decisions.md`
2026-07-11 girdisi. **Üç yönlü izole karşılaştırma** (aynı başlangıç
Σslack=68865.62, aynı component-seçici, farklı worker):

| Yaklaşım | İterasyon | Süre | Σslack sonucu | Azalma |
|---|---|---|---|---|
| flat/fix (worst-first, eski builder) | 51-61 | ~85-100dk | 49086.73 / 50204.06 | %27-29 |
| **component/fix** (yeni hedefleme, ESKİ builder) | 120 | 40dk (duvar-bütçesi doldu) | **68865.62 (DEĞİŞMEDİ)** | **%0** |
| **component/fold** (yeni hedefleme, YENİ builder) | 3 | **~20s solve** | 62487.27 | **%9.28** |

**Sonuç açık**: component/fix'in SIFIR ilerlemesi, hedeflemenin (component
seçimi) kendi başına yeterli olmadığını kanıtlıyor — sorun HIZDI. Aynı
hedefleme, fold-tabanlı builder ile birleşince 3 iterasyonda (satır sayısı
fixed'in ~%17'si) flat/fix'in 50+ iterasyon/onlarca dakikada ulaştığı
büyüklük mertebesine ulaştı. Fold'un eşdeğerliği gerçek fixture verisiyle
kanıtlandı (`tests/solve/test_lns_fold_equivalence.py`, E2+A+G'yi aynı anda
karışık hale getiren senaryo, satır oranı %16.9).

**Adım 13 SONUÇ (2026-07-11, gerçek full-data koşusu)**: `--builder folded
--selection component`, aynı başlangıç Σslack=68865.62. **Kriter (b)
tetiklendi** — sadece **22 iterasyonda** (3 saatlik bütçenin çok altında,
gerçek çalışma süresi birkaç dakika), tüm bağlantılı bileşenler (ağda
TOPLAM 9 tane) 2'şer kez denendi, 20 iterasyon boyunca iyileşme olmadı →
otomatik DUR. Final Σslack=**62487.27** (**%9.28** azalma) — izole
3-iterasyonluk ölçümle BİREBİR AYNI sayı: yani gerçek koşu da iyileşmesini
yalnızca İLK İKİ iterasyonda yaptı (iter 1: 68865.62→63522.55, iter 2:
63522.55→62487.27), sonraki 20 iterasyon boyunca hiçbir şey değişmedi.

**Yeni ve daha ciddi bulgu**: 9 bileşenin 7'si stubborn işaretlendi, ama
"iyileşme yok" değil çoğunlukla **GERÇEK INFEASIBLE** sonucuyla (ör.
comp_34884/comp_69945/comp_79198/comp_55384/comp_45834/comp_33381 —
6/7 stubborn bileşen "status=infeasible NO USABLE RESULT" verdi, yalnızca
1/7 zaman-aşımıyla iyileşmesiz kaldı). Bu, önceki turların "iyileşme
yavaş/plato" bulgusundan FARKLI ve daha keskin: bir bağlantılı bileşeni
TEK BAŞINA serbest bırakıp geri kalan AĞIN TAMAMINI (A/F/G hâlâ HARD
kısıt olan elastik modelde) mevcut referans noktasına dondurunca, o
bileşen için HİÇBİR atama (E1/E2 slack'i ne olursa olsun) A/F/G'yi
sağlayamıyor — yani mevcut referans noktası, bu bileşenlerin çevresinde
o kadar sıkışmış ki yerel bir düzeltme alanı bile yok. Kalan 2 bileşen
(comp_13969/comp_34677, attempts=0) tam olarak iter 1/2'nin başarılı
bileşenleriydi — hiç stubborn olmadılar.

| component_id | boyut (pair) | deneme | stubborn? | kalan slack |
|---|---|---|---|---|
| comp_34884 | 245 | 2 | evet | 9614.78 |
| comp_69945 | 238 | 3 | evet | 9475.46 |
| comp_79198 | 236 | 3 | evet | 9409.17 |
| comp_55384 | 233 | 3 | evet | 8915.25 |
| comp_45834 | 232 | 3 | evet | 8882.26 |
| comp_33381 | 236 | 3 | evet | 8620.98 |
| comp_81757 | 124 | 3 | evet | 1280.72 |
| comp_13969 | 216 | 0 | hayır (başarılı, iter 1) | 1278.92 |
| comp_34677 | 130 | 0 | hayır (başarılı, iter 2) | 1273.98 |

Tam çıktı: `runs/lns_summary_20260711T103522Z.log.json` (stubborn_component_breakdown
+ slack_trajectory + worst_remaining_pairs), kısmi nokta:
`runs/lns_best_partial_20260711T103522Z.json`. **Kriter (a) [Σslack≈0]
tetiklenmedi — doğrulanmış objective_value HÂLÂ YOK.** Kullanıcıya
dönülecek (protokol gereği reward-max tırmanışına veya yeni bir arama
stratejisine OTONOM geçilmiyor).

### Ham iterasyon logu (koşu 2, son 15)

| iter | status | Σslack (önce) | Σslack (sonra) | serbest örnek | m | süre |
|---|---|---|---|---|---|---|
| 47 | time_limit | 50204.06 | 50204.06 | 1287 | 320 | 94.4s |
| 48 | time_limit | 50204.06 | 50204.06 | 1304 | 320 | 94.2s |
| 49 | time_limit | 50204.06 | 50204.06 | 1348 | 320 | 93.8s |
| 50 | time_limit | 50204.06 | 50204.06 | 1358 | 320 | 95.5s |
| 51 | time_limit | 50204.06 | 50204.06 | 1320 | 320 | 94.3s |
| 52 | time_limit | 50204.06 | 50204.06 | 1206 | 320 | 92.7s |
| 53 | time_limit | 50204.06 | 50204.06 | 1308 | 320 | 93.1s |
| 54 | time_limit | 50204.06 | 50204.06 | 1385 | 320 | 94.6s |
| 55 | time_limit | 50204.06 | 50204.06 | 1225 | 320 | 92.9s |
| 56 | time_limit | 50204.06 | 50204.06 | 1304 | 320 | 95.8s |
| 57 | time_limit | 50204.06 | 50204.06 | 1312 | 320 | 97.4s |
| 58 | time_limit | 50204.06 | 50204.06 | 1396 | 320 | 95.3s |
| 59 | time_limit | 50204.06 | 50204.06 | 1347 | 320 | 92.4s |
| 60 | time_limit | 50204.06 | 50204.06 | 1369 | 320 | 94.2s |
| 61 | time_limit | 50204.06 | 50204.06 | 1440 | 320 | 97.7s |

## LNS İlerleme (M5d)

Son güncelleme: 2026-07-11T14:57:10.276142+00:00. Son 15 iterasyon (tam log: `runs/lns_progress.log`, gitignored):

| iter | status | Σslack (önce) | Σslack (sonra) | serbest örnek | m | süre |
|---|---|---|---|---|---|---|
| 9 | infeasible | 62821.90 | 62821.90 | 618 | 235 | 2.7s |
| 10 | infeasible | 62821.90 | 62821.90 | 624 | 239 | 2.7s |
| 11 | infeasible | 62821.90 | 62821.90 | 624 | 239 | 2.7s |
| 12 | infeasible | 62821.90 | 62821.90 | 667 | 240 | 2.8s |
| 13 | infeasible | 62821.90 | 62821.90 | 667 | 240 | 2.7s |
| 14 | infeasible | 62821.90 | 62821.90 | 656 | 243 | 2.8s |
| 15 | infeasible | 62821.90 | 62821.90 | 656 | 243 | 2.7s |
| 16 | infeasible | 62821.90 | 62821.90 | 652 | 247 | 2.7s |
| 17 | infeasible | 62821.90 | 62821.90 | 652 | 247 | 2.7s |
| 18 | time_limit | 62821.90 | 63223.80 | 337 | 120 | 3.1s |
| 19 | infeasible | 62821.90 | 62821.90 | 637 | 235 | 2.7s |
| 20 | infeasible | 62821.90 | 62821.90 | 618 | 235 | 2.7s |
| 21 | infeasible | 62821.90 | 62821.90 | 624 | 239 | 2.6s |
| 22 | infeasible | 62821.90 | 62821.90 | 667 | 240 | 2.7s |
| 23 | infeasible | 62821.90 | 62821.90 | 656 | 243 | 2.7s |

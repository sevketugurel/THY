# Full-Data Solve Durumu (STATUS)

Bu dosya, `runs/` altındaki tüm full-data (gerçek veri) solve denemelerinin
tek-bakışta özetidir. Ayrıntılı gerekçe/kanıt zinciri için `docs/decisions.md`
(kronolojik) ve `ASSUMPTIONS.md` (VARSAYIM-12/13). Her anlamlı koşudan sonra
bu dosya güncellenir.

**Güncel durum (2026-07-11): full-data'da bağımsız validator'dan geçen bir
objective_value HÂLÂ YOK.** `m5d-first-incumbent` tag'i ÜRETİLEMEDİ.

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

Son güncelleme: 2026-07-11T10:36:36.779358+00:00. Son 15 iterasyon (tam log: `runs/lns_progress.log`, gitignored):

| iter | status | Σslack (önce) | Σslack (sonra) | serbest örnek | m | süre |
|---|---|---|---|---|---|---|
| 8 | infeasible | 62487.27 | 62487.27 | 610 | 233 | 2.7s |
| 9 | infeasible | 62487.27 | 62487.27 | 656 | 236 | 2.9s |
| 10 | infeasible | 62487.27 | 62487.27 | 656 | 236 | 2.8s |
| 11 | infeasible | 62487.27 | 62487.27 | 615 | 236 | 2.7s |
| 12 | infeasible | 62487.27 | 62487.27 | 615 | 236 | 2.7s |
| 13 | infeasible | 62487.27 | 62487.27 | 644 | 238 | 2.8s |
| 14 | infeasible | 62487.27 | 62487.27 | 644 | 238 | 2.6s |
| 15 | infeasible | 62487.27 | 62487.27 | 641 | 245 | 2.6s |
| 16 | infeasible | 62487.27 | 62487.27 | 641 | 245 | 2.6s |
| 17 | time_limit | 62487.27 | 62864.74 | 348 | 124 | 3.3s |
| 18 | infeasible | 62487.27 | 62487.27 | 626 | 232 | 2.6s |
| 19 | infeasible | 62487.27 | 62487.27 | 610 | 233 | 2.6s |
| 20 | infeasible | 62487.27 | 62487.27 | 656 | 236 | 2.6s |
| 21 | infeasible | 62487.27 | 62487.27 | 615 | 236 | 2.5s |
| 22 | infeasible | 62487.27 | 62487.27 | 644 | 238 | 2.6s |

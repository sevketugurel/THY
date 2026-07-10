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

## Sıradaki adım

Kullanıcıya soruldu (bu oturumda otonom ilerlenmedi): (a) çok daha büyük bir
k (binlerce, ayak-izi analizinin gösterdiği ~4536'ya yakın) ile local-branching
denemek — bu pratikte full-adjustable'a geri dönmek demek ve muhtemelen aynı
sonucu verecek; (b) Gurobi/başka bir solver'ı yeniden değerlendirmek (pip
lisansı ~2000 satır/değişkenle sınırlı, akademik lisans gerekiyor — M5c'de
temin edilemediği için kartı oynanamamıştı); (c) M5d'yi de M5c gibi
"doğrulanmış değer olmadan, çok-açılı kanıtla" kapatıp M6'ya geçmek.

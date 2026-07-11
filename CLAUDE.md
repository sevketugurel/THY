# THY IST Hub Tarife Optimizasyonu — TEKNOFEST

Pyomo/HiGHS MIP: IST hub üzerinden aktarmalı O–D pazarlarında ayarlanabilir uçuş
saatlerini optimize eder. Teslim: 2026-07-16 17:00. Plan: `.claude/plans/1-rol-ve-merry-dove.md`
(veya `/Users/sevketugurel/.claude/plans/1-rol-ve-merry-dove.md`).

## Durum

- **M0 tamam** (tag: `m0-walking-skeleton`) — loaders, block_times sağlayıcısı,
  candidate generation, trivial Pyomo model, HiGHS solve, JSON writer, bağımsız
  validator.
- **M1 tamam** (tag: `m1-core-objective`) — B (bağlantı uygunluğu, bidirectional
  reification, per-candidate Big-M) + C (Modül-5 monoton slot). Integer zaman
  değişkenleri.
- **M2 tamam** (tag: `m2-competition`) — D (rakip yenme + sıralama). N_od/T_comp
  derivation (rakip=taşıyıcı, min-konsolidasyon), W(r) monotonluk kontrolü
  (gerçek veri: 0/820 ihlal → forward-only forcing güvenli), b_od derivasyonu,
  rank one-hot (kritik infeasibility-tuzağı düzeltmesiyle — bkz. Kilit Kararlar).
  `main.py` artık `build_model_with_competition` kullanıyor. 96/96 test yeşil.
  CLI: objective=668.75, valid=True (668.75 **insan doğrulaması bekliyor**).
- **M3 tamam** (tag: `m3-operations`) — A (rotasyon, koşulsuz kısıt) + G
  (düzenlilik, referans-zaman formülasyonu). **Kritik bug bulundu ve
  düzeltildi**: G ilk denemede infeasible çıktı çünkü `t_arr`/`t_dep` global
  epoch_anchor'a göre kurulu, farklı `gun` değerleri ~1440dk farklı ham
  değerlere sahip (farklı takvim günü) — gün-içi normalizasyon eksikliği
  hem modeli hem validator'ı etkiliyordu, ikisi de düzeltildi (bkz. Kilit
  Kararlar). Bu turda Bash/Python execution classifier'ı bir süre kullanılamaz
  hale geldi (onlarca deneme başarısız oldu); "continue" ile devam edildiğinde
  düzeldi ve gerçek infeasibility'ler bu şekilde ortaya çıktı/düzeltildi.
  102/102 test yeşil. CLI: objective=668.75 (M2'yle aynı — A/G mevcut
  optimumu bozmadı), valid=True.
- **M4 tamam** (tag: `m4-directional-capacity`) — E1 (yönsel sayı dengesi,
  VARSAYIM-6): n_fwd/n_bwd lineer, Big-M gerekmiyor. E2 (yön-arası
  seyahat-süresi farkı, argmin sandviç): $a_{dir}$ (D'nin OR-aggregation'ıyla
  aynı desen), $w_\pi$ argmin seçici, $J_{best}$ sandviç (candidate-bazlı +
  pazar-çifti-bazlı Big-M, `src/model/big_m.py`), adversarial "sahte-düşük
  Jbest" testi, 4 satırlık aktivasyon tablosu ayrı testler, validator
  bağımsız Jbest recompute + Gamma kontrolü. F (kova/kapasite bağlama,
  VARSAYIM-7): pencere-ulaşılabilir kova kısıtlaması (144 DEĞİL), ayrı
  departure/arrival z-aileleri (10/15 kapasite), kapsam-dışı TK bacakları
  için rezidüel kapasite precompute (`src/model/constraints_capacity.py`),
  sıkı-kapasite fixture'ı + validator bağımsız kova-sayım kontrolü. **3 ek
  kritik bug F tasarımı sırasında bulundu ve düzeltildi** (hepsi
  RED→GREEN kanıtlandı, bkz. `docs/decisions.md`): (1) A'nın rotasyon
  kısıtı bir Flight Pair bacağı kapsam-dışıysa SESSİZCE atlıyordu —
  `out_of_scope_baselines` ile düzeltildi; (2) G'nin gün-içi
  normalizasyonu gerçek gece yarısına yakın uçuşlarda (23:55 vs 00:05)
  ~1430dk'lık SAHTE ihlal üretiyordu ("G check") — referans noktası her
  uçuşun kendi baseline'ının 12 saat karşısına kaydırılarak düzeltildi;
  (3) `runner.py`'nin rank_values çıkarımı `add_rank_onehot`'un [1,N]
  clamp'ini yok sayıyordu (M2'den beri gizli, E1'in dengeleme baskısı bir
  pazarı ilk kez TÜM rakiplerini yenmeye zorlayınca CLI'da `valid=False`
  olarak ortaya çıktı) — `max(1,raw_rank)` ile düzeltildi. `build_model_m4`
  artık A-G'nin TÜMÜNÜ içeriyor, `main.py` buna bağlandı (tek entegrasyon
  geçişi). 147/147 test yeşil. CLI (full A-G, `adjustable_set: all`):
  objective=668.75 (M2/M3'le AYNI — E1/E2/F fixture'ın mevcut optimumunu
  bozmadı), selected=18, valid=True.
- **M5 kapandı — çözüm bulunamadan, kapsamlı teşhisle** (tag: `m5-full-data`).
  Fixture: 668.75 artık BAĞIMSIZ doğrulandı (`tests/slow/test_bruteforce_oracle.py`
  saf-Python brute-force + `independent_validator.py::recompute_objective`,
  `src.model` import ETMEDEN). Full-data: G küme-bazlı (VARSAYIM-9) + A
  baseline-kronoloji eşleştirmesi+istisna (VARSAYIM-10/11) uygulandıktan
  SONRA bile solve merdiveni (dış-bekçili + `mip_heuristic_effort=0.3`)
  step1'de (18118 candidate, 756174 satır) 660s'de incumbent'sız kesildi,
  step2'nin DÖRT K değeri de (50/100/200/400) TEMİZ `infeasible` verdi.
  Bağımsız baseline-feasibility tanığı (solve YOK, 30.2s): ham baseline TÜM
  BEŞ kısıt ailesinde (A/E1/E2/F/G) eş zamanlı ihlalli (2048 ihlal, E2 en
  büyüğü: 1181). Sistematik tek-tek kaldırma testi (K=400'de, kod
  değiştirmeden, `scripts/diagnose_e1_e2_f.py`): A/E1/E2/F/G'nin BEŞİ de
  tek başına kaldırıldığında hâlâ infeasible — tek suçlu YOK. VARSAYIM-12
  olarak işlendi, organizatöre somut soru (`docs/organizer_questions.md`
  madde 12). **Full-data'da doğrulanmış objective_value YOK** — bu M5'in
  kapanış durumu (kullanıcı onaylı: daha fazla tanı yerine mevcut kanıtla
  organizatöre raporlama). Bu turda ayrıca: appsi_highs `time_limit`'inin
  büyük modellerde kök-düğüm cut turlarını kesemediği bulundu (dış
  SIGTERM/SIGKILL bekçisi eklendi, `src/solve/subprocess_watchdog.py`),
  `run_full_data.py`/`ladder.py` gözlemlenebilirlik yaması (canlı [ladder]
  log akışı, HiGHS log parse, wall-clock bütçe koruması), çıktı şemasına
  `k_od_sources[]`, `docs/report_outline.md`/`organizer_questions.md`/`output_format.md`.
  190+ test yeşil (127 unit + 63 solve + yeni watchdog/parse testleri).
- **M5c sürüyor — M5 kapanışı ASKIDA** (kullanıcı: "M5'i 'kapalı' değil
  'yarım' ilan et", VARSAYIM-12 organizatöre gitmeden bu teşhis turu
  bitecek). LP anatomisi (`docs/lp_anatomy.md`): kök LP/tavan oranı %65
  (aşırı gevşek değil), ama F (kova/kapasite) TEK BAŞINA satırların
  %53.7'si (405,982/756,174, per-reachable-bucket Big-M) ve w/x en
  kararsız ikili (LP'de %50.3/%44.5 fractional) — iki AYRI tamamlayıcı
  sıkılaştırma hedefi. §0 D-folding uygulandı (beat değişkeni -%35, satır
  -%4.4, LP/tavan oranı DEĞİŞMEDİ — F/w-x'e dokunmadı, beklenen). §1
  K-subset merdiveni YAPISAL OLARAK ETKİSİZ bulundu (K=50'de 0/13273 aday
  tam donuyor, aday üretimi leg-bazlı değil market-bazlı cross-product,
  bacak başına ortalama 4.4 market) — emekliye ayrıldı (config'te
  `step2_k_schedule` default kapalı, kod silinmedi), VARSAYIM-12
  güncellendi. §5 Faz-1: reward yerine min-sapma amacıyla (Σ|t-baseline|,
  `src/model/deviation_objective.py`) full-data denendi — dual bound çok
  daha hızlı/küçük ölçekte yakınsadı (142→4219.48) ama 1800s uzatmada
  (DAL P1-B tek hakkı) dahi 800s+ hiç B&B düğümü/incumbent üretmeden
  durdu → **DAL P1-C (zaman-aşımı, sonuçsuz)**: amaç fonksiyonu sorunu
  DEĞİL, doğrulandı. Sıradaki adım (kullanıcı onaylı sıra): Gurobi DEĞİL,
  önce F'nin satır patlamasını azaltan bir ön-filtre + w/x fractionality
  sıkılaştırması (lp_anatomy'nin "iki ayrı hedef"i). Ayrıntı:
  `docs/decisions.md` (kronolojik) + `docs/lp_anatomy.md` (karşılaştırma
  tablosu).
- **M5c sıkılaştırma turu TÜKENDİ (2026-07-10) — Gurobi kararı kullanıcıda**.
  Öncelik #1 (F satır-patlaması): per-bucket Big-M çifti tek bijective
  eşitliğe (`t=bucket_start*z+offset`) indirgendi — satır 722,947→329,842
  (-%54.4), F satırları -%96.8, LP çözüm süresi -%41, LP amaç/oranı
  BİREBİR AYNI (eşdeğerlik kanıtlı). Öncelik #2 (E2 w/a_dir fold): singleton
  pazar-yönleri (%51.4'ü, adayların %21.7'si) `pyo.Expression`'a katlandı —
  a_dir binary -%51.4, w binary -%21.7, ama w fractionality NEREDEYSE
  DEĞİŞMEDİ (%49.8) çünkü fold binary SAYISINI azaltıyor, LP GEVŞEKLİĞİNİ
  değil (x hiç dokunulmadı). Reward-amaçlı full-data step1 AYNI 600s+120s
  bütçesiyle ÜÇ kez koşuldu (F öncesi / F tek başına / F+E2 birlikte):
  dual bound yörüngesi F fix'le HIZLANDI (5.53M→4.90M idi, 5.13M→4.19M'e
  düştü) ama E2 fold'un ek katkısı YOK (5.13M→4.20M, ayırt edilemez), ve
  `Nodes=0` ÜÇÜNDE DE değişmedi — HiGHS hiçbir zaman kök-düğüm cut
  üretiminden dallanmaya geçemedi, `watchdog_killed`, sıfır incumbent.
  Kullanıcının kendi eşiği ("bu sıkılaştırma turu da kök düğümü açamazsa
  Gurobi kartını, aynı modeli iki solver'da koşan tek karşılaştırma
  tablosuyla") artık karşılandı — Gurobi kurulumu bir bağımlılık/lisans
  kararı olduğundan otonom ilerlenmedi, kullanıcıya soruldu.
- **M5c KAPANDI (2026-07-10, tag: `m5c-diagnosis-closed`) — çözüm
  bulunamadan, ÇOK-AÇILI teşhisle**. Gurobi'nin pip lisansı ~2000
  satır/değişkenle SINIRLI olduğu doğrulandı (bizim model ~314K satır,
  sığmıyor) — akademik lisans temin edilemedi, Gurobi kartı OYNANAMADI.
  Kullanıcı redirect: "Seçenek 2 erken, önce fizibiliteyi kesin
  cevaplıyoruz". Üç ek yön denendi: (1) `build_feasibility_model`
  (yalnızca A/B/E1/E2/F/G, C/D'nin reward-hesaplama makinesi TAMAMEN
  çıkarıldı — ultrathink: C/D hiçbir t/x/gap kısıtı KURMUYOR, salt-fizibilite
  modelinde feasible olan HER nokta tam modelde de feasible) full-data'da
  min-sapma amacıyla denendi — satır 756174→205799'a düşse BİLE AYNI
  "hızlı yakınsa sonra tam sessizlik" semptomu (214s'de donuk). (2)
  `mip_detect_symmetry=False` denendi — dual bound yörüngesi SATIR SATIR
  ÖZDEŞ kaldı, symmetry-detection hipotezi REDDEDİLDİ. Artık BEŞ bağımsız
  model/amaç/ayar kombinasyonu AYNI semptomu gösteriyor. (3) Statik E1/E2
  fizibilite sertifikaları (`scripts/feasibility_certificates.py`, saf
  pandas, MIP yok — B'nin reifikasyonundan forced_on/forced_off/undetermined
  türetilip üç necessary-condition testi kuruldu) **ÜÇÜ DE TEMİZ (0/0/0)**
  — E1/E2 provably infeasible DEĞİL. Saf-Python greedy repair
  (`scripts/greedy_feasibility_witness.py`, `validate_output`'u oracle
  kullanarak baseline'dan onarım) denendi — iter=1'de 2137 ihlal
  (baseline_autopsy'yle tutarlı), TEK toplu onarım turu SONRASINDA 2380'e
  KÖTÜLEŞTİ (koordinesiz onarımlar paylaşılan bacaklar üzerinden birbirini
  bozuyor — K-subset'in leg-sharing bulgusuyla AYNI yapısal gerçek, bu bir
  infeasibility kanıtı DEĞİL, heuristiğin kabalığı). Kullanıcı kararı:
  mevcut kanıtla kapat. ASSUMPTIONS.md VARSAYIM-12 GÜNCELLEME 3,
  organizer_questions.md madde 12 yeniden yazıldı, report_outline.md'ye
  8 satırlık "çözüm stratejisi yolculuğu" karşılaştırma tablosu eklendi.
  140 unit + 87 solve yeşil. **Full-data'da doğrulanmış objective_value
  HÂLÂ YOK** — ama artık NEDEN bulunamadığına dair beş bağımsız
  model/amaç/ayar denemesi + statik kanıt + kurucu-tanık denemesinden
  gelen çok-açılı, tutarlı bir kanıt zinciri var (tek bir kısıt hatası
  değil, HiGHS'in bu problem sınıfındaki kesme-düzlemi davranışının
  kendine özgü bir sınırı gibi görünüyor).
- **M5d sürüyor — bu turda da doğrulanmış objective_value bulunamadan
  kapandı** (tag YOK — hedeflenen `m5d-first-incumbent` tag'i
  ÜRETİLEMEDİ). Bu turun somut bulguları (hepsi `docs/decisions.md`
  2026-07-10/11 kayıtlarında, `ASSUMPTIONS.md` VARSAYIM-12 GÜNCELLEME 4 ve
  VARSAYIM-13'te ayrıntılı): (1) **gerçek formülasyon bug'ı bulundu ve
  düzeltildi**: E2'nin `Jbest` değişkeni `Integers` yerine `Reals` olmalıydı
  (full-data pazarlarının ~yarısının LS-estimate K_od'u kesirli — Integers
  domain bunları KOŞULSUZ infeasible yapıyordu, M4'ten beri TÜM full-data
  denemelerini zehirlemiş bir bug). (2) Warm-start borusu
  (`src/model/warm_start.py::derive_and_set_warm_start`, `solve(warmstart=True)`)
  full-data'da HiGHS tarafından GERÇEKTEN kabul edildiği log-kanıtlandı
  ("MIP start solution is feasible") ve `mip_max_improving_sols=1` kurtarma
  hilesi çalışıyor — ama kurtarılan nokta (elastik model, obj=388889.16)
  STRICT validator'dan GEÇMEDİ (1879 ihlal: E1=665, E2=1214) — bu Phase-2
  seed'dir, "ilk doğrulanmış değer" SAYILMAZ. (3) `runner.py`'nin appsi
  status eşlemesi düzeltildi (`maxIterations`/`feasible`→`"time_limit"`,
  artık incumbent'ları sessizce düşürmüyor). (4) Jbest fix'i TEK BAŞINA
  (K-subset/fold/warm-start olmadan, full-adjustable, 900s+120s bekçi)
  kök-düğüm davranışını DEĞİŞTİRMEDİ — yine `watchdog_killed`/`Nodes=0`.
  (5) `src/model/local_branching.py::add_local_branching` (Fischetti-Lodi
  tarzı trust-region, TDD 4 test) full-data'da k=200 ile denendi — AYNI
  semptom (presolve/probing 278163 binary'nin sadece 3765'ini işleyebildi,
  "moved=0⇒t=referans" çıkarımı hiç gerçek küçülmeye dönüşmedi). (6) Ucuz
  bir ön-teşhis (`scripts/analyze_violation_footprint.py`, solve yok):
  E1/E2 ihlallerini düzeltmeye şans tanımak için arr instance'larının
  %85.7'sinin (2311/2697), dep instance'larının %82.8'inin (2225/2688)
  serbest bırakılması gerekiyor — **M5c'nin candidate/market-seviyesi
  bacak-paylaşımı bulgusunun flight-instance seviyesinde BAĞIMSIZ ikinci
  doğrulaması**: ihlaller ağın küçük bir köşesinde değil, neredeyse HER
  YERDE — herhangi bir mütevazı k (200/400/800) baştan umutsuz. 141 unit +
  106 solve yeşil. Kullanıcıya soruldu: nasıl devam edilsin (daha büyük k,
  farklı çözücü, ya da bu haliyle kapat).
- **M5e Bölüm 1 tamam (tag: `m5e-data-v2`) — veri v2 entegrasyonu (TDD)**.
  Organizatör 2026-07-09'da `ElapsedTime1`/`ElapsedTime2`/`ML2` kolonlu
  güncellenmiş bir O&D paketi yayınladı + resmi WRAP uyarısı verdi
  ("Gate-to-Gate" alanı 24h'yi aşınca sıfırlanabiliyor). İkisi de gerçek
  veride bağımsız doğrulandı: wrap bug'ı 57.317 satırın TAMAMINDA tam
  1440'ın-katı bir formülle kanıtlandı (495 satır/60 pazar gerçek ≥24h,
  max 35h — hand-verified oracle: TK EZE→IST→PEK, 1020+155+545=1720dk,
  görüntülenen 280dk); 3 kardeş dosya + O&D'nin `_updated`-olmayan kopyası
  byte-özdeş (yalnızca O&D değişti). Yeni `src/data/elapsed_parser.py`
  (wrap-güvenli dakika parse + süre birleştirme) + `loaders.py::load_od_table`
  TEK düzeltme noktası (competitors.py/ranking.py SIFIR kod değişikliğiyle
  miras aldı, regresyon testleriyle kanıtlandı) — VARSAYIM-14.
  `BlockTimeProvider` v2: Elapsed kolonları mevcutken K_od/R_o artık
  DOĞRUDAN bacak-gözlemi (`[L,U]` filtresi K_od için kaldırıldı — VARSAYIM-15,
  skor-etkileyen veri-yorumu kararı olarak açıkça işaretlendi), kolonlar
  yoksa mevcut LS yolu byte-byte korunuyor (arayüz değişmedi). Çapraz
  doğrulama (`scripts/validate_block_times_v2.py` →
  `docs/block_time_cross_validation.md`): 805 TK-gözlemli pazarın 25'i
  tablo-seviyesinde LS tahminine muhtaçtı, hepsi artık doğrudan değer
  alıyor, LS hatası medyan=1.28dk/p90=6.72dk/max=124.11dk —
  `organizer_questions.md` madde 8/14 "veri ile çözüldü" kapatıldı. Path
  temizliği: `FULL_OD` vb. 19 dosyada tekrarlanan sabitler
  `src/config/paths.py`'ye konsolide edildi (`(1)` son eki düşürüldü).
  313 test yeşil (unit+slow), fixture objective **668.75 korundu**.
- **M5e Bölüm 2 tamam (tag: `m5e-remeasured`) — yeniden ölçüm, v1↔v2 yan
  yana**. Metodolojik disiplin: v1 sütunu bugünkü kodla YENİDEN ölçüldü
  (arşivlenmiş eski O&D dosyası üzerinden) — kod-düzeltmesi kaynaklı kayma
  ile veri-kaynaklı kaymayı karıştırmamak için. Tam tablo
  `docs/STATUS.md`'nin "DATA v2 EPOCH" bölümünde. Özet: baseline ihlal
  toplamı 2137→2102 (-1.6%, A ailesi tek başına -26.4% düşerken E1/F/G
  DEĞİŞMEDİ — beklenen, blok-süresine bağlı değiller); Gamma-infeasible
  pair 76→63 (-17.1%, ama TEK YÖNLÜ DEĞİL — 19 çözüldü, 6 yeni); A
  uzlaştırılamaz-çift (VARSAYIM-11) 382→349 (-8.6%); statik E1/E2
  sertifikaları hâlâ 0/0/0 temiz; A+G+F referans min_total_deviation
  4233.0→4551.0 (+7.5%); elastik Σslack tabanı 68865.62→69559.20 (+1.0%,
  pratikte aynı mertebe); LNS bağlı-bileşen sayısı 9→7 (boyutlar
  217-247, yapısal karakter DEĞİŞMEDİ). **Dur-ve-sor değerlendirmesi**:
  hiçbir kalem büyük yapısal çelişki göstermiyor, Bölüm 3'e (son kampanya,
  Pazartesi 2026-07-13 23:59'a kadar) geçiş için engel YOK. Bölüm 3 henüz
  başlamadı.

## Kilit Kararlar

- **Zaman**: **integer** dakika (M1'de continuous'tan değişti — gerekçe:
  B'nin backward-reifikasyonu epsilon=1 kullanıyor, continuous+epsilon
  kombinasyonu meşru kesirli-dakikalı çözümleri yasaklardı), veri kümesindeki
  en erken tarihin GECE YARISINDAN itibaren epoch (en erken timestamp'in
  kendisi değil — hand-calc'ları keyfi offsetle kaydırmamak için).
- **K_od / R_o sağlayıcısı** (`src/data/block_times.py`): K_od = satır bazlı medyan
  (gate_to_gate − gap, sadece [L,U] içindeki satırlar); R_o = bipartite least-squares,
  shift-invariant (T_IB/T_OB ayrı raporlanamaz ama R_o kesin). **Uyarı**: R_o'nun LS
  ile kesin kurtarılabilmesi için istasyon grafiğinin bağlantılı olması gerekir — 2
  istasyonlu minik sistemlerde (ör. sentetik fixture'ın kendisi) tekil değil, ayrı
  3-istasyonlu bağlantılı bir grafikle test edilir (`tests/unit/test_block_times.py`).
- **Validator** (`src/validate/independent_validator.py`): `src.model.*` /
  `src.candidates.*`'tan import ALMAZ — OUTPUT'un kendi raporladığı
  `adjusted_flight_times`'tan gap'i bağımsız yeniden hesaplar (M1'de raw
  baseline'dan hesaplamaktan bu şekle geçti — zamanlar artık gerçekten
  hareket edebiliyor). Bağlantı-varlık kontrolü her bacağı AYRI doğrular
  (tam (flno1,flno2) eşleşmesinin ham veride satır olması ŞART DEĞİL —
  cross-product sentezlenmiş bağlantılar meşru).
- **Aday üretimi**: TK inbound×outbound cross-product, achievable-range
  fizibilite kapısıyla budanmış (Modül-3 kapı 1, M1'de baseline-only'den
  genelleştirildi). `r1_id`/`r2_id` rol-namespaced (`"IB"|"OB"`, flno, gün) —
  26 gerçek uçuş numarası hem inbound hem outbound rolünde görünüyor.
- **Big-M**: per-candidate, `src/model/big_m.py`, model kurulumunda
  otomatik `<=1440` assert (B ve D için ayrı fonksiyonlar). `adjustable_window_min=180`
  (720 değil — `ASSUMPTIONS.md` VARSAYIM-3).
- **Gerçek veri bulguları**: Yolcu Verisi'nde 12 duplicate (orig,dest) satırı (toplanıyor)
  ve 3 eksik-dest satırı (reddediliyor) — ayrıntı `ASSUMPTIONS.md`.
- **D / rakip tanımı** (`src/data/competitors.py`): bir "rakip" TEK BİR
  TAŞIYICI (Cr1), o taşıyıcının o pazardaki TÜM itineraryleri min T_comp'a
  konsolide edilir — `ASSUMPTIONS.md` VARSAYIM-4.
- **Rank one-hot linking EŞİTSİZLİK, EŞİTLİK DEĞİL** (`add_rank_onehot`):
  $r=N-$beaten $[0,N]$ üretebilir ama onehot $[1,N]$ — eşitlik solver'ı
  beaten=N'e ulaşmaktan YAPISAL OLARAK engelliyordu (kritik bug, CLI testiyle
  yakalandı). `>=` + W monotonluğu otomatik $r=\max(1,N-$beaten$)$'e oturtuyor.
- **Under-claim toleransı**: validator D'de under-claim'i (gerçekte yenilen
  ama raporlanmayan rakip) violation SAYMAZ — forward-only forcing bunu
  yapısal olarak ZARARSIZ kılıyor (claimed⊆actual her zaman, ödül asla şişmez).
- **A rotasyon**: koşulsuz kısıt (Big-M YOK, reifikasyon değil). Yalnızca
  Pair grubundaki ARDIŞIK (Orig==IST→Dest==IST) bacaklara uygulanır — IST'e
  değmeyen ara bacaklar (ör. IST→MEX→CUN→IST, ~50/707 gerçek grup) modelin
  değişken kapsamı dışında, kısıt EKSİK kalır (`ASSUMPTIONS.md` VARSAYIM-5).
- **A OB/IB eşleştirmesi BASELINE KRONOLOJİSİ (M5, VARSAYIM-10/11)**: "aynı
  gun" eşleştirmesi gerçek veride %54.7 uzlaştırılamaz, %45.3 kronolojik
  TERS çıktı (R_o saatler mertebesinde, uzun menzilde aynı-gün IB çoğu
  zaman alakasız bir rotasyon). Artık `src/model/rotation_matching.py::match_rotation_legs`
  ile OB kalkışının partneri, baseline saat-of-day'e göre KENDİSİNDEN
  SONRAKİ EN YAKIN IB varışı (dairesel-haftalık, açgözlü-birebir). Sarma
  (Gün7→Gün1) durumunda kısıt bir HAFTA (10080dk) ileri kaydırılır
  (`week_offset`). Doğru eşleştirmeyle bile uzlaştırılamayan %24.3'lük
  kesim (382/1571) G'nin TK2841 mantığıyla MUAF tutulur (VARSAYIM-11).
  Validator aynı algoritmayı bağımsız yeniden uyguluyor.
- **G gün-içi normalizasyon ZORUNLU** (`constraints_operations.py::_day_offsets`):
  farklı `gun` değerleri GLOBAL epoch'ta ~1440dk farklı ham değerlere sahip
  (farklı takvim günü) — normalize etmeden `max(t)-min(t)<=X_dev` kontrolü
  HER ZAMAN infeasible verir (gerçek bir solve denemesiyle yakalandı, ipucu
  değil). Validator'ın x_dev kontrolü AYNI normalizasyonu tekrarlar, aksi
  halde geçerli çözümleri yanlışlıkla reddeder. Gece yarısı SARMASI için
  referans noktası gerçek 00:00 değil, uçuşun kendi baseline'ının 12 saat
  karşısı (`_flight_cut_points`).
- **G KÜME-BAZLI (M5, VARSAYIM-9)**: gerçek veride TK2841 kendi baseline'ında
  bile G'nin uzlaştırılabilirlik sınırını aşıyor (645dk>375dk) — koşulsuz
  okuma full data'yı KOŞULSUZ infeasible yapardı (formel Helly-özelliği
  kanıtıyla ASSUMPTIONS.md'de gösterildi). G artık `src/model/day_clustering.py::cluster_flight_days`
  ile EN AZ sayıda uzlaştırılabilir kümeye bölünmüş halde uygulanıyor
  (dairesel en-büyük-boşluktan kes + soldan-sağa açgözlü ÇAP taraması,
  ARDIŞIK-boşluk DEĞİL — data-türetilmiş, hiçbir uçuşa özel hardcode yok).
  Tüm günler uzlaştırılabilirse (yaygın durum) TEK küme = M3 davranışı
  DEĞİŞMEDEN korunur. Validator aynı algoritmayı bağımsız yeniden uyguluyor.

## Çalıştırma

```bash
source .venv/bin/activate
python main.py --config src/config/standard.yaml --fixture   # sentetik fixture
python main.py --config src/config/standard.yaml --full-data  # gerçek veri (ASSUMPTIONS.md'deki 3 satır hatası nedeniyle Yolcu Verisi reddedilir, M5'te çözülecek)
pytest                    # tüm testler
pytest -m unit            # solver'sız, <1sn
pytest -m solve           # küçük HiGHS solve, <60sn
```

## Milestone Disiplini

Her yeşil milestone sonunda: commit + tag (`m<N>-<kısa-ad>`), `docs/model.md`
güncelle (kümeler/parametreler/kısıtlar formel gösterim — kod↔doküman tutarsızlığı
diskalifiye sebebi), gerekirse `ASSUMPTIONS.md`'ye yeni VARSAYIM ekle.

## Aktif Otonom Tur (2026-07-09) — context sıkışırsa buradan devam et

Kullanıcı, M1→M2→(ritüel tamsa)M3'ü bitirip, M4'ün TASARIM NOTUNU yazıp
**M4 koduna başlamadan** durmamı istedi. Tam protokol kullanıcı mesajında;
özet:

- **TDD sırası bozulmaz**: kırmızı→minimum yeşil→refactor.
- **Her kısıt formülasyonundan önce ultrathink**: 3-5 satır yazılı doğruluk
  argümanı, sonra kod. (M2'de b_od derivasyonunda tam bu yüzden bir hata
  yakalandı — bkz. `docs/decisions.md`.)
- **Validator her kısıtla aynı milestone'da büyür**, model kodundan bağımsız.
  Kısıt başına 3 test: bağlayıcı / bağlayıcı-değil / kasıtlı-ihlal-yakalanıyor.
- **docs/model.md + ASSUMPTIONS.md + docs/decisions.md** ilgili kodla AYNI
  commit'te güncellenir.
- **Solve testlerine 60sn limit.** Full data'da MIP çözme YOK bu turda (M5 işi)
  — full data'ya sadece hızlı pandas kontrolleri için dokunulur.
- **Dur-ve-sor eşiği** (bunlar dışında otonom ilerle): brief yorumunu değiştiren
  keşif; skoru etkileyen yeni veri-yorumu kararı; 45dk'da çözülemeyen
  infeasibility; 1440 altında türetilemeyen Big-M; remote/config'e dokunan git
  işlemi. Diğer her şey: kendi kararımı ver, `docs/decisions.md`'ye tek satır
  gerekçeyle logla, devam et.
- **Milestone kapanış ritüeli**: tüm suite yeşil → validator sıfır ihlal →
  docs güncel → commit+tag (`m1-core-objective`, `m2-competition`,
  `m3-operations`) → CLAUDE.md Durum güncelle → 10 satır özet → dur madan
  devam.

**M3 tamamlandı** (tag: `m3-operations`) — ritüel tam uygulandı. M4 tasarım
notu (E1/E2/F) sunuldu ve onaylandı, şimdi KOD yazılıyor.

## Aktif Otonom Tur #2 (2026-07-09 devamı) — bu turun kapsamı: M4 + M5

Önceki turun §1 sürekli disiplini (TDD, ultrathink, validator eş-büyümesi,
üçlü test standardı, model.md/ASSUMPTIONS aynı commit'te, 60sn solve limiti)
AYNEN geçerli. Bu turun EK özeti:

- **Doğrulama borcu (M4'ten ÖNCE)**: `tests/slow/test_bruteforce_oracle.py`
  (src/model import ETMEYEN saf-Python 10-dk grid brute-force, solver'ı
  doğrular) + validator'a `recompute_objective()` (668.75'i bağımsız
  yeniden hesaplar, bileşen dökümünü dosyaya yazar).
- **M4 sırası**: E1 (basit lineer, Big-M yok) → E2 (argmin sandviç, en zor,
  adversarial test + validator'ın Jbest'i yeniden hesaplaması) → F (kova
  binary'leri yalnızca pencere-erişilebilir kovalarla, residual capacity
  full-scan precompute, kapsam-dışı TK uçuşları baseline'da sabit). +G
  gece-yarısı dairesel mesafe düzeltmesi kontrolü.
- **M5**: full data'da boyut bütçesi logu → Modül-3 budaması zorunlu →
  çözüm merdiveni (1: tam-ayarlanabilir+budama, 2: 15dk'da olmazsa
  adjustable-subset top-K kademeli, 3: o da olmazsa DUR+teşhis) → full-data
  koşusu pytest DEĞİL (ayrı komut+log) → çıktı brief §5 + golden + determinizm.
- **Ek dur-ve-sor eşikleri**: merdivenin 3. basamağına düşülmesi; E1 yüzünden
  pazarların >%20'si sıfır bağlantıya düşerse.
- **Kapanış (M5 ritüeli sonrası, M6'ya girmeden)**: `docs/report_outline.md`
  (6 sayfalık rapor iskeleti, rubrik-haritalı), konsolide organizatör soru
  listesi, M6 maliyet/kazanç öneri listesi (kod yok), tek kapanış raporu.

Detaylı alt-maddeler (E1 formülü, E2 sandviç, F reachable-bucket, residual
capacity, solve ladder eşikleri) kullanıcının bu turdaki mesajında birebir —
context sıkışırsa o mesaj otorite kaynağıdır, bu özet sadece hatırlatma.

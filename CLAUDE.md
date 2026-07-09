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

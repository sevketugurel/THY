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
- **M3 KOD YAZILDI, TEST EDİLEMEDİ** — A (rotasyon) + G (düzenlilik) implement
  edildi (`src/model/constraints_operations.py`, `main.py`'ye `build_model_with_operations`
  ile bağlandı, validator A/G-check ile genişletildi), TÜM dosyalar elle
  satır satır gözden geçirildi AMA **pytest/python çalıştırılamadı** — Bash
  tool'un güvenlik sınıflandırıcısı (`claude-sonnet-5 is temporarily
  unavailable`) onlarca denemeye rağmen code-execution komutlarını (basit
  `python -c "print(1+1)"` bile) sürekli reddetti; salt-okunur komutlar
  (`ls`,`echo`,`pwd`) çalışıyordu, spesifik olarak execution classifier'ı
  etkilendi. **Bu yüzden M3 COMMIT/TAG EDİLMEDİ** (m3-operations tag'i YOK) —
  "tüm suite yeşil" doğrulanmadan ritüel tamamlanamaz, sahte "test geçti"
  iddiası YAPILMADI. **Devam ederken ilk iş**: `pytest tests/solve/test_m3_constraints_a.py
  tests/solve/test_m3_constraints_g.py -v` çalıştır, çıkan hataları düzelt,
  sonra tüm suite + CLI + M3 ritüelini normal şekilde tamamla.

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

**M3 ek şartları** (kullanıcı mesajından, henüz uygulanmadı):
- **A rotasyon**: Flight Pair eşleşmesiyle, dönüş IST varışı ≥ gidiş IST
  kalkışı + R_o (block-time sağlayıcıdan, T_OB+T_IB zaten birleşik) + τ.
  3+ üyeli Pair grupları ardışık işlenir (plan §4, zaten sentetik fixture'da
  ROT-A/ROT-B ile 2-üyeli test edilebilir durumda).
- **G düzenlilik**: gün-çifti mutlak farkları yerine REFERANS-ZAMAN
  formülasyonu — serbest $T^{dep}_f$ ve $T^{arr}_f$, $t_{f,h}\in[T_f,T_f+X_{dev}]$.
  Aynı semantik (max−min ≤ X_dev), O(H) kısıt (H=gün sayısı), daha sıkı
  gevşetme (mutlak-fark formülasyonundan daha az Big-M). Doğruluk argümanı
  model.md'ye yazılacak.
- Üçlü test standardı + validator genişletmesi (A/G için de bağlayıcı/
  bağlayıcı-değil/kasıtlı-ihlal-yakalanıyor) burada da geçerli.

**M3 ritüeli bitince**: M4 (E1/E2 koşullu aktivasyon + F kova bağlama) için
TASARIM NOTU yaz (değişkenler, kısıtlar, Big-M türetimleri, E2 doğruluk
tablosu test planı, fixture genişletme planı) ama **M4 KODUNA BAŞLAMA** —
orada dur, tek rapor bırak (biten milestone'lar, insan doğrulaması
bekleyenler, mikro-kararlar, M4 notu, organizatör soruları).

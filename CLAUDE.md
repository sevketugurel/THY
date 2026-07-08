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
  değişkenleri. `main.py` artık `build_model` (gerçek model) kullanıyor,
  `build_trivial_model` yalnızca M0'ın kendi testleri için duruyor.
  65/65 test yeşil (49 unit + 16 solve). CLI: `python main.py --config
  src/config/standard.yaml --fixture` → objective=568.75, valid=True
  (568.75 **insan doğrulaması bekliyor** — bkz. `tests/fixtures/README.md`
  "M1 eki").
- **M2 sırada** — D (rakip yenme + sıralama), b_od derivasyonu (bkz. aşağıdaki
  "Aktif Otonom Tur" notundaki önceden-tespit-edilmiş b_od tutarsızlığı).

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
  otomatik `<=1440` assert. `adjustable_window_min=180` (720 değil —
  `ASSUMPTIONS.md` VARSAYIM-3).
- **Gerçek veri bulguları**: Yolcu Verisi'nde 12 duplicate (orig,dest) satırı (toplanıyor)
  ve 3 eksik-dest satırı (reddediliyor) — ayrıntı `ASSUMPTIONS.md`.

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

**M2 ek şartları** (kullanıcı mesajından, henüz uygulanmadı):
- W(r) tablosu monotonluğu (sabit N,b için son-rank arttıkça artmayan) YÜKLEME
  sırasında assert edilir; geçerse tek-yönlü forcing (over-claim engellenir,
  under-claim asla optimal olamaz — monotonluk garantisi), düşerse otomatik
  çift-yönlü fallback (ikisi de kodda hazır olmalı).
- Yenme Big-M'i candidate-tight: $M_{\pi,k}=\max(0,J_{hi}(\pi)-T_{comp,k})$,
  $J_{hi}(\pi)=K_{od}+gap_{hi}(\pi)$.
- **b_od derivasyonunda ÖNCEDEN TESPİT EDİLEN tutarsızlık** (bu tur içinde,
  kod yazılmadan önce ultrathink ile bulundu): fixture README'sindeki ilk
  b_od=2 (ZZA-ZZB) değeri HAND-PICKED'di (M0'da lookup satırını test etmek
  için), gerçek derivasyon formülü (N − baseline'da yenilen rakip sayısı,
  D'nin ≤ kuralıyla TUTARLI) uygulanınca b_od=1 çıkıyor. M2'de b_od
  derivasyon fonksiyonu YAZILDIKTAN SONRA fixture'ın b_od'si YENİDEN
  hesaplanmalı (hardcode değil, fonksiyondan), ve W(2,1,1) lookup satırı
  kullanılacak (W(2,2,1) değil) — hand-calc'ı buna göre YENİDEN yaz.
- Aynı rakibin (od,h) içinde birden çok bağlantısı varsa T_comp=rakibin EN
  İYİ (min) süresi — VARSAYIM, organizatör sorusuna eklenecek.

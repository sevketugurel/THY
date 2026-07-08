# THY IST Hub Tarife Optimizasyonu — TEKNOFEST

Pyomo/HiGHS MIP: IST hub üzerinden aktarmalı O–D pazarlarında ayarlanabilir uçuş
saatlerini optimize eder. Teslim: 2026-07-16 17:00. Plan: `.claude/plans/1-rol-ve-merry-dove.md`
(veya `/Users/sevketugurel/.claude/plans/1-rol-ve-merry-dove.md`).

## Durum

- **M0 tamam** (tag: `m0-walking-skeleton`) — loaders, block_times sağlayıcısı,
  candidate generation, trivial Pyomo model, HiGHS solve, JSON writer, bağımsız
  validator. Tek komut: `python main.py --config src/config/standard.yaml --fixture`.
  40/40 test yeşil (`pytest -m unit`, `pytest -m solve`).
- **M1 sırada** — kanonik zaman temsili, B (boşluk bağlama), C (monoton slot).

## Kilit Kararlar (M0'dan)

- **Zaman**: tam sayı dakika, veri kümesindeki en erken timestamp'ten epoch.
- **K_od / R_o sağlayıcısı** (`src/data/block_times.py`): K_od = satır bazlı medyan
  (gate_to_gate − gap, sadece [L,U] içindeki satırlar); R_o = bipartite least-squares,
  shift-invariant (T_IB/T_OB ayrı raporlanamaz ama R_o kesin). **Uyarı**: R_o'nun LS
  ile kesin kurtarılabilmesi için istasyon grafiğinin bağlantılı olması gerekir — 2
  istasyonlu minik sistemlerde (ör. sentetik fixture'ın kendisi) tekil değil, ayrı
  3-istasyonlu bağlantılı bir grafikle test edilir (`tests/unit/test_block_times.py`).
- **Validator** (`src/validate/independent_validator.py`): `src.model.*` /
  `src.candidates.*`'tan import ALMAZ — ham veriden gap'i bağımsız yeniden hesaplar.
- **Aday üretimi**: TK inbound×outbound cross-product, [L,U] fizibilite kapısıyla
  budanmış (Modül-3 kapı 1). M0'da baseline-gap kontrolü; M1'de adjustable-window
  altında achievable-range kontrolüne geçecek (bkz. M1 tasarım notu).
- **Gerçek veri bulguları**: Yolcu Verisi'nde 12 duplicate (orig,dest) satırı (toplanıyor)
  ve 3 eksik-dest satırı (reddediliyor) — ayrıntı `ASSUMPTIONS.md`.

## Çalıştırma

```bash
source .venv/bin/activate
python main.py --config src/config/standard.yaml --fixture   # sentetik fixture
python main.py --config src/config/standard.yaml --full-data  # gerçek veri (M0'da henüz tam desteklenmiyor - ASSUMPTIONS.md'deki 3 satır hatası nedeniyle Yolcu Verisi reddedilir)
pytest                    # tüm testler
pytest -m unit            # solver'sız, <1sn
pytest -m solve           # küçük HiGHS solve
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

M1 tasarım notu onaylandı (bu conversation'ın önceki turunda) — ek şartlar:
integer zaman değişkenleri (continuous+epsilon=1 kombinasyonu (L-1,L) ve
(U,U+1) gap aralıklarını YASAKLAR, meşru çözüm keser — bkz. docs/decisions.md),
per-candidate Big-M M1'den itibaren, adjustable_window_min=180 (720 değil,
Big-M≤1440 disiplinini korumak için), J_max(od,h)=|candidates(od,h)| (veri-
türetilmiş, sabit değil).

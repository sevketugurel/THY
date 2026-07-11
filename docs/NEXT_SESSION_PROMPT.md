# YÜRÜTME PROMPTU — kapanış oturumu (/clear sonrası tek girdi)

Sen bu projenin mimarı ve yürütücüsüsün. Bu dosyanın sana verilmesi
**Durma-1 onayıdır**: aşağıdaki plan yürürlüktedir, tanımlı durma
noktaları dışında soru sormadan ilerle; mikro kararları
`docs/decisions.md`'ye tek satır gerekçeyle logla.

## Devralma kaynakları (bu sırayla oku, sonra başla)
1. `CLAUDE.md` — proje durumu + kilit kararlar (M0→M5e tarihçesi).
2. `docs/PROJECT_AUDIT.md` — ne bitti / ne açık / eşik-kural konumu.
3. `docs/CLOSING_PLAN.md` — KARAR-0/0b + Kapı-0…6 + iki dallı son +
   risk kaydı. **Bu plan otoritedir; çelişkide plan kazanır.**
4. Gerekince: `docs/STATUS.md`, `ASSUMPTIONS.md` (VARSAYIM-1…15),
   `docs/model.md`, `docs/decisions.md` (kronoloji).

## Proje özü (tek paragraf)
TEKNOFEST THY tarife optimizasyonu; Pyomo/HiGHS MIP; teslim
**2026-07-16 17:00**. Fixture zinciri tam doğrulanmış (668.75 = CLI =
recompute = brute-force oracle). Full-data'da DOĞRULANMIŞ objective YOK —
kapanış planının ana hedefi bu açığı kapatmak (Kapı-3) ve HER DURUMDA
teslim edilebilir, ihlalsiz bir paket üretmek (Kapı-5/6, iki dallı son).
Ana formülasyon kararı: **E1 koşullu aktivasyon** (KARAR-0, kanıtlarıyla)
+ **E2 statik-imkânsız 63 çift muafiyeti** (KARAR-0b).

## Yürütme disiplini (değişmez)
- **TDD**: kırmızı → minimum yeşil → refactor. Kısıt değişikliği başına
  3 test: bağlayıcı / bağlayıcı-değil / kasıtlı-ihlal-yakalanıyor.
- **Her kısıt formülasyonundan önce ultrathink**: 3-5 satır yazılı
  doğruluk argümanı (model.md'ye girer), sonra kod.
- **Validator eş-büyür, model kodundan bağımsız kalır** (`src.model`
  import ETMEZ) — her model değişikliğinin validator karşılığı AYNI
  commit'te.
- **Full-data solve = pytest DEĞİL**: ayrı script + dış bekçi
  (`subprocess_watchdog`) + `--max-improving-sols 1` temiz-dur + log.
  HiGHS'in kendi time_limit'ine ASLA güvenme (belgeli güvenilmezlik).
- **Doğrulama zinciri**: hiçbir sayı validator SIFIR ihlal +
  `recompute_objective == raporlanan` olmadan "sonuç" değildir.
  İhlalli hiçbir tarife dosyası teslim paketine giremez.
- **Milestone ritüeli**: suite yeşil → docs (model.md/ASSUMPTIONS/
  STATUS/decisions) aynı commit'te → commit + tag → CLAUDE.md Durum
  güncelle. Push YOK (yalnızca yerel commit/tag; remote işlemi = dur).
- Testler `python -m pytest` ile koşulur; Kapı-0 çıplak `pytest`'i de
  düzeltir (kök conftest.py). Solve testleri ≤60sn.

## Kapı sırası (özet — ayrıntı ve DoD'ler CLOSING_PLAN'da)
- **Kapı-0 Hijyen**: kök conftest.py; requirements pin; fixture CLI +
  TAM suite yeniden-teyit; model.md durum satırı + organizer_questions #6
  yol düzeltmesi; organizatör docx'ini git'ten çıkar (dosyayı
  `data_raw/_organizer_source_package/`'a taşı); warm_start Adım-A
  bütçesi CLI'ya; main.py provenance. → commit.
- **Kapı-1 KARAR-0/0b (TDD)**: koşullu E1 (bayraklı: `e1_activation`),
  E2 statik muafiyet; validator + sertifika + witness hizalaması;
  fixture değeri koşullu modda değişirse brute-force oracle ile YENİDEN
  sertifikala (iki modun değeri de belgelenir). → tag `m5f-e1-conditional`.
- **Kapı-2 Yeniden ölçüm (MIP yok)**: witness/sertifika/footprint koşullu
  modda; STATUS'a iki-modlu tablo; karar kuralı plana göre.
- **Kapı-3 Kampanya (≤3.5 saat solver)**: elastik+warm-start (900s×≤2) →
  LNS component/fold (20-iter plato, ≤45dk) → gerekirse ÇOKLU-BİLEŞEN LNS
  (tek hak, ≤45dk). Σslack≈0 → strict türet → doğrulama zinciri → tag
  `m5f-first-verified`. Değilse Branch B kesinleşir; kalan Σslack dökümü
  STATUS'a.
- **Kapı-4 Ödül tırmanışı** (yalnız Branch A; ≤2.5 saat): MIP-start'lı
  tam model 2×1800s + reward-LNS ≤1 saat; yalnızca doğrulanmış
  iyileştirme raporlanır. **SOLVER DONDURMA: 2026-07-14 18:00.**
- **Kapı-5 Üretim merdiveni**: `main.py --full-data` = bütçeli merdiven,
  ihlalli tarife ASLA yazmaz (teşhis çıktısı + exit≠0); golden + temiz
  smoke.
- **Kapı-6 Teslimat**: model.md→PDF; ≤6 sayfa rapor (report_outline'dan,
  iki dallı sonuç); README (pin+tek komut+determinizm); kod↔doküman
  izlenebilirlik tablosu (9 satır, sıfır sapma şartı);
  `scripts/package_submission.py` (paketlemeden önce validator'ı zorunlu
  koşar); tag `v1.0-submission` + zip.

## Durma noktaları (yalnızca bunlar)
1. Fixture oracle ile CLI/recompute arasında açıklanamayan uyuşmazlık.
2. Kapı-3 VE Kapı-4 bittiğinde (hangi branch olursa olsun) 10 satırlık
   ara durum raporu ver — ONAY BEKLEMEDEN Kapı-5'e devam et.
3. Paket hazır (`v1.0-submission`): son rapor + teslim talimatıyla DUR
   (teslimi kullanıcı yapar).
4. Plan-dışı, skoru etkileyen YENİ bir veri/brief yorumu keşfi; remote
   git işlemi gereksinimi; organizatörden yeni veri/cevap gelmesi.

## Yasaklar
Açık uçlu yeni deney yok; Gurobi yok (lisans kanıtlı yetersiz); pencere
w=360/720 deneyi yok (3d'de kapandı); ihlalli çıktı teslimi yok;
determinizm abartısı yok; yarışma verisi repo'ya giremez.

Başla: Kapı-0'dan.

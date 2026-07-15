# Benchmark-Safe Üretim Yolu — "Dürüst Tam-İddia Incumbent" Pipeline

**Tarih:** 2026-07-15 (teslim: 2026-07-16 17:00 — ~18 saat)
**Durum:** Kullanıcı tasarımı iki P0 revizyonla şartlı onayladı; bu spec revizyonları İŞLENMİŞ halidir.
**İlgili:** `docs/superpowers/specs/2026-07-12-residual-repair-design.md` (M5i),
`runs/underclaim_floor_note.json` (C1 risk paragrafı), `docs/CLOSING_PLAN.md`.

---

## 0. Terminoloji Sözleşmesi (P0 — her şeyden önce gelir)

Organizatör sunumda çözümleri **kendi benchmark'larında aynı veriyle çalıştıracaklarını**
söyledi. Bu pipeline'ın ürettiği full-data çıktısı strict E1/E2 okuması altında
ihlallidir. Bu gerçeği gizleyen HER dil seçimi tasarım hatasıdır:

**YASAK** (strict validator-clean olmayan hiçbir çıktı/log/doküman için kullanılamaz):
- "geçerli tarife", "geçerli çözüm", "valid solution", `valid=True`,
  "validator-clean", "feasible solution"

**ZORUNLU** (bu çıktının resmî adlandırması):
- "şema-uyumlu, **tam-iddia** (claim-complete), **recompute-objective'li** incumbent,
  **açık strict teşhisi ekli**"
- Kısa biçim: "dürüst incumbent + teşhis"

**exit 0 garantisinin anlamı**: yalnızca **dosya üretimi garantisidir**
(şema-uyumlu, tam-iddia, non-null objective'li bir çıktı her koşuda yazılır).
Fizibilite garantisi DEĞİLDİR ve öyle anlatılamaz.

`--strict-gate` (eski davranış) dokümanlarda **"resmî strict feasibility kapısı"**
olarak adlandırılır: validator-clean olmayan hiçbir tarifeyi yazmayan, kanıt-disiplinli yol.
Yeni benchmark yolu bu kapının YERİNİ ALMAZ; benchmark koşusu için PRAGMATİK ve
DÜRÜST bir ek yoldur.

---

## 1. Amaç ve Arka Plan

Mevcut `main.py --full-data`: exact-MIP merdiveni → başarısızlıkta şema-uyumlu
null-teşhis (`objective_value: null`, boş tarife) + **exit 1**. Mühendislik olarak
dürüst; otomatik benchmark için "çözüm üretmedi" demek.

Eldeki varlıklar (2026-07-12/13 M5h/M5i kampanyaları):
- `runs/lns_best_partial_20260712T150223Z.json` — en iyi bilinen saatler
  (elastik model: A/B/C/D/F/G hard, E1/E2 slack'li; Σslack=10944).
- Bu saatlerin **tam-iddia recompute değeri: 1.488.074,81**
  (`runs/underclaim_floor_note.json::objective_before_recompute`) — ≈285
  (o,d,gün)-çifti strict E1/E2 ihlalli (aile dökümü doğrulama koşusunda ölçülecek).
- C1 underclaim (1.336.525,27, bağlantı listesi kırpılmış): kendi not dosyası
  yeniden-türetme riskini kaydetmiş — **ana çıktı OLMAZ**; yeni claim-complete
  validator modundan da geçemez (kasıtlı).

Savunma argümanı (rapora girecek): **ham baseline'ın kendisi** aynı strict okuma
altında A/E1/E2/F/G'yi eş zamanlı ihlal ediyor (2102 ihlal, dokuz bağımsız kanıt
turu — VARSAYIM-12 zinciri). Organizatörün değerlendiricisi bizim strict okumamızı
uygulasaydı kendi yayınladıkları tarife de elenirdi. Dolayısıyla: saatleri veren,
tüm uygun bağlantıları listeleyen, amaç değerini bağımsız recompute ile yazan ve
kalan strict ihlalleri AÇIKÇA raporlayan bir çıktı, null'dan hem daha yararlı hem
daha savunulabilirdir.

## 2. Kapsam / Kapsam Dışı

**Kapsam:** `main.py --full-data`'nın varsayılan yolunun değişmesi; `src/benchmark/`
modülü; seed dosyası üretim scripti; validator'a iki mod; writer'a diagnostics;
hedefli doküman güncellemesi; gerçek doğrulama koşusu; paketleme.

**Kapsam dışı:** matematiksel modelde değişiklik (docs/model.md/pdf dokunulmaz);
elastik+reward-ağırlıklı yeni iyileştirme objektifi (gelecek iş — improve aşaması
v1'de mevcut strict tam-MIP denemesini yeniden kullanır); fixture yolunda herhangi
bir değişiklik; Gurobi/alternatif solver.

## 3. Mimari (onaylı: Yaklaşım A — ayrı modül)

```
main.py --full-data                → src/benchmark/pipeline.py  (YENİ varsayılan)
main.py --full-data --strict-gate  → mevcut solve_with_ladder   (resmî strict feasibility kapısı, AYNEN)
main.py --fixture                  → SIFIR dokunuş (668.75 korunur)
```

### 3.1 Akış

```
1. Veri oku (mevcut loaders, strict=False — değişmez)
2. FLOOR  : baseline saatleri → tam-iddia türet → recompute → YAZ
            (≈30-60sn; bu andan itibaren null imkânsız, exit 0 garanti —
             yalnızca DOSYA ÜRETİMİ garantisi, bkz. §0)
3. SEED   : data_seed/full_data_best_deltas.json varsa uçuş-bazında uygula
            → tam-iddia türet → recompute (beklenen ≈1.488M) →
            recompute-reward floor'dan yüksekse ÜZERİNE YAZ
4. IMPROVE: kalan bütçede (varsayılan toplam 600sn, `--time-budget-sec` ile değiştirilebilir)
            mevcut strict tam-MIP denemesi (bugünkü step-1 makinesi,
            subprocess watchdog'lu). Kabul kapısı (üçü birden):
            (a) solver incumbent verdi, (b) strict validator SIFIR ihlal,
            (c) recompute-reward mevcut en iyiden yüksek → üzerine yaz.
            Beklenen: incumbent çıkmaz (dokuz kanıt turu) → log'a düşer.
5. Bitiş  : en iyi nokta + diagnostics dosyada; exit 0.
```

Anytime özelliği: adım 2'den itibaren harness bizi ne zaman keserse kessin
dosyada şema-uyumlu, tam-iddia, non-null bir incumbent vardır.

### 3.2 Seed dosyası: mutlak saat değil DELTA

`data_seed/full_data_best_deltas.json`:

```json
{
  "generated_utc": "...",
  "source_run": "runs/lns_best_partial_20260712T150223Z.json",
  "source_campaign": "M5h/M5i elastik+LNS (Σslack=10944)",
  "data_provenance": {"FULL_OD": {"sha256": "fec548...", "size_bytes": 5553508}},
  "deltas": [{"role": "IB|OB", "flno": 123, "gun": 3, "delta_min": -45}, ...]
}
```

- **Neden delta:** epoch anchor veri kümesinin en erken tarihinden türetiliyor;
  organizatör kopyasında parse/sıralama farkı mutlak dakikaları kaydırır ama
  `delta = seed_saat − baseline_saat` uçuş-bazında anlamını korur.
- Uygulama kuralları (hepsi loglanır):
  (a) `(role, flno, gun)` onların verisinde yoksa → delta atlanır, uçuş baseline'da kalır;
  (b) `|delta| > adjustable_window_min` → baseline'a düş (bağımsız pencere bekçisi);
  (c) dosya yok/bozuk → floor zaten yazılı, pipeline seed'siz devam eder.
- Seed dosyası pakete girer (~1MB ≪ 300MB); jüri anlatısı: "kodun daha uzun
  bütçeyle bulduğu noktanın taşınabilir kaydı; kod onu her koşuda veriye karşı
  doğrular, uygular ve geçmeye çalışır." README'nin "sabit tohum/parametre"
  determinizm çerçevesiyle uyumlu.
- Üretim scripti: `scripts/make_seed_deltas.py` (LNS partial + raw baseline → delta
  dosyası; tek seferlik, bizim makinede koşar, çıktısı commit'lenir).

### 3.3 Tam-iddia tamamlama (`src/benchmark/claim.py`)

Final saatlerden **taze türetme** (budanmış aday listesi DEĞİL):
rho'lu pazarların TK inbound×outbound tam cross-product'ında
`gap = t_dep(OB) − t_arr(IB)`; `[L,U]` içindeki HER bağlantı listeye girer.
`ranking_results` aynı saatlerden yeniden türetilir (`recompute_objective`'in
market-bazlı iç hesapları yeniden kullanılır/ayıklanır).

**Objective'in kaynağı:** `objective_value`'ya hiçbir zaman solver sayısı yazılmaz;
her zaman `recompute_objective` → `finalize_reported_objective` zinciri yazar
(recompute-reconciled).

**Doğruluk çapası (test):** fixture'da, çözülmüş saatlerden tam-iddia türetimi
modelin seçtiği x kümesiyle BİREBİR aynı olmak zorunda (B çift yönlü reifikasyon).

### 3.4 Improve aşaması — gerekçe

v1 improve = mevcut strict tam-MIP denemesi. Gerekçe: (i) yeni solver kodu sıfır
(runner + subprocess_watchdog aynen); (ii) "Pyomo/HiGHS üretim yolunda her koşuda
gerçekten çalışır" şartı somut karşılanır; (iii) anlatı dürüst: "tam model her
koşuda denenir; bulunamazsa en iyi bilinen incumbent korunur". Elastik+reward
iyileştirme objektifi bilinçli kapsam dışı (18 saatte yeni solver davranışı
ayarlamak en riskli iş kalemi). Improve, planın SON ve KESİLEBİLİR maddesidir.

## 4. Çıktı Şeması

Mevcut alanlar aynen (şema-uyumluluk). EK `diagnostics` bloğu:

```json
"diagnostics": {
  "mode": "benchmark_full_claim",
  "strict_feasible": false,
  "constraint_interpretation": "strict_A_G_checked; E1_E2_reported_as_diagnostics",
  "claim_complete": true,
  "claim_check": {"missing_claims": 0, "extra_claims": 0},
  "seed": {"file": "data_seed/full_data_best_deltas.json",
            "applied": "<n>", "skipped_missing_flight": "<n>",
            "fallback_window_exceeded": "<n>"},
  "strict_violations": {
    "total_pairs": "<n>",
    "by_family": {"A": 0, "B": 0, "C": 0, "D": 0, "E1": "<n>", "E2": "<n>", "F": 0, "G": 0},
    "examples": [
      {"family": "E2", "o": "...", "d": "...", "gun": 3,
       "measured": "<değer>", "bound": "<sınır>", "excess": "<fark>"}
    ]
  },
  "baseline_reference": {"objective": "<floor recompute>",
                          "strict_violations_total": "<n>"},
  "note": "E1/E2 strict okuması altında yayınlanan baseline tarifesi de ihlallidir; bkz. docs/report.md §<X>"
}
```

- `strict_violations.examples`: aile başına ilk N=10 ihlal, izlenebilirlik için
  (o,d,gün + ölçülen değer + sınır + aşım).
- `solver_metrics.status` değerleri:
  - `baseline_floor_with_strict_violations` — yalnız floor yazılabildi
  - `heuristic_incumbent_with_strict_violations` — seed kabul edildi (beklenen durum)
  - `improved_incumbent_with_strict_violations` — improve reward'ı yükseltti ama strict-clean değil
    (v1'de erişilemez: improve kabul kapısı strict-clean şartı içerir; alan ileriye dönük tanımlı)
  - `strict_feasible_incumbent` — improve strict validator-clean nokta buldu
    (yalnız bu durumda `strict_feasible: true`)
- CLI özet satırı (örnek): `status=heuristic_incumbent_with_strict_violations
  objective=1488074.81 claim_complete=True strict_feasible=False violations=E1:<n>,E2:<n>`
  — `valid=` kelimesi benchmark yolunda HİÇ kullanılmaz.
- Beklenti: ihlaller ağırlıkla E1/E2 (seed elastik modelden; A/B/F/G orada hard'dı).
  **Dur-ve-sor kapısı:** doğrulama koşusunda E1/E2 dışı ailede sıfırdan farklı
  ihlal çıkarsa kullanıcıya dönülür (M5e'de bir noktada G=4 görülmüştü — küçük
  G kalıntısı çıkarsa gizlenmez, raporlanır ve sorulur).
- `docs/output_format.md` güncellenir (diagnostics + status sözlüğü + §0 terminolojisi).

## 5. Validator: İki Mod (bağımsızlık korunarak)

`validate_output` iki AYRI moda ayrılır (parametrelerle; `src.model` import
etmeme kuralı aynen):

- **`strict=True`** (mevcut davranış, değişmez): tüm kısıt aileleri kontrol,
  herhangi bir ihlal = geçmez. `--strict-gate` ve mevcut test suite bunu kullanır.
- **`claim_complete=True`** (YENİ): output'taki saatlerden bağımsızca türetilen
  uygun-bağlantı kümesi listelenen kümeye **EŞİT mi**
  (`derived_feasible_connections == listed_connections`)? Eksik bağlantı
  (underclaim) DA fazla/uygunsuz bağlantı (overclaim) DA ihlaldir — overclaim
  kritiktir çünkü `recompute_objective` listelenen kümeden beslenir; fazladan
  bağlantı objective'i ŞİŞİRİR ve strict yalnız raporlandığı için başka hiçbir
  kapı bunu yakalamaz. (C1-tarzı underclaim de, şişirilmiş overclaim de artık
  bizim validator'ımızdan geçemez — bilinçli.)

Benchmark pipeline HER İKİSİNİ de koşar:
- `claim_complete` → üretim KAPISI (bizim yazdığımız listeyi bizim bağımsız
  türetmemiz tutmalı; tutmazsa bu bizim bug'ımızdır — testler ve doğrulama
  koşusu yakalar; benchmark koşusunda yine de dosya üretilir,
  `diagnostics.claim_complete: false` yazılır ve loglanır, ASLA gizlenmez).
- `strict` → KAPINOT; sonuç `diagnostics.strict_violations`'a RAPORLANIR,
  çıktı bloklanmaz, İHLALLER SAKLANMAZ.

Ek: aile-bazlı ihlal sayacı + örnek toplayıcı (diagnostics beslemesi) —
mevcut violation listesinden türetilen saf özet fonksiyonu.

## 6. Kenar Durumları

| Durum | Davranış |
|---|---|
| Seed dosyası yok/bozuk | Floor yazılıdır; loglanır; exit 0 |
| Seed'deki uçuş veride yok | O uçuş baseline'da kalır (delta atlanır, sayaç diagnostics'e) |
| Delta pencereyi aşıyor | Baseline'a düş, logla (bağımsız pencere bekçisi) |
| Improve solver çöker / watchdog keser | Yakalanır; mevcut en iyi dosyada kalır; exit 0 |
| Harness bizi ortada keser | Dosya son kabul edilen incumbent'ı içerir (anytime) |
| Veri dosyaları eksik/okunamaz | Açık hata mesajı, exit ≠ 0 (dosya üretim garantisi veri varlığına koşullu) |
| claim_complete kendi kontrolünden geçmedi | Dosya yine yazılır; `claim_complete: false` + yüksek sesli log (bug göstergesi; testler önler) |
| `--strict-gate` | Eski ladder + null-teşhis + exit 1 AYNEN (resmî strict feasibility kapısı) |
| `--fixture` | Tamamen eski yol; 668.75/`valid=True` çıktısı değişmez (strict yolda `valid` dili meşru: orası gerçekten validator-clean) |

## 7. Test Planı (TDD)

Unit:
- delta uygulama: eşleşme / eksik-uçuş / pencere-aşımı / dosya-yok / bozuk-json
- claim-completion: fixture eşdeğerlik (model x'leri == saatlerden türetilen küme);
  kasıtlı-eksik-liste (underclaim) `claim_complete=True` modunda yakalanıyor;
  **kasıtlı-overclaim** (saatlerin desteklemediği fazladan bağlantı eklenmiş liste)
  da yakalanıyor VE şişirilmiş listenin recompute'u kabul edilmeden önce
  `extra_claims > 0` ile bloklanıyor
- diagnostics üretimi: aile sayaçları + örnekler + `strict_feasible` bayrağı doğru
- writer: diagnostics'li çıktı şema-uyumlu + deterministik (byte-özdeşlik,
  `solve_time_sec` hariç)
- exit-0: floor yazıldıktan sonra hiçbir istisna exit≠0 üretemez
- terminoloji: benchmark yolunun CLI çıktısında `valid=` geçmez (regresyon testi)

Solve:
- fixture CLI 668.75 regresyonu (dokunulmamış yol)
- `--strict-gate` eski davranış testi (null-teşhis + exit 1)
- benchmark pipeline fixture verisiyle uçtan uca (sentetik seed'le)

Gerçek doğrulama koşusu (pytest DEĞİL, ayrı komut + log):
- `main.py --full-data` → recompute değeri `underclaim_floor_note.json`'daki
  1.488.074,81 ile çapraz kontrol (birebir eşleşme beklenir)
- ihlal ailesi dökümü ölçülür; E1/E2 dışı aile → dur-ve-sor
- `outputs/full_data_output.json` bu koşudan yenilenir
- temiz-klon provası (zip → venv → test → demo → full-data floor+seed)

## 8. Doküman + Paket (onaylı hedefli minimum)

- **README**: "Üretim merdiveni ve garanti" bölümü yeniden — yeni garanti dili
  (§0 sözleşmesine uygun): "benchmark yolu her koşuda şema-uyumlu, tam-iddia,
  recompute-objective'li bir incumbent yazar ve strict ihlalleri açıkça raporlar;
  resmî strict feasibility kapısı `--strict-gate`'te yaşamaya devam eder".
- **KURULUM.md**: resmî çıktı tanımı güncellenir (null-teşhis → dürüst incumbent + teşhis).
- **docs/report.md**: TEK yeni bölüm — benchmark-safe yol; 1.488M sonucu;
  ≈285 çift teşhisi; baseline'ın-kendisi-ihlalli savunması; C1'in neden ana
  çıktı olmadığı; "valid solution" DEĞİL "dürüst incumbent + teşhis" çerçevesi.
  Ardından report.pdf yeniden üretilir.
- **ASSUMPTIONS.md**: **VARSAYIM-18** — skor-etkileyen yorum kararı: benchmark
  üretim yolunda E1/E2 teşhise iner (kanıt zinciri: VARSAYIM-12 GÜNCELLEME 5 +
  baseline ihlalleri + organizatör-benchmark gerekçesi).
- **docs/output_format.md**: diagnostics + status sözlüğü.
- **docs/traceability.md**: 1 satır (üretim yolu değişikliği, model değişikliği değil).
- **CLAUDE.md Durum + docs/decisions.md**: standart kapanış girdileri.
- **package_submission.py**: `data_seed/` + yeni `outputs/` + yeni testler pakete girer.
- **TESLIM_BEKLENTILERI.md**: beklenen çıktı/süre/rubrik güncellenir.
- **Dokunulmaz**: docs/model.md, docs/model.pdf.

## 9. Zaman Planı (~18 saat, kesilebilirlik sırası)

1. Spec + plan (≈1s)
2. TDD çekirdek: seed/claim/validator-iki-mod/writer-diagnostics (≈3-4s)
3. main.py bağlama + exit kodları + seed dosyası üretimi (≈1,5s)
4. Gerçek doğrulama koşusu + 1.488M çapraz kontrol (≈1s)
5. Doküman + PDF + paket + temiz-klon provası (≈2-3s)
6. Improve aşaması (SON, KESİLEBİLİR — süre daralırsa "denendi-loglandı"
   seviyesinde kalır, seed+floor+doküman önceliklidir)

## 10. Açık Riskler

- **1.488M çapraz kontrolü tutmazsa** (recompute farklı çıkarsa): dur-ve-sor —
  underclaim notu ile yeni claim-completion arasında evren farkı olabilir
  (rho-filtreli pazar evreni açıkça dokümante edildi; fark çıkarsa neden bulunmadan
  outputs yenilenmez).
- **E1/E2 dışı aile ihlali çıkarsa**: dur-ve-sor (bkz. §4).
- **Organizatör verisi "aynı" değilse**: delta mimarisi + uçuş-bazı doğrulama
  zarif düşüş sağlar; en kötüde floor (baseline + tam-iddia + recompute) yazılır.
- **Jüri seed dosyasını "hazır cevap" sayarsa**: şeffaflık savunması —
  provenance'lı, kaynağı belgeli, kod tarafından her koşuda veriye karşı doğrulanan
  bir warm-start kaydı; README/report bunu açıkça anlatır (gizli değil, vitrine konmuş).

# Teknik Rapor İskeleti (brief §5 madde 8, ~6 sayfa)

Brief madde 8: *"Teknik rapor (en fazla ~6 sayfa): formülasyon gerekçeleri,
varsayımlar, doğrusallaştırma seçimleri ve sonuç tartışması."* Bu iskelet,
§6 puanlama kriterlerine (toplam 100 puan) doğrudan haritalanmış — her bölüm
başlığının yanında hangi kriteri beslediği not edildi, rapor yazarken
hangi bölüme ne kadar alan ayrılacağı ağırlıklarla orantılı olmalı.

| Kriter | Ağırlık |
|---|---|
| 1. Model Doğruluğu ve Kapsam | %30 |
| 2. Çözüm Kalitesi | %25 |
| 3. Hesaplama Performansı ve Ölçeklenebilirlik | %15 |
| 4. Kod Kalitesi ve Yeniden Üretilebilirlik | %15 |
| 5. Teknik Rapor ve Dokümantasyon | %10 |

(Kriter 4 kod kalitesi rapor DEĞİL kod tarafından karşılanıyor — README +
determinizm testleri; rapor kriter 4'ü yalnızca "nasıl doğrulanır" diye
1-2 cümleyle referanslar.)

---

## Sayfa 1 · Özet + Problem Çerçevesi (Kriter 1 destek)

- Problemin 3-4 cümlelik özeti: IST hub üzerinden aktarmalı O–D pazarlarında
  ayarlanabilir uçuş saatleri optimizasyonu.
- Amaç fonksiyonunun iki bileşeni: bağlantı-sayısı ödülü (azalan getiri) +
  sıralama ödülü (rakip yenme).
- Kısıt seti özeti (A–G) tek paragraf, `docs/model.md` §1-§4'e referans.
- Nihai amaç değeri, hangi merdiven basamağında elde edildiği (bu turun
  DAL A/B/C sonucu), gap.

## Sayfa 2 · Formülasyon Gerekçeleri (Kriter 1, ~%30 — en büyük bölüm)

- Kümeler/parametreler/karar değişkenleri tablosu (docs/model.md'den kısaltılmış).
- Her kısıt (A-G) için TEK paragraf: brief'in doğal-dil ifadesi → matematiksel
  form → neden bu form (alternatiflere karşı).
- Big-M disiplini: per-candidate türetim, `<=1440` assert, neden gerekli
  (B'nin reifikasyonu, D'nin OR-aggregation'ı, E2'nin argmin sandviçi).

## Sayfa 3 · Varsayımlar (Kriter 1 + Kriter 5 "varsayımların açıklığı")

- VARSAYIM-1 ... VARSAYIM-11'in özet tablosu (bulgu → karar → gerekçe, 1 satır
  her biri) — tam detay `ASSUMPTIONS.md`'de, rapor yalnızca özet + organizatör
  sorusu referansı verir (`docs/organizer_questions.md`).
- **Veri anomalisi ve kanıtlanabilir infeasibility alt-bölümü** (VARSAYIM-9/10/11
  keşif zincirleri) — ayrı vurgulanmalı, çünkü bunlar "biz öyle tercih ettik"
  değil "veri + brief'in kendi tutarlılığı bizi buna zorladı" türünden:
  - TK2841 gün-içi 645dk sapması → G'nin koşulsuz okuması TÜM full-data'yı
    infeasible kılardı (formel Helly-özelliği kanıtı) → küme-bazlı G.
  - A'nın "aynı gun" eşleştirmesi 1496 çiftin %54.7'sini uzlaştıramıyor,
    %45.3'ü kronolojik ters → baseline-kronoloji eşleştirmesine geçildi.
  - Düzeltmeden SONRA bile 382/1571 (%24.3) çift fiziksel olarak imkansız →
    G'yle aynı mantıkla (kendi en-iyi-durumunda bile imkansızsa) muaf tutuldu.
  - Bu üç bulgu, brief'in kendisinin çözülemez bir problem tasarlamadığı
    varsayımına dayanıyor — organizatöre üç somut soru olarak yansıtıldı.
- **Hub yoğunluğu ve ayrıştırılamazlık** (M5c, 2026-07-10 bulgusu):
  full-data'da bir fiziksel uçuş bacağı ORTALAMA 4.4 farklı (o,d) pazarına
  katılıyor (maksimum 183) — aday üretiminin TAM inbound×outbound
  cross-product olmasının doğal sonucu. Bu, "pazar bazında ayrıştır"
  türü yaklaşımların (adjustable-subset K-merdiveni, Benders dekompozisyonu)
  neden ERKEN elendiğinin/başarısız olduğunun VERİ-KANITI: küçük bir
  "tohum" pazar kümesini bile serbest bırakmak, bacak-paylaşımı üzerinden
  geçişken olarak AĞIN NEREDEYSE TAMAMINA yayılıyor (K=50'de bile
  candidate'ların %100'ü en az bir bacağı serbest kalıyor) — IST hub'ı
  GERÇEKTEN ayrıştırılamaz bir ağ, alt-problem bölme stratejileri
  yapısal olarak beklenen kazancı sağlamıyor.

## Sayfa 4 · Doğrusallaştırma Seçimleri (Kriter 1 + Kriter 3)

- Big-M vs sıkı-M tartışması: per-candidate M neden global M'den daha sıkı,
  hangi testler bunu doğruluyor (`test_big_m.py`).
- E1'in lineer (Big-M'siz) formu, E2'nin argmin sandviç deseni (D'nin
  OR-aggregation'ıyla aynı desen, tekrar kullanım).
- F'nin kova/kapasite bağlama tasarımı: pencere-ulaşılabilir kova kısıtlaması
  (144 DEĞİL), ayrı departure/arrival z-aileleri, residual capacity precompute.

## Sayfa 5 · Çözüm Kalitesi ve Performans (Kriter 2, Kriter 3)

- Fixture sonucu (668.75) — brute-force oracle ile bağımsız doğrulanmış
  (`tests/slow/test_bruteforce_oracle.py`).
- Full-data sonucu: bu turun kapanış raporundan — hangi merdiven basamağı,
  gap, model boyutu (satır/sütun/nonzero/binary, presolve öncesi/sonrası),
  K_od kaynak dağılımı (direct/estimated).
- Ölçeklenebilirlik: adjustable-subset merdiveninin KENDİSİ bu kriterin
  kanıtı — tam problem çözülemezse top-K pazar alt-kümesine kademeli düşüş,
  hiçbir aşamada sessizce "çöz-veya-hiç" değil.
- E1/E2 teşhis özeti (varsa) — sıfır-bağlantıya düşen pazar oranı, hangi
  kısıtın "amaç bastırıcı" davranışı gösterdiği.
- **HiGHS zaman-limiti güvenilirliği** (M5, 2026-07-09 bulgusu, `docs/decisions.md`):
  `appsi_highs`'ın `config.time_limit`'i, büyük modellerde (605K satır)
  kök-düğüm cut üretimi TEK BİR turu 600s'lik limiti kendi başına aşabildiği
  için, YALNIZCA B&B düğümleri arasında kontrol ediliyor gibi görünüyor —
  solver-içi limite güvenmeden DIŞARIDAN bir bekçi (SIGTERM+timeout) gerekli.
  Bu; "Hesaplama Performansı" kriterinin (Kriter 3, "çözüm süresi") somut bir
  ölçekleme bulgusu — büyük örneklerde solver'ın kendi zaman-yönetimi
  mekanizmasına kör güvenmemek gerektiğini gösteriyor.
- **Baseline-feasibility tanığı** (M5, `scripts/baseline_feasibility_witness.py`,
  MIP koşusu OLMADAN, 30.2s): B'nin "gap∈[L,U]⟹x=1 zorunlu" kuralı
  (VARSAYIM-6) sayesinde, TÜM zamanlar baseline'a sabitlendiğinde seçim
  ZORUNLU hale geliyor — bu, hiç solver çağırmadan bağımsız validator'la
  ucuza test edilebilir. Full data'da baseline'ın kendisi TÜM BEŞ kısıt
  ailesinde (A/E1/E2/F/G) eş zamanlı ihlalli (2048 toplam ihlal; A'nın
  487'si VARSAYIM-11 exemption'ıyla çapraz kontrol edilince büyük kısmı
  zaten-beklenen exempt-fail çıkıyor, ~144'ü gerçek "adjustment gerekli").
  **En büyük kategori E2 (1181)** — başlangıç şüphesi olan E1'den (296) bile
  fazla. Yorum: TEK bir suçlu kısıt değil, binlerce koordineli ayarlamanın
  eş zamanlı bulunması gereken bir arama-zorluğu problemi.

## Sayfa 6 · Kod Kalitesi Referansı + Sonuç Tartışması (Kriter 4 referans, Kriter 5)

- README'ye 1 cümle referans (tek komutla çalıştırma, determinizm testleri).
- Validator mimarisi: `src.model.*` import ETMEYEN bağımsız yeniden-hesaplama
  — neden bu bir "sigorta" (kod hatası ile validator hatası aynı anda aynı
  yönde yanılamaz).
- Sonuç tartışması: hangi kısıtların birbirini nasıl kısıtladığı (ör. E1'in
  amaç-bastırıcı etkisi, F'nin residual-capacity muhafazakarlığı), M6 için
  önerilen sonraki adımlar (kod yok, ayrı listede — bkz. kapanış raporu).

---

**Kaynak referansları** (rapor yazarken doğrudan alıntılanacak): `docs/model.md`
(formel gösterim), `ASSUMPTIONS.md` (VARSAYIM detayları), `docs/decisions.md`
(kronolojik karar günlüğü — hangi bug ne zaman bulundu), `docs/output_format.md`
(çıktı şeması), `runs/full_data_run_*.log.json` (full-data koşu kanıtı).

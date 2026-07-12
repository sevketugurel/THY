# M6 — Maliyet / Kazanç ve Sonraki Adımlar (kod yok)

Brief teslimi (2026-07-16) sonrası veya organizatör cevapları geldikten sonra
değerlendirilebilecek öneriler. M5c teşhisi ve M5d warm-start altyapısına dayanır;
hiçbiri bu repoda uygulanmış değildir.

---

## 1. Çözüm kalitesi (Kriter 2 — en yüksek etki)

| Öneri | Kazanç | Maliyet / risk | Öncelik |
|-------|--------|----------------|---------|
| **Warm-start + tam reward modeli** (Jbest Reals fix sonrası, `build_model_m4` + `derive_warm_start.py`) | İlk geçerli full-data incumbent; B&B'ye başlangıç noktası | 720s+ compute, E1/E2 ihlalli başlangıç noktasından temiz çözüme gidiş belirsiz | **P0** |
| **Gurobi akademik lisans** ile aynı modeli karşılaştırma | HiGHS'in kök-düğüm takılması solver mı model mi ayırır | Lisans temini; pip sürümü ~2K satır limiti yetersiz | **P0** (lisans varsa) |
| **Koordineli onarım** (greedy yerine bacak-paylaşımlı LP/MIP alt-problemi) | Baseline'dan fizibil noktaya gidiş; warm-start kalitesi | Yüksek implementasyon karmaşıklığı; hub ayrıştırılamaz (bacak paylaşımı) | P1 |
| **Elastic model + cezalandırılmış E1/E2 slack** (`constraints_elastic.py`) | Yapısal infeasible yerine "en az ihlal" çözüm | Slack'li çözüm brief'e uymayabilir; raporlama gerekir | P1 |
| **Adjustable-subset top-K** (merdiven step 2) | Kısmi pazar optimizasyonu, daha küçük MIP | K-subset yapısal olarak etkisiz bulundu (leg-sharing); sınırlı kazanç | P2 |

---

## 2. Hesaplama performansı (Kriter 3)

| Öneri | Kazanç | Maliyet / risk | Öncelik |
|-------|--------|----------------|---------|
| **Subprocess watchdog** (mevcut) | HiGHS zaman limiti güvenilirliği | Zaten uygulandı | — |
| **F bijective bucket equality** (mevcut) | Satır −%54, F satırları −%97 | Zaten uygulandı | — |
| **E2 singleton fold** (mevcut) | Binary −%20+ | LP gevşekliği neredeyse değişmedi | — |
| **D-folding** (beat elimination, mevcut) | Değişken −%35 | LP/tavan oranı değişmedi | — |
| **CPLEX / SCIP** alternatif solver | Farklı kesme-düzlemi davranışı | Yeni bağımlılık, lisans | P1 |
| **Daha agresif aday budama** (Modül-3 kapısı sıkılaştırma) | Daha küçük \|Π\| | Bağlantı ödülü kaybı; brief yorumu netleşmeli | P2 |
| **Zaman ızgarası (10 dk)** brute-force alt-problemler | Küçük pazarlarda kanıtlanmış optimum | Full ölçekte uygulanamaz | P3 (rapor referansı) |

---

## 3. Model doğruluğu / varsayımlar (Kriter 1)

Organizatör cevabına bağlı tek-nokta güncellemeler (`docs/organizer_questions.md`):

| Soru | Etki |
|------|------|
| VARSAYIM-9 (TK2841 / G küme-bazlı) | G kapsamı genişler veya daralır |
| VARSAYIM-10/11 (A rotasyon eşleştirmesi) | ~382 muaf çiftin statüsü |
| VARSAYIM-8 (K_od LS tahmini) | 575 pazarın journey constant kaynağı |
| VARSAYIM-12 (full-adjustable süre) | Resmi zaman bütçesi / kısmi çözüm kabulü |

**Senin katkın:** Organizatör sorularını gözden geçirip önceliklendirme; cevap gelince ilgili `ASSUMPTIONS.md` maddesini ve tek kod noktasını güncelleme.

---

## 4. Dokümantasyon ve teslim (Kriter 5)

| Görev | Durum | Kim |
|-------|-------|-----|
| `docs/report_outline.md` → 6 sayfalık PDF rapor | İskelet var, metin yok | **Sen** (yüksek değer) |
| `docs/organizer_questions.md` gönderimi | Liste hazır | **Sen** |
| Fixture 668.75 insan doğrulaması | Brute-force oracle yeşil | **Sen** (elle kontrol) |
| Full-data koşu logu + tablo (report §5) | M5c kanıt zinciri var | Rapor yazımında birleştir |
| README güncelleme (M5 durumu, `data_raw` kurulumu) | Kısmen eski | **Sen** |

---

## 5. Önerilen çalışma sırası (ekip için)

```
Adım 1  Ortam + fixture doğrulama          ← bugün yapıldı
Adım 2  data_raw/ dosyalarını yerleştir   ← gerçek veri deneyleri için
Adım 3  Warm-start full reward denemesi   ← scripts/derive_warm_start.py + ladder
Adım 4  Sonuçları rapor tablosuna işle    ← report_outline §5
Adım 5  M6 önerilerini rapora özetle      ← bu dosya
Adım 6  Organizatör sorularını gönder     ← VARSAYIM-9/10/12 öncelikli
Adım 7  Teknik rapor PDF                  ← teslim
```

---

## 6. Gerçekçi beklenti (M5c sonucu)

Full-adjustable modelin **tek solver / tek makine** ile 720s içinde geçerli bir
incumbent üretmemesi, beş bağımsız model/amaç denemesi + statik E1/E2
sertifikaları + greedy repair regresyonu ile tutarlı. Teslim stratejisi:

1. **Fixture:** 668.75 optimal, bağımsız doğrulanmış → güçlü kanıt.
2. **Full-data:** Teşhis raporu + warm-start kısmi ilerleme + organizatör soruları.
3. **Dürüst sınırlama:** "HiGHS bu problem sınıfında kök düğümden dallanamadı;
   Gurobi karşılaştırması lisans eksikliği nedeniyle yapılamadı" (`docs/decisions.md`).

Bu üçlü, rubrikte Kriter 2'yi zayıflatır ama Kriter 1 (model doğruluğu) ve
Kriter 5 (dokümantasyon) için güçlü bir hikâye sunar.

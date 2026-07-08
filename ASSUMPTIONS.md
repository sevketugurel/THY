# Varsayımlar (VARSAYIM)

Brief'in belirtmediği veya gerçek veride keşfedilen belirsizlikler; her biri organizatöre
sorulabilecek açık bir soru olarak işaretli. Cevap geldiğinde ilgili kod noktası (tek
nokta olacak şekilde tasarlandı) güncellenecek. Daha geniş açık-soru listesi için plan
§7'ye bakınız — bu dosya yalnızca **koda dokunan, kod içinde bir davranış kararına
dönüşmüş** varsayımları tutar.

---

## VARSAYIM-1: Yolcu Verisi'nde duplicate (orig,dest) satırları toplanıyor

**Bulgu**: `Yolcu Verisi_masked.xlsx`'te 12 satır, 6 farklı (orig,dest) çiftini
duplicate ediyor (ör. AGP-PEK iki kez: rho=569 ve rho=722):

```
orig dest  rho
AGP  PEK   569
AGP  PEK   722
AGP  VCE   509
AGP  VCE   494
PEK  AGP   45
PEK  AGP   627
PEK  VCE   73
PEK  VCE   548
VCE  AGP   424
VCE  AGP   956
VCE  PEK   364
VCE  PEK   185
```

**Karar**: `src/data/loaders.py::load_yolcu_verisi` bu satırları **rho toplamı** ile
tek satıra indirger (`groupby(["orig","dest"])["rho"].sum()`).

**Neden**: Şema dokümanı (orig,dest)'in unique key olduğunu ima ediyor ama gerçek
veri bunu ihlal ediyor. En makul yorum: bu satırlar aynı pazarın segmentlenmiş
(farklı kabin sınıfı / farklı zaman dilimi / farklı veri kaynağı) rho katkıları —
toplamak "pazarın toplam önemi" yorumuyla tutarlı ve veri kaybı yaratmıyor.
Alternatif yorumlar (ör. son satır kazanır, ilk satır kazanır, ortalama) veri kaybına
veya keyfi bir seçime yol açardı.

**Etki alanı**: `src/data/loaders.py::load_yolcu_verisi`, tek nokta. Cevap gelirse
(ör. "son giriş geçerlidir" ise) sadece bu fonksiyondaki `groupby(...).sum()` satırı
değişir.

**Organizatöre soru**: "Yolcu Verisi dosyasında bazı (orig,dest) çiftleri birden
fazla satırda tekrarlanıyor (farklı rho değerleriyle) — bu satırlar toplanmalı mı,
yoksa farklı bir anlamları mı var (ör. farklı zaman dilimi/kabin sınıfı)?"

---

## VARSAYIM-2: Yolcu Verisi'ndeki 3 eksik-dest satırı reddediliyor (silinmiyor)

**Bulgu**: `Yolcu Verisi_masked.xlsx`'te 3 satırın `Dest Airport Code` alanı boş,
ancak `rho` değerleri anlamlı büyüklükte (küçük/ihmal edilebilir değil):

```
orig  dest  rho
AGP   NaN   931
VCE   NaN   427
PEK   NaN   356
```

**Karar**: `load_yolcu_verisi` bu satırları **sessizce atmak yerine `SchemaError`
ile reddediyor** (pipeline durur, `--full-data` şu an bu yüzden çalışmıyor).

**Neden**: Proje kuralı ("loader'lar ... anlamlı hata mesajıyla düşer") boş
değerlerde sessiz davranmamayı gerektiriyor. rho değerleri küçük değil (356-931
aralığında, medyan civarında) — bu üç pazarın optimizasyon dışı bırakılması amaç
değerini fark edilir şekilde etkileyebilir; organizatör onayı olmadan atlamak riskli.

**Etki alanı**: `src/data/loaders.py::load_yolcu_verisi`, tek nokta (mevcut
`SchemaError` fırlatma satırı). Cevap gelirse iki olası değişiklik: (a) organizatör
"düşür" derse, `SchemaError` yerine `logger.warning` + drop'a çevrilir; (b) düzeltilmiş
resmi dosya gelirse loader değişmeden çalışır.

**Organizatöre soru**: "Yolcu Verisi dosyasında 3 satırda Dest Airport Code alanı boş
(Orig: AGP, VCE, PEK — rho: 931, 427, 356). Bu satırlar veri hatası mı, yoksa resmi
(maskelenmemiş) veri setinde dolduruluyor mu? Düzeltilmiş dosya paylaşılabilir mi,
yoksa bu satırları atlamamız mı bekleniyor?"

---

## VARSAYIM-3 (M1'de eklenecek): adjustable_window_min varsayılan değeri

Brief Standard senaryoda ayarlanabilir saatler için "herhangi bir sınır yok, gerekirse
tanımlanabilir" diyor — pratik/sonlu bir MIP için bir pencere config'ten tanımlanmak
zorunda. M1 tasarım notunda Big-M sıkılığı ile bu pencere boyutu arasındaki ilişki
türetildi; kesin varsayılan değer M1 onayıyla birlikte buraya işlenecek.

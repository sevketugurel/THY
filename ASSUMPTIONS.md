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

## VARSAYIM-3: adjustable_window_min = 180 dk (Standard senaryo)

**Bulgu**: Brief Standard senaryoda ayarlanabilir saatler için "herhangi bir sınır
yok, gerekirse tanımlanabilir" diyor — pratik/sonlu bir MIP için bir pencere
config'ten tanımlanmak zorunda. B kısıtının per-candidate Big-M türetimi
($M\approx O(4w)$, $w$=pencere) ile plan'ın kendi Big-M disiplini ("hiçbir M
1440'ı aşmamalı") arasında gerilim var: $w=720$ (ilk VARSAYIM) bazı adaylarda
$M>1440$ üretiyordu.

**Karar**: $w=180$ dk (3 saat) — hem Big-M'i güvenle $\le 1440$ tutuyor (elle
doğrulandı: `tests/unit/test_big_m.py::test_ms_never_exceed_1440_for_recommended_window`,
model kurulumunda da otomatik assert var) hem operasyonel olarak gerçekçi
(tarife redesign'da uçuşlar genelde birkaç saatten fazla kaymaz).

**Etki alanı**: `src/config/standard.yaml::adjustable_window_min`, tek nokta.
Organizatörden farklı bir pencere beklentisi gelirse (ör. "6 saat serbestlik
istiyoruz") sadece bu config değeri değişir; Big-M formülü otomatik olarak
yeni pencereye göre yeniden türetilir (data-derived, hardcode yok), sadece
$\le 1440$ assert'i o durumda tekrar kontrol edilmeli.

**Organizatöre soru**: "Ayarlanabilir saatler için pratik bir hareket penceresi
öngörüyor musunuz (ör. baseline ±kaç saat), yoksa bizim seçtiğimiz makul bir
varsayım (3 saat) kabul edilebilir mi?"

---

## VARSAYIM-4: "Rakip" = taşıyıcı (Cr1), aynı rakibin çoklu itineraryleri min T_comp'a konsolide edilir

**Bulgu**: O&D tablosunda bir rakip taşıyıcı (ör. gerçek veride Emirates/"EK")
aynı (o,d,gün) pazarında BİRDEN FAZLA satırda (farklı uçuş numarası
kombinasyonlarıyla) görünebiliyor. Brief, "rakip" (rival) kavramını net
tanımlamıyor — bir SATIR mı, yoksa bir TAŞIYICI mı?

**Karar**: Bir "rakip" TEK BİR TAŞIYICI (Cr1 kodu). O taşıyıcının o
(o,d,gün)'deki TÜM itineraryleri o rakibin PARÇASI (ayrı rakipler değil).
$N_{od,h}$ = o pazardaki DİSTİNCT Cr1 (TK hariç) sayısı.
$T^{comp}_{od,h,k}$ = carrier $k$'nin o pazardaki TÜM itinerarylerinin
gate-to-gate süresinin MİNİMUMU (rakibin EN İYİ/en hızlı alternatifi).

**Neden**: (a) D kısıtının "bir rakip ancak onu yenen en az bir bağlantı
sunuluyorsa yenilmiş sayılır" ifadesi, "rakip"in tek bir rekabetçi ANTİTE
olduğunu ima ediyor — aynı taşıyıcının 2 farklı uçuşu 2 AYRI rakip olarak
sayılırsa, N_od suni şekilde şişer. (b) TK bir rakibi yenmek için rakibin
EN HIZLI alternatifinden daha hızlı olmalı — aksi halde yolcu hala rakibin
daha hızlı seçeneğini tercih edebilir, gerçekte "yenilmiş" sayılmaz.

**Etki alanı**: `src/data/competitors.py::derive_rival_best_times`, tek nokta.
Alternatif bir tanım gelirse (ör. her itinerary ayrı rakip) bu fonksiyonun
groupby mantığı değişir, N_od/T_comp'u kullanan D kısıtı ve b_od derivasyonu
otomatik güncellenir (tek noktadan besleniyorlar).

**Organizatöre soru**: "Aynı rakip taşıyıcının bir O–D/gün pazarında birden
fazla itinerary'si varsa, bunlar N_od hesabında AYRI rakipler mi sayılmalı,
yoksa tek bir rakip (en iyi/en hızlı itineraryi ile temsil edilen) olarak mı
konsolide edilmeli?"

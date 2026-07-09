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

**UYGULANDI (2026-07-09, M5)**: organizatör cevabı gelmeden deadline'a
yetişmek için, önceden planlanmış (a) seçeneği uygulandı — `load_yolcu_verisi`
artık bir `strict: bool = True` parametresi alıyor. **Varsayılan (strict=True)
DEĞİŞMEDİ** — tüm mevcut çağıranlar (testler, `--fixture`) hâlâ SchemaError ile
loudly reddediyor. `main.py`'nin `--full-data` yolu AÇIKÇA `strict=False`
geçiyor — 3 satır `logging.warning` ile (sessiz DEĞİL, görünür) atılıyor. Bu,
organizatör cevabı gelene kadar geçici bir köprü; cevap gelirse (b)'ye veya
farklı bir karara geçilecek.

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

---

## VARSAYIM-5: A rotasyon kısıtı yalnızca IST'e değen ARDIŞIK bacaklara uygulanıyor

**Bulgu**: `Flight Pairs.xlsx`'teki Pair gruplarının çoğu (657/707) tam 2
üyeli (basit IST→o, o→IST round-trip). Ancak 50/707 grup 3+ üyeli, ve
incelenen bir örnekte (`Pair=181`) yapı **IST→MEX→CUN→IST** şeklinde —
ORTADAKİ bacak (MEX→CUN) IST'e HİÇ DEĞMİYOR.

**Karar**: A rotasyon kısıtı yalnızca bir Pair grubu içindeki ARDIŞIK
(Orig==IST → sonra Dest==IST) bacak çiftlerine uygulanıyor. IST'e değmeyen
ara bacaklar (ör. MEX→CUN) modelin karar değişkeni kapsamı DIŞINDA (model
yalnızca IST'e gelen/IST'ten giden uçuşların saatlerini ayarlıyor) — bu
bacaklar için rotasyon kısıtı KURULMUYOR.

**Neden**: Modelin `t_arr`/`t_dep` değişkenleri yalnızca IST tarafındaki
zamanları temsil ediyor (brief'in kapsamı da bu — "ayarlanabilir uçuşların
IST kalkış/varış saatleri"). MEX→CUN gibi bir bacağın kendi zamanları hiç
modellenmiyor, dolayısıyla o bacağın rotasyon-uygunluğunu (uçağın MEX'te
yeterli yer süresi bulup bulamadığını) kontrol edecek bir mekanizma yok.

**Etki**: Bu tip çoklu-duraklı rotasyonlarda (grupların küçük bir azınlığı,
≤50/707) A kısıtı EKSİK kalıyor — model bu rotasyonların fiziksel
gerçekleştirilebilirliğini garanti ETMİYOR. `src/model/constraints_operations.py::build_rotation_pairs`
ve `src/validate/independent_validator.py::_rotation_subpairs` bu senaryoyu
sessizce atlıyor (ne kısıt kuruluyor ne ihlal raporlanıyor).

**Organizatöre soru**: "Flight Pairs'teki 3+ üyeli gruplar (ör. IST→MEX→CUN→IST)
gerçek çoklu-duraklı rotasyonlar mı? Bu durumda ara bacağın (MEX→CUN) zamanı
sabit mi kabul edilmeli, yoksa bu tip rotasyonlar için ayrı bir modelleme
yaklaşımı mı bekleniyor?"

---

## VARSAYIM-6: E1 "bağıl dengesizlik" formülü

**Bulgu**: Brief "İki yöndeki sunulan bağlantı sayıları arasındaki bağıl
dengesizlik α eşiğini aşmamalı" diyor ama KESİN formülü vermiyor.

**Karar**: $|n_{fwd} - n_{bwd}| \le \alpha \cdot (n_{fwd}+n_{bwd})$, her
$(o,d,h)$ vs $(d,o,h)$ çifti için AYRI AYRI (gün bazında, TOPLAM değil).
Yalnızca HER İKİ yönde de en az bir candidate'ı olan pazar çiftlerine
uygulanır — tek-yönlü pazarlar (bwd modelin kapsamı dışındaysa) atlanır
(aksi halde fwd'nin de SIFIRA zorlanması gerekirdi, ki bu modelin kendi
kapsam sınırlamasından kaynaklanan YAPAY bir kısıtlama olurdu, gerçek bir
dengesizlik değil).

**Neden**: "Bağıl dengesizlik" (relative imbalance) ifadesi standart
$|a-b|/(a+b) \le \alpha$ formuna en yakın yorum; iki-yönlü lineer eşitsizliğe
(Big-M gerekmeden) doğrudan çevrilebiliyor. Gün bazında (toplam değil) seçimi,
brief'in $r_{od,h}$ gibi diğer TÜM formüllerinin de $h$ indeksli olmasıyla
tutarlı.

**Kritik davranışsal etki** (`docs/model.md` E1 bölümüne işlendi): B'nin
"gap∈[L,U] ise x=1 ZORUNLU" kuralı nedeniyle, E1'i sağlamanın YEGANE yolu
bir bağlantıyı KISMEN gizlemek DEĞİL (B tarafından yasaklı), zamanı kaydırıp
gap'i [L,U] dışına iterek bağlantıyı TAMAMEN ÖLDÜRMEKTİR. Küçük/asimetrik
pazarlarda bu, E1'in bir "amaç bastırıcı" olmasına yol açabilir — solver tek
bir fazla bağlantıyı dengelemek yerine TÜM pazarı sıfırlamayı (kendiliğinden
sağlanan durum) tercih edebilir. `e1_diagnostics` bu davranışı post-solve
izler (kaç pazar sıfıra indi).

**Organizatöre soru**: "E1'in kesin formülü nedir — bağıl dengesizlik
$|n_{fwd}-n_{bwd}|/(n_{fwd}+n_{bwd})$ mi, yoksa farklı bir tanım mı? Gün
bazında mı yoksa dönem toplamında mı uygulanmalı? Yalnızca tek yönde
candidate'ı olan pazarlar (modelin kapsam sınırlaması nedeniyle) E1'den
muaf mı sayılmalı?"

## VARSAYIM-7: F rezidüel kapasite -- kapsam-dışı TK bacakları kendi baseline'ında SABİT kabul edilir

**Bulgu**: Hub kapasitesi (F, kova/kapasite bağlama) TÜM TK trafiğini
paylaşıyor — hem modelin ayarlanabilir değişkeni OLAN uçuşları hem de
OLMAYANLARI (ör. achievable-range kapısını hiçbir eşleşmede geçemeyen bir
flno, ya da M5'in adjustable-subset modunda dışarıda bırakılan uçuşlar).
İkinci grup modelin hiç `t_arr`/`t_dep` değişkeni değil — kapasiteye
katkılarını nasıl hesaba katacağımız açık değil.

**Karar**: kapsam-dışı her TK bacağı, kendi HAM (baseline) O&D tablosu
zamanında SABİT olarak hub kapasitesini işgal ettiği kabul edilir —
`src/model/constraints_capacity.py::compute_out_of_scope_baselines` (ham
tabloyu tam tarar, model kurulmadan önce BİR KEZ) +
`compute_residual_capacity` (o zamana denk gelen kovadan kapasiteyi düşer).
Bu rezidüel kapasite, F'in z-binary'lerinin karşılaştığı GERÇEK kapasite
tavanı olur (`capacity_departure`/`capacity_arrival` - kapsam-dışı işgal).

**Neden**: Kapsam-dışı bir uçuşun GERÇEKTE modelin hiç dokunmadığı (ayarlama
kolu olmayan) bir zamanı var — onu "yok" saymak (kapasiteden hiç düşmemek)
hub'ın fiziksel doluluğunu hafife alır ve modelin GERÇEKTE ulaşılamaz
kapasiteyi ayarlanabilir uçuşlara vaat etmesine yol açar (aşırı-iyimser,
gerçek dünyada uygulanamaz bir çözüm). Baseline'da sabit kabul etmek en
muhafazakar/doğru varsayım — modelin bilmediği bir şeyi TAHMİN etmiyor,
sadece VERİDEKİ GÖZLEMLENMİŞ değeri kullanıyor.

**Etki**: A'nın rotasyon kısıtı da AYNI kapsam-dışı-baseline verisini
paylaşıyor (edge case: bir Flight Pair alt-çiftinin bacaklarından biri
kapsam dışıysa, rotasyon kısıtı yine de in-scope bacağa, kapsam-dışı
ortağın SABİT baseline'ına karşı kurulur — `build_rotation_pairs`'in
`partial_pairs` çıktısı, bkz. `tests/solve/test_m3_constraints_a.py::test_rotation_applies_against_out_of_scope_*`).

**Organizatöre soru**: "Modelin ayarlayamadığı (kapsam dışı) TK uçuşları
için hub kapasitesi hesabında nasıl bir varsayım yapılmalı — kendi mevcut
tarifelerinde sabit mi kabul edilmeli, yoksa organizatörün başka bir resmi
kapasite-tahsis verisi mi var?"

## VARSAYIM-8: K_od yoksa T_IB+T_OB LS-tahminine düşülüyor (575/1329 pazar full data'da doğrudan gözlenemiyor)

**Bulgu**: `BlockTimeProvider.get_journey_constant(o,d)`, o pazar için EN AZ
BİR TK satırının geçerli ([L,U]) gap'e sahip olmasını gerektiriyor (medyan
alınacak kaynak satır). Full data'da (M5 boyut bütçesi sırasında bulundu)
805 TK O-D pazarının 1.329 aday-pazarından (candidate generation sonrası,
ρ-filtresi öncesi) **575'inde HİÇBİR baseline satırı [L,U] içinde değil**
(o pazar yalnızca ayarlanabilir pencere sayesinde bir aday üretiyor) — bu
pazarlarda `get_journey_constant` `KeyError` fırlatıyor, D/E2'nin objektifi
hesaplayamamasına yol açıyor.

**Karar**: `R_o`'nun kendi LS sistemi zaten HER istasyon için `T_IB_x`/`T_OB_x`
BİREYSEL tahminlerini üretiyor (önceden yalnızca `R_o=T_IB_x+T_OB_x`
toplamı için kullanılıyordu, ayrı raporlanmıyordu). Yeni
`get_journey_constant_estimate(o,d) = T_IB_o + T_OB_d` bu tahminleri
doğrudan pazar-kombinasyonu için kullanıyor. `main.py`, direkt medyan
başarısız olursa (KeyError) bu fallback'e düşüyor; o da başarısız olursa
(istasyon LS ağında HİÇ görülmemiş) o pazarın candidate'ları modelden
düşürülüyor (VARSAYIM, aşağıda).

**Neden matematiksel olarak sağlam**: `T_IB_o+T_OB_d` kombinasyonu, `R_o`'nun
KENDİ shift-invariance kanıtıyla AYNI mantıkla shift-invariant — bağlı bir
bileşende TÜM `T_IB_x`'lere `+c`, TÜM `T_OB_x`'lere `-c` uygulamak HER satır
denklemini (`T_IB_o+T_OB_d=k`) değişmez bırakıyor, bu yüzden `o+d`
kombinasyonu `o+o` (R_o) kombinasyonu kadar KESİN kurtarılabilir (ridge
pinleme'nin BİREYSEL değerleri etkilemesi R_o için zararsız olduğu gibi,
burada da zararsız — toplam/kombinasyon değişmiyor). Doğrudan gözlemlenen
bir pazarda fallback tahmini medyan-bazlı K_od ile UYUŞUYOR (test:
`test_journey_constant_estimate_matches_direct_when_directly_observed`).

**Etki**: fallback'in KENDİSİ de başarısız olursa (istasyon hiçbir role'de
hiç LS ağında yoksa) o pazarın TÜM candidate'ları D/E2 hesaplayamayacağından
modelden düşürülüyor — VARSAYIM, bu pazarların connection_reward'ı (B/C,
K_od'a bağlı değil) da kaybediliyor demek, ama bu istisna full data'da
NADİR (ağ neredeyse tamamen bağlı, bkz. `runs/`'daki full-data log'u).

**Organizatöre soru**: "775 O-D pazarının 575'i için gate-to-gate uçuş
süresi hiçbir mevcut tarifede [L,U] penceresine denk gelmiyor (yalnızca
ayarlanabilir senaryoda ulaşılabilir). Bu pazarlar için resmi bir K_od
(gate-to-gate uçuş süresi sabiti) verisi var mı, yoksa ağ-genelinde
istasyon-bazlı bir tahmin (bizim LS yaklaşımımız gibi) kabul edilebilir mi?"

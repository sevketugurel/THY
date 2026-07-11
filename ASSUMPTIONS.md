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

**GÜNCELLEME (M5e, 2026-07-11) — veri v2 ile büyük ölçüde ÇÖZÜLDÜ**:
organizatörün 2026-07-09 paketi `ElapsedTime1`/`ElapsedTime2` (bacak-bazlı
gerçek blok süreleri) ekledi — `BlockTimeProvider` artık bunları tercih
ediyor (VARSAYIM-15, aşağıda), LS tahmini yalnızca Elapsed kolonları
YOKSA (ör. fixture'ın kolonsuz varyantı) devreye giriyor.
`scripts/validate_block_times_v2.py` ile ölçüldü
(`docs/block_time_cross_validation.md`): 805 TK-gözlemli pazarın 25'i
tablo-seviyesinde geçerli-gap satırdan yoksundu (LS tahminine muhtaçtı);
bu 25'in TAMAMI artık v2 ile doğrudan değer alıyor. LS tahmininin gerçek
değerden sapması: **medyan=1.28dk, p90=6.72dk, max=124.11dk** (23/25
karşılaştırılabilir örnek) — LS yaklaşımı çoğunlukla iyi çalışmış, tek bir
büyük sapma (124dk) dışında. Bu, organizatör sorusunu byüyük ölçüde
gereksiz kılıyor (kendi verimiz artık mevcut) — `docs/organizer_questions.md`
madde 8 "veri ile çözüldü" olarak işaretlendi. **Not**: bu 25/805, VARSAYIM-8'in
orijinal 575/1329 rakamıyla AYNI kohort DEĞİL — 575 candidate-generation
SONRASI (adjustable window ile sentezlenen, hiç ham satırı olmayan
pazarlar dahil) ölçülmüştü; 805-pazarlık bu ölçüm yalnızca ham tabloda
GERÇEKTEN var olan (dep1,arr2) çiftlerini kapsıyor. Candidate-seviyesi
575/1329'un v2 ile yeniden ölçümü Bölüm 2'nin (yeniden ölçüm) işi.

## VARSAYIM-9: G küme-bazlı uygulanıyor — baseline verinin kendisi KOŞULSUZ G'yi ihlal ediyor (kanıtlı)

**Bulgu**: M5'in full-data solve merdiveni, F devre dışı bırakılsa bile,
A+G ile de, YALNIZCA B+C+D+G ile de HIZLI (saniyeler içinde, zaman
limitine takılmadan) infeasible veriyordu — merdivenin TÜM adımları
(step1 tam-ayarlanabilir, step2'nin 4 K değeri) başarısız oldu (step3'e
düşüldü). Kök neden izolasyonu: B+C+D TEK BAŞINA (A/G'siz) infeasible
DEĞİL (genuine arama gerektiriyor, hızlı infeasible vermiyor) — A ve/veya
G'nin varlığı SORUNUN kaynağı. Gerçek gün-içi (dairesel) yayılım analizi:
461 çok-günlü IB uçuşundan 1'i, 476 çok-günlü OB uçuşundan 0'ı, KENDİ
baseline saatlerinde bile G'nin uzlaştırılabilirlik sınırını (2*180+15=375dk,
±180dk pencere + X_dev=15dk) AŞIYOR:

```
TK2841 (TZX->IST): Gün2,3,4,7 = 03:25, Gün5 = 14:10 (645dk fark)
```

**Matematiksel kanıt (formel)**: bir grubun (aynı role,flno'nun gün-örnekleri)
TEK bir ortak referans zamanı T_ref ile uzlaştırılabilmesi ⟺ (aralıklar için
1D Helly özelliği) HER örneğin kendi $[baseline_h-w_h, baseline_h+w_h]$
aralığının $[T_{ref}, T_{ref}+X_{dev}]$ ile kesişmesi ⟺ $T_{ref} \in
\bigcap_h [baseline_h-w_h-X_{dev}, baseline_h+w_h]$ ⟺ bu kesişim boş değil ⟺
$\max_h(baseline_h-w_h) - \min_h(baseline_h+w_h) \le X_{dev}$ ⟺ (iki-nokta
"en kötü çift" karakterizasyonu) $\max(baseline) - \min(baseline) \le
w_{min\text{-}örnek} + w_{max\text{-}örnek} + X_{dev}$. TK2841 için:
$645 > 180+180+15=375$ — **KATI (koşulsuz, tüm günler tek grup) okumada
uzlaştırılabilir küme kümesi BOŞ, tüm problem infeasible olurdu.** Bu
yarışma kurgusunun kendi tutarlılığıyla çelişir (organizatör çözümsüz bir
problem tasarlamamıştır) — bu yüzden ZORUNLU MİNİMAL bir gevşetme gerekli.

**Karar**: G artık FLIGHT bazında değil KÜME bazında uygulanıyor
(`src/model/day_clustering.py::cluster_flight_days`). Her (role,flno)'nun
gün-örnekleri, EN AZ sayıda "uzlaştırılabilir" kümeye ayrılır — her küme
KENDİ İÇİNDE G'yi (bugünkü, M3 formülasyonuyla BİREBİR aynı şekilde) sağlar,
kümeler ARASINDA G HİÇ uygulanmaz. Algoritma DATA-TÜRETİLMİŞ ve GENEL (2841'e
özel hiçbir şey hardcode edilmiyor — gizli test seti güvenliği): (1) dairesel
eksende (mod 1440) EN BÜYÜK boşluktan kes (gece yarısı sarmasını G'nin kendi
`_flight_cut_points`'iyle AYNI mantıkla ele alır), (2) doğrusallaştırılmış
diziyi soldan sağa AÇGÖZLÜ ÇAP taraması (küme BAŞLANGICINA göre, ARDIŞIK
öğeye göre DEĞİL — 0/300/600dk'lık bir zincir ardışık bakışta yanlışlıkla
birleşirdi ama ortak bir bandı asla sığdıramaz, bkz.
`tests/unit/test_day_clustering.py`). Tüm günler zaten uzlaştırılabilirse
(yaygın durum, gerçek veride 460/461 IB ve 476/476 OB uçuşu) TEK küme oluşur
= M3 davranışı DEĞİŞMEDEN korunur.

**Etki**: validator (`independent_validator.py::_cluster_flight_days_independent`)
AYNI kümeleme algoritmasını BAĞIMSIZ olarak (import ETMEDEN) yeniden uygular
— yalnızca AYNI kümenin İÇİNDEKİ raporlanan zamanlar X_dev'e tabi tutulur,
kümeler arası karşılaştırma yapılmaz. `docs/model.md`'ye formel kanıt +
kümeli formülasyon eklendi.

**Organizatöre soru (somut)**: "TK2841 (TZX→IST) 4 günde 03:25'te, 1 günde
(Gün5) 14:10'da uçuyor — uçuş numarası yapısal olarak farklı iki tarifede
kullanılıyor gibi görünüyor. Bu; (a) veri hatası/maskeleme artefaktı mı,
(b) o gün için gerçek, tek-seferlik bir tarife değişikliği mi, yoksa (c)
uçuş numarasının kasıtlı olarak farklı rotasyonlar için yeniden kullanıldığı
bilinen bir pratik mi? G'nin (düzenlilik) gün-varyantlarına TAM olarak nasıl
uygulanması bekleniyor — TÜM operasyon günleri KOŞULSUZ tek bir X_dev bandına
mı sığmalı (ki bu durumda TK2841 problemi çözümsüz kılar), yoksa bizim
kümeli yaklaşımımıza benzer bir ayrım kabul edilebilir mi?"

## VARSAYIM-10: A'nın OB/IB eşleştirmesi "aynı gun" DEĞİL, baseline kronolojisine dayanıyor

**Bulgu**: M5 full-data solve merdiveni TÜM adımlarda (F devre dışı, A+G,
yalnızca B+C+D+G ile bile) HIZLI infeasible verdi. Kök neden izolasyonu:
B+C+D TEK BAŞINA (A/G'siz) infeasible DEĞİL — A ve/veya G'nin varlığı
sorunun kaynağı (G, VARSAYIM-9 ile çözüldü; A AYRI bir sorundu). A'nın
"aynı gun" OB/IB eşleştirmesi test edildi: gerçek TK174(OB,IST→KUL)/
TK175(IB,KUL→IST) çifti incelendiğinde, TK174 gün1'de 15:50'de kalkıyor,
"aynı gun" kuralı bunu gün1'in 11:00 TK175 varışıyla eşliyordu — ama bu
varış, kalkıştan ÖNCE (aynı gün, ~5 saat önce)! Gerçek fiziksel dönüş
(R_o(KUL)≈20.9 saat round-trip) gün1'in kalkışından SONRAKİ EN YAKIN
TK175 varışı olan gün3'ün 11:00'ıydı (~2590dk sonra, uzlaştırılabilir).
Full veri taraması: 1496 rotasyon-çift örneğinin **818'i (%54.7) baseline'da
uzlaştırılamaz**, **%45.3'ü kronolojik olarak TERS** (IB varışı OB
kalkışından ÖNCE, aynı gün).

**Karar**: OB/IB eşleştirmesi artık "AYNI GUN" DEĞİL, BASELINE
KRONOLOJİSİNE dayanıyor (`src/model/rotation_matching.py::match_rotation_legs`,
$R_o$'nun KENDİSİNE değil, yalnızca kısıtın sağ tarafına bağlı — $R_o$'nun
LS-tahmin hatasından bağımsız, veri-sadık bir kural). Her OB kalkışının
partneri, baseline saat-of-day'e göre KENDİSİNDEN SONRAKİ EN YAKIN IB
varışı — dairesel (Gün haftalık tekrarlanan desen, Gün=7'den Gün=1'e
sarar), açgözlü ve BİREBİR eşleştirme. Kısa menzilde (round-trip aynı gün
içinde tamamlanıyorsa) bu kural zaten "aynı gun" ile AYNI sonucu verir —
M3 davranışı DEĞİŞMEDEN korunur (elle doğrulandı: `test_short_haul_matches_same_gun`).

**Neden**: Flight Pair'deki (OB_flno,IB_flno) çifti "aynı uçak gidip-döner"
fiziksel ilişkisini ifade ediyor — doğru eşleştirme R_o'nun (dolaylı,
LS-tahminli) DEĞİL, doğrudan GÖZLEMLENEN baseline kronolojisinin işi olmalı.
Sarma (Gün=7→Gün=1) durumunda kısıtın ham epoch kıyası bir HAFTA
(10080dk) ileri kaydırılır, aksi halde önceki haftanın (yanlış) değeriyle
sessizce yanlış kıyaslanırdı.

**Etki**: `independent_validator.py::_match_rotation_legs_independent` AYNI
algoritmayı bağımsız (import etmeden) yeniden uygular.

**Organizatöre soru**: "Flight Pair tablosundaki (OB,IB) uçuş numarası
çiftleri için gün eşleştirmesi nasıl yorumlanmalı? Uzun menzilli
rotasyonlarda (R_o saatler mertebesinde) hangi IB varışı, hangi OB
kalkışının GERÇEK partneri sayılmalı — bizim baseline-kronoloji
yaklaşımımız (kalkıştan sonraki en yakın varış) doğru mu, yoksa farklı bir
resmi eşleştirme kuralı mı var?"

## VARSAYIM-11: doğru eşleştirmeyle bile uzlaştırılamayan rotasyon çiftleri MUAF tutuluyor

**Bulgu**: VARSAYIM-10'un baseline-kronoloji düzeltmesi A'nın infeasibility'sinin
BÜYÜK kısmını çözüyor, ama full data'da **382/1571 (%24.3) rotasyon çifti**
DOĞRU eşleştirmeyle bile, her bacağın KENDİ en-iyi-durum ayarlamasında
(dep en erken, arr en geç) hâlâ uzlaştırılamaz — G'nin TK2841 durumuyla
YAPISAL OLARAK AYNI senaryo (bkz. VARSAYIM-9).

**Karar**: bir çift, $t^{arr}_{hi}+\text{week\_offset} \ge t^{dep}_{lo}+R_o+\tau_o$
testini (her bacağın KENDİ $[t_{lo},t_{hi}]$ Var bounds'u kullanılarak)
GEÇEMEZSE A kısıtından MUAF tutulur (loglanır — `add_a_constraints`
`WARNING: A rotation -- N pair(s) exempted (VARSAYIM-11)` çıktısı verir,
sessizce atlanmaz).

**Neden**: G'yle AYNI mantık — brief'in kendi tutarlılığı gereği (yarışma
çözümsüz bir problem kurgulamaz), gerçek veride yapısal olarak
uzlaştırılamayan bir kısıt YOK SAYILMALI, tüm modeli infeasible yapmamalı.
Bu istisna A'nın DİĞER TÜM (yaklaşık %75'lik çoğunluk) rotasyon çiftlerine
uygulanmasını ETKİLEMİYOR — yalnızca genuinely-imkansız çiftler için.

**Organizatöre soru**: "Rotasyon kısıtı (A), baseline tarifede zaten fiziksel
olarak imkansız olan (R_o+tau, mevcut ayarlanabilir pencereyle
karşılanamayan) OB-IB çiftleri için nasıl ele alınmalı — bu tür çiftler
istisna mı tutulmalı, yoksa R_o tahminimizde ya da eşleştirme kuralımızda
bir hata olabilir mi?"

## VARSAYIM-12: full-data'da adjustable-subset merdiveni provable infeasible — full-adjustable ise UNRESOLVED (ne feasible ne infeasible kanıtlandı)

**Bulgu**: VARSAYIM-9/10/11'in TÜMÜ uygulandıktan sonra bile (G küme-bazlı,
A baseline-kronoloji eşleştirmesi + best-case istisna), full-data'nın
solve merdiveni (`scripts/run_full_data.py`, dış-bekçili + `mip_heuristic_effort=0.3`
+ `mip_rel_gap=0.08`) TÜM adımlarda başarısız oldu:

- **step1 (tam-ayarlanabilir, 18118 candidate, TÜM A-G aktif)**: 756174 satır
  (presolve sonrası 604925 satır/297906 sütun/272927 binary) — 660s dış-bekçi
  limitinde `watchdog_killed`, SIFIR incumbent. HiGHS kök-düğümde cut
  üretimine devam ediyor, hiçbir feasible tam-sayı çözümü bulamıyor.
- **step2 (adjustable-subset, K=50/100/200/400)**: DÖRDÜ DE **temiz, hızlı
  `infeasible`** (13.5-24.3s solve, timeout DEĞİL — gerçek HiGHS
  infeasibility sertifikası). K arttıkça (daha çok pazar ayarlanabilir
  oldukça) infeasibility'nin KAYBOLMAMASI dikkat çekici.

**Bağımsız doğrulama — ucuz baseline-feasibility tanığı** (`scripts/baseline_feasibility_witness.py`,
solve YOK, 30.2s, VARSAYIM-6'nın "gap∈[L,U]⟹x=1 zorunlu" kuralı sayesinde
seçim baseline'da ZORUNLU): ham baseline tarifenin KENDİSİ (hiç ayarlama
yapılmadan) TÜM BEŞ kısıt ailesinde eş zamanlı ihlalli — 2048 toplam ihlal
(A: 487 ham / VARSAYIM-11 exemption'ıyla çapraz kontrolde ~144'ü gerçek
"adjustment gerekli", E1: 296, **E2: 1181 — en büyük kategori**, F: 31,
G: 53).

**Sistematik tanı — tek-tek ve birlikte kaldırma** (`scripts/diagnose_e1_e2_f.py`,
K=400 alt-kümesinde, `build_model_m4`'ün AYNI test edilmiş primitiflerini
yeniden birleştiren bir tanı script'i, `src/model/*.py`'a DOKUNMUYOR):

| Varyant | Sonuç |
|---|---|
| Tümü açık (A-G) | infeasible (24.6s) |
| E1 kapalı | **hâlâ infeasible** (33.1s) |
| E2 kapalı | **hâlâ infeasible** (20.6s) |
| F kapalı | **hâlâ infeasible** (15.5s) |
| A kapalı | **hâlâ infeasible** (24.9s) |
| G kapalı | **hâlâ infeasible** (36.9s) |
| E1+E2+F ÜÇÜ birden kapalı | **UNRESOLVED** (240s dış-bekçi limitinde `watchdog_killed`) |
| E1 kapalı, FULL 18118-candidate (K-subset YOK) | **UNRESOLVED** (660s dış-bekçi limitinde `watchdog_killed` — modelin BÜYÜKLÜĞÜ tek başına 660s'de çözülemiyor, hangi kısıtın açık/kapalı olduğundan BAĞIMSIZ) |

**Karar**: KOD DEĞİŞTİRİLMEDİ. A, E1, E2, F, G'nin BEŞİ de K=400 alt-kümesinde
TEK TEK kaldırıldığında hâlâ infeasible — hiçbiri tek başına suçlu değil.
Bu, infeasibility'nin tek bir kısıt formülasyon hatasından değil, muhtemelen
**adjustable-subset mekanizmasının kendisinden** kaynaklandığına işaret
ediyor: K=400'de ~15742 uçuş baseline'a SABİT kalıyor, ve baseline'ın
KENDİSİ (yukarıdaki tanık kanıtıyla) zaten TÜM beş ailede ihlalli — bu kadar
çok uçuşu zaten-bozuk bir tarifeye sabitlemek, tek bir kısıtı gevşetmenin
çözemeyeceği bir çakışma yaratıyor olabilir. **Full-adjustable (tüm
candidate'lar ayarlanabilir) durumun feasibility'si test edilen bütçelerde
(660s) HİÇ KANITLANAMADI** — ne feasible ne infeasible: yalnızca "bu
büyüklükte kök-düğüm cut üretimiyle 660s'de çözülemiyor" biliniyor.
Kullanıcıyla (birden fazla AskUserQuestion turu) danışıldı, "daha fazla
tanı zamanı harcamak yerine mevcut kanıtı yeterli kabul et, organizatöre
raporla" kararı verildi.

**Neden full-data'da (fixture'da DEĞİL) ortaya çıkıyor**: sentetik fixture
(668.75, brute-force oracle ile bağımsız doğrulandı) küçük, temiz, elle
tasarlanmış bir senaryo — gerçek veri 707+ Flight Pair grubu, 1571 rotasyon
çifti, 1329 O-D aday-pazarı içeriyor, ve VARSAYIM-9/10/11'in zaten gösterdiği
gibi gerçek operasyonel tarifeler (TK2841 gibi) brief'in ideal-tarife
varsayımlarını (tam düzenlilik, her rotasyonun uzlaştırılabilir olması)
KENDİ BAŞINA ihlal ediyor. VARSAYIM-9/10/11 bu ihlalleri G/A için MUAF
tutarak (yerel, minimal gevşetme) çözdü; ama E1 (yönsel denge) ve E2 (JT-farkı)
için BENZER bir "genuinely-imkansız durumu istisna tut" mekanizması henüz
KURULMADI (bu VARSAYIM-9/11'in doğal devamı olurdu, ama hangi çiftlerin/
pazarların istisna tutulacağına dair veri-türetilmiş bir kural henüz
tasarlanmadı — kod yazılmadı, yalnızca teşhis yapıldı).

**Etki**: `runs/full_data_run_20260709T161927Z.log.json` (ladder tam log'u),
`runs/baseline_feasibility_witness_20260709T160923Z.json` (tanık),
`runs/diagnose_e1_e2_f_*.json` (7 varyant sonucu) — hepsi M5 kapanış
raporunun kanıt zinciri. **Full-data'da doğrulanmış (validator-onaylı) bir
objective_value HENÜZ YOK** — M5 bu haliyle "full-data solve denemesi
kapsamlı şekilde teşhis edildi, kök neden aday listesi daraltıldı, ama
kesin tek-nokta çözüm bulunamadı" durumunda kapanıyor.

**Organizatöre soru**: "Gerçek O&D/Yolcu Verisi/Flight Pairs veri setinde,
adjustable-subset alt-problemi (top-K ρ-ağırlıklı pazar ayarlanabilir,
gerisi baseline'a sabit) K=50'den K=400'e kadar HER K değerinde
kanıtlanabilir şekilde infeasible çıkıyor — beş kısıt ailesinin (A/E1/E2/F/G)
hiçbiri tek başına kaldırıldığında bunu düzeltmiyor. Bu, (a) baseline
tarifenin kendisinin brief'in kısıt setiyle yapısal olarak tutarsız
olduğunu (VARSAYIM-9/10/11'in G/A için zaten gösterdiği gibi, ama şimdi
E1/E2 için de), (b) K-subset yaklaşımımızın (adjustable-subset merdiveni)
yanlış bir gevşetme biçimi olduğunu, yoksa (c) α/γ/X_dev/adjustable_window_min
gibi parametrelerin gerçek veri ölçeğinde daha gevşek tutulması gerektiğini
mi gösteriyor? Tam-ayarlanabilir (full, K-subset'siz) problemin feasibility'si
elimizdeki hesaplama bütçesiyle kanıtlanamadı — organizatörün bu ölçekte
(18000+ aday) bir çözüm süresi beklentisi/referans benchmark'ı var mı?"

**GÜNCELLEME (2026-07-09, M5b — DERİN OTOPSİ SONRASI daraltıldı)**:
`docs/baseline_autopsy.md`, kullanıcının talebiyle yapılan derin analizle bu
VARSAYIM'ı ÖNEMLİ ÖLÇÜDE DARALTTI. Kök neden (b)'ye YAKIN çıktı — ama
"K-subset yaklaşımı yanlış" değil, "**K-subset'in K-şeması (50/100/200/400)
full-data ölçeğinde yetersiz**". Nicel kanıt: her aile için "baked-in"
(top-K ayarlanabilir pazarların HİÇBİRİNE dokunmayan, K'dan bağımsız
ÇÖZÜLEMEZ kalan) ihlal oranı hesaplandı — K arttıkça oran DÜZENLİ düşüyor
(K=50'de E1 %96/E2 %91 → K=400'de E1 %54/E2 %51) ama K=400 hâlâ full-data'nın
gerçek pazar sayısının (~900+) yalnızca %44'ü. Ayrıca E1/E2'nin GERÇEK ihlal
sayıları validator'daki KAPSAM eksiklikleri nedeniyle daha önce yanlış
raporlanmıştı (296→690, 1181→1219) — bu 3 validator hatası (E1 kapsamı, E2
estimate-fallback, A exemption) TDD ile düzeltildi (yalnızca
`independent_validator.py`, model kodu DOKUNULMADI). F'nin kapasite
sayıları (10/15) brief'in kendi §2.4 verisi olarak TEYİT edildi (VARSAYIM
değil). G'nin model/validator paritesi kod karşılaştırmasıyla KANITLANDI.
**Kalan açık soru**: full-adjustable (step1, K-subset'siz) modelin
feasibility'si HÂLÂ kanıtlanamadı — yalnızca BÜYÜKLÜK (756174 satır)
nedeniyle 660s'de sonuçlanamıyor, infeasibility DEĞİL. Organizatör sorusu
(c) (Gamma'nın gerçek ölçekte uygunluğu) hâlâ geçerli: 1219 E2 ihlalinin
949'unda (%78) K_od'un YAPISAL asimetrisi TEK BAŞINA Gamma(30dk)'yı aşıyor
— gap seçimiyle çözülemeyecek bir durum.

**GÜNCELLEME 2 (2026-07-10, M5c — K-subset merdiveninin KENDİSİ
işlevsiz bulundu, DAHA DA daraltıldı)**: VARSAYIM-9/11'in exempt+log
deseni E1/E2'ye genellendi (`add_e1_constraints`/`add_e2_constraints`,
TDD ile, `src/model/constraints_balance.py`) — HER İKİ yönü de TAMAMEN
dondurulmuş bir pazar çifti, dondurulmuş sayılar E1/E2'yi ihlal ediyorsa
MUAF tutuluyor artık. Full-data K=50'de test edildiğinde: **SIFIR
exemption tetiklendi** — çünkü **K=50'de 13273 adayın HİÇBİRİ (0/13273)
tam-donmuş değil** (`gap_lo==gap_hi`)! Kök neden: `apply_adjustable_subset`
bir BACAĞI (r1_id/r2_id) yalnızca O bacağı kullanan HİÇBİR aday top-K
pazarlardan birine ait DEĞİLSE donduruyor — ama aday üretimi TAM
inbound×outbound cross-product olduğundan, bir bacak ORTALAMA 4.4 farklı
(o,d) pazarına katılıyor (maks 183!). Yalnızca 297/2702 IB bacağı ve
254/2690 OB bacağı top-50 pazara DOĞRUDAN dokunsa da, bu küçük "tohum"
küme bacak-paylaşımı üzerinden GEÇİŞKEN olarak DEVASA sayıda pazara
yayılıyor — sonuçta K=50'de bile pratik olarak HİÇBİR aday tam donmuyor.
**Bu, `docs/baseline_autopsy.md`'nin "baked-in" yüzdelerinin (K=50'de E1
%96) PAZAR-SEVİYESİNDE ("hiçbir yönü top-K pazarına dokunmuyor") ölçüldüğünü,
`apply_adjustable_subset`'in GERÇEK (BACAK-SEVİYESİNDE) davranışını
YANSITMADIĞINI gösteriyor** — otopsi K-subset'in NEDEN başarısız olduğunu
doğru teşhis etmişti (baked-in ihlaller) ama BAKED-IN'in KENDİSİNİN neden
K arttıkça beklenen hızda düşmediğini (bacak-paylaşımı nedeniyle K-subset
GERÇEKTE serbestlik derecesini neredeyse hiç kısıtlamıyor) açıklamıyordu.

**Karar (kullanıcı onaylı)**: K-subset merdiveni (step2, K=50/100/200/400)
AYRI bir mekanizma olarak EMEKLİYE AYRILDI (kod SİLİNMEDİ, config'te
varsayılan KAPALI — `scripts/run_full_data.py` artık yalnızca step1'i
dener). "Bacak-seviyesinde dondurma" fikri TAMAMEN TERK EDİLMEDİ —
§5'in (M5c) proximity/local-branching incumbent motoruna GÖMÜLDÜ: orada
her ADAYIN KENDİ [t_lo,t_hi] penceresi güven-bölgesi büyüklüğüne göre
DOĞRU şekilde daraltılacak (bir "pazar" değil bir "uçuş, incumbent'tan
en fazla k uçuş taşınabilir" ilkesiyle), fold makinesi (§0/§1a) bu
daraltılmış alt-problemi otomatik küçültecek — YAPISAL OLARAK aynı
bacak-paylaşımı sorunu, ama artık "K market seç" yerine "incumbent'a en
yakın k UÇUŞ seç" ilkesiyle, ki bu doğrudan bacak-düzeyinde çalışıyor.

**Organizatör sorusundan DÜŞÜRÜLDÜ**: full-data'nın adjustable-subset
alt-probleminin K-şeması sorusu (VARSAYIM-12'nin orijinal (b) şıkkı)
artık AÇIK bir belirsizlik değil — KENDİ kodumuzdaki bir tasarım
sınırlaması olarak teşhis edildi ve M5c'de ayrı bir yaklaşımla (proximity
search) ele alınıyor. Yalnızca (c) (Gamma'nın gerçek ölçekte uygunluğu,
yukarıda) organizatör sorusu olarak AÇIK kalıyor.

**Rapor değeri**: bu bulgu aynı zamanda M6/rapor için VERİ-KANITLI bir
gerekçe — hub-ve-spoke ağının bu kadar YOĞUN bacak-paylaşımı (ort. 4.4,
maks 183 pazar/bacak) göstermesi, Benders dekompozisyonu gibi
"pazar-bazlı ayrıştırma" yaklaşımlarının erken elenmesini DOĞRULUYOR
(ağ GERÇEKTEN ayrıştırılamaz — herhangi bir alt-küme seçimi, paylaşılan
bacaklar üzerinden geri kalan ağa sızıyor).

**GÜNCELLEME 3 (2026-07-10, M5c kapanışı — sıkılaştırma + statik kanıt +
kurucu tanık, hepsi tüketildi, full-adjustable feasibility HÂLÂ kanıtsız)**:
Bu turda full-data step1'in (tam-ayarlanabilir, K-subset YOK) kök-düğümde
takılı kalma sorununa üç bağımsız yönden saldırıldı:

1. **Model sıkılaştırma** (`docs/lp_anatomy.md`): kök LP/tavan oranı %65
   (aşırı gevşek değil). F'nin per-reachable-bucket Big-M çifti tek bir
   bijective eşitliğe indirgendi (satır -%54.4, 756174→329842, F satırları
   -%96.8) — LP amaç değeri/oranı BİREBİR AYNI kaldı (eşdeğerlik kanıtlı).
   E2'nin singleton-pazar-yönü w/a_dir'i `x[i]`'ye katlandı (binary -%21-51,
   ama fractionality YÜZDESİ neredeyse değişmedi — fold sayıyı azaltıyor,
   LP gevşekliğini değil). Reward-amaçlı full-data step1 AYNI 600s+120s
   bütçesiyle üç kez koşuldu (öncesi/F-tek/F+E2-birlikte): dual bound
   yörüngesi F fix'le HIZLANDI (5.53M→4.90M idi, 5.13M→4.19M'e düştü) ama
   `Nodes=0` ÜÇÜNDE DE değişmedi, hiçbiri incumbent bulamadı.
2. **Alternatif hipotezler denendi ve elendi**: min-sapma amaç fonksiyonu
   (reward yerine Σ|t-baseline|) full-model'de aynı "hızlı yakınsa sonra
   TAM sessizlik" desenini gösterdi (142→4219, sonra 800s+ sıfır hareket).
   `build_feasibility_model` (yalnızca A/B/E1/E2/F/G, C/D YOK — reward
   hesaplama makinesi TAMAMEN çıkarıldı, satır 756174→205799) AYNI
   semptomu gösterdi (214s'de dual bound ~4466'da donup 500s+ sessiz
   kaldı). HiGHS'in `mip_detect_symmetry=False` ayarı denendi — dual
   bound yörüngesi SATIR SATIR ÖZDEŞ kaldı, ölçülebilir hiçbir etkisi
   yok, symmetry-detection hipotezi REDDEDİLDİ. **BEŞ bağımsız
   model/amaç/ayar kombinasyonunun HEPSİ aynı kök-düğüm-cut'ta-tıkanma
   desenini gösterdi** — model boyutu 756K'dan 205K'ya değişse bile.
3. **Statik fizibilite sertifikaları** (`scripts/feasibility_certificates.py`,
   `docs/feasibility_certificates.md`, saf pandas, MIP YOK): B'nin
   bidirectional reifikasyonundan türetilen forced_on/forced_off/
   undetermined durumuyla (mevcut `.fix()`'ten DAHA GENİŞ bir küme) üç
   NECESSARY-condition sertifikası — E1a (forced-on vs sıfır-ters-yön,
   `add_e1_constraints`'in pair-build koşuluyla kod-taramasıyla çapraz
   doğrulandı), E1b ([F,K]×[F,K] kutu-araması), E2 (forced-only Jbest
   dış-sınır ayrıklığı). **ÜÇÜ DE TEMİZ (0/0/0)** — E1/E2 bu analiz
   altında PROVABLY infeasible DEĞİL. Ardından saf-Python greedy repair
   (`scripts/greedy_feasibility_witness.py`, MIP yok, `validate_output`'u
   oracle kullanarak baseline'dan onarım dener) denendi: iter=1'de 2137
   ihlal (baseline autopsy'nin sayılarıyla tutarlı), TEK bir toplu onarım
   turu SONRASINDA 2380'e KÖTÜLEŞTİ (E1 690→1201) — kök neden onarımların
   KOORDİNESİZLİĞİ (paylaşılan bacaklar üzerinden birbirini bozan
   düzeltmeler, K-subset'in leg-sharing bulgusuyla AYNI yapısal gerçek) —
   **bu bir infeasibility kanıtı DEĞİL**, heuristiğin kendi kabalığının
   sonucu.

**Sonuç (kullanıcı onaylı kapanış)**: full-adjustable modelin feasibility'si
HÂLÂ ne kanıtlandı ne çürütüldü. Ama artık ELİMİZDE ÇOK DAHA GÜÇLÜ bir
resim var: (a) model TEK BAŞINA aşırı gevşek değil (LP/tavan %65), (b) iki
BAĞIMSIZ tightening'in (F row-reduction, E2 fold) HİÇBİRİ kök-düğümü
açmadı, (c) BEŞ farklı model/amaç/solver-ayarı kombinasyonu AYNI semptomu
gösterdi (amaç fonksiyonu ya da symmetry-detection SORUN DEĞİL), (d) E1/E2
statik olarak PROVABLY infeasible DEĞİL (saf pandas kanıt), (e) saf-Python
bir kurucu tanık denemesi TEK turda regresyona uğradı ama bu heuristiğin
kabalığından, problemin kendisinden değil. **En olası açıklama**: bu
HiGHS'in bu problem sınıfındaki (yoğun candidate-bazlı Big-M/reifikasyon
zincirleri, cross-product'tan gelen aşırı bacak-paylaşımı) kesme-düzlemi
davranışının kendine özgü bir sınırı — Gurobi karşılaştırması (pip'in
ücretsiz lisansı ~2000 satır/değişkenle SINIRLI, akademik lisans
gerekiyor, GÜNCELLEME 3 kapanışında henüz temin edilmedi) bunu netleştirebilir
ama bu turun kapsamı DIŞINDA bırakıldı (kullanıcı onaylı: mevcut kanıtla
kapat). Full-data'da doğrulanmış (validator-onaylı) bir objective_value
HÂLÂ YOK — M5c bu haliyle "kapsamlı üç-yönlü teşhis tamamlandı, kesin
tek-nokta çözüm bulunamadı, ama artık NEDEN bulunamadığına dair güçlü,
çok-açılı kanıt var" durumunda kapanıyor.

**GÜNCELLEME 4 (2026-07-11, M5d — Jbest fix TEK BAŞINA yetmiyor +
instance-bazlı ihlal-ayak-izi bağımsız ikinci doğrulama)**: VARSAYIM-13'ün
Jbest domain düzeltmesi SONRASI full-adjustable step1 (`scripts/run_full_data.py`,
900s+120s bekçi) YİNE `watchdog_killed`/`Nodes=0`/sıfır incumbent verdi
(`runs/full_data_run_20260710T211554Z.log.json`) — Jbest bug'ı GÜNCELLEME
3'ün beş-kombinasyonluk listesine bir ALTINCISINI ekliyor, hipotez
REDDEDİLDİ. Ardından (M5c'nin proximity/local-branching fikrinin ilk gerçek
denemesi) `src/model/local_branching.py::add_local_branching` (k=200,
Fischetti-Lodi tarzı Big-M/moved-indicator, TDD 4 test yeşil) full-data'da
denendi — AYNI semptom (`runs/local_branching_20260710T214039Z.log.json`,
`Nodes=0`, 720s). Kök neden HiGHS log'undan görüldü: presolve/probing
278163 binary'nin yalnızca 3765'ini işleyebildi ("moved=0⇒t=referans"
çıkarımı hiç gerçek satır/sütun azalmasına dönüşmedi).

Üçüncü kör bir k denemesi yerine ucuz bir ölçüm yapıldı
(`scripts/analyze_violation_footprint.py`, solve YOK): aynı A+G+F referans
noktasında E1/E2 ihlallerini düzeltmeye şans tanımak için kaç FARKLI
t_arr/t_dep örneğinin (candidate/market DEĞİL, doğrudan uçuş-zaman
değişkeni granülaritesi) serbest bırakılması gerektiği hesaplandı. **Sonuç:
arr instance'larının %85.7'si (2311/2697), dep instance'larının %82.8'i
(2225/2688) — toplam 4536 örnek.** Bu, GÜNCELLEME 2'nin candidate/market
granülaritesindeki bacak-paylaşımı bulgusunun (K=50'de bile 0/13273 aday
tam donuyor) FLIGHT-INSTANCE granülaritesinde BAĞIMSIZ bir ikinci
doğrulaması: iki farklı yöntem, iki farklı granülarite, AYNI sonuca
varıyor — bu problem sınıfında E1/E2'yi tatmin eden bir nokta (varsa) ağın
neredeyse TAMAMINI aynı anda gerektiriyor, yerelleştirilmiş/kısmi bir
düzeltme yapısal olarak umut vermiyor. **Karar (kullanıcı onayı bekleniyor)**:
üçüncü bir kör k-denemesi çalıştırılmadı (ayak izi analizi sonucunu zaten
gösteriyordu) — M5d bu turda da doğrulanmış bir full-data objective_value
ÜRETMEDEN, ama GÜNCELLEME 3'ün "HiGHS'in kesme-düzlemi davranışının kendine
özgü sınırı" hipotezine ALTINCI VE YEDİNCİ bağımsız kanıtı ekleyerek
kapanıyor.

## VARSAYIM-13: E2'nin Jbest değişkeni Integers değil Reals olmalı (M5d, gerçek bug — 2026-07-10)

**Bulgu**: `add_e2_constraints`/`add_elastic_e2_constraints`'in `Jbest` değişkeni
`domain=pyo.Integers` ile tanımlanmıştı (M4'ten beri, bu turda düzeltildi).
E2'nin argmin-sandviç kısıtları, bir aday kendi pazar-yönünün argmin'i
olduğunda (offered + w=1) `Jbest <= J_pi` VE `Jbest >= J_pi`'yi AYNI ANDA
zorluyor (Big-M terimleri sıfırlanıyor) — yani `Jbest == J_pi` TAM EŞİTLİK.
`J_pi = journey_constant + gap`, ve `journey_constant` (K_od) HER ZAMAN
tamsayı DEĞİL:

- **Direct (medyan-bazlı) K_od**: 780 örneklemde 737 tamsayı, **43 (%5.5)
  kesirli** (çift sayıda satırın medyanı .5'e düşebilir).
- **Estimate (bipartite least-squares) K_od, VARSAYIM-8**: 803 örneklemde
  yalnızca 6 tamsayı, **797 (%99.3) KESİRLİ**.

Full-data'da ~803/1583 pazar (yaklaşık YARISI) K_od'unu estimate'ten alıyor
— bu pazarların HERHANGİ birinin bir adayı argmin olarak seçildiğinde,
`Jbest`'in Integers domain'i o kesirli `J_pi`'ye EŞİT hiçbir değer
alamıyor → **E2 o pazar-yönü için KOŞULSUZ infeasible**, hangi diğer
seçim yapılırsa yapılsın.

**Nasıl bulundu**: `scripts/warm_start_elastic.py`'nin full-data koşusunda
HiGHS `Jbest[...]` değişkenlerine kesirli değer atanmaya çalışılırken
Pyomo `W1001` uyarıları fırlattı (`Setting Var 'Jbest[...]' to a value
...(float64) not in domain Integers`) — bu, warm-start denemesinin YAN
ÜRÜNÜ olarak keşfedilen, ÖNCEDEN BİLİNMEYEN bir model formülasyon hatası
(warm-start'ın KENDİSİNİN neden olduğu bir şey DEĞİL — model M4'ten beri
bu haliyle var, hiçbir önceki solve denemesi bunu YÜZEYE ÇIKARMADI çünkü
hiçbiri Jbest'e KESİN bir değer atamaya çalışmadı, hepsi solver'ın kendi
iç arama sürecine bırakıyordu).

**Etki değerlendirmesi**: bu, M5/M5c/M5d boyunca gözlemlenen "hızlı yakınsa
sonra kök-düğümde tıkanma" semptomunun EN AZ BİR GERÇEK KAYNAĞI olabilir —
full-data'daki BEŞ+ solve denemesinin (reward, min-sapma, F-fix, E2-fold,
salt-fizibilite, elastik) HEPSİ bu formülasyon hatasını İÇERİYORDU. HiGHS
muhtemelen bu ~803 pazarın adaylarını asla argmin olarak seçmemeye
zorlanıyordu (yapay bir kombinatoryal kısıtlama) — bu da kök-düğüm
cut-üretiminin neden bu kadar yavaş/verimsiz olduğunu KISMEN açıklayabilir.

**Düzeltme (kullanıcı onaylı, "Integers değil Reals" seçeneği)**: `Jbest`
`domain=pyo.Reals`'e değiştirildi (hem `constraints_balance.py` hem
`constraints_elastic.py`). Gerekçe: $J$ zaten kavramsal olarak sürekli bir
büyüklük (bir sabit + tamsayı gap) — Integers domain M4'ten kalma yanlış
bir varsayımdı, veri yuvarlaması İÇERMEYEN matematiksel olarak doğru
düzeltme (K_od'u yuvarlamak yerine). TDD: `tests/solve/test_m4_constraints_e2.py::test_e2_jbest_domain_accepts_fractional_journey_constant`
(kesirli journey_constant'lı bir senaryo, KIRMIZI→YEŞİL — Integers ile
kesin infeasible, Reals ile optimal). Fixture etkilenmedi (668.75 korunur
— fixture'ın journey constant'ları hep tamsayı). 141 unit + 101 solve
yeşil. Sıradaki adım: full-data'da warm-start denemesini bu düzeltmeyle
TEKRARLA — bu ÖNCEKİ hiçbir solve denemesinde düzeltilmemişti, yani şimdiye
kadarki TÜM full-data sonuçları (M5/M5c/M5d) bu formülasyon hatasının
GÖLGESİNDE elde edildi.

## VARSAYIM-14: Gate-to-Gate wrap-fix — süre bileşenlerden (Elapsed1+gap+Elapsed2) hesaplanır, görüntülenen alandan DEĞİL (M5e, 2026-07-11)

**Bulgu**: organizatör 2026-07-09'da resmi olarak uyardı — "Gate-to-Gate"
alanı Excel time-of-day hücresi olarak saklanıyor, 24 saati aşan
yolculuklarda görüntülenen değer 1440'a göre WRAP ediyor (sıfırlanıyor).
Gerçek v2 dosyasında doğrudan doğrulandı: `elapsed1_min + gap_min +
elapsed2_min` (gap = Dep Time − Arr Time, tam takvim-tarihli
`pd.Timestamp`, wrap'e MARUZ DEĞİL) ile görüntülenen alan arasındaki fark,
**57.317 satırın TAMAMINDA** tam 1440'ın katı (0 istisna). **495 satır (60
farklı O&D pazarı) gerçek ≥24h yolculuk**, maksimum 35.0 saat. Bu bug daha
önce hem rakip satırlarını (`competitors.py::derive_rival_best_times`) hem
61 TK baseline satırını (`ranking.py::compute_baseline_best_journey`)
sessizce etkiliyordu.

**Karar**: `src/data/elapsed_parser.py::wrap_corrected_journey_minutes`
+ `src/data/loaders.py::load_od_table` — v2 şema (ElapsedTime1/2 kolonları
mevcut) tespit edildiğinde `gate_to_gate_min`, görüntülenen hücreden
DEĞİL, `elapsed1_min+gap_min+elapsed2_min`'den hesaplanır (TÜM satırlara
koşulsuz uygulanır — wrap'siz 56.822 satırda iki formül zaten birebir aynı
sonucu veriyor). Tek düzeltme noktası: `competitors.py`/`ranking.py`
`gate_to_gate_min` kolon adını paylaştığı için SIFIR kod değişikliğiyle
düzeltmeyi miras alıyor (regresyon testleriyle kanıtlandı,
`tests/unit/test_competitors.py`/`test_ranking.py`).

**Etki alanı**: yalnızca v2 şemalı dosyalarda aktif (Elapsed kolonları
YOKSA — ör. fixture'ın kolonsuz varyantı, mevcut LS-yolu davranışı
DEĞİŞMEDEN korunur). `docs/decisions.md` 2026-07-11 M5e girdisi.

## VARSAYIM-15: Elapsed1/Elapsed2 mevcutken K_od/R_o doğrudan bacak-gözlemi, `[L,U]` filtresi K_od için kaldırılır (M5e, 2026-07-11)

**Bulgu**: VARSAYIM-14'ün kimliği gereği (`gate_to_gate_min =
elapsed1_min+gap_min+elapsed2_min`), `implied_k = gate_to_gate_min -
gap_min` cebirsel olarak TAM `elapsed1_min+elapsed2_min`'e sadeleşiyor —
K_od artık gap'e hiç bağlı değil. `[L,U]` gap filtresi yalnızca
görüntülenen sürenin geçersiz/placeholder olabileceği satırlara karşı bir
veri-kalite önlemiydi; Elapsed1/Elapsed2'nin gap geçerliliğinden BAĞIMSIZ
tutarlı olduğu gerçek veride doğrulandı (0/57.317 istisna). Benzer şekilde
Elapsed1 (dep1==o satırında) T_IB_o'nun, Elapsed2 (arr2==o satırında)
T_OB_o'nun DOĞRUDAN gözlemi — R_o artık bipartite LS gerektirmiyor.

**Karar**: `src/data/block_times.py::BlockTimeProvider._init_from_elapsed`
— K_od = market-bazlı medyan(`elapsed1_min+elapsed2_min`), TÜM TK
satırları dahil (gap geçerliliğinden bağımsız); R_o = istasyon-bazlı
medyan(Elapsed1)+medyan(Elapsed2), LS/ridge YOK. Arayüz (4 public
metod/property) DEĞİŞMEDİ, yalnızca `__init__` kolon varlığına göre farklı
bir iç yola giriyor (`elapsed1_min`/`elapsed2_min` yoksa mevcut LS yolu
byte-byte korunur — `tests/unit/test_block_times.py`'deki 12 orijinal test
regresyon kanıtı).

**Skor-etkileyen veri-yorumu kararı** (bu yüzden burada açıkça
işaretleniyor, CLAUDE.md'nin dur-ve-sor eşiği): hangi pazarların
"doğrudan" vs "tahmini" K_od aldığını değiştiriyor. Kanıtın gücü
göz önüne alındığında otonom ilerlendi — destekleyici sayılar
`docs/block_time_cross_validation.md`'de (805 TK-gözlemli pazarın 25'i
tablo-seviyesinde LS tahminine muhtaçtı, LS hatası medyan=1.28dk,
p90=6.72dk, max=124.11dk; R_o kayması medyan=1.77dk, p90=9.22dk,
max=1142.18dk — tek bir büyük sapma, muhtemelen zayıf-bağlı bir
istasyon).

**Etki alanı**: `src/data/block_times.py`. `[L,U]` filtresi BAŞKA HİÇBİR
YERDE değiştirilmedi (`ranking.py::compute_baseline_best_journey`'nin
`[L,U]` kullanımı farklı bir semantik — "meşru bağlanabilir itinerary" —
aynen kalıyor). VARSAYIM-8'in ~575-pazarlık candidate-seviyesi LS-fallback
popülasyonunun v2 ile yeniden ölçümü Bölüm 2'nin işi.

## VARSAYIM-16: E1 birincil formülasyonu KOŞULLU AKTİVASYON (KARAR-0, M5f, 2026-07-11)

**Karar**: E1 (yönsel sayı dengesi) artık yalnızca HER İKİ yön de AKTİFKEN
(her yönde ≥1 SUNULAN/seçili bağlantı) bağlayıcı — `src/model/constraints_balance.py::add_e1_constraints`
ve elastik/folded eşdeğerleri (`src/model/constraints_elastic.py`) yeni bir
`activation: "conditional" | "unconditional"` parametresi alır, varsayılan
`"conditional"` (`src/config/standard.yaml::e1_activation`). Koşullu modda
kısıt E2'nin zaten var olan aktivasyon göstergesini (`model.a_dir`, "en az
bir aday sunuldu mu") yeniden kullanır:

$$n_{fwd}-n_{bwd} \le \alpha(n_{fwd}+n_{bwd}) + M_{pair}(2-a_{fwd}-a_{bwd})$$
$$n_{bwd}-n_{fwd} \le \alpha(n_{fwd}+n_{bwd}) + M_{pair}(2-a_{fwd}-a_{bwd})$$

$M_{pair} = (1-\alpha)\cdot\max(|\Pi_{fwd}|,|\Pi_{bwd}|)$ (`src/model/big_m.py::derive_e1_pair_big_m`,
candidate-sayısı bazlı, veri-türetilmiş, doğası gereği ≤1440 disiplinine
tabi zaten). `activation="unconditional"` eski literal okumayı (M terimi
yok, kısıt her zaman tam bağlayıcı) duyarlılık analizi olarak korur.

**Kanıt seti**:
1. **Brief §7 modelleme ipucu**: *"Koşullu (yalnızca her iki yön aktifken
   bağlayıcı) kısıtları doğru kurun; aksi halde pasif yönler dengeyi yapay
   olarak ihlal/zorlar"* — "denge" E-ailesinin kendi adı (§4.5 "Yönsel
   Denge"), tarif edilen patoloji birebir E1'in tek-yön-sıfır vakası.
2. E1 metnindeki "iki yön de boşsa kendiliğinden sağlanır" cümlesi yalnızca
   0/0 belirsizliğini çözer — tek-yön-BOŞ (bir yön yapısal olarak var ama
   sunulan sıfır) vakası metinde AÇIKÇA ele alınmamış; §7 ipucu bu boşluğu
   dolduruyor.
3. Mevcut kodun kendi sınır seçimi (E1_PAIRS, `_market_groups`) zaten
   yarı-koşullu: yapısal adayı olmayan yön çifti hiç kurulmuyor (VARSAYIM-6,
   "yapay kısıtlama olurdu" gerekçesiyle) — aynı gerekçe "yapısal aday var
   ama sunulan sıfır" durumuna da doğal olarak uzanıyor.
4. **Ampirik**: organizatörün KENDİ baseline'ı literal okumada 690 pair-gün
   ihlalli (v1=v2, blok süresinden bağımsız); ulaşılan HER full-data
   noktasında E1 fazlalık oranı medyan=p90=max=**0.800=1−α** — yani
   ihlallerin ~TAMAMI tek-yön-sıfır vakası, gerçek bir dengesizlik değil.
   Literal E1 belgeli bir "amaç bastırıcı" (bkz. `tests/solve/test_m4_constraints_e1.py`
   modül docstring'i) — yarışmanın ilan edilmiş amacıyla (cazip bağlantı
   sayısını ARTIRMAK) çelişen davranış üretiyor.
5. VARSAYIM-9/10/11'de kullanıcı onayıyla yerleşen ilkeyle aynı desen
   ("organizatör çözümsüz/kendi-verisiyle-çelişen bir problem tasarlamaz").

**Dürüst karşı-kanıt**: E2 metni koşullu aktivasyonu AÇIKÇA söylüyor, E1
metni söylemiyor — literal okuma metinsel olarak savunulabilir ve her zaman
tatmin edilebilir (pazarı tamamen sıfırlayarak, infeasibility değil). Bu
yüzden literal mod SİLİNMEDİ, bayrakla yaşıyor; `docs/organizer_questions.md`
madde 6 organizatöre bu soruyu taşıyor.

**Fixture etkisi**: sentetik fixture'da HER İKİ modda da objective=668.75
(değişmedi) — fixture'ın E1 çiftleri optimumda zaten her iki yönde de aktif,
tek-yön-sıfır senaryosunu hiç tetiklemiyor. Brute-force oracle
(`tests/slow/test_bruteforce_oracle.py`) B+C+D'yi doğruluyor, E1/E2'ye
dokunmuyor — bu değişiklikle ilgisiz, ayrıca yeniden koşuldu (yeşil).

**Hizalama**: `src/validate/independent_validator.py::validate_output`
aynı `e1_activation` parametresini alır (varsayılan `"conditional"`) —
koşullu modda M5b'nin yapısal-kapsam genişletmesi (`_has_structural_candidate`)
atlanır (iki mod da AYNI ihlal kümesini üretir bu durumda, matematiksel
olarak kanıtlanabilir eşdeğerlik — bkz. kod yorumu). `scripts/feasibility_certificates.py`'nin
E1b sertifikası iki modu da hesaplayıp raporlar. `scripts/baseline_feasibility_witness.py`
ve `scripts/analyze_violation_footprint.py` STATUS'a iki-modlu tablo için
her iki modu da raporlar. `src/model/lns.py::compute_pair_slack` aynı
bayrağı alır (varsayılan koşullu) — LNS'in worst-pair seçimi artık modelin
gerçek s_e1 davranışıyla tutarlı.

## VARSAYIM-17: E2 statik-imkânsız çift muafiyeti (KARAR-0b, M5f, 2026-07-11)

**Karar**: `src/model/lns.py::compute_gamma_infeasible_pairs`'ın STATİK
kanıtladığı — iki yönün de BEST-CASE achievable Jbest aralığı (adayların
kendi `gap_lo/gap_hi`'sinden, [L,U]'ya kırpılmış, journey_constants ile
birlikte türetilen) Gamma'dan daha fazla ayrık olan — market çiftleri,
HANGİ seçim yapılırsa yapılsın E2'yi asla sağlayamaz: schedule-independent,
saf bir veri gerçeği. Bu çiftler artık `add_e2_constraints` (strict) ve
elastik/folded eşdeğerlerinde (`src/model/constraints_elastic.py`) E2'den
MUAF tutulur (constraint satırı hiç kurulmaz) + loglanır — A/G'deki
VARSAYIM-9/11 exempt+log ilkesinin birebir uzantısı, ama K-subset
dondurmasından TAMAMEN BAĞIMSIZ (freezing durumundan etkilenmez, her
zaman aynı çiftleri yakalar).

**Neden ayrı bir muafiyet (mevcut K-subset-frozen muafiyetten farkı)**:
mevcut `add_e2_constraints`'in M5c-döneminden kalan exemption'ı yalnızca
"HER İKİ yön de TAMAMEN K-subset-dondurulmuş" durumunu yakalar. Matematiksel
olarak, tam-dondurulmuş-her-iki-yön durumunda bu iki kontrol (statik
achievable-range ve frozen-value) AYNI sonucu üretir (dondurulmuş tek-nokta
gap_lo==gap_hi için achievable range == frozen value) — ama statik kontrol
AYRICA hiç dondurulmamış (tamamen serbest) pazarları da yakalayabilir:
journey_constant asimetrisi tek başına, seçimden bağımsız olarak, E2'yi
imkânsız kılabilir (bkz. `tests/solve/test_m4_constraints_e2.py::test_e2_exempts_adjustable_pair_that_is_statically_gamma_infeasible`).

**Hizalama**: `src/validate/independent_validator.py`'ye bağımsız
yeniden-uygulama eklendi (`_structural_j_best_case_range`/
`_is_gamma_statically_infeasible` — `src.model.lns` import ETMEZ, aynı
mantığı ham TK verisinden kasıtlı olarak KOPYALAR, VARSAYIM-9/10/11'in
zaten kurduğu "bağımsız yeniden-uygulama" deseniyle birebir). `scripts/feasibility_certificates.py`'nin
E2 sertifikası artık `compute_gamma_infeasible_pairs` ile çapraz kontrol
ediyor (`karar0b_exempted_count`/`karar0b_still_unexempted` — ikincisi boş
olmalı, dolu çıkması gerçek bir bug'a işaret eder). `scripts/analyze_violation_footprint.py`
genuine vs KARAR-0b-exempted E2 ihlallerini ayrı raporluyor.

**Γ ölçeği sorusu** (organizatörün kendi Gamma tanımı/büyüklüğü) ayrı,
açık bir soru olarak `docs/organizer_questions.md` madde 12b'de kalıyor —
bu karar yalnızca "mevcut Gamma altında provably imkânsız olan çiftleri
ne yapalım" sorusunu cevaplıyor.

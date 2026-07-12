# Organizatöre Sorular — Konsolide Liste

`ASSUMPTIONS.md`'deki VARSAYIM-1 ... VARSAYIM-11'in "Organizatöre soru" alt-bölümlerinin
tek listede toplanmış hali, artı plan §7'de kod-kararına dönüşmemiş açık sorular.
Her madde, cevap geldiğinde değişecek TEK kod noktasına referans veriyor — bu bir
"nice to know" listesi değil, her sorunun cevabı somut bir davranış değişikliğine
bağlı.

## Veri kalitesi

**1. (VARSAYIM-1) Yolcu Verisi'nde duplicate (orig,dest) satırları** — 6 çift, 12
satır. Toplanmalı mı (şu anki karar), yoksa farklı bir anlamları mı var (farklı
kabin sınıfı/zaman dilimi/veri kaynağı)? → `src/data/loaders.py::load_yolcu_verisi`.

**2. (VARSAYIM-2) Yolcu Verisi'ndeki 3 eksik-dest satırı** (AGP/VCE/PEK, rho=931/427/356)
— veri hatası mı, resmi dosyada dolduruluyor mu? Düzeltilmiş dosya var mı, yoksa
atlamamız mı bekleniyor? → `src/data/loaders.py::load_yolcu_verisi` (şu an
`strict=False` ile `--full-data` yolunda atılıyor, geçici köprü).

## Model varsayımları

**3. (VARSAYIM-3) Ayarlanabilir pencere genişliği** — Standard senaryo için pratik
bir hareket penceresi öngörülüyor mu (baseline ±kaç saat), yoksa bizim 180dk
varsayımımız kabul edilebilir mi? → `src/config/standard.yaml::adjustable_window_min`.

**4. (VARSAYIM-4) "Rakip" tanımı** — aynı taşıyıcının bir pazardaki birden fazla
itinerary'si N_od hesabında ayrı rakipler mi, yoksa tek (en iyi itinerary'yle
temsil edilen) rakip olarak mı konsolide edilmeli? → `src/data/competitors.py::derive_rival_best_times`.

**5. (VARSAYIM-5) Çok-duraklı rotasyonlar** — Flight Pairs'teki 3+ üyeli gruplar
(ör. IST→MEX→CUN→IST) gerçek çoklu-duraklı rotasyonlar mı? Ara bacağın (MEX→CUN)
zamanı sabit mi kabul edilmeli, yoksa ayrı bir modelleme yaklaşımı mı bekleniyor?
→ `src/model/constraints_operations.py::build_rotation_pairs` (şu an ≤50/707 grup
kısıt kapsamı DIŞINDA kalıyor).

**6. (VARSAYIM-6/16) E1 formülü — KARAR-0 ile içeride karara bağlandı, organizatör
teyidi bekleniyor (M5f, 2026-07-11)**: bağıl dengesizlik
$|n_{fwd}-n_{bwd}|/(n_{fwd}+n_{bwd})$ kesin formül mü? Gün bazında mı dönem
toplamında mı? **Asıl açık soru**: E1 KOŞULLU mu (yalnızca her iki yön de
aktifken bağlayıcı, E2'nin metninde AÇIKÇA yazan gibi) yoksa LİTERAL mi
(her zaman bağlayıcı)? Brief §7'nin modelleme ipucu ("koşullu kısıtları
doğru kurun, aksi halde pasif yönler dengeyi yapay olarak zorlar") ve
ampirik kanıt (organizatörün kendi baseline'ı literal okumada 690 pair-gün
ihlalli; full-data'da ulaşılan her noktada E1 fazlalık oranı sabit
$0.800=1-\alpha$, yani ihlallerin ~tamamı tek-yön-sıfır vakası) ışığında,
**varsayılan davranış artık KOŞULLU aktivasyona geçirildi**
(`ASSUMPTIONS.md` VARSAYIM-16, `docs/CLOSING_PLAN.md` KARAR-0). Literal
okuma `e1_activation: unconditional` bayrağıyla duyarlılık analizi olarak
yaşamaya devam ediyor — E1 metni E2'nin aksine koşullu aktivasyonu AÇIKÇA
söylemediğinden, bu metinsel olarak dürüst bir belirsizlik, organizatör
cevabı gelirse config-düzeyinde tek satırlık bir değişiklikle entegre
edilecek. → `src/model/constraints_balance.py::add_e1_constraints`
(E1/E2 kısıt grupları), `src/config/standard.yaml::e1_activation`.

**7. (VARSAYIM-7) Kapsam-dışı TK uçuşları için hub kapasitesi** — modelin
ayarlayamadığı uçuşlar kendi mevcut tarifelerinde sabit mi kabul edilmeli, yoksa
başka bir resmi kapasite-tahsis verisi mi var? → `src/model/constraints_capacity.py::compute_out_of_scope_baselines`.

**8. (VARSAYIM-8) Resmi K_od verisi — VERİ İLE ÇÖZÜLDÜ (M5e, 2026-07-11)**:
organizatörün 2026-07-09 veri v2 paketi `ElapsedTime1`/`ElapsedTime2`
(bacak-bazlı gerçek blok süreleri) sağladı — `BlockTimeProvider` artık
bunları tercih ediyor (VARSAYIM-15), LS tahmini yalnızca bu kolonlar
YOKSA devreye giriyor. Ölçüldü (`docs/block_time_cross_validation.md`):
805 TK-gözlemli pazarın 25'i tablo-seviyesinde LS tahminine muhtaçtı, LS
hatası medyan=1.28dk/p90=6.72dk/max=124.11dk (23/25 karşılaştırılabilir
örnek) — LS yaklaşımı çoğunlukla iyi çalışmış. Artık sorulacak bir şey
kalmadı, bu madde kapalı. → `src/data/block_times.py::BlockTimeProvider`.
Çıktıda `k_od_sources[]` ile hangi pazarların "estimated" olduğu görünür
(bkz. `docs/output_format.md`).

**9. (VARSAYIM-9) G'nin TK2841 anomalisi** — TK2841 (TZX→IST) 4 günde 03:25'te,
1 günde (Gün5) 14:10'da uçuyor (645dk fark, G'nin 375dk uzlaştırılabilirlik
sınırını AŞIYOR — formel Helly-özelliği kanıtıyla `ASSUMPTIONS.md`'de gösterildi).
Veri hatası/maskeleme artefaktı mı, gerçek tek-seferlik tarife değişikliği mi,
yoksa uçuş numarasının kasıtlı yeniden kullanımı mı? G TÜM operasyon günlerine
KOŞULSUZ tek bir X_dev bandı mı uygulamalı (bu durumda TK2841 problemi
çözümsüz kılar), yoksa bizim küme-bazlı yaklaşımımız (VARSAYIM-9 kararı) kabul
edilebilir mi? → `src/model/day_clustering.py::cluster_flight_days`.

**10. (VARSAYIM-10) A'nın OB/IB gün-eşleştirmesi** — Flight Pair'deki (OB,IB) çifti
için gün eşleştirmesi nasıl yorumlanmalı? Uzun menzilli rotasyonlarda hangi IB
varışı hangi OB kalkışının GERÇEK partneri sayılmalı — bizim baseline-kronoloji
yaklaşımımız (kalkıştan sonraki en yakın varış, dairesel-haftalık) doğru mu,
yoksa farklı bir resmi eşleştirme kuralı mı var? → `src/model/rotation_matching.py::match_rotation_legs`.
**Bulgu büyüklüğü**: eski "aynı gun" kuralıyla 1496 çiftin %54.7'si uzlaştırılamaz,
%45.3'ü kronolojik TERS çıkıyordu.

**11. (VARSAYIM-11) Fiziksel olarak imkansız rotasyon çiftleri** — baseline
tarifede zaten imkansız olan (R_o+tau, ayarlanabilir pencereyle karşılanamayan)
OB-IB çiftleri (VARSAYIM-10 düzeltmesinden SONRA bile 382/1571, %24.3) istisna
mı tutulmalı, yoksa R_o tahminimizde/eşleştirme kuralımızda bir hata mı var?
→ `src/model/constraints_operations.py::add_a_constraints`.

**12. (VARSAYIM-12, M5c KAPANIŞI — çok-açılı teşhis tüketildi, full-adjustable
modelin çözüm süresi HÂLÂ açık) Full-adjustable modelin (K-subset'siz, tüm
18118 aday) çözüm süresi** — K-subset merdiveninin kendisi (leg-sharing
nedeniyle) yapısal olarak etkisiz bulunup emekliye ayrıldıktan sonra, bu
turda full-adjustable modelin kök-düğümde takılı kalma sorununa üç bağımsız
yönden saldırıldı: (1) model sıkılaştırma (F'nin satır-patlaması -%54.4
düzeltildi, E2'nin singleton-pazar binary'leri katlandı — ikisi de LP
eşdeğerliğini bozmadan ölçülebilir iyileşme sağladı ama kök-düğümü
AÇMADI), (2) beş bağımsız model/amaç/solver-ayarı kombinasyonu (reward,
min-sapma, reward-only-A/B/E1/E2/F/G, symmetry-detection kapalı) HEPSİ AYNI
"hızlı yakınsa sonra tam sessizlik, sıfır incumbent" desenini gösterdi —
model boyutu 756K'dan 205K satıra değişse bile, (3) E1/E2'nin KENDİSİNİN
statik/saf-pandas necessary-condition sertifikalarla PROVABLY infeasible
OLMADIĞI kanıtlandı (üç sertifika de temiz), ve saf-Python bir kurucu
tanık denemesi baseline'dan başlayıp onarmayı denedi (koordinesiz onarım
adımları nedeniyle bir turda regresyona uğradı — bu heuristiğin kabalığından,
problemin kendisinden değil). Organizatörün bu ölçekte (18000+ aday, ~900+
pazar) beklediği bir çözüm süresi/referans benchmark'ı var mı, yoksa
brief'in gerçek veri ölçeğinde ticari bir solver (Gurobi/CPLEX) veya daha
uzun bir bütçe (saatler) mi öngörülüyor? → `docs/lp_anatomy.md`,
`docs/feasibility_certificates.md`, `scripts/run_full_data.py`,
`scripts/feasibility_certificates.py`, `scripts/greedy_feasibility_witness.py`,
`docs/decisions.md` (2026-07-10 kronolojisi).

**12b. (Otopsi'den yeni) Gamma=30dk gerçek veri ölçeğinde uygulanabilir mi?**
— E2'nin 1219 gerçek ihlalinin %78'inde (949) K_od'un YAPISAL asimetrisi
($T^{IB}_o+T^{OB}_d$ vs $T^{IB}_d+T^{OB}_o$, istasyonların KENDİ blok
sürelerinin farkı) TEK BAŞINA Gamma(30dk)'yı aşıyor — gap SIFIR olsa bile
(imkansız ama ideal), bu ihlaller çözülemez. Bu, "en iyi yolculuk süresi
farkı"nın Gamma ile karşılaştırılmasının küresel/coğrafi çeşitliliği yüksek
bir ağda çok sıkı bir eşik olduğunu gösteriyor olabilir — Gamma'nın büyük
ölçekli ağlarda nasıl yorumlanması/ölçeklenmesi gerektiği konusunda
organizatör rehberliği var mı? → `docs/baseline_autopsy.md` §2.
**KARAR-0b güncellemesi (VARSAYIM-17, M5f, 2026-07-11)**: bu maddenin
"ne yapalım" kısmı içeride karara bağlandı — statik olarak (schedule-
independent, `compute_gamma_infeasible_pairs`) provably imkânsız çıkan
çiftler artık E2'den MUAF tutuluyor (exempt+log), Gamma'nın KENDİ
büyüklüğü/ölçeği sorusu ise AÇIK kalıyor (organizatörden gelecek bir cevap
yalnızca `gamma` config değerini değiştirir, muafiyet mekanizmasının
kendisini değil).

**Γ-duyarlılık ön-tarama güncellemesi (Kapı-B, 2026-07-12, solver YOK)**:
Gamma'nın "büyüklüğü/ölçeği" sorusuna solver harcamadan kısmi bir cevap
üretildi — full-data'da Γ ∈ {30,45,60,90,120,150,180} taraması
(`scripts/scan_gamma_sensitivity.py`, tablo `docs/STATUS.md` "Kapı-B"
bölümünde) gösteriyor ki bağımsız-çift alt sınır (her çiftin kendi en iyi
durumuna bağımsız ulaştığını varsayan iyimser tahmin) Γ=180'de bile
717.5dk ile sıfırdan uzak — yani **Γ'yı 6 katına çıkarmak (30→180) bile
E2'yi full-data'da çözülebilir kılmaya YETMEZ**. Bu, sorunun sadece "Gamma
çok mu dar" sorusundan öte, ağ genelinde kuplajlı bacak-paylaşım yapısından
kaynaklandığını gösteriyor (VARSAYIM-12 GÜNCELLEME 6) — organizatöre
sorulacak soru buna göre daralıyor: "Gamma'yı büyütmek E2'yi pratikte
çözülebilir kılmaya yetmiyor görünüyor; brief'in E2 kısıtını gerçek veri
ölçeğinde YORUMLAMA biçimimizde (pazar-çifti-bazlı simetrik JT-farkı) bir
gözden kaçırma mı var, yoksa bu ölçekte E2'nin BEKLENEN davranışı zaten
kısmi/istisna-tutmalı mı?"

## Kapsam / veri (plan §7'den, henüz kod kararına dönüşmemiş)

**13. Slot pencereleri (H)** — kick-off'ta "düzenlenmiş havalimanlarında varış
pencereleri" geçiyor, brief'te detay yok, elimizdeki 4 veri dosyasında da böyle
bir alan yok. MVP kapsamında no-op (veri yok → uygulanamaz). Resmi bir
slot-penceresi dosyası var mı?

**14. Resmi blok-süresi (T_IB/T_OB) master dosyası var mı? — VERİ İLE ÇÖZÜLDÜ
(M5e, 2026-07-11)**: organizatörün 2026-07-09 paketindeki `ElapsedTime1`/
`ElapsedTime2` kolonları tam olarak bu ihtiyacı karşılıyor (bacak-bazlı
gerçek blok süreleri) — ayrı bir master dosyaya gerek kalmadı, bkz. madde 8.

**15. Gün kümesi H'nin kapsamı** — Flight Pairs ve O&D tablosu `Gün∈{1..7}`
kullanıyor; bunun haftalık döngü indeksi (her hafta tekrarlanan) olduğu
varsayılıyor (G'nin dairesel karşılaştırması da bu varsayıma dayanıyor). Gerçek
takvim mi, yoksa döngü indeksi mi?

---

Kayıt & Soru-Cevap penceresi (organizatör tarafından, 16 Temmuz'a kadar açık —
bkz. brief) kapanmadan önce bu liste güncel tutulmalı; yeni bir VARSAYIM eklenirse
bu dosyaya da eklenir (tek nokta, `ASSUMPTIONS.md` ile senkron).

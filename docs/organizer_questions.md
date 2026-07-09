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

**6. (VARSAYIM-6) E1 formülü** — bağıl dengesizlik $|n_{fwd}-n_{bwd}|/(n_{fwd}+n_{bwd})$
kesin formül mü? Gün bazında mı dönem toplamında mı? Tek-yönlü candidate'ı olan
pazarlar E1'den muaf mı? → `src/model/constraints_e1.py` (varsa) / ilgili E1 kısıt
modülü. **Not**: full-data koşusunda E1 ilk şüpheli — bkz. bu turun kapanış raporu.

**7. (VARSAYIM-7) Kapsam-dışı TK uçuşları için hub kapasitesi** — modelin
ayarlayamadığı uçuşlar kendi mevcut tarifelerinde sabit mi kabul edilmeli, yoksa
başka bir resmi kapasite-tahsis verisi mi var? → `src/model/constraints_capacity.py::compute_out_of_scope_baselines`.

**8. (VARSAYIM-8) Resmi K_od verisi** — full data'da 775 pazarın 575'i için
gate-to-gate süresi hiçbir mevcut tarifede [L,U]'ya denk gelmiyor. Resmi bir K_od
(gate-to-gate sabit) verisi var mı, yoksa istasyon-bazlı LS tahmini (bizim
yaklaşımımız) kabul edilebilir mi? → `src/data/block_times.py::get_journey_constant_estimate`.
Çıktıda artık `k_od_sources[]` ile hangi pazarların "estimated" olduğu görünür
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

**12. (VARSAYIM-12) Full-data'nın adjustable-subset alt-problemi HER K
değerinde (50/100/200/400) kanıtlanabilir infeasible** — beş kısıt ailesinin
(A/E1/E2/F/G) hiçbiri tek başına kaldırıldığında bunu düzeltmiyor (K=400'de
6 varyant test edildi, hepsi infeasible). Bu; (a) baseline tarifenin
kendisinin brief'in kısıt setiyle yapısal olarak tutarsız olduğunu
(VARSAYIM-9/10/11'in G/A için zaten gösterdiği gibi, ama artık E1/E2 için
de — baseline-feasibility tanığı ham baseline'ın TÜM beş ailede eş zamanlı
2048 ihlali olduğunu gösterdi), (b) K-subset gevşetme yaklaşımının yanlış
biçimde tasarlandığını, yoksa (c) α/γ/X_dev/adjustable_window_min gibi
parametrelerin gerçek veri ölçeğinde daha gevşek tutulması gerektiğini mi
gösteriyor? Tam-ayarlanabilir (K-subset'siz) problemin feasibility'si
elimizdeki hesaplama bütçesiyle (660s, dış-bekçili) kanıtlanamadı —
organizatörün bu ölçekte (18000+ aday) beklediği bir çözüm süresi/referans
benchmark var mı? → `scripts/run_full_data.py`, `scripts/diagnose_e1_e2_f.py`,
`scripts/baseline_feasibility_witness.py`.

## Kapsam / veri (plan §7'den, henüz kod kararına dönüşmemiş)

**13. Slot pencereleri (H)** — kick-off'ta "düzenlenmiş havalimanlarında varış
pencereleri" geçiyor, brief'te detay yok, elimizdeki 4 veri dosyasında da böyle
bir alan yok. MVP kapsamında no-op (veri yok → uygulanamaz). Resmi bir
slot-penceresi dosyası var mı?

**14. Resmi blok-süresi (T_IB/T_OB) master dosyası var mı?** — block_times
sağlayıcısı değiştirilebilir tasarlandı (`src/data/block_times.py`); organizatörde
ayrı bir resmi T_IB_o/T_OB_o dosyası varsa bizim bipartite-LS türetmemizin
yerini alabilir.

**15. Gün kümesi H'nin kapsamı** — Flight Pairs ve O&D tablosu `Gün∈{1..7}`
kullanıyor; bunun haftalık döngü indeksi (her hafta tekrarlanan) olduğu
varsayılıyor (G'nin dairesel karşılaştırması da bu varsayıma dayanıyor). Gerçek
takvim mi, yoksa döngü indeksi mi?

---

Kayıt & Soru-Cevap penceresi (organizatör tarafından, 16 Temmuz'a kadar açık —
bkz. brief) kapanmadan önce bu liste güncel tutulmalı; yeni bir VARSAYIM eklenirse
bu dosyaya da eklenir (tek nokta, `ASSUMPTIONS.md` ile senkron).

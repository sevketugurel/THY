# Baseline İhlal Otopsisi (2026-07-09)

M5'in DAL C teşhisi (`ASSUMPTIONS.md` VARSAYIM-12) organizatöre gitmeden önce
kullanıcı talebiyle yapılan derin analiz. Kod değişikliği YOK — yalnızca
kaynak kod incelemesi (`add_e1_constraints`, `add_e2_constraints`,
`add_f_constraints`, `add_a_constraints`, `add_g_constraints`,
`independent_validator.py`) + brief'in tam metniyle (sayfa 4-6) çapraz
kontrol + iki yeni analiz script'i (`scripts/autopsy_baseline_violations.py`
ve ek ad-hoc A/G/F baked-in hesapları, `runs/autopsy_baseline_violations.json`).

## Özet tablo

| Aile | Orijinal tanık sayısı | **Düzeltilmiş gerçek sayı** | Sınıflandırma | K=400'de "baked-in" (çözülemez kalan) |
|---|---|---|---|---|
| E1 | 296 | **690** | GERÇEK (model doğru, validator eksik kapsam) | 372/690 (%54) |
| E2 | 1181 | **1219** | GERÇEK (model doğru, validator eksik kapsam) | 618/1219 (%51) |
| F | 31 | 27 (küçük fark, aşağıda) | GERÇEK (brief'in kendi kapasite sayıları) | 0/27 (%0 — K≥100'de tamamen çözülebilir) |
| A | 487 ham | **144** (VARSAYIM-11 exemption sonrası) | GERÇEK (validator'da exemption eksik — ayrı bug) | 44/144 (%31) |
| G | 53 | 53 (değişmedi — model/validator birebir aynı kod) | GERÇEK | 13/53 (%25) |

**En önemli bulgu**: K=400'de bile E1'in %54'ü ve E2'nin %51'i **kesinlikle
çözülemez** durumda — çünkü ihlale karışan pazarların HİÇBİRİ top-400
ayarlanabilir kümede değil (VARSAYIM-6'nın "gap∈[L,U]⟹x=1 zorunlu" kuralı
gereği, alt-küme modunda sabitlenen uçuşların hiçbir hareket özgürlüğü yok).
Bu, K=50/100/200/400'ün TAMAMININ neden infeasible çıktığını doğrudan
açıklıyor — tek bir kısıt formülasyon hatası DEĞİL, **K-subset mekanizmasının
kendisi**, sabitlenen ~15000+ uçuşun baseline'ının kendi ihlallerini modele
KOŞULSUZ HARD CONSTRAINT olarak taşıyor.

---

## 1. E1 — validator KAPSAM hatası bulundu (690 gerçek, 296 değil)

**Model tarafı** (`add_e1_constraints`): market-pair kümesi `_market_groups(candidates)`
üzerinden TÜM YAPISAL olarak var olan adaylardan kuruluyor (gap geçerliliğine
bakmadan) — `groups[(o,d,gun)]` bir aday listesi, `fwd = sum(x_i for i in groups[...])`.
Bir pazar-çifti E1_PAIRS'e girmesi için gereken TEK şart: HER İKİ yönde de
YAPISAL OLARAK en az bir aday olması (VARSAYIM-6'nın ifadesiyle BİREBİR
tutarlı: "en az bir candidate'ı olan pazar çiftlerine uygulanır").

**Validator tarafı** (`independent_validator.py::validate_output`, E1 bölümü):
`counts` sözlüğü YALNIZCA `data["selected_connections"]`'tan (yani SEÇİLMİŞ/
offered bağlantılardan) kuruluyor — bir pazar `counts`'ta anahtar olmak için
en az BİR SEÇİLMİŞ bağlantıya sahip olmalı. Bu, VARSAYIM-6'nın "en az bir
CANDIDATE'ı olan" ifadesinden DAHA DAR bir kapsam.

**Somut fark**: bir pazar çiftinde fwd yönünde YAPISAL adaylar var ama
HİÇBİRİ baseline'da [L,U] içinde değilken (n_fwd=0, seçilen SIFIR), bwd
yönünde n_bwd>0 seçilmiş bağlantı varsa:
- Model: pazar E1_PAIRS'te (her iki yönde de yapısal aday var) → `bwd_rule`:
  `n_bwd - 0 <= alpha*(0+n_bwd)` → `n_bwd <= 0.2*n_bwd` → **HER ZAMAN YANLIŞ**
  (n_bwd>0 için) → bu pazar İHLAL sayılır.
- Validator: `counts`'ta fwd YOK (n_fwd=0, seçilmiş SIFIR bağlantı) →
  `(o,d,gun) not in counts` → pazar çifti TAMAMEN ATLANIR, hiç kontrol
  edilmez.

Bu YAPISAL bir validator eksikliği — **394 ihlal (690-296) validator
tarafından KAÇIRILIYOR**. `scripts/autopsy_baseline_violations.py`, modelin
`_market_groups` mantığını BİREBİR replike ederek 690 gerçek ihlali ortaya
çıkardı.

**E1'in "koşullu aktivasyon" YOK olması bilinçli mi?** Brief'in E1 metni
(sayfa 5): *"(E1) Skor/bağlantı-sayısı dengesi: İki yöndeki sunulan bağlantı
sayıları arasındaki bağıl dengesizlik α eşiğini aşmamalı. İki yön de boşsa
kısıt kendiliğinden sağlanır."* — E2'nin metninden FARKLI olarak, E1'in
metninde **"yalnızca ... varken" / "koşullu aktivasyon"** ifadesi YOK. E2
metni AÇIKÇA şunu söylüyor: *"Yalnızca her iki yönde de en az bir aktif
bağlantı varken ... Yönlerden biri pasifse kısıt bağlayıcı olmamalıdır
(koşullu aktivasyon)."* Bu FARK muhtemelen KASITLI (brief E1 için Big-M/
koşullu-aktivasyon istemiyor, yalnızca "ikisi de boşsa otomatik sağlanır"
diyor — TEK yönün boş olması durumu AÇIKÇA ele alınmamış, model bunu
UNCONDITIONALLY (E2 gibi Big-M'siz) uyguluyor, ki bu VARSAYIM-6'nın zaten
belgelediği "amaç bastırıcı" davranışı doğuruyor). **Sınıflandırma: E1'in
KENDİSİ muhtemelen doğru yorumlanmış (GERÇEK ihlal), ama validator'ın
KAPSAM eksikliği bir ACCOUNTING bug.**

**Önerilen aksiyon**: `independent_validator.py`'nin E1 bölümünü,
`add_e1_constraints`'in `_market_groups` mantığıyla BİREBİR eşleşecek şekilde
düzelt (seçilmiş bağlantı sayısı DEĞİL, yapısal aday varlığı temelinde
pazar-çifti kapsamı kur).

---

## 2. E2 — model DOĞRU (koşullu aktivasyon var), validator'da 2 kapsam hatası

**Model tarafı** (`add_e2_constraints`): `a_dir[o,d,gun] >= x[i]` (herhangi
bir aday seçilirse a_dir=1) + `e2_fwd`/`e2_bwd` kısıtları yalnızca
`a_dir[fwd]=1 VE a_dir[bwd]=1` olduğunda BAĞLAYICI (Big-M ile gevşetilmiş
aksi halde) — brief'in "koşullu aktivasyon" talebini TAM olarak karşılıyor.
**Bu doğru.**

**Validator'daki 2 kapsam hatası**:
1. `provider_e2.get_journey_constant(o, d)` — YALNIZCA DİREKT medyan, LS-tahmin
   FALLBACK'İ (`get_journey_constant_estimate`) YOK. Model'in KENDİSİ
   (`journey_constants` dict, VARSAYIM-8) her iki kaynağı da kullanıyor.
   Sonuç: **571 "estimated" pazarın E2 kontrolleri validator tarafında
   SESSİZCE ATLANIYOR** (`except KeyError: continue`).
2. (E1 ile aynı desende) pazar-çifti kapsamı `data["selected_connections"]`
   temelli, yapısal aday varlığı DEĞİL — ama E2'de bu daha az kritik çünkü
   `a_dir`'in Big-M mekanizması zaten "hiç seçilmemiş yön" durumunu kendi
   içinde doğru ele alıyor (validator'ın журneys_by_market'i de aynı mantıkla
   inşa ediliyor — sadece SEÇİLİ olanlardan).

Bu iki eksiklik nedeniyle validator 1181 raporluyordu, gerçek sayı **1219**
(`scripts/autopsy_baseline_violations.py`, `journey_constants` dict'in TAM
halini kullanarak).

**Yeni ve önemli bulgu — Gamma'nın kendisi sorgulanmalı**: 1219 ihlalin
**949'unda (%78) K_od ASİMETRİSİNİN KENDİSİ Gamma(30dk)'yı AŞIYOR** —
yani gap SIFIR olsa bile (imkansız ama ideal durum), yalnızca
$K_{od}=T^{IB}_o+T^{OB}_d$ ile $K_{do}=T^{IB}_d+T^{OB}_o$ arasındaki YAPISAL
fark (istasyonların KENDİ blok sürelerinin asimetrisi) tek başına Gamma'yı
aşıyor. Bu, GAP SEÇİMİYLE (bizim yorumumuzla) ÇÖZÜLEMEYECEK bir durum —
Gamma=30dk parametresi gerçek veri ölçeğinde (küresel ağ, büyük istasyon
çeşitliliği) çok sıkı olabilir, ya da "en iyi yolculuk süresi" tanımının
KENDİSİ (K_od'un TAMAMINI mı, yoksa yalnızca bağlantı boşluğu kısmını mı
karşılaştırmalı?) yeniden gözden geçirilmeli.

**Sınıflandırma: E2'nin KENDİSİ doğru yorumlanmış ve doğru implemente
edilmiş (model tarafı GERÇEK ihlal + doğru koşullu aktivasyon). Validator'ın
2 kapsam eksikliği ACCOUNTING bug. Gamma=30dk'nın gerçek veri ölçeğinde
uygulanabilirliği ayrı bir VARSAYIM/organizatör sorusu (aşağıda).**

**Önerilen aksiyon**: (a) validator'a estimate-fallback ekle (aynı
`get_journey_constant_estimate` sırası), (b) organizatöre Gamma'nın büyük
ölçekli/coğrafi olarak çeşitli ağlarda nasıl yorumlanması gerektiğini sor.

---

## 3. F — model ve sayılar DOĞRU (brief'in kendi rakamları), gerçek kapasite sıkışıklığı

**Model tarafı**: `z_dep`/`z_arr` kova-atama binary'leri HER ayarlanabilir
kalkış/varış için KOŞULSUZ kuruluyor (adayın x=1 olup olmadığından bağımsız)
— brief'in "Her ayarlanabilir kalkış/varış tam olarak bir kovaya atanmalı"
ifadesiyle BİREBİR tutarlı (bir uçuş, bağlantısı pazarlansın ya da
pazarlanmasın, fiziksel olarak bir slot işgal eder). **Bu doğru.**

**Kapasite sayıları (10/15) bizim VARSAYIM'ımız DEĞİL** — brief'in §2.4
"Girdi Verileri" bölümünde AÇIKÇA veriliyor: *"IST Hub kapasiteleri (10
dk'lık zaman aralıkları (kova) için kalkış (10)/varış (15) slot
kapasiteleri)"* (sayfa 4). Önceden `ASSUMPTIONS.md`'de bu net belgelenmemişti
— artık burada teyit edildi, ayrı bir VARSAYIM gerekmiyor.

**Sayı farkı (31 vs 27)**: witness'in orijinal F kontrolü (`validate_output`)
ile bu otopsinin bağımsız rekonstrüksiyonu arasında küçük bir fark var (4
ihlal) — muhtemelen kova sınırı yuvarlama/epoch hesaplama detayında ufak bir
fark (iki ayrı `epoch_min` çağrısı, `_epoch_min(ts, anchor)` vs kendi
`epoch_min` fonksiyonum). **Küçük ölçekli (toplam ~31'in %13'ü), kök neden
teşhisini DEĞİŞTİRMİYOR — ayrı, düşük öncelikli bir iz sürme kalemi.**

**Sınıflandırma: GERÇEK.** K≥100'de F'nin KENDİSİ tamamen çözülebilir
(baked-in=0) — F, K=400'ün infeasible kalmasının SEBEBİ DEĞİL (F_off testinin
hâlâ infeasible çıkması bunu zaten doğrulamıştı).

---

## 4. A — validator'da EXEMPTION mantığı YOK (ayrı, önemli accounting bug)

**Model tarafı** (`add_a_constraints`): VARSAYIM-11'in best-case-uzlaştırılabilirlik
testini uyguluyor (`arr_hi + week_offset >= dep_lo + r_o + tau`, HER bacağın
KENDİ [lo,hi] bounds'uyla) — geçemeyen çiftler MUAF tutuluyor (kısıt hiç
kurulmuyor), 349 çift full-data'da bu şekilde exempt.

**Validator tarafı** (`independent_validator.py`, A bölümü): `_rotation_subpairs`
+ `_match_rotation_legs_independent` AYNI eşleştirmeyi yapıyor, AMA
exemption testi HİÇ UYGULANMIYOR — HER eşleşen çift KOŞULSUZ kontrol
ediliyor. **Bu, gerçek bir model solüsyonunu (VARSAYIM-11 muafiyetini meşru
şekilde kullanan) YANLIŞLIKLA ihlalli olarak işaretleyebilir** — henüz test
edilmedi çünkü M5'te hiç geçerli bir full-data çözümü ÜRETİLEMEDİ (validate
edilecek bir şey olmadı), ama bu bağımsız, önemli bir düzeltme kalemi.

**Ham 487 vs gerçek 144**: `scripts/autopsy_baseline_violations.py`'nin
tamamlayıcı analizi (bu oturumun başında, DAL C teşhisi sırasında zaten
hesaplanmıştı): 1524 kapsam-içi rotasyon çiftinin 343'ü VARSAYIM-11 ile
exempt (best-case'te bile imkansız), kalan 1181'i (E2 ile TESADÜFEN aynı
sayı, bağımsız hesaplamalar — çapraz kontrol edildi, kod hatası değil)
best-case'te reconcilable ama bunların yalnızca **144'ü baseline'ın KENDİ
(ayarlanmamış) değerlerinde İHLALLİ**.

**Sınıflandırma: GERÇEK (144), ama validator'ın exemption eksikliği AYRI bir
ACCOUNTING bug — ilerideki (Phase 4) bir gerçek çözüm doğrulanırken mutlaka
düzeltilmeli, aksi halde geçerli bir çözüm yanlışlıkla reddedilir.**

**Önerilen aksiyon**: `independent_validator.py`'ye VARSAYIM-11'in best-case
testini (`add_a_constraints`'in AYNISI, ama `src.model` import etmeden —
mevcut "hiçbir import" disiplinini koruyarak) ekle.

---

## 5. G — model/validator BİREBİR aynı kod, parity kanıtlı, ihlal GERÇEK

`src/model/day_clustering.py::cluster_flight_days` ve
`independent_validator.py::_cluster_flight_days_independent` KARŞILAŞTIRILDI
— iki fonksiyon SATIR SATIR aynı (kasıtlı kopya, "diskalifiye sigortası"
olarak yorumlanmış). **Hiçbir kapsam/parity sorunu yok.** 53 ihlal tamamen
GERÇEK — VARSAYIM-9'un küme-bazlı çözümünden SONRA bile kalan, kümenin
KENDİ İÇİNDE X_dev'i aşan gerçek düzensizlikler.

---

## 6. Phase 2 hipotezi — DOĞRULANDI (nicel kanıtla)

**Hipotez**: alt-küme modunda (K=50/100/200/400) baseline'a sabitlenen
uçuşlar, baseline'ın KENDİ ihlallerini modele KOŞULSUZ hard-constraint olarak
taşıyor.

**Kanıt**: her aile için "baked-in" (HER İKİ pazarı da top-K ayarlanabilir
kümenin dışında kalan, dolayısıyla K'nın büyüklüğünden TAMAMEN bağımsız
olarak çözülemez kalan) ihlal sayısı:

| K | E1 baked-in | E2 baked-in | A baked-in | G baked-in | F baked-in |
|---|---|---|---|---|---|
| 50 | 659/690 (%96) | 1114/1219 (%91) | 104/144 (%72) | 46/53 (%87) | 10/27 (%37) |
| 100 | 605/690 (%88) | 1019/1219 (%84) | 99/144 (%69) | 40/53 (%75) | 0/27 (%0) |
| 200 | 509/690 (%74) | 861/1219 (%71) | 58/144 (%40) | 27/53 (%51) | 0/27 (%0) |
| 400 | 372/690 (%54) | 618/1219 (%51) | 44/144 (%31) | 13/53 (%25) | 0/27 (%0) |

K arttıkça baked-in oranı düzenli DÜŞÜYOR (mekanizma beklendiği gibi
çalışıyor) ama **K=400'de bile E1'in %54'ü, E2'nin %51'i hâlâ MUTLAK
ÇÖZÜLEMEZ** — bu, adjustable-subset merdiveninin K-şemasının (50/100/200/400)
full-data ölçeğinde YETERSİZ KALDIĞINI kanıtlıyor. K çok daha büyük olmalı
(muhtemelen ~900+ pazarın tamamına yakını, yani full-adjustable'a yakın) —
ki bu da step1'in (full-adjustable, tüm 18118 aday) neden BÜYÜKLÜK
nedeniyle 660s'de çözülemediğini (ayrı bir sorun, infeasibility DEĞİL,
tractability) açıklıyor.

**Sonuç**: DAL C'nin "hangi kısıt suçlu" sorusu YANLIŞ SORUYDU — suçlu tek
bir kısıt DEĞİL, **K-subset yaklaşımının KENDİSİ** (tractability için
gerekli ama mevcut K-şeması yetersiz). Bu VARSAYIM-12'yi ÖNEMLİ ÖLÇÜDE
DARALTIYOR: full-data muhtemelen brief'in kısıt setiyle YAPISAL OLARAK
TUTARSIZ DEĞİL — yalnızca mevcut adjustable-subset merdiveninin K değerleri
yetersiz, VE bazı gerçek (E1/E2 validator-doğru, A/G zaten exempt-sonrası)
ihlaller full-adjustable modda (step1) muhtemelen ÇÖZÜLEBİLİR olacak, ama
step1'in KENDİSİ modelin BÜYÜKLÜĞÜ nedeniyle 660s'de sonuçlanamadı.

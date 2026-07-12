# Teknik Rapor — IST Hub Tarife Optimizasyonu

TEKNOFEST "Yapay Zeka Destekli Havayolu Optimizasyonu" — Pyomo/HiGHS MIP.
Teslim: 2026-07-16 17:00. Kod: `main.py`, `src/`; kanıt zinciri: `docs/STATUS.md`,
`docs/decisions.md`, `ASSUMPTIONS.md`.

## 1 · Özet + Problem Çerçevesi

İstanbul (IST) hub'ı üzerinden aktarmalı O–D pazarlarında, TK uçuşlarının
ayarlanabilir varış/kalkış saatlerini (baseline ±180dk pencere) optimize
ederek (a) [L,U]=[60,300] dakikalık meşru bağlantı sayısını ve (b) rakip
taşıyıcılara karşı sıralama ödülünü maksimize eden bir tarife üretiyoruz.
Amaç fonksiyonu iki bileşenli: bağlantı-sayısı ödülü (azalan getiri, Modül-5
monoton slot) + O–D bazında rakip-yenme sıralama ödülü. Yedi kısıt ailesi
(A–G) modelin tamamını oluşturuyor: A (rotasyon), B (bağlantı uygunluğu,
bidirectional reifikasyon), C (monoton slot), D (rakip yenme + sıralama), E1
(yönsel sayı dengesi), E2 (yön-arası seyahat-süresi farkı), F (hub
kova/kapasite bağlama), G (düzenlilik). Formel gösterim `docs/model.md`'de.

**Sonuç — iki dallı**: Fixture (sentetik, şema-doğru küçük ölçekli veri
kümesi) üzerinde amaç değeri **668.75**, ÜÇ bağımsız yoldan doğrulanmış
(CLI = bağımsız `recompute_objective` = saf-Python brute-force oracle).
Full-data'da (gerçek yarışma verisi, 18.147 aday, ~900+ pazar) **doğrulanmış
bir objective_value bulunamadı** — kapsamlı, çok-açılı bir kampanyadan sonra
(bkz. §5) full-data'nın kendine özgü bir yapısal zorluk sergilediği
sonucuna varıldı. Teslim paketi bu yüzden **Branch B**: hiçbir ihlalli
tarife dosyaya yazılmaz (üretim merdiveninin kendi garantisi, §5), fixture
zincirinin tam doğruluğu + full-data'daki sistematik teşhis + organizatöre
somut sorular sunulur.

## 2 · Formülasyon Gerekçeleri

| Kısıt | Doğal-dil (brief) | Matematiksel form (özet) | Neden bu form |
|---|---|---|---|
| A | Rotasyon: OB kalkışı, önceki IB varışından R_o+τ sonra olmalı | $t^{dep}_{OB} \ge t^{arr}_{IB} + R_o + \tau$, koşulsuz | Big-M gerekmiyor — rotasyon fiziksel bir alt-sınır, reifikasyon değil |
| B | Bağlantı gap∈[L,U] ⟺ sunuluyor | $x_\pi=1 \Leftrightarrow gap_\pi\in[L,U]$, per-candidate Big-M, İKİ YÖNLÜ | Tek yönlü (yalnız $x=1\Rightarrow gap\in[L,U]$) E1/E2 varlığında solver'a geçerli bağlantıyı gizleme teşviki verir |
| C | Modül-5 monoton slot | azalan-getiri merdiveni, slot değişkenleri | Brief'in kendi "azalan getiri" tanımının doğrudan MIP kodlaması |
| D | Rakip yenme + sıralama | $beat_{\pi,k}=1\Leftrightarrow J_\pi\le T_{comp,k}$, OR-aggregation `beaten_k`, rank one-hot | Gerçek ranking tablosu monotonik (0/820 ihlal) — tek yönlü forcing yeterli; rank linking EŞİTSİZLİK ($r\ge N-beaten$), eşitlik solver'ı $beaten=N$'e ulaşmaktan yapısal olarak engelliyordu (CLI testiyle yakalandı) |
| E1 | Yönsel sayı dengesi | $\lvert n_{fwd}-n_{bwd}\rvert\le\alpha(n_{fwd}+n_{bwd})$, **koşullu** (KARAR-0, §3) | Lineer, Big-M'siz ana toplamlar için; koşullu aktivasyon E2'nin `a_dir` göstergesini yeniden kullanır (satır ekonomisi) |
| E2 | Yön-arası seyahat-süresi farkı ≤Γ | argmin sandviç ($J_{best}$ candidate-bazlı Big-M ile üstten/alttan sıkıştırılır), koşullu (D'nin OR-aggregation'ıyla aynı desen) | MIP'in doğal $\min(\cdot)$ operatörü yok — "en iyi seyahat süresi" bir SEÇİLEBİLİR alt-kümenin minimumu |
| F | Hub kova/kapasite | pencere-ulaşılabilir kova bağlama, ayrı departure/arrival z-aileleri, residual-capacity precompute | 144 kova yerine yalnızca [t_lo,t_hi]'nin kestiği kovalar — M5c'de satır sayısını %96.8 azaltan bijective eşitlik formu |
| G | Düzenlilik (gün-içi spread ≤X_dev) | küme-bazlı referans-zaman formülasyonu (VARSAYIM-9) | Koşulsuz okuma TK2841'in 645dk'lık gerçek sapması yüzünden full-data'yı formel olarak infeasible kılıyordu (Helly-özelliği kanıtı) |

**Big-M disiplini**: her M candidate/pair-bazlı türetilir (`src/model/big_m.py`),
global bir sabit YOK; model kurulumunda otomatik `<=1440` assert. Bu, hem
LP gevşekliğini azaltıyor (tighter relaxation) hem `w=720` gibi geniş
pencerelerin Big-M'i 1440'ın üzerine taşıyabildiği bir hatayı erken
yakalıyor (M1 tasarım notu).

## 3 · Varsayımlar ve Veri Anomalileri

17 VARSAYIM belgelendi (`ASSUMPTIONS.md`), en önemlileri:

| # | Bulgu → Karar |
|---|---|
| 6/16 | E1'in formülü belirsiz (koşullu mu literal mi) → **KARAR-0**: koşullu aktivasyon varsayılan. Kanıt: brief §7'nin açık ipucu ("koşullu kısıtları doğru kurun, aksi halde pasif yönler dengeyi yapay zorlar"), organizatörün KENDİ baseline'ı literal okumada 690 pair-gün ihlalli, full-data'da E1 fazlalık oranının HER noktada sabit 0.800=1−α çıkması (ihlallerin ~tamamı tek-yön-sıfır vakası — gerçek bir dengesizlik değil). Literal okuma duyarlılık analizi olarak bir bayrakla (`e1_activation`) yaşıyor. |
| 9 | TK2841 gün-içi 645dk sapması → G'nin koşulsuz okuması TÜM full-data'yı infeasible kılardı → küme-bazlı G (dairesel en-büyük-boşluktan kes). |
| 10/11 | A'nın "aynı gün" OB/IB eşleştirmesi 1496 çiftin %54.7'sini uzlaştıramıyor, %45.3'ü kronolojik TERS → baseline-kronoloji eşleştirmesi (dairesel-haftalık, açgözlü). Düzeltmeden SONRA bile 382/1571 (%24.3) çift fiziksel olarak imkânsız → aynı mantıkla (kendi en-iyi-durumunda bile imkânsızsa) muaf. |
| 17 | E2'nin bazı çiftleri (63 adet) journey-constant asimetrisi yüzünden HANGİ seçim yapılırsa yapılsın Γ'yı aşıyor (schedule-independent, statik kanıt) → **KARAR-0b**: bu çiftler E2'den muaf (exempt+log), model ve bağımsız validator aynı statik testi ayrı ayrı uyguluyor. |
| 12 | Full-adjustable modelin çözüm süresi belirsiz → §5. |

**Hub yoğunluğu ve ayrıştırılamazlık** (kritik bir olumsuz bulgu, M5c):
full-data'da bir fiziksel uçuş bacağı ORTALAMA 4.4 farklı (o,d) pazarına
katılıyor (maksimum 183) — aday üretiminin tam inbound×outbound
cross-product olmasının doğal sonucu. Küçük bir "tohum" pazar kümesini bile
serbest bırakmak, bacak-paylaşımı üzerinden geçişken olarak ağın neredeyse
TAMAMINA yayılıyor (K=50'de bile candidate'ların adjustable-subset merdiveni
gerçek bir boyut küçültmesi sağlamıyor) — IST hub'ı gerçekten ayrıştırılamaz
bir ağ; alt-problem bölme stratejileri (K-subset, Benders) yapısal olarak
beklenen kazancı sağlamadı, bu yüzden emekliye ayrıldı.

## 4 · Doğrusallaştırma Seçimleri

- **Per-candidate Big-M** global sabitten sistematik olarak daha sıkı
  (`tests/unit/test_big_m.py`, worked examples). E1'in koşullu aktivasyonu
  için yeni $M_{pair}=(1-\alpha)\cdot\max(|\Pi_{fwd}|,|\Pi_{bwd}|)$ —
  candidate-SAYISI bazlı (zaman-ölçekli değil), doğası gereği küçük.
- **E1'in lineer (Big-M'siz) ana formu**: $n_{fwd},n_{bwd}$ zaten $\sum x_\pi$
  — reifikasyon gerekmiyor; yalnızca koşullu aktivasyonun M-terimi Big-M
  gerektiriyor.
- **E2'nin argmin sandviç deseni**, D'nin OR-aggregation'ıyla (`beaten_k`)
  AYNI yapısal desen — kod ve doğruluk argümanı tekrar kullanıldı.
- **F'nin bijective kova eşitliği** (M5c row-fix): $t=bucket\_start\cdot z+offset$
  — eski per-bucket Big-M çiftini TEK bir eşitliğe indirgeyerek satır
  sayısını %96.8 azalttı, LP amaç/oranı BİREBİR AYNI kaldı (eşdeğerlik
  kanıtlı).
- **M5c fold'ları**: E2'nin singleton-pazar-yönü binary'leri (gerçek seçim
  özgürlüğü olmayan durumlar) `pyo.Expression`'a katlandı; D'nin
  always-beats/never-beats çiftleri de aynı ilkeyle satır/Var'dan
  düşürüldü.

## 5 · Çözüm Kalitesi ve Performans

**Fixture (668.75)**: `main.py --fixture` (CLI) = `recompute_objective`
(bağımsız) = `tests/slow/test_bruteforce_oracle.py` (saf-Python, `src.model`
import ETMEYEN 10-dakika grid brute-force). Her iki `e1_activation` modunda
(koşullu/literal) DA 668.75 — fixture'ın E1 çiftleri optimumda zaten her
iki yönde aktif, KARAR-0 bu senaryoyu değiştirmiyor.

**Full-data zorluğu — sekiz bağımsız kanıt yönü**: full-adjustable model
(18.147 aday, 205.981 satır/308.475 sütun/253.731 binary, presolve sonrası
169.859 satır) kök-düğümde takılı kalıyor — `appsi_highs`'ın kendi
`time_limit`'i büyük modellerde kök-düğüm cut üretimini güvenilir şekilde
kesemediği için dış (SIGTERM/SIGKILL) bir bekçi zorunlu (`src/solve/subprocess_watchdog.py`).
Sistematik teşhis (M5/M5c/M5d/M5e/M5f, kronolojik):

1. Beş bağımsız model/amaç/solver-ayarı kombinasyonu (reward, min-sapma,
   F-fix, F+E2-fold, symmetry-detection kapalı) AYNI "hızlı yakınsa sonra
   tam sessizlik, Nodes=0" semptomunu gösterdi.
2. Statik E1/E2 fizibilite sertifikaları (saf pandas, MIP yok) TEMİZ —
   E1/E2 provably infeasible DEĞİL.
3. Saf-Python greedy repair (baseline'dan onarım) koordinesiz onarımlar
   yüzünden regresyona uğradı — heuristiğin kabalığı, infeasibility kanıtı
   değil.
4. **KARAR-0'ın gerçek etkisi** (M5f, bu kapanış turu): koşullu E1
   baseline'ın E1 ihlal kütlesini 690→296'ya düşürdü (**-57.1%**, gerçek ve
   ölçülebilir) ama full-data'nın temel zorluğunu TEK BAŞINA çözmedi.
5. Elastik+warm-start (M5f Kapı-3, koşullu E1): 900s bütçe, ilk denemede
   gerçek incumbent — elastik-obj=347.660,50 (KARAR-0-öncesi eşdeğer
   ölçümden — 369.921,70 — daha iyi).
6. LNS component/fold: Σslack 62.418,40→56.540,60 (%9.5) ilk 4
   iterasyonda, sonra TAM PLATO — kalan slack'in **%99,78'i E2**
   (E1'in payı 123,60dk'ya düşmüş, KARAR-0'ın öngörülen etkisi doğrulandı).
   20 iterasyon boyunca iyileşmesizlik → protokol gereği dur.
7. Çoklu-bileşen LNS (tek deneme, en kötü 3 bağlantılı bileşen AYNI ANDA
   serbest): **6.8 saniyede KESİN infeasible** (belirsiz zaman-aşımı değil,
   HiGHS'in kendi sertifikası) — "yerel düzeltme alanı boş" hipotezinin
   panzehiri k=3'te bile işlemedi.
8. Ağ-çapı ihlal ayak izi: E1+E2 ihlalli pazarlardan serbest bırakılması
   gereken flight-instance oranı **%74.5-74.8** — sorun birkaç izole
   bileşende değil, ağın büyük bir kesiminde eşzamanlı.

**Sonuç**: sekiz bağımsız yönün TÜMÜ aynı temel semptomu gösteriyor — bu
artık ne bir formülasyon-yorumu sorunu (KARAR-0 altında bile kalıcı) ne
solver-ayarı sorunu (beş kombinasyon aynı) ne model-boyutu sorunu (205K
satırlık en küçük model bile aynı duvara çarpıyor). En olası açıklama,
HiGHS'in bu problem sınıfındaki (yoğun candidate-bazlı Big-M zincirleri +
cross-product'tan gelen aşırı bacak-paylaşımı) kesme-düzlemi davranışının
kendine özgü bir sınırı — ticari bir solver (Gurobi/CPLEX) veya çok daha
uzun bir bütçe (saatler) bunu netleştirebilirdi; Gurobi'nin ücretsiz
lisansı ~2000 satır/değişkenle sınırlı olduğundan (model ~330K satır)
denenemedi, akademik lisans temin edilemedi.

### 5b · Γ Duyarlılık Analizi (EK — resmî sonucu değiştirmez)

**Resmî teslim konfigürasyonu Γ=30'da kalır.** Bu bölüm, "E2'nin zorluğu
toleransın (Γ) dar olmasından mı kaynaklanıyor?" sorusuna solver
harcamadan kısmi bir cevap arayan bir ek analizdir (Kapı-B,
`scripts/scan_gamma_sensitivity.py`, saf-pandas — solve YOK).

Üç solver-free sinyal, full-data'da (18.147 aday, 3.258 yön-çifti):

| Γ (dk) | Statik-imkânsız çift | Baseline E2 ihlal (adet) | Baseline E2 ihlal kütlesi (dk) | Bağımsız-çift alt sınır (dk) |
|---|---|---|---|---|
| 30 (resmî) | 63 | 1.222 | 70.072,5 | 5.055,0 |
| 45 | 49 | 926 | 53.245,0 | 4.200,0 |
| 60 | 38 | 710 | 40.712,5 | 3.552,5 |
| 90 | 29 | 333 | 25.325,0 | 2.502,5 |
| 120 | 29 | 215 | 17.032,5 | 1.632,5 |
| 150 | 11 | 136 | 11.427,5 | 1.047,5 |
| 180 | 7 | 92 | 8.165,0 | 717,5 |

Son sütun (bağımsız-çift alt sınır), her yön-çiftinin kendi en iyi
durumuna BAĞIMSIZ ulaştığını varsayan iyimser bir tahmindir (bacak-paylaşım
kuplajını yok sayar — §5'in 8. maddesindeki ağ-çapı ayak izi bulgusuyla
aynı yapısal gerçek). Gerçek bir solve'un Σs_e2'si bu sayıdan KÜÇÜK
OLAMAZ. **Γ=180'de bile bu alt sınır 717,5dk ile sıfırdan uzak** — Γ'yı
6 katına çıkarmak (30→180) mutlak ihlal sayılarını ~86% azaltıyor ama
Σslack=0'a ulaştırmıyor. Karar kuralı gereği (alt sınır swept aralığın
hiçbir noktasında 0'a inmediği için Γ*>180), bu bulgudan sonra planlanan
solver kampanyası (Kapı-C) **koşulmadı** — ek 3 saatlik bütçe harcamak
yerine, mevcut kanıt "Γ tek başına yeterli değil" sonucunu zaten net
gösteriyordu.

**Yorum**: bu, §5'in dokuzuncu bağımsız kanıt yönüdür ve aynı sonuca
Γ ekseninde ulaşır — full-data'daki E2 zorluğu toleransın darlığından
değil, ağ genelindeki kuplajlı bacak-paylaşım yapısından kaynaklanıyor.
Ham veri: `outputs/GAMMA_SENSITIVITY_STATIC_SCAN.json`, ayrıntı
`docs/STATUS.md` "Kapı-B" bölümü, `ASSUMPTIONS.md` VARSAYIM-12
GÜNCELLEME 6.

**Üretim merdiveni garantisi** (Kriter 3 + dayanıklılık): `main.py --full-data`
tek komutla 3 adımlı bir merdiven koşar — (1) tam model bütçeli solve, (2)
başarısızsa TEK bir bekçili elastik solve denemesi (Σslack≈0 ise
strict-feasible), (3) ikisi de olmazsa şema-uyumlu bir teşhis çıktısı
(`objective_value: null`, `solver_metrics.status: "no_feasible_solution_found"`)
— **hiçbir adım, dosyaya yazılmadan önce bağımsız validator'dan sıfır
ihlalle geçmeden kabul edilmez**. Bu garanti GERÇEK full-data'da uçtan uca
doğrulandı (`docs/STATUS.md` Kapı-5): adım1+adım2 watchdog_killed, adım3
devreye girdi, yazılan çıktı tam şema-uyumlu ve boş tarife, hiçbir ihlalli
tarife dosyaya yazılmadı.

## 6 · Kod Kalitesi Referansı + Sonuç Tartışması

**Kod kalitesi** (Kriter 4, ayrıntı README.md): tek komut kurulum
(`pip install -r requirements.txt`, pin'li), tek komut çalıştırma
(`python main.py --config ... --fixture|--full-data`), 348+ test
(`python -m pytest`), determinizm testi
(`test_main_cli_is_deterministic_excluding_wall_clock`). Bağımsız validator
mimarisi (`src/validate/independent_validator.py`) `src.model.*`/`src.candidates.*`
import ETMEZ — model kodundaki bir hata ile validator'daki bir hata AYNI
yönde birbirini maskeleyemez; bu, teslim edilen HER sayının (fixture
668.75, kalan Σslack dökümleri, full-data teşhisi) iki bağımsız katmandan
geçtiği anlamına gelir.

**Kod↔model-dokümanı izlenebilirliği** (Kriter 1 kanıtı): A, B, C, D, E1,
E2, F, G + amaç fonksiyonu için 9 satırlık bir izlenebilirlik tablosu
(`docs/traceability.md`) — her satır `docs/model.md`'nin formel bölümünü,
`src/model/constraints_*.py`'deki uygulayan fonksiyonu, bağımsız
validator'ın karşılık gelen kontrolünü ve test dosyasını eşliyor. Bu
commit'te 9 satırın hepsi elle doğrulandı, sapma bulunmadı.

**Sonuç tartışması**: E1'in koşullu aktivasyonu (KARAR-0) somut, ölçülmüş
bir iyileştirme sağladı (baseline E1 kütlesi -57.1%, LNS'in kalan slack'inin
E1 payı ~%0.2'ye düştü) — ama bu, E2'nin ve ağ-çapına-yayılmış yapısal
ihlal ayak izinin baskınlığını gösterdi, tek bir "gizli hata"yı ortaya
çıkarmadı. Full-data'nın zorluğu muhtemelen brief'in kendi ölçeğinde
(18.000+ aday, 900+ pazar) bu tür yoğun candidate-bazlı MIP formülasyonları
için HiGHS'in pratik sınırlarını yansıtıyor. M6 için önerilen sonraki
adımlar (kod yok, ayrı listede — `docs/organizer_questions.md`): (1) Γ
ölçeğinin büyük/coğrafi-çeşitli ağlarda nasıl yorumlanması gerektiği
konusunda organizatör rehberliği, (2) full-ölçekte beklenen bir çözüm
süresi/solver referansı, (3) ticari bir solver ile (Gurobi/CPLEX) tek bir
karşılaştırma koşusu.

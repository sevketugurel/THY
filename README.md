# THY İstanbul Hub Tarife Optimizasyonu

> TEKNOFEST **Yapay Zekâ Destekli Havayolu Optimizasyonu** problemi için geliştirilen; İstanbul (IST) aktarma merkezi üzerinden sunulan bağlantıları, uçuş saatlerini, rakiplere göre pazar sıralamasını ve operasyonel kısıtları birlikte ele alan Pyomo/HiGHS tabanlı karma tamsayılı programlama (MIP) projesi.

## Yönetici özeti

| Başlık | Açıklama |
|---|---|
| Temel amaç | Ayarlanabilir TK uçuş saatlerini değiştirerek O–D pazarlarındaki uygun aktarmaları ve rakiplere karşı sıralama ödülünü en büyüklemek |
| Optimizasyon yaklaşımı | Pyomo ile modellenen karma tamsayılı doğrusal programlama; varsayılan çözücü HiGHS |
| Operasyon merkezi | İstanbul Havalimanı (IST) |
| Karar kapsamı | IST varış/kalkış zamanları, sunulan bağlantılar, yön dengesi, seyahat süresi dengesi, rotasyon, kapasite ve düzenlilik |
| Veri kapsamı | O&D bağlantı tablosu, yolcu/pazar önem ağırlıkları, sıralama ağırlıkları ve uçuş çiftleri |
| Güvenilir demo | Sentetik fixture üzerinde uçtan uca model kurma, çözme, çıktı üretme ve bağımsız doğrulama |
| Gerçek veri durumu | Model ve deney altyapısı çalışır; ancak 11 Temmuz 2026 tarihli son kayıt itibarıyla tüm A–G kısıtlarını sağlayan ve bağımsız validator'dan geçen bir full-data amaç değeri henüz elde edilmemiştir |
| Kalite durumu | 15 Temmuz 2026 yerel doğrulaması: **380 test geçti** |
| Ana giriş noktası | `main.py` |
| Varsayılan yapılandırma | `src/config/standard.yaml` |
| Sonuç formatı | Deterministik sıralanmış JSON |

> **Durum uyarısı:** Fixture sonucu, modelin küçük ve kontrol edilebilir bir veri kümesinde doğru çalıştığını kanıtlar. Full-data üzerinde bulunan elastik çözümler ve kısmi LNS iyileştirmeleri, bütün katı kısıtları sağlamadıkları sürece teslim edilebilir çözüm sayılmaz. Güncel deney kaydı için [`docs/STATUS.md`](docs/STATUS.md) esas alınmalıdır.

## İçindekiler

1. [Problem tanımı](#problem-tanımı)
2. [Kapsam ve başarı ölçütleri](#kapsam-ve-başarı-ölçütleri)
3. [Sistem mimarisi](#sistem-mimarisi)
4. [Proje dizinleri](#proje-dizinleri)
5. [Teknoloji yığını](#teknoloji-yığını)
6. [Veri kaynakları ve veri işleme](#veri-kaynakları-ve-veri-işleme)
7. [Aday bağlantı üretimi](#aday-bağlantı-üretimi)
8. [Matematiksel model özeti](#matematiksel-model-özeti)
9. [Çözüm stratejileri](#çözüm-stratejileri)
10. [Kurulum](#kurulum)
11. [Çalıştırma](#çalıştırma)
12. [Yapılandırma](#yapılandırma)
13. [Çıktı ve bağımsız doğrulama](#çıktı-ve-bağımsız-doğrulama)
14. [Test stratejisi](#test-stratejisi)
15. [Araştırma ve teşhis araçları](#araştırma-ve-teşhis-araçları)
16. [Mevcut sonuçlar ve performans](#mevcut-sonuçlar-ve-performans)
17. [Varsayımlar, riskler ve sınırlamalar](#varsayımlar-riskler-ve-sınırlamalar)
18. [Tekrar üretilebilirlik](#tekrar-üretilebilirlik)
19. [Dokümantasyon haritası](#dokümantasyon-haritası)
20. [Geliştirme rehberi](#geliştirme-rehberi)

## Problem tanımı

Bir hub-and-spoke ağında yalnızca tek bir uçuşu iyileştirmek yeterli değildir. Bir IST varış saatindeki değişiklik, aynı anda çok sayıda giden bağlantıyı; kapasite kovalarını; uçak rotasyonunu; haftalık düzenliliği ve karşı yön pazarlarını etkileyebilir. Bu proje, bu etkileşimleri tek bir optimizasyon modeli içinde birleştirir.

| İş problemi | Modeldeki karşılığı |
|---|---|
| Daha fazla geçerli aktarma sunmak | Bağlantı boşluğunun `[L,U]` içinde olup olmadığını belirleyen `x_π` değişkeni ve bağlantı ödülü |
| Yolcusu/önemi yüksek pazarları öncelemek | O–D bazlı `ρ_od` ağırlığı |
| Rakiplerden daha kısa seyahat süresi sunmak | Rakip bazlı yenme göstergeleri ve sıralama ödülü |
| Uçak rotasyonunu uygulanabilir tutmak | A kısıt ailesi |
| Aktarmanın gerçekten geçerli olup olmadığını doğru belirlemek | İki yönlü B reifikasyonu |
| Aynı pazarda azalan marjinal faydayı temsil etmek | C monoton slot kısıtları ve `2^{-(j-1)}` ağırlıkları |
| Gidiş/dönüş tekliflerini dengeli tutmak | E1 yönsel bağlantı sayısı dengesi |
| Gidiş/dönüş seyahat sürelerini yakın tutmak | E2 en iyi yolculuk süresi farkı |
| IST kapasitesini aşmamak | F kalkış/varış kova kapasitesi |
| Haftanın farklı günlerinde tarifeyi tutarlı tutmak | G gün kümeli düzenlilik kısıtları |

## Kapsam ve başarı ölçütleri

### Proje kapsamı

| Kapsama dâhil | Kapsam dışı / henüz desteklenmiyor |
|---|---|
| TK'nin IST bağlantılı iki bacaklı O–D seyahatleri | Çok hub'lı ağ optimizasyonu |
| Gün 1–7 için uçuş örnekleri | 7 günden uzun takvim planlama ufku |
| Tamsayı dakika hassasiyetinde zaman kararı | Saniye veya kesirli dakika hassasiyeti |
| Tüm uçuşları sabit veya tümünü ayarlanabilir çalıştırma | `adjustable_set` için keyfî uçuş alt kümesi; ana aday üretici yalnızca `all` ve `none` kabul eder |
| HiGHS üzerinden üretim/araştırma koşuları | Gurobi kod seviyesinde soyutlanmış olsa da bu proje turunda lisanslı ve tam ölçekli olarak doğrulanmamıştır |
| JSON sonuç ve bağımsız yeniden doğrulama | Yarışma organizatörünce kesinleştirilmiş resmî çıktı şeması; brief kesin şema vermediği için proje kendi izlenebilir JSON şemasını kullanır |

### Bir sonucun kabul edilme koşulları

| Kontrol | Kabul ölçütü |
|---|---|
| Çözücü sonucu | `optimal` veya kullanılabilir incumbent içeren `time_limit` |
| Yapısal doğrulama | Bağımsız validator tüm etkin A–G kontrollerinden geçmeli |
| Amaç değeri | Çözücü değeri yerine bağımsız yeniden hesaplanan değer raporlanmalı |
| Uzlaştırma | Çözücü amacı ile yeniden hesaplanan amaç tolerans içinde uzlaşmalı |
| Çıktı bütünlüğü | Seçilen bağlantılar, ayarlanan saatler, sıralamalar ve çözücü metrikleri eksiksiz yazılmalı |

## Sistem mimarisi

```mermaid
flowchart LR
    A["Excel girdi dosyaları"] --> B["Şema doğrulama ve normalizasyon"]
    B --> C["Blok süreleri, rakipler ve pazar ağırlıkları"]
    C --> D["Aday bağlantı üretimi ve güvenli budama"]
    D --> E["Pyomo MIP model kurucusu"]
    E --> F["HiGHS çözümü / warm-start / LNS"]
    F --> G["SolveResult"]
    G --> H["Deterministik JSON yazıcı"]
    H --> I["Bağımsız A-G validator"]
    H --> J["Bağımsız amaç yeniden hesabı"]
    I --> K["Geçerli / geçersiz kararı"]
    J --> K
```

### Uçtan uca veri akışı

| Aşama | Girdi | İşlem | Çıktı | İlgili modül |
|---|---|---|---|---|
| 1. Okuma | Dört Excel dosyası | Kolon adlarını normalize eder, şema ve alan kurallarını kontrol eder | Pandas tabloları | `src/data/loaders.py` |
| 2. Süre düzeltme | Elapsed ve zaman damgası alanları | 24 saat üzeri Excel wrap sorununu düzeltir | Güvenli dakika süreleri | `src/data/elapsed_parser.py` |
| 3. Sabit türetme | TK satırları | `K_od`, `R_o`, rakip en iyi süreleri ve başlangıç sıralamasını türetir | Model parametreleri | `src/data/block_times.py`, `competitors.py`, `ranking.py` |
| 4. Aday üretimi | TK inbound/outbound örnekleri | Aynı gün çapraz çarpım kurar, ulaşılabilir boşluk aralığıyla budar | `Candidate[]` | `src/candidates/generate.py` |
| 5. Model kurma | Adaylar ve parametreler | Karar değişkenleri, A-G kısıtları ve amaç fonksiyonunu kurar | `ConcreteModel` | `src/model/build.py` |
| 6. Çözme | Pyomo modeli | HiGHS ayarları, warm-start, zaman limiti ve gerektiğinde dış watchdog uygular | `SolveResult` | `src/solve/` |
| 7. Yazma | `SolveResult` | Doğal anahtarlarla sıralanmış JSON üretir | `runs/*.json` | `src/output/writer.py` |
| 8. Doğrulama | JSON ve ham veriler | Model paketinden bağımsız olarak A-G kurallarını ve amacı yeniden hesaplar | `ValidationResult` | `src/validate/independent_validator.py` |

## Üretim davranışı (`--full-data`): benchmark-safe dürüst incumbent

`main.py --full-data` varsayılan yolu her koşulda **şema-uyumlu,
tam-iddia (claim-complete), recompute-objective'li bir incumbent** yazar ve
exit 0 döner:

1. **FLOOR** — ham baseline saatleri hemen yazılır. Bu yalnızca null'a
   düşmeme emniyetidir; final seçimde hard-family ihlal profili kötüyse
   objective'i yüksek olsa bile tercih edilmez.
2. **SEED** — `data_seed/full_data_best_deltas.json` uygulanır, saatlerden
   tüm uygun bağlantılar yeniden türetilir ve amaç değeri bağımsız
   `recompute_objective` ile yazılır.
3. **IMPROVE** — kalan bütçede strict tam-MIP denenir; yalnız claim-complete
   ve strict-clean bir incumbent seçim sırasını iyileştirirse terfi eder.

Final seçim sırası: `claim_complete=True`, sonra hard-family ihlalleri
(`A+B+D+F+G`) minimum, sonra `E1+E2` minimum, en son objective maksimum.
Bu yüzden ölçülen final `outputs/full_data_output.json`, floor'un
`objective=2,983,669.09` değerinden düşük olsa da hard-family temiz olduğu
için seed-derived incumbent'tır: `objective=1,488,074.8064039326`,
`claim_complete=True`, `A/B/D/F/G=0`, `E1=106`, `E2=221`,
`strict_feasible=False`.

**exit 0 yalnız DOSYA-ÜRETİM garantisidir, fizibilite garantisi değildir.**
Strict-clean olmayan benchmark çıktısı fizibilite iddiası olarak
adlandırılmaz; `solver_metrics.status = heuristic_incumbent_with_strict_violations`
ve `diagnostics` bloğu kalan
strict E1/E2 teşhisini açıkça taşır. Resmî strict feasibility kapısı
`--strict-gate` bayrağında korunur: eski davranış, strict-clean olmayan
tarifeyi yazmaz; bulunamazsa null-teşhis + exit 1.

## Proje dizinleri

| Yol | Sorumluluk | Önemli içerik |
|---|---|---|
| `main.py` | Tek komutlu uygulama girişi | Oku → aday üret → model kur/çöz → yaz → doğrula |
| `src/config/` | Yapılandırma ve merkezi veri yolları | `standard.yaml`, `paths.py` |
| `src/data/` | Excel okuma, şema doğrulama, süre ve pazar parametreleri | Loader'lar, blok süresi sağlayıcısı, veri provenance |
| `src/candidates/` | Bağlantı adayı üretimi ve deneysel alt küme mantığı | `generate.py`, `subset.py` |
| `src/model/` | Matematiksel model | Amaç, A–G kısıtları, Big-M, elastik model, LNS ve warm-start yardımcıları |
| `src/solve/` | Çözücü soyutlaması ve orkestrasyon | Runner, warm pipeline, ladder ve subprocess watchdog |
| `src/output/` | Sonuç serileştirme | Deterministik JSON yazıcı |
| `src/validate/` | Modelden bağımsız doğrulama | Kısıt ve amaç yeniden hesabı |
| `scripts/` | Full-data deney, fizibilite ve teşhis komutları | Warm-start, LNS, LP anatomisi, sertifikalar ve worker süreçleri |
| `tests/unit/` | Hızlı, çözücüsüz mantık testleri | Loader, aday, Big-M, validator ve yardımcı algoritmalar |
| `tests/solve/` | Küçük HiGHS entegrasyon testleri | A–G kısıtları, model kurucular, warm-start ve CLI |
| `tests/slow/` | Yavaş veya geniş kapsamlı testler | Brute-force oracle ve full-data odaklı kontroller |
| `tests/fixtures/` | Paylaşılabilir sentetik Excel verileri | Dört sentetik girdi ve fixture üreticisi |
| `docs/` | Teknik raporlar ve karar kayıtları | Matematiksel model, durum, varsayımlar, çıktı formatı ve deney raporları |
| `data_raw/` | Yerel yarışma verileri | Git tarafından izlenmez; yeniden dağıtılmaz |
| `runs/` | Üretilen çözüm ve loglar | JSON/HiGHS logları; çoğu Git tarafından izlenmez |

Komutları yeniden koşmadan sonuçları incelemek için: `outputs/fixture_output.json`
(sentetik demo referansı) ve `outputs/full_data_output.json` (**resmî
full-data teslim çıktısı**: seed-derived, tam-iddia, bağımsız-recompute
`objective_value=1488074.8064039326`, açık E1/E2 strict teşhisi ekli —
strict-clean iddiası değil). `outputs/GAMMA_SENSITIVITY_STATIC_SCAN.json`
raporun bir EKİDİR, resmî sonucu değiştirmez — ayrıntı `KURULUM.md` §4b.

## Teknoloji yığını

| Teknoloji | Rol | Sürüm politikası |
|---|---|---|
| Python | Uygulama ve araştırma dili | Sistem üzerinde `python3`; proje sanal ortamı önerilir |
| Pyomo | Matematiksel modelleme | `>=6.7` |
| HiGHS / highspy | Varsayılan MIP çözücü | `>=1.7` |
| pandas | Excel verisi işleme | `>=2.2` |
| NumPy | Sayısal hesaplar ve kestirimler | `>=1.26` |
| openpyxl | `.xlsx` okuma | `>=3.1` |
| PyYAML | Senaryo yapılandırması | `>=6.0` |
| pytest | Birim ve entegrasyon testleri | `>=8.0` |

Bağımlılıklar alt sürüm sınırıyla tanımlanmıştır; kesin kilit dosyası bulunmadığı için farklı kurulum tarihlerinde küçük sürüm farkları oluşabilir.

## Veri kaynakları ve veri işleme

### Beklenen full-data dosyaları

`src/config/paths.py`, gerçek veri için tek doğruluk kaynağıdır.

| Dosya | Beklenen yol | Kullanım |
|---|---|---|
| O&D Rakip Bağlantı Tablosu | `data_raw/O&D Rakip Bağlantı Tablosu.xlsx` | Uçuşlar, taşıyıcılar, zamanlar, günler, O–D seyahatleri ve v2 elapsed alanları |
| Yolcu Verisi | `data_raw/Yolcu Verisi_masked.xlsx` | O–D önem/gelir ağırlığı `ρ_od` |
| Ranking girdisi | `data_raw/change_ranking_input.xlsx` | `(rakip sayısı, ilk sıra, son sıra) → ağırlık` lookup tablosu |
| Flight Pairs | `data_raw/Flight Pairs.xlsx` | Operasyonel uçuş rotasyonu eşleşmeleri |

> Gerçek yarışma verileri kullanım koşulları nedeniyle depoya dâhil edilmez. `data_raw/` tamamen `.gitignore` kapsamındadır. Paylaşılabilir test verileri `tests/fixtures/` altındadır.

### Şema kontrolleri

| Veri | Kontrol | Hata davranışı |
|---|---|---|
| O&D | `Cr1 == Cr2` | Interline satır desteklenmediği için `SchemaError` |
| O&D | `Dep2 == Arr1` | Hub tutarsızlığında `SchemaError` |
| O&D | Gün değeri `1..7` | Aralık dışında `SchemaError` |
| Yolcu | `orig`/`dest` dolu | Fixture'da katı hata; full-data'da bilinen eksikler loglanarak düşürülür |
| Yolcu | Aynı `(orig,dest)` tekrarları | `ρ` katkıları toplanarak tek pazara konsolide edilir |
| Yolcu | `ρ > 0` | Aksi durumda `SchemaError` |
| Ranking | `(n,b,r)` benzersiz | Tekrarda `SchemaError` |
| Ranking | `b,r ∈ [1,n]` | Aralık ihlalinde `SchemaError` |

### Süre ve sabit türetimi

| Parametre | Tanım | v2 veri yolu | Geri dönüş yolu |
|---|---|---|---|
| `K_od` | İki uçuş bacağının blok süresi toplamı; bağlantı boşluğu hariç yolculuk sabiti | Pazar bazlı `median(ElapsedTime1 + ElapsedTime2)` | Geçerli bağlantılardan medyan; gerekirse iki parçalı least-squares kestirimi |
| `R_o` | İstasyon rotasyon sabiti | İstasyon bazlı elapsed medyanlarının toplamı | Bipartite least-squares |
| `T_comp` | Rakibin en iyi yolculuk süresi | Taşıyıcı bazında aynı pazar/gündeki minimum | Ek fallback yok |
| `b_od` | Başlangıç sıralaması | Baseline seyahat süresinin aynı rakip yenme kuralına uygulanması | Baseline yoksa çağıran akışta `0` |

`ElapsedTime1/2` bulunan v2 veride, 24 saati aşan Excel sürelerinin saat gibi sarılması şu mantıkla düzeltilir:

```text
gerçek_yolculuk_dakikası = elapsed1 + bağlantı_boşluğu + elapsed2
```

Bu düzeltme tek noktada `load_od_table()` içinde yapılır; rakip, ranking ve blok süresi bileşenleri düzeltilmiş veriyi otomatik olarak devralır.

## Aday bağlantı üretimi

Her gün için TK inbound ve outbound uçuş örneklerinin çapraz çarpımı alınır. Aynı dış istasyona geri dönen `o == d` çiftleri elenir. Bir aday, yalnızca yasal zaman pencereleri içinde en az bir geçerli bağlantı boşluğu oluşturabiliyorsa modele girer.

| Adım | Açıklama |
|---|---|
| Uçuş örneği kimliği | Inbound için `("IB", flno, gün)`, outbound için `("OB", flno, gün)`; rol namespace'i aynı uçuş numarasının iki rolde çakışmasını engeller |
| Zaman referansı | Tüm veri kümesindeki en erken takvim tarihinin gece yarısı; dakika cinsinden global epoch |
| Ayar penceresi | `all` modunda baseline etrafında `±adjustable_window_min`; `none` modunda tek nokta |
| Ulaşılabilir boşluk | `[dep_lo - arr_hi, dep_hi - arr_lo]` |
| Güvenli budama | Bu aralık `[L,U]` ile kesişmiyorsa aday kesinlikle geçersizdir ve çözücüye gönderilmez |
| Pazar filtresi | Yolcu verisinde `ρ_od` bulunmayan pazarlar çıkarılır |
| Sabit filtresi | `K_od` doğrudan veya kestirimle türetilemiyorsa ilgili pazar görünür uyarıyla düşürülür |

Bu budama, çözüm uzayındaki geçerli bir noktayı kaldırmaz; yalnızca hiçbir zaman geçerli olamayacak bağlantıları önceden eler.

## Matematiksel model özeti

Ayrıntılı formülasyon için [`docs/model.md`](docs/model.md) okunmalıdır. Aşağıdaki bölüm, uygulanan modelin yönetici ve geliştirici seviyesinde özetidir.

### Temel kümeler

| Sembol | Açıklama |
|---|---|
| `S` | IST dışındaki istasyonlar |
| `H` | Günler, `1..7` |
| `R` | Rol, uçuş numarası ve gün ile tanımlanan uçuş örnekleri |
| `Π` | Ulaşılabilir zaman penceresi bulunan inbound–outbound bağlantı adayları |
| `O-D` | Sıralı pazar çiftleri |

### Başlıca parametreler

| Sembol / ad | Varsayılan | İşlev |
|---|---:|---|
| `ρ_od` | Veriden | Pazar önem/gelir katsayısı |
| `L` | 60 dk | Minimum bağlantı boşluğu |
| `U` | 300 dk | Maksimum bağlantı boşluğu |
| `τ` | 45 dk | Minimum rotasyon yer süresi |
| `X_dev` | 15 dk | Günler arası düzenlilik toleransı |
| `α` | 0.20 | Yönsel bağlantı sayısı dengesizlik toleransı |
| `Γ` | 30 dk | Karşı yönlerin en iyi seyahat süreleri arasındaki azami fark |
| Kova boyutu | 10 dk | IST kapasite zaman dilimi |
| Kalkış kapasitesi | 10 | Kova başına kalkış üst sınırı |
| Varış kapasitesi | 15 | Kova başına varış üst sınırı |
| Ayar penceresi | ±180 dk | Uçuş örneğinin baseline çevresindeki karar aralığı |

### Karar değişkenleri

| Değişken | Domain | Anlam |
|---|---|---|
| `t_arr[r]`, `t_dep[r]` | Integer | Uçuş örneğinin IST varış/kalkış dakikası |
| `gap[π]` | Integer | Outbound kalkış eksi inbound varış |
| `x[π]` | Binary | Bağlantı gerçekten `[L,U]` içinde sunuluyor mu |
| `y[π]` | Binary | Geçersiz bağlantının alt mı üst sınırı mı ihlal ettiğini seçen yardımcı değişken |
| `s[o,d,h,j]` | `[0,1]` sürekli | Azalan bağlantı ödülü slotu |
| `beat[π,k]` | Binary | Aday bağlantı rakip `k`dan hızlı mı |
| `beaten[o,d,h,k]` | Binary | Pazarda rakip en az bir aday tarafından yenildi mi |
| `onehot[o,d,h,r]` | Binary | Güncellenmiş sıralama seçimi |
| `a_dir`, `w`, `Jbest` | Binary / Real | E2 için yön aktivasyonu, en iyi aday seçimi ve en iyi seyahat süresi |
| `z` ve `offset` ailesi | Binary / bounded | Uçuş örneğini kapasite kovasına bağlama |
| Elastik slack'ler | NonNegativeReals | E1/E2 ihlallerini teşhis ve warm-start amacıyla ölçme |

### Amaç fonksiyonu

Tam model iki ödül bileşenini birlikte en büyükler:

```text
toplam_amaç = bağlantı_ödülü + sıralama_ödülü
```

| Bileşen | Mantık |
|---|---|
| Bağlantı ödülü | Her pazar ve gün için sunulan bağlantılar, `ρ_od` ile ve azalan slot ağırlığı `2^{-(j-1)}` ile çarpılır |
| Sıralama ödülü | Yenilen rakip sayısından türetilen yeni sıra, `change_ranking_input.xlsx` lookup ağırlığı ve `ρ_od` ile değerlendirilir |

Araştırma modellerinde amaç geçici olarak `min toplam sapma` veya `min Σslack` olabilir. Bu amaçlar fizibilite bulmak/teşhis etmek içindir; yarışma ödül amacıyla karıştırılmamalıdır.

### A–G kısıt aileleri

| Aile | Ad | Ne garanti eder? | Uygulama |
|---|---|---|---|
| A | Rotasyon | Eşleşmiş outbound/inbound bacakları arasında blok süre ve minimum yer süresi kadar zaman bırakır; kısmi kapsamda sabit baseline bacağını kullanır | `constraints_operations.py` |
| B | Bağlantı uygunluğu | `x_π = 1` ancak ve ancak `gap_π ∈ [L,U]`; aday bazlı sıkı Big-M ve iki yönlü reifikasyon kullanır | `constraints_selection.py` |
| C | Azalan getiri slotları | Sunulan bağlantı sayısını monoton slotlara bağlar; yüksek ağırlıklı slotların önce dolmasını sağlar | `constraints_selection.py` |
| D | Rekabet ve sıralama | Adayın rakipten hızlı olup olmadığını, pazar bazlı OR toplamını ve rank one-hot seçimini kurar | `constraints_competition.py` |
| E1 | Yönsel sayı dengesi | `(o,d)` ve `(d,o)` yönlerindeki sunulan bağlantı sayılarının bağıl farkını sınırlar | `constraints_balance.py` |
| E2 | Seyahat süresi dengesi | Her iki yön aktifse en iyi seyahat süreleri arasındaki farkı `Γ` ile sınırlar | `constraints_balance.py` |
| F | Hub kapasitesi | Uçuşları yalnızca ulaşılabilir 10 dakikalık kovalara bağlar; kapsam dışı TK trafiğini baseline'da sabit sayıp rezidüel kapasiteyi kullanır | `constraints_capacity.py` |
| G | Düzenlilik | Uçuşun karşılaştırılabilir gün kümelerindeki gün-içi zaman sapmasını `X_dev` içinde tutar; gece yarısı çevresini güvenli ele alır | `constraints_operations.py` |

### Big-M disiplini

| İlke | Uygulama |
|---|---|
| Global gevşek sabit kullanılmaz | B, D ve E2 için aday/pazar aralıklarından özel Big-M türetilir |
| Üst güvenlik sınırı | Her Big-M değeri `<= 1440` olmalıdır; aşım model kurulurken `ValueError` üretir |
| Neden önemli? | Daha sıkı LP gevşemesi, daha güvenilir reifikasyon ve formülasyon hatalarını erken yakalama |

## Çözüm stratejileri

Kod tabanı yalnızca tek bir `solve()` çağrısı değil, full-data ölçeğinde gözlenen davranışlara karşı geliştirilmiş birkaç tamamlayıcı strateji içerir.

| Strateji | Model / akış | Amaç | Durum |
|---|---|---|---|
| Doğrudan fixture çözümü | Tam A–G model | Uçtan uca doğruluk ve regresyon | Aktif ve güvenilir |
| Doğrudan full-data (`main.py --full-data`) | Tam A–G model → süre/watchdog aşımında elastik yedek (2-adımlı ladder) | Uçtan uca üretim merdiveni; ihlalli tarife asla yazılmaz | `main.py --full-data` varsayılanı |
| Dış watchdog | Çözümü ayrı süreçte çalıştırır | HiGHS iç zaman limitinin kök kesme turlarını zamanında durduramadığı durumlarda duvar saatini korur | Full-data araçlarında aktif |
| Solve ladder | Full adjustable → eski K-subset denemeleri → teşhis | Kademeli küçültme | K-subset yapısal olarak etkisiz bulundu; varsayılan kapalı, karşılaştırma için korunuyor |
| Core feasibility | Yalnız A+G+F | Fiziksel alt modelin çözülebilirliğini sınamak ve seed üretmek | Aktif teşhis aracı |
| Elastic feasibility | A+G+F+B + slack'li E1/E2 | Katı fizibiliteye uzaklığı `Σslack` ile ölçmek | Aktif araştırma aracı |
| LNS fix | Tam elastik modeli kurup çoğu zamanı `.fix()` eder | Yerel iyileştirme | Referans/baseline olarak korunuyor; presolve maliyeti yüksek |
| LNS folded | Yalnız serbest uçuş örnekleri için gerçek değişken/satır kurar | Aynı komşuluğu daha küçük modelle çözmek | Eşdeğerlik testli, full-data araştırmasında tercih edilen LNS builder |
| Local branching | Referans etrafında `k` değişikliklik trust region | Yakın fizibilite arama | Denendi; full-data kök-düğüm davranışını çözmedi |

## Kurulum

### Ön koşullar

| Gereksinim | Not |
|---|---|
| Python 3 | `python3` komutuyla erişilebilir olmalı |
| Sanal ortam desteği | `python3 -m venv` |
| Yerel disk | Sanal ortam ve çözücü bağımlılıkları için yeterli alan |
| Full-data için Excel dosyaları | Yalnız gerçek veri koşularında gerekir |

### Adım adım kurulum

```bash
cd THY

python3 -m venv .venv
source .venv/bin/activate

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

Kurulum kontrolü:

```bash
.venv/bin/python3 -c "import pyomo, highspy, pandas; print('bağımlılıklar hazır')"
```

## Çalıştırma

### 1. Hızlı ve güvenli fixture çalıştırması

Gerçek veri gerektirmez ve yeni bir kurulumun ilk doğrulaması olarak önerilir.

```bash
.venv/bin/python3 main.py \
  --config src/config/standard.yaml \
  --fixture \
  --output runs/fixture_output.json
```

Beklenen süreç:

| Sıra | Konsol/çıktı davranışı |
|---:|---|
| 1 | Sentetik dört Excel dosyası okunur |
| 2 | Tam A–G modeli kurulur ve HiGHS ile çözülür |
| 3 | `runs/fixture_output.json` yazılır |
| 4 | Bağımsız validator çalışır |
| 5 | Konsolda `status`, `objective`, seçilen bağlantı sayısı ve `valid` görünür |

### 2. Full-data warm-start çalıştırması

Önce [beklenen dört dosyayı](#beklenen-full-data-dosyaları) `data_raw/` içine yerleştirin.

```bash
.venv/bin/python3 -u main.py \
  --config src/config/standard.yaml \
  --full-data \
  --output runs/full_data_output.json
```

`-u`, uzun koşularda logların tamponda beklememesi için önerilir. Varsayılan full-data akışı 2-adımlı ladder'dır: Adım 1 tam A–G modeli (~30dk, watchdog sınırlı), Adım 2 elastik yedek (~12dk, watchdog sınırlı). İhlalli tarife asla yazılmaz; çözüm bulunamazsa şema-uyumlu tanı çıktısı üretilir.

### Ana CLI seçenekleri

| Seçenek | Zorunlu? | Açıklama |
|---|---|---|
| `--config PATH` | Evet | YAML yapılandırma dosyası |
| `--fixture` | İkisinden tam biri | Sentetik veriyi kullanır |
| `--full-data` | İkisinden tam biri | `data_raw/` altındaki gerçek veriyi kullanır |
| `--output PATH` | Hayır | Varsayılan `runs/output.json` |

`--fixture` ve `--full-data` birlikte verilemez; ikisinden biri mutlaka seçilmelidir.

## Yapılandırma

Varsayılan senaryo: `src/config/standard.yaml`.

| Anahtar | Varsayılan | Etki | Not |
|---|---:|---|---|
| `solver` | `highs` | Çözücü seçimi | Runner `highs` ve `gurobi` adlarını bilir; Gurobi bu turda tam ölçekli test edilmedi |
| `time_limit_sec` | `1800` | Ana çözüm zaman limiti | Warm pipeline her aşamada ayrıca üst sınır uygular |
| `mip_gap` | `0.01` | Göreli MIP gap hedefi | Warm reward aşamasında kullanılır; bazı araştırma script'leri CLI ile override eder |
| `seed` | `42` | Çözücü ve araştırma deterministikliği | Zaman limitli paralel MIP'te aynı alternatif çözümü garanti etmez |
| `adjustable_set` | `all` | Uçuşların zaman kararı | Ana üreticide yalnız `all` / `none` |
| `adjustable_window_min` | `180` | Baseline çevresinde ± dakika | 360 deneyi adayları %44.7 artırdı; varsayılan 180 korunuyor |
| `bucket_size_min` | `10` | F kapasite kovası | Dakika |
| `capacity_departure` | `10` | Kova başına IST kalkış kapasitesi | Kapsam dışı trafik düşüldükten sonra rezidüel kapasite uygulanır |
| `capacity_arrival` | `15` | Kova başına IST varış kapasitesi | Aynı |
| `L` | `60` | Minimum bağlantı boşluğu | Dakika |
| `U` | `300` | Maksimum bağlantı boşluğu | Dakika |
| `tau` | `45` | Minimum yer süresi | Dakika |
| `X_dev` | `15` | Düzenlilik toleransı | Kodda `x_dev` olarak iletilir |
| `alpha` | `0.20` | E1 bağıl yön dengesizliği | Oran |
| `gamma` | `30` | E2 yönler arası süre farkı | Dakika |
| `enabled_constraints` | `[A..G]` | Senaryo niyeti | Mevcut `main.py`, listeyi dinamik anahtar olarak okumaz; `build_model_m4` A–G'nin tümünü kurar |
| `max_slots_per_market` | `20` | Eski/planlanan slot üst sınırı | Mevcut C modeli slot sayısını aday sayısından türetir; bu anahtar doğrudan kullanılmaz |

> Yeni bir konfigürasyon anahtarının YAML'da bulunması, otomatik olarak model davranışını değiştirdiği anlamına gelmez. Kullanım noktası kodda ve testte doğrulanmalıdır.

## Çıktı ve bağımsız doğrulama

### JSON şeması

| Alan | Tür | İçerik |
|---|---|---|
| `objective_value` | number / null | Bağımsız yeniden hesapla uzlaştırılan toplam amaç |
| `selected_connections[]` | array | `od`, `flno1`, `flno2`, `gun`, gerçek çözülmüş `gap_min` |
| `adjusted_flight_times[]` | array | `role`, `flno`, `gun`, global epoch dakika `time_min` |
| `ranking_results[]` | array | `o`, `d`, `gun`, yeni `rank`, `beaten_rivals[]` |
| `k_od_sources[]` | array | Pazar sabitinin `direct` veya `estimated` kaynağı; çağıran akış sağlarsa dolar |
| `solver_metrics` | object | `status` ve `solve_time_sec` |

Örnek iskelet:

```json
{
  "objective_value": 668.75,
  "selected_connections": [
    {"od": "AAA-BBB", "flno1": 101, "flno2": 202, "gun": 1, "gap_min": 90}
  ],
  "adjusted_flight_times": [
    {"role": "IB", "flno": 101, "gun": 1, "time_min": 480}
  ],
  "ranking_results": [
    {"o": "AAA", "d": "BBB", "gun": 1, "rank": 1, "beaten_rivals": ["XX"]}
  ],
  "k_od_sources": [],
  "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1}
}
```

Bu örnekteki pazar ve uçuş numaraları şema göstermek içindir. `668.75`, sentetik fixture için bağımsız oracle ile doğrulanmış referans amaç değeridir; full-data sonucu değildir.

### Doğrulama savunma hattı

| Katman | Kontrol |
|---|---|
| Veri loader | Girdi şemasını ve temel veri değişmezlerini doğrular |
| Model kısıtları | Çözücü içinde A–G fizibilitesini uygular |
| JSON writer | Çözülmüş değerleri kararlı ve izlenebilir biçimde yazar |
| Independent validator | `src.model` ve `src.candidates` kodunu kullanmadan çıktıdan A–G koşullarını yeniden hesaplar |
| Objective recompute | Bağlantı ve ranking ödüllerini ham veriden yeniden kurar |
| Final reconciliation | Resmî `objective_value` alanını bağımsız değerle uzlaştırır; fark varsa başarısız sayar |

Bu ayrım, modeldeki bir formülasyon hatasının validator tarafından aynı kod yolu üzerinden tekrar edilmesi riskini azaltır.

## Test stratejisi

### Test sınıfları

| Marker / dizin | Kapsam | Tipik süre |
|---|---|---|
| `unit` / `tests/unit/` | Saf mantık, veri dönüşümü, Big-M, aday üretimi, validator ve yardımcı algoritmalar | Çoğu 1 saniyenin altında |
| `solve` / `tests/solve/` | Küçük sentetik Pyomo/HiGHS modelleri, A–G kısıtları, warm-start ve CLI | Genellikle 60 saniyenin altında |
| `slow` / `tests/slow/` | Brute-force oracle ve daha pahalı kontroller | Ortama göre değişir |

### Test komutları

```bash
# Tüm testler
.venv/bin/pytest -q

# Sadece hızlı birim testleri
.venv/bin/pytest -q -m unit

# Çözücü kullanan küçük entegrasyon testleri
.venv/bin/pytest -q -m solve

# Yavaş testler
.venv/bin/pytest -q -m slow

# Tek dosya / tek test örneği
.venv/bin/pytest -q tests/unit/test_big_m.py
```

### Son doğrulama kaydı

| Tarih | Komut | Sonuç |
|---|---|---|
| 2026-07-15 | `.venv/bin/pytest -q` | **380 passed, 21.44s** |

Atlanan testler başarısızlık değildir; pytest tarafından mevcut koşul/işaretleyici nedeniyle çalıştırılmayan testlerdir. Yeni ortamda kesin sayı bağımlılık ve veri mevcudiyetine göre yeniden kontrol edilmelidir.

## Araştırma ve teşhis araçları

Alt çizgiyle başlayan `scripts/_*_worker.py` dosyaları kullanıcı komutu değil, watchdog tarafından ayrı süreçte çağrılan iç worker'lardır.

| Komut | Amaç | Ne zaman kullanılır? |
|---|---|---|
| `scripts/run_full_data.py` | Bütçeli, loglu full-data solve ladder | Doğrudan model performansı ve karşılaştırmalı koşular |
| `scripts/run_core_feasibility.py` | A+G+F alt modelini çözer | Fiziksel çekirdek fizibilite ve warm seed |
| `scripts/run_feasibility_only.py` | Ödül hesap makinesini çıkararak katı fizibiliteyi dener | C/D'nin performans etkisini ayırmak |
| `scripts/run_elastic_feasibility.py` | E1/E2'yi slack ile gevşetir | Fizibilite uzaklığı ve ihlal haritası |
| `scripts/warm_start_elastic.py` | Core çözümden elastik warm-start üretir | Full-data incumbent/seed arama |
| `scripts/run_lns.py` | Fix-and-optimize LNS uygular | Elastik slack'i yerel komşuluklarla azaltmak |
| `scripts/run_local_branching.py` | Referans etrafında local branching uygular | Yakın çözüm arama karşılaştırması |
| `scripts/run_min_deviation.py` | Baseline'dan toplam sapmayı küçültür | Amaç fonksiyonunun kök düğüm davranışını ayırmak |
| `scripts/lp_anatomy.py` | LP gevşemesi ve değişken fractionality analizi | Formülasyon darboğazını teşhis etmek |
| `scripts/size_budget.py` | Aday, satır ve kapasite kovası boyut tahmini | Büyük koşudan önce kaynak planlamak |
| `scripts/baseline_feasibility_witness.py` | Baseline tarifeyi A–G açısından kontrol eder | Hangi kısıt ailelerinin başlangıçta ihlalli olduğunu görmek |
| `scripts/feasibility_certificates.py` | Çözücüsüz gerekli koşul sertifikaları | E1/E2'nin kanıtlanabilir biçimde imkânsız olup olmadığını sınamak |
| `scripts/analyze_violation_footprint.py` | İhlallerin dokunduğu uçuş örneklerini ölçer | Yerel komşuluk boyutunu belirlemek |
| `scripts/validate_block_times_v2.py` | v2 elapsed tabanlı blok sürelerini çapraz doğrular | Veri sürümü ve `K_od/R_o` geçiş kontrolü |

Örnek araştırma komutları:

```bash
# Fiziksel çekirdek model
.venv/bin/python3 -u scripts/run_core_feasibility.py

# Warm-start + elastik model
.venv/bin/python3 -u scripts/warm_start_elastic.py \
  --time-limit-sec 900 \
  --max-improving-sols 1

# Folded, bileşen tabanlı LNS
.venv/bin/python3 -u scripts/run_lns.py \
  --builder folded \
  --selection component \
  --max-wall-sec 10800
```

Full-data araştırma komutları dakikalar veya saatler sürebilir ve yüksek bellek kullanabilir. Önce fixture testleri çalıştırılmalı, ardından `docs/STATUS.md` ve script yardım metni incelenmelidir.

## Mevcut sonuçlar ve performans

### Kanıt seviyesi tablosu

| Ortam / sonuç | Durum | Ne kanıtlıyor? | Ne kanıtlamıyor? |
|---|---|---|---|
| Sentetik fixture, amaç `668.75` | Bağımsız brute-force ve validator ile doğrulanmış | Tam A–G uygulamasının küçük örnekte doğru ve uçtan uca çalıştığını | Full-data fizibilitesini veya optimumunu |
| Full-data A+G+F çekirdeği | Geçmiş koşularda optimum/usable sonuç bulundu | Fiziksel çekirdeğin tek başına çözülebilir olduğunu | E1/E2 ile birlikte katı fizibiliteyi |
| Full-data elastik warm-start | Incumbent bulundu | Warm-start borusunun ve slack modelinin çalıştığını | Katı A–G geçerliliğini |
| Full-data LNS | `Σslack` azaltıldı fakat sıfırlanmadı | Yerel aramanın ihlalleri iyileştirebildiğini | Teslim edilebilir çözümü |
| Full-data reward değeri | Bağımsız validator'dan geçen değer yok | — | Herhangi bir raporlanan kısmi reward değerinin resmî sonuç sayılmasını |

### Son full-data araştırma özeti

| Ölçüm | v2 veri bulgusu |
|---|---:|
| Varsayılan `±180` pencerede aday sayısı | 18.147 |
| `±360` pencerede aday sayısı | 26.258; **%44,7 artış** |
| Baseline toplam kısıt ihlali | 2.102 |
| Statik E1/E2 gerekli koşul sertifikaları | `0 / 0 / 0` ihlal; basit bir imkânsızlık kanıtı bulunmadı |
| A+G+F referans minimum toplam sapması | 4.551 dakika |
| Elastik başlangıç `Σslack` | 69.559,20 |
| Folded component LNS sonrası `Σslack` | 62.821,90; **%9,68 azalma** |
| Kısmi noktanın katı validator ihlalleri | 1.763 (`E1=645`, `E2=1114`, `G=4`) |
| Full-data doğrulanmış amaç | **Yok** |

Bu değerler deney kaydıdır; yeni commit, veri veya çözücü sürümünde değişebilir. Kaynak ve bağlam: [`docs/STATUS.md`](docs/STATUS.md).

### Bilinen ölçek davranışları

| Gözlem | Etki | Alınan önlem |
|---|---|---|
| F'nin eski per-bucket Big-M formu satırların büyük kısmını oluşturuyordu | Model boyutu ve LP süresi artıyordu | Birebir eşdeğer kova eşitliğiyle F satırlarında büyük azaltım |
| HiGHS iç zaman limiti kök kesme turlarını her zaman zamanında durdurmadı | Koşu bütçesi aşılabiliyordu | SIGTERM/SIGKILL kullanan dış subprocess watchdog |
| Market tabanlı K-subset, paylaşılan fiziksel bacaklar nedeniyle modeli yeterince küçültmedi | Ladder alt adımları etkisiz kaldı | Varsayılan kapatıldı; uçuş örneği düzeyinde fold/LNS geliştirildi |
| `.fix()` tabanlı LNS'te presolve maliyeti yüksekti | İterasyon süresi uzadı | Yalnız serbest değişkenleri kuran folded builder |
| Pencereyi 180'den 360'a çıkarmak | Aday sayısında %44,7 artış; çekirdek adım bütçeyi aştı | Varsayılan 180 korundu; Big-M üst sınırı runtime kontrolünde |

## Varsayımlar, riskler ve sınırlamalar

Tüm ayrıntılı varsayımlar [`ASSUMPTIONS.md`](ASSUMPTIONS.md), kronolojik kararlar [`docs/decisions.md`](docs/decisions.md) içindedir.

| Konu | Uygulanan karar | Risk / açık nokta |
|---|---|---|
| Eksik yolcu destinasyonları | Full-data'da loglanarak düşürülür | Organizatör yorumu gelirse kapsam/amaç değişebilir |
| Ayarlanabilir pencere | ±180 dakika | Brief'in sınırsız Standard yorumu farklı olabilir; daha geniş pencere kombinatoryal olarak pahalıdır |
| Rakip tanımı | `Cr1` taşıyıcısı tek rakiptir; aynı taşıyıcının itinerary'leri minimumla birleşir | Resmî rakip tanımı uçuş/itinerary bazlıysa ranking değişir |
| Ranking monotonluğu | Gerçek tabloda doğrulanır; tek yönlü beat zorlaması buna dayanır | Monoton olmayan yeni tabloda farklı reifikasyon gerekir |
| Tek yönlü pazarlar | E1, sıfır karşı yönle sert denge baskısı yaratabilir | Organizatörden muafiyet/hesaplama tanımı beklenebilir |
| Kapsam dışı TK uçuşları | Kendi baseline kovasında sabit kapasite tüketir | Resmî kapasite tahsisi verilirse güncellenmelidir |
| `K_od` bulunamaması | Doğrudan → LS kestirim → pazar düşürme | Düşürülen pazarlar kapsamı azaltır; loglar incelenmelidir |
| Uçuş rotasyonu | Baseline kronolojisiyle eşleştirme ve belgelenmiş istisnalar | Flight Pairs semantiğinin resmî yorumu sonucu etkileyebilir |
| Jbest domaini | Gerçek sayıdır | Eski integer formülasyon full-data'yı yanlış biçimde infeasible yapabiliyordu; düzeltilmiştir |
| Full-data çözüm durumu | Henüz katı doğrulanmış incumbent yok | Proje, gerçek veri için “optimum bulundu” iddiasında bulunmaz |
| Çözücü | HiGHS varsayılan | Alternatif ticari çözücü karşılaştırması lisans ve ölçek nedeniyle tamamlanmadı |
| Bağımlılık kilidi | `requirements.txt` minimum sürümler içerir | Tam byte-seviyesi ortam tekrarı için lock/container eksiktir |
| Lisans | Depoda açık bir yazılım lisansı dosyası yok | Haricî kullanım/dağıtım öncesi proje sahibi lisans koşullarını belirlemelidir |

### Operasyonel güvenlik notları

| Durum | Öneri |
|---|---|
| `status=time_limit`, `objective_value=null` | Incumbent yoktur; sonucu çözüm gibi kullanmayın |
| Elastik sonuçta amaç değeri var | `Σslack≈0` ve katı validator geçmeden teslim etmeyin |
| Validator ihlal yazıyor | JSON'u geçersiz kabul edin; yalnız teşhis amacıyla saklayın |
| Yeni veri paketi geldi | SHA256 provenance kaydı, loader testleri ve v2 süre doğrulamasını yeniden çalıştırın |
| Geniş pencere deneniyor | Önce `size_budget.py`; ardından Big-M sınırı ve bellek bütçesini kontrol edin |

## Tekrar üretilebilirlik

| Mekanizma | Sağladığı güvence |
|---|---|
| Sabit `seed=42` | Çözücü ve LNS rastgeleliğini mümkün olduğunca sabitler |
| Doğal anahtarla JSON sıralama | Aynı sonuç nesnesinden kararlı dosya üretir |
| `file_provenance()` | Aktif girdi yolunu ve SHA256 özetini deney loguna ekler |
| Sentetik fixture | Gerçek veriyi paylaşmadan şema ve model davranışını tekrarlar |
| Brute-force oracle | Fixture amaç değerini `src.model` kodundan bağımsız doğrular |
| Independent validator | Model uygulamasından ayrı ikinci doğruluk hattı sağlar |
| Tarihli full-data logları | Model boyutu, status, zaman ve HiGHS davranışını koşu bazında saklar |

Sınırlama: zaman limitli ve paralel MIP araması, aynı seed ile bile alternatif eşdeğer çözümler arasından farklı birini seçebilir. Determinizm iddiası, özellikle full-data koşularında “her seferinde byte-byte aynı optimum çözüm” anlamına gelmez.

## Dokümantasyon haritası

| Belge | Ne zaman okunmalı? |
|---|---|
| [`README.md`](README.md) | Projeye giriş, kurulum, mimari ve genel durum |
| [`CLAUDE.md`](CLAUDE.md) | Ayrıntılı kilometre taşı geçmişi, kilit teknik kararlar ve çalışma bağlamı |
| [`ASSUMPTIONS.md`](ASSUMPTIONS.md) | Veri/model yorumları ve organizatöre bağlı açık varsayımlar |
| [`docs/model.md`](docs/model.md) | Kümeler, değişkenler, amaç ve A–G matematiksel formülasyonu |
| [`docs/STATUS.md`](docs/STATUS.md) | Full-data koşularının güncel tek-bakışta durumu |
| [`docs/decisions.md`](docs/decisions.md) | Kronolojik karar ve deney kanıt zinciri |
| [`docs/output_format.md`](docs/output_format.md) | JSON şeması, brief eşlemesi ve determinizm |
| [`docs/block_time_cross_validation.md`](docs/block_time_cross_validation.md) | v2 elapsed süreleri ve eski LS kestirimlerinin karşılaştırması |
| [`docs/lp_anatomy.md`](docs/lp_anatomy.md) | LP gevşemesi, model boyutu ve fractionality analizi |
| [`docs/feasibility_certificates.md`](docs/feasibility_certificates.md) | Çözücüsüz E1/E2 gerekli koşul kontrolleri |
| [`docs/baseline_autopsy.md`](docs/baseline_autopsy.md) | Baseline tarifenin ihlal analizi |
| [`docs/organizer_questions.md`](docs/organizer_questions.md) | Organizatöre yöneltilmesi gereken veri/model soruları |
| [`docs/report_outline.md`](docs/report_outline.md) | Nihai teknik rapor taslağı ve kanıt tablosu |

## Geliştirme rehberi

### Önerilen değişiklik akışı

| Adım | Eylem |
|---:|---|
| 1 | Değişikliğin hangi veri, model veya doğrulama varsayımını etkilediğini belirleyin |
| 2 | Önce küçük unit/solve testiyle beklenen davranışı tanımlayın |
| 3 | Model değişikliği varsa `docs/model.md`; varsayım değişikliği varsa `ASSUMPTIONS.md` ve `docs/decisions.md`yi aynı değişiklikte güncelleyin |
| 4 | İlgili dar testleri, ardından tüm test paketini çalıştırın |
| 5 | Fixture CLI'yi uçtan uca çalıştırıp `valid=True` sonucunu kontrol edin |
| 6 | Full-data koşusu gerekiyorsa önce boyut bütçesi çıkarın ve watchdog kullanın |
| 7 | Sonuçları `docs/STATUS.md`ye; veri sürümünü provenance alanına kaydedin |

### Kod değişikliği kontrol listesi

| Değişiklik türü | Zorunlu kontroller |
|---|---|
| Loader / veri şeması | Fixture üreticisi, loader testleri, eski ve yeni kolon yolu |
| Aday üretimi | Ulaşılabilir aralık kanıtı, gece yarısı, rol namespace'i ve pencere sınır testleri |
| Big-M | Aday aralıklarından türetim, `<=1440` assert'i ve sınır testleri |
| A–G kısıtı | Pozitif/negatif/adversarial küçük solve testleri ve bağımsız validator eşlemesi |
| Amaç fonksiyonu | Solver sonucu ile bağımsız recompute karşılaştırması |
| Warm-start / LNS | Başlangıç noktasının modele gerçekten aktarılması, log kanıtı ve fold/fix eşdeğerliği |
| Çıktı şeması | Writer determinismi, validator tüketimi ve `docs/output_format.md` |

### Hızlı sorun giderme

| Belirti | Olası neden | İlk kontrol |
|---|---|---|
| `python: command not found` | Ortam yalnız `python3` sağlıyor | `.venv/bin/python3` veya `python3` kullanın |
| `FileNotFoundError` full-data'da | Dosya adı/yolu `paths.py` ile uyuşmuyor | `data_raw/` içindeki dört kesin adı kontrol edin |
| `SchemaError` | Yeni veri şeması veya bozuk alan | Hata mesajındaki kolon/değişmezi ve loader testini inceleyin |
| Big-M `ValueError` | Pencere çok geniş veya sınırlar tutarsız | `adjustable_window_min`, `L`, `U` ve aday bounds |
| `time_limit` ve boş amaç | Çözücü incumbent bulamadı | HiGHS logu, watchdog statusu ve core/warm-start hattı |
| Warm-start var ama validator geçmiyor | Elastik E1/E2 slack'i sıfır değil | `Σslack` ve ihlal ailesi dökümü |
| LNS hiç ilerlemiyor | Gamma-imkânsız çift, çok küçük komşuluk veya fix/presolve maliyeti | `--builder folded --selection component`, sertifika ve footprint raporları |

## Sonuç

Bu depo, yalnızca bir optimizasyon betiği değil; veri kalitesi kontrolleri, açık matematiksel model, farklı fizibilite arama stratejileri, bağımsız doğrulama ve deney kanıt zinciri içeren bir karar destek araştırma altyapısıdır. Küçük sentetik problemde tam model doğrulanmıştır. Gerçek veri tarafında ise proje mevcut kanıtı olduğundan güçlü göstermemekte; katı A–G fizibilitesi ve doğrulanmış amaç değeri bulunana kadar elastik/LNS sonuçlarını açıkça **kısmi ve teslim edilemez** olarak sınıflandırmaktadır.

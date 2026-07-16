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
| Gerçek veri durumu | Benchmark-safe pipeline ile seed-türevli tam-iddia çıktı üretildi: `objective=1,488,074.81`, `claim_complete=True`, `A/B/D/F/G=0`, `E1=106`, `E2=221`, `strict_feasible=False` |
| Kalite durumu | 16 Temmuz 2026 yerel doğrulaması: **433 test geçti** |
| Ana giriş noktası | `main.py` |
| Varsayılan yapılandırma | `src/config/standard.yaml` |
| Sonuç formatı | Deterministik sıralanmış JSON |

> **Durum uyarısı:** `main.py --full-data` her koşulda şema-uyumlu, tam-iddia (`claim_complete=True`), bağımsız-recompute'lu bir JSON yazar (`status=heuristic_incumbent_with_strict_violations`). Mevcut çıktı `outputs/full_data_output.json`: `objective=1,488,074.8064039326`, hard-family kısıtları temiz (`A/B/D/F/G=0`), E1/E2 strict ihlalleri diagnostics bloğunda dürüstçe raporlanıyor (`E1=106`, `E2=221`), `strict_feasible=False`. Fixture (`--fixture`) için: `status=optimal`, `objective=668.75`, `valid=True`, `selected=18`.

## İçindekiler

1. [Problem tanımı](#problem-tanımı)
2. [Kapsam ve başarı ölçütleri](#kapsam-ve-başarı-ölçütleri)
3. [Sistem mimarisi](#sistem-mimarisi)
4. [Üretim davranışı](#üretim-davranışı---full-data-benchmark-safe-dürüst-incumbent)
5. [Proje dizinleri](#proje-dizinleri)
6. [Teknoloji yığını](#teknoloji-yığını)
7. [Veri kaynakları ve veri işleme](#veri-kaynakları-ve-veri-işleme)
8. [Aday bağlantı üretimi](#aday-bağlantı-üretimi)
9. [Matematiksel model özeti](#matematiksel-model-özeti)
10. [Çözüm stratejileri](#çözüm-stratejileri)
11. [Kurulum](#kurulum)
12. [Çalıştırma](#çalıştırma)
13. [Yapılandırma](#yapılandırma)
14. [Çıktı ve bağımsız doğrulama](#çıktı-ve-bağımsız-doğrulama)
15. [Test stratejisi](#test-stratejisi)
16. [Araştırma ve teşhis araçları](#araştırma-ve-teşhis-araçları)
17. [Mevcut sonuçlar ve performans](#mevcut-sonuçlar-ve-performans)
18. [Varsayımlar, riskler ve sınırlamalar](#varsayımlar-riskler-ve-sınırlamalar)
19. [Tekrar üretilebilirlik](#tekrar-üretilebilirlik)
20. [Dokümantasyon haritası](#dokümantasyon-haritası)
21. [Geliştirme rehberi](#geliştirme-rehberi)

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
    E --> F["HiGHS çözümü / warm-start"]
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

`main.py --full-data` varsayılan yolu her koşulda **şema-uyumlu, tam-iddia (claim-complete), recompute-objective'li bir incumbent** yazar ve exit 0 döner:

1. **FLOOR** — ham baseline saatleri hemen yazılır. Bu yalnızca null'a düşmeme emniyetidir; final seçimde hard-family ihlal profili kötüyse objective'i yüksek olsa bile tercih edilmez.
2. **SEED** — `data_seed/full_data_best_deltas.json` uygulanır, saatlerden tüm uygun bağlantılar yeniden türetilir ve amaç değeri bağımsız `recompute_objective` ile yazılır.
3. **IMPROVE** — kalan bütçede strict tam-MIP denenir; yalnız claim-complete ve strict-clean bir incumbent seçim sırasını iyileştirirse terfi eder.

Final seçim sırası: `claim_complete=True`, sonra hard-family ihlalleri (`A+B+D+F+G`) minimum, sonra `E1+E2` minimum, en son objective maksimum. Bu yüzden ölçülen final `outputs/full_data_output.json`, floor'un `objective=2,983,669.09` değerinden düşük olsa da hard-family temiz olduğu için seed-derived incumbent'tır:

- `objective=1,488,074.8064039326`
- `claim_complete=True`
- `A/B/D/F/G=0`
- `E1=106`, `E2=221`
- `strict_feasible=False`

**exit 0 yalnız DOSYA-ÜRETİM garantisidir, fizibilite garantisi değildir.** Strict-clean olmayan benchmark çıktısı fizibilite iddiası olarak adlandırılmaz; `solver_metrics.status = heuristic_incumbent_with_strict_violations` ve `diagnostics` bloğu kalan strict E1/E2 teşhisini açıkça taşır. Resmî strict feasibility kapısı `--strict-gate` bayrağında korunur: strict-clean olmayan tarifeyi yazmaz; bulunamazsa null-teşhis + exit 1.

## Proje dizinleri

| Yol | Sorumluluk | Önemli içerik |
|---|---|---|
| `main.py` | Tek komutlu uygulama girişi | Oku → aday üret → model kur/çöz → yaz → doğrula |
| `src/config/` | Yapılandırma ve merkezi veri yolları | `standard.yaml`, `paths.py` |
| `src/data/` | Excel okuma, şema doğrulama, süre ve pazar parametreleri | Loader'lar, blok süresi sağlayıcısı, veri provenance |
| `src/candidates/` | Bağlantı adayı üretimi ve deneysel alt küme mantığı | `generate.py`, `subset.py` |
| `src/model/` | Matematiksel model | Amaç, A–G kısıtları, Big-M, elastik model ve warm-start yardımcıları |
| `src/solve/` | Çözücü soyutlaması ve orkestrasyon | Runner, warm pipeline, ladder ve subprocess watchdog |
| `src/output/` | Sonuç serileştirme | Deterministik JSON yazıcı |
| `src/validate/` | Modelden bağımsız doğrulama | Kısıt ve amaç yeniden hesabı, claim-completeness kontrolü |
| `src/benchmark/` | Benchmark-safe pipeline | `times.py`, `claim.py`, `pipeline.py`, `writer.py` — seed-delta üzerinden tam-iddia incumbent üretimi |
| `src/report/` | Pano ve rapor üretimi | `dashboard.py` — self-contained HTML dashboard |
| `data_seed/` | Seed delta dosyaları | `full_data_best_deltas.json` — baseline saatlere uygulanacak delta vektörü |
| `scripts/` | Full-data deney, fizibilite ve teşhis komutları | Warm-start, E1/E2 onarım, delta üretici ve worker süreçleri |
| `tests/unit/` | Hızlı, çözücüsüz mantık testleri | Loader, aday, Big-M, validator ve yardımcı algoritmalar |
| `tests/solve/` | Küçük HiGHS entegrasyon testleri | A–G kısıtları, model kurucular, warm-start ve CLI |
| `tests/slow/` | Yavaş veya geniş kapsamlı testler | Brute-force oracle ve full-data odaklı kontroller |
| `tests/fixtures/` | Paylaşılabilir sentetik Excel verileri | Dört sentetik girdi ve fixture üreticisi |
| `outputs/` | Teslim çıktı dosyaları | `fixture_output.json`, `full_data_output.json`, `dashboard.html`, `GAMMA_SENSITIVITY_STATIC_SCAN.json` |
| `data_raw/` | Yerel yarışma verileri | Git tarafından izlenmez; yeniden dağıtılmaz |
| `runs/` | Üretilen çözüm ve loglar | JSON/HiGHS logları; çoğu Git tarafından izlenmez |

Komutları yeniden koşmadan sonuçları incelemek için: `outputs/fixture_output.json` (sentetik demo referansı) ve `outputs/full_data_output.json` (**resmî full-data teslim çıktısı**: seed-derived, tam-iddia, bağımsız-recompute `objective_value=1,488,074.8064039326`, `claim_complete=True`, `A/B/D/F/G=0`, `E1=106`, `E2=221`, `strict_feasible=False`). `outputs/GAMMA_SENSITIVITY_STATIC_SCAN.json` raporun bir EKİDİR, resmî sonucu değiştirmez.

**Teslim paketi:** `runs/bias_cozum.zip` — paket çalışır, fixture valid, full-data output claim-complete/hard-family-clean ve diagnostics dürüsttür. Strict feasibility iddiası yoktur; risk Kriter 2'dedir.

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

Ayrıntılı formülasyon aşağıda özetlenmektedir.

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
| E1 | Yönsel sayı dengesi | `(o,d)` ve `(d,o)` yönlerindeki sunulan bağlantı sayılarının bağıl farkını sınırlar; yalnızca her iki yön de aktifken bağlayıcı | `constraints_balance.py` |
| E2 | Seyahat süresi dengesi | Her iki yön aktifse en iyi seyahat süreleri arasındaki farkı `Γ` ile sınırlar; statik imkânsız çiftler muaf | `constraints_balance.py` |
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
| Benchmark-safe pipeline (`main.py --full-data`) | FLOOR → SEED → IMPROVE merdiveni | Her koşulda claim-complete JSON üretimi | Aktif varsayılan |
| Dış watchdog | Çözümü ayrı süreçte çalıştırır | HiGHS iç zaman limitinin kök kesme turlarını zamanında durduramadığı durumlarda duvar saatini korur | Full-data araçlarında aktif |
| Core feasibility | Yalnız A+G+F | Fiziksel alt modelin çözülebilirliğini sınamak ve seed üretmek | Aktif teşhis aracı |
| Elastic feasibility | A+G+F+B + slack'li E1/E2 | Katı fizibiliteye uzaklığı `Σslack` ile ölçmek | Aktif araştırma aracı |
| Solve ladder | Full adjustable → elastik yedek → teşhis | Kademeli küçültme | Full-data varsayılan akışında yerleşik |
| Local branching | Referans etrafında `k` değişikliklik trust region | Yakın fizibilite arama | Denendi; full-data kök-düğüm davranışını çözmedi |

### LNS (Large Neighborhood Search) algoritması

Fix-and-Optimize döngüsü: her iterasyonda E1/E2 ihlali en yüksek pazar çiftlerini seçer, o çiftlere bağlı uçuş sürelerini serbest bırakır, geri kalanı sabit tutar ve küçük bir alt-MIP çözer.

```
┌─────────────────────────────────────────────────────────┐
│                    LNS DÖNGÜSÜ                          │
│                                                         │
│  Başlangıç noktası                                      │
│  (elastik warm-start çözümü, Σslack = başlangıç)       │
│            │                                            │
│            ▼                                            │
│  ┌─────────────────────┐                               │
│  │  En kötü m çift seç │  ← E1+E2 slack'i en yüksek   │
│  │  (seed ile rastgele │    market pair'lar             │
│  │   çeşitlendirme)    │                               │
│  └─────────┬───────────┘                               │
│            │                                            │
│            ▼                                            │
│  ┌─────────────────────┐                               │
│  │  Seçili uçuşları    │  ← Diğer tüm t_arr/t_dep     │
│  │  serbest bırak,     │    .fix() ile sabitlenir      │
│  │  gerisini kilitle   │                               │
│  └─────────┬───────────┘                               │
│            │                                            │
│            ▼                                            │
│  ┌─────────────────────┐                               │
│  │  HiGHS ile alt-MIP  │  ← iter_time_limit_sec        │
│  │  çöz (elastik amaç) │    watchdog korumalı          │
│  └─────────┬───────────┘                               │
│            │                                            │
│            ▼                                            │
│  ┌─────────────────────┐   Σslack azaldı?              │
│  │  Kabul / Ret         ├──────────────────┐           │
│  │  (greedy accept)    │  Evet             │ Hayır     │
│  └─────────┬───────────┘   ↓               ↓          │
│            │            güncelle        mevcut          │
│            │            referansı       referansta       │
│            │                            kal             │
│            ▼                                            │
│  Plato (plateau_iters) veya Σslack=0 → DUR             │
└─────────────────────────────────────────────────────────┘
```

**Σslack yolculuğu** (tam-data, Γ=360 dk, E1/E2 hedefi sıfır):

```
  Σslack
  851 ──▶ 128 ──▶ 90 ──▶ 57 ──▶ ... ──▶ 0 (hedef)
  │        │        │      │
  elastik  iter     iter   iter
  warm-    13       ~20    devam
  start    E2 temiz
```

| Terim | Açıklama |
|---|---|
| `Σslack` | Tüm pazar çiftlerindeki E1 + E2 ihlallerinin toplamı (dakika) |
| `m` | Her iterasyonda serbest bırakılan uçuş örneği sayısı |
| Plato | `plateau_iters` iterasyon boyunca iyileşme olmadığında durdurma |
| Σslack = 0 | E1 ve E2 tamamen temiz → strict `valid=True` adayı |

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

### Docker ile kurulum

Yerel Python ortamı gerektirmeyen alternatif:

```bash
docker compose run --rm test    # 433 test (<15 sn)
docker compose run --rm demo    # fixture: objective=668.75, valid=True
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

Beklenen çıktı: `status=optimal`, `objective=668.75`, `valid=True`, `selected=18`.

Komut tamamlandığında `outputs/` klasöründe iki dosya otomatik üretilir:
- `outputs/fixture_output.json` — makine-okunabilir JSON sonuç
- `outputs/dashboard.html` — tarayıcıda açılabilen görsel rapor

### 2. Full-data benchmark-safe çalıştırması

Önce [beklenen dört dosyayı](#beklenen-full-data-dosyaları) `data_raw/` içine yerleştirin.

```bash
.venv/bin/python3 -u main.py \
  --config src/config/standard.yaml \
  --full-data \
  --output runs/full_data_output.json
```

`-u`, uzun koşularda logların tamponda beklememesi için önerilir. Pipeline FLOOR → SEED → IMPROVE adımlarını sırayla çalıştırır; ihlalli tarife asla yazılmaz.

Komut tamamlandığında `outputs/` klasöründe iki dosya otomatik üretilir:
- `outputs/full_data_output.json` — makine-okunabilir JSON sonuç
- `outputs/dashboard.html` — tarayıcıda açılabilen görsel rapor

### Ana CLI seçenekleri

| Seçenek | Zorunlu? | Açıklama |
|---|---|---|
| `--config PATH` | Evet | YAML yapılandırma dosyası |
| `--fixture` | İkisinden tam biri | Sentetik veriyi kullanır |
| `--full-data` | İkisinden tam biri | `data_raw/` altındaki gerçek veriyi kullanır |
| `--output PATH` | Hayır | Varsayılan `runs/output.json` |
| `--strict-gate` | Hayır | Strict-clean olmayan tarifeyi yazmaz; bulunamazsa exit 1 |

`--fixture` ve `--full-data` birlikte verilemez; ikisinden biri mutlaka seçilmelidir.

## Yapılandırma

Varsayılan senaryo: `src/config/standard.yaml`.

| Anahtar | Varsayılan | Etki | Not |
|---|---:|---|---|
| `solver` | `highs` | Çözücü seçimi | Runner `highs` ve `gurobi` adlarını bilir; Gurobi bu turda tam ölçekli test edilmedi |
| `time_limit_sec` | `1800` | Ana çözüm zaman limiti | Warm pipeline her aşamada ayrıca üst sınır uygular |
| `mip_gap` | `0.01` | Göreli MIP gap hedefi | Warm reward aşamasında kullanılır |
| `seed` | `42` | Çözücü deterministikliği | Zaman limitli paralel MIP'te aynı alternatif çözümü garanti etmez |
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
| `e1_activation` | `conditional` | E1 etkinleşme modu | `conditional`: yalnız her iki yön aktifken bağlayıcı; `unconditional`: her koşulda |

> Yeni bir konfigürasyon anahtarının YAML'da bulunması, otomatik olarak model davranışını değiştirdiği anlamına gelmez. Kullanım noktası kodda ve testte doğrulanmalıdır.

## Çıktı ve bağımsız doğrulama

### JSON şeması

| Alan | Tür | İçerik |
|---|---|---|
| `objective_value` | number / null | Bağımsız yeniden hesapla uzlaştırılan toplam amaç |
| `selected_connections[]` | array | `od`, `flno1`, `flno2`, `gun`, gerçek çözülmüş `gap_min` |
| `adjusted_flight_times[]` | array | `role`, `flno`, `gun`, global epoch dakika `time_min` |
| `ranking_results[]` | array | `o`, `d`, `gun`, yeni `rank`, `beaten_rivals[]` |
| `k_od_sources[]` | array | Pazar sabitinin `direct` veya `estimated` kaynağı |
| `solver_metrics` | object | `status` ve `solve_time_sec` |
| `diagnostics` | object | E1/E2 ihlal sayıları ve strict_feasible bayrağı |

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
  "solver_metrics": {"status": "optimal", "solve_time_sec": 0.1},
  "diagnostics": {}
}
```

`668.75`, sentetik fixture için bağımsız oracle ile doğrulanmış referans amaç değeridir.

### Doğrulama savunma hattı

| Katman | Kontrol |
|---|---|
| Veri loader | Girdi şemasını ve temel veri değişmezlerini doğrular |
| Model kısıtları | Çözücü içinde A–G fizibilitesini uygular |
| JSON writer | Çözülmüş değerleri kararlı ve izlenebilir biçimde yazar |
| Independent validator | `src.model` ve `src.candidates` kodunu kullanmadan çıktıdan A–G koşullarını yeniden hesaplar |
| Objective recompute | Bağlantı ve ranking ödüllerini ham veriden yeniden kurar |
| Claim-completeness kontrolü | Her bağlantı adayı için iddia ile gözlem eşleşmesini doğrular |
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
```

### Son doğrulama kaydı

| Tarih | Komut | Sonuç |
|---|---|---|
| 2026-07-16 | `.venv/bin/pytest -q` | **433 passed** |

Atlanan testler başarısızlık değildir; pytest tarafından mevcut koşul/işaretleyici nedeniyle çalıştırılmayan testlerdir (`data_raw/` yokken bazı slow testler skip eder).

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
| `scripts/run_conflict_deactivation_feasibility.py` | E2-çakışan pazar-yönlerini seçici devre dışı bırakır | Hedefli E2 conflict analizi |
| `scripts/scan_gamma_sensitivity.py` | Farklı Γ değerlerinde statik ön-tarama | E2 sınırının global etkisi |
| `scripts/generate_dashboard.py` | Self-contained HTML pano üretir | Sonuçların görsel özeti |
| `scripts/analyze_violation_footprint.py` | İhlallerin dokunduğu uçuş örneklerini ölçer | Yerel komşuluk boyutunu belirlemek |
| `scripts/validate_block_times_v2.py` | v2 elapsed tabanlı blok sürelerini çapraz doğrular | Veri sürümü ve `K_od/R_o` geçiş kontrolü |
| `scripts/lp_anatomy.py` | LP gevşemesi ve değişken fractionality analizi | Formülasyon darboğazını teşhis etmek |
| `scripts/size_budget.py` | Aday, satır ve kapasite kovası boyut tahmini | Büyük koşudan önce kaynak planlamak |
| `scripts/baseline_feasibility_witness.py` | Baseline tarifeyi A–G açısından kontrol eder | Hangi kısıt ailelerinin başlangıçta ihlalli olduğunu görmek |
| `scripts/feasibility_certificates.py` | Çözücüsüz gerekli koşul sertifikaları | E1/E2'nin kanıtlanabilir biçimde imkânsız olup olmadığını sınamak |

Örnek araştırma komutları:

```bash
# Fiziksel çekirdek model
.venv/bin/python3 -u scripts/run_core_feasibility.py

# Warm-start + elastik model
.venv/bin/python3 -u scripts/warm_start_elastic.py \
  --time-limit-sec 900 \
  --max-improving-sols 1

# HTML pano üret
.venv/bin/python3 scripts/generate_dashboard.py
```

Full-data araştırma komutları dakikalar veya saatler sürebilir ve yüksek bellek kullanabilir. Önce fixture testleri çalıştırılmalıdır.

## Mevcut sonuçlar ve performans

### Kanıt seviyesi tablosu

| Ortam / sonuç | Durum | Ne kanıtlıyor? | Ne kanıtlamıyor? |
|---|---|---|---|
| Sentetik fixture, amaç `668.75` | Bağımsız brute-force oracle ve validator ile doğrulanmış | Tam A–G uygulamasının küçük örnekte doğru ve uçtan uca çalıştığını | Full-data fizibilitesini veya optimumunu |
| Full-data benchmark çıktısı | `objective=1,488,074.81`, `claim_complete=True`, `A/B/D/F/G=0` | Hard-family temiz, tam-iddia, bağımsız-recompute'lu incumbent üretilebildiğini | Strict A–G geçerliliğini (E1=106, E2=221 ihlali var) |
| Full-data A+G+F çekirdeği | Geçmiş koşularda optimum/usable sonuç bulundu | Fiziksel çekirdeğin tek başına çözülebilir olduğunu | E1/E2 ile birlikte katı fizibiliteyi |
| Statik E1/E2 sertifikaları | `0 / 0 / 0` ihlal | Basit bir imkânsızlık kanıtı bulunmadığını | Çözüm varlığını |
| Γ duyarlılık taraması (Γ=30..180) | Her değerde bağımsız çift alt sınırı > 0 | Darboğazın Γ seçiminden değil çift-bağlaşımdan kaynaklandığını | Hangi Γ'da strict fizibilitenin sağlanacağını |
| Full-data doğrulanmış amaç | **Yok** | — | Herhangi bir raporlanan kısmi reward değerinin resmî sonuç sayılmasını |

### Bilinen ölçek davranışları

| Gözlem | Etki | Alınan önlem |
|---|---|---|
| F'nin eski per-bucket Big-M formu satırların büyük kısmını oluşturuyordu | Model boyutu ve LP süresi artıyordu | Birebir eşdeğer kova eşitliğiyle F satırlarında -%54.4 azaltım |
| HiGHS iç zaman limiti kök kesme turlarını her zaman zamanında durduramadı | Koşu bütçesi aşılabiliyordu | SIGTERM/SIGKILL kullanan dış subprocess watchdog |
| Market tabanlı K-subset, paylaşılan fiziksel bacaklar nedeniyle modeli yeterince küçültmedi | Ladder alt adımları etkisiz kaldı | Varsayılan kapatıldı; uçuş örneği düzeyinde fold/LNS geliştirildi |
| Pencereyi 180'den 360'a çıkarmak | Aday sayısında %44.7 artış; çekirdek adım bütçeyi aştı | Varsayılan 180 korundu |

## Varsayımlar, riskler ve sınırlamalar

Tüm ayrıntılı varsayımlar [`ASSUMPTIONS.md`](ASSUMPTIONS.md) içindedir.

| Konu | Uygulanan karar | Risk / açık nokta |
|---|---|---|
| Eksik yolcu destinasyonları | Full-data'da loglanarak düşürülür | Organizatör yorumu gelirse kapsam/amaç değişebilir |
| Ayarlanabilir pencere | ±180 dakika | Brief'in sınırsız Standard yorumu farklı olabilir; daha geniş pencere kombinatoryal olarak pahalıdır |
| Rakip tanımı | `Cr1` taşıyıcısı tek rakiptir; aynı taşıyıcının itinerary'leri minimumla birleşir | Resmî rakip tanımı uçuş/itinerary bazlıysa ranking değişir |
| Ranking monotonluğu | Gerçek tabloda doğrulanır; tek yönlü beat zorlaması buna dayanır | Monoton olmayan yeni tabloda farklı reifikasyon gerekir |
| E1 etkinleşme | Koşullu: yalnızca her iki yön aktifken bağlayıcı | Organizatörden kesin tanım gelmesi durumunda değişebilir |
| E2 muafiyet | Statik imkânsız çiftler (Γ=30'da 63 çift) modelden muaf | Γ değişirse yeniden hesaplanmalı |
| Kapsam dışı TK uçuşları | Kendi baseline kovasında sabit kapasite tüketir | Resmî kapasite tahsisi verilirse güncellenmelidir |
| Jbest domaini | Gerçek sayıdır | Eski integer formülasyon full-data'yı yanlış biçimde infeasible yapabiliyordu; düzeltilmiştir |
| Full-data çözüm durumu | Strict doğrulanmış incumbent yok | Proje, gerçek veri için "optimum bulundu" iddiasında bulunmaz |
| Çözücü | HiGHS varsayılan | Alternatif ticari çözücü karşılaştırması lisans ve ölçek nedeniyle tamamlanmadı |

### Operasyonel güvenlik notları

| Durum | Öneri |
|---|---|
| `status=time_limit`, `objective_value=null` | Incumbent yoktur; sonucu çözüm gibi kullanmayın |
| Elastik sonuçta amaç değeri var | Strict validator geçmeden teslim etmeyin |
| Validator ihlal yazıyor | JSON'u geçersiz kabul edin; yalnız teşhis amacıyla saklayın |
| Yeni veri paketi geldi | SHA256 provenance kaydı, loader testleri ve v2 süre doğrulamasını yeniden çalıştırın |
| Geniş pencere deneniyor | Önce `size_budget.py`; ardından Big-M sınırı ve bellek bütçesini kontrol edin |

## Tekrar üretilebilirlik

| Mekanizma | Sağladığı güvence |
|---|---|
| Sabit `seed=42` | Çözücü rastgeleliğini mümkün olduğunca sabitler |
| Doğal anahtarla JSON sıralama | Aynı sonuç nesnesinden kararlı dosya üretir |
| `file_provenance()` | Aktif girdi yolunu ve SHA256 özetini deney loguna ekler |
| Sentetik fixture | Gerçek veriyi paylaşmadan şema ve model davranışını tekrarlar |
| Brute-force oracle | Fixture amaç değerini `src.model` kodundan bağımsız doğrular |
| Independent validator | Model uygulamasından ayrı ikinci doğruluk hattı sağlar |
| `data_seed/full_data_best_deltas.json` | Seed-derived incumbentin delta vektörünü saklar; aynı koşu tekrarlanabilir |

Sınırlama: zaman limitli ve paralel MIP araması, aynı seed ile bile alternatif eşdeğer çözümler arasından farklı birini seçebilir. Determinizm iddiası, özellikle full-data koşularında "her seferinde byte-byte aynı optimum çözüm" anlamına gelmez.

## Dokümantasyon haritası

| Belge | Ne zaman okunmalı? |
|---|---|
| [`README.md`](README.md) | Projeye giriş, kurulum, mimari ve genel durum |
| [`ASSUMPTIONS.md`](ASSUMPTIONS.md) | Veri/model yorumları ve organizatöre bağlı açık varsayımlar |
| [`KURULUM.md`](KURULUM.md) | Adım adım kurulum, Docker ve teslim paketi çalıştırma talimatları |

## Geliştirme rehberi

### Önerilen değişiklik akışı

| Adım | Eylem |
|---:|---|
| 1 | Değişikliğin hangi veri, model veya doğrulama varsayımını etkilediğini belirleyin |
| 2 | Önce küçük unit/solve testiyle beklenen davranışı tanımlayın |
| 3 | Varsayım değişikliği varsa `ASSUMPTIONS.md` aynı değişiklikte güncelleyin |
| 4 | İlgili dar testleri, ardından tüm test paketini çalıştırın |
| 5 | Fixture CLI'yi uçtan uca çalıştırıp `valid=True` sonucunu kontrol edin |
| 6 | Full-data koşusu gerekiyorsa önce boyut bütçesi çıkarın ve watchdog kullanın |

### Kod değişikliği kontrol listesi

| Değişiklik türü | Zorunlu kontroller |
|---|---|
| Loader / veri şeması | Fixture üreticisi, loader testleri, eski ve yeni kolon yolu |
| Aday üretimi | Ulaşılabilir aralık kanıtı, gece yarısı, rol namespace'i ve pencere sınır testleri |
| Big-M | Aday aralıklarından türetim, `<=1440` assert'i ve sınır testleri |
| A–G kısıtı | Pozitif/negatif/adversarial küçük solve testleri ve bağımsız validator eşlemesi |
| Amaç fonksiyonu | Solver sonucu ile bağımsız recompute karşılaştırması |
| Benchmark pipeline | FLOOR/SEED/IMPROVE sırası, claim-completeness, hard-family seçim sırası |
| Çıktı şeması | Writer determinismi ve validator tüketimi |

### Hızlı sorun giderme

| Belirti | Olası neden | İlk kontrol |
|---|---|---|
| `python: command not found` | Ortam yalnız `python3` sağlıyor | `.venv/bin/python3` veya `python3` kullanın |
| `FileNotFoundError` full-data'da | Dosya adı/yolu `paths.py` ile uyuşmuyor | `data_raw/` içindeki dört kesin adı kontrol edin |
| `SchemaError` | Yeni veri şeması veya bozuk alan | Hata mesajındaki kolon/değişmezi ve loader testini inceleyin |
| Big-M `ValueError` | Pencere çok geniş veya sınırlar tutarsız | `adjustable_window_min`, `L`, `U` ve aday bounds |
| `time_limit` ve boş amaç | Çözücü incumbent bulamadı | HiGHS logu, watchdog statusu ve core/warm-start hattı |
| Warm-start var ama validator geçmiyor | Elastik E1/E2 slack'i sıfır değil | İhlal ailesi dökümü ve diagnostics bloğu |
| Benchmark pipeline SEED adımı boş | `data_seed/full_data_best_deltas.json` eksik veya uyumsuz | Dosyanın varlığını ve veri versiyonunu kontrol edin |

## Sonuç

Bu depo, yalnızca bir optimizasyon betiği değil; veri kalitesi kontrolleri, açık matematiksel model, farklı fizibilite arama stratejileri, benchmark-safe incumbent pipeline, bağımsız doğrulama ve deney kanıt zinciri içeren bir karar destek araştırma altyapısıdır. Küçük sentetik problemde tam model doğrulanmıştır. Gerçek veri tarafında ise proje mevcut kanıtı olduğundan güçlü göstermemekte; katı A–G fizibilitesi ve doğrulanmış amaç değeri bulunana kadar elastik/heuristic sonuçları açıkça **kısmi ve strict-clean değil** olarak sınıflandırmaktadır.

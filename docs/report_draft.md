# THY IST Hub Tarife Optimizasyonu — Teknik Rapor Taslağı

**TEKNOFEST · Yapay Zeka Destekli Havayolu Optimizasyonu**  
**Tarih:** 2026-07-12 · **Durum:** Taslak (PDF'e dönüştürülecek)

---

## 1. Özet ve Problem Çerçevesi

### 1.1 Problem

Türk Hava Yolları'nın İstanbul (IST) hub'ı üzerinden aktarmalı Origin–Destination (O–D) pazarlarında, TK uçuşlarının kalkış/varış saatlerini ayarlayarak hem bağlantı sayısını hem de rakiplere karşı sıralamayı iyileştirmeyi hedefliyoruz. Her aday bağlantı, bir TK inbound uçuşu (o→IST) ile aynı gündeki bir TK outbound uçuşunun (IST→d) eşleşmesidir; bağlantı boşluğu $gap = t^{dep}_{OB} - t^{arr}_{IB}$ dakika cinsinden $[L,U]=[60,300]$ aralığında olmalıdır.

### 1.2 Amaç Fonksiyonu

Amaç fonksiyonu iki bileşenden oluşur:

$$\max \; \underbrace{\sum_{o,d,h,j} \rho_{od}\, W^{(c)}_j\, s_{o,d,h,j}}_{\text{bağlantı ödülü}} + \underbrace{\sum_{o,d,h,r} \rho_{od}\, W^{(r)}(N,b,r)\, onehot_{o,d,h,r}}_{\text{sıralama ödülü}}$$

- **Bağlantı ödülü (M1):** Modül-5 monoton slot — $W^{(c)}_j = 2^{-(j-1)}$.
- **Sıralama ödülü (M2):** Rakip yenme sonrası $W^{(r)}$ lookup tablosu (`change_ranking_input.xlsx`).

### 1.3 Kısıt Seti (A–G)

| Kod | İçerik | Standard parametre |
|-----|--------|-------------------|
| **B** | Bağlantı uygunluğu (bidirectional reifikasyon) | $L=60$, $U=300$ dk |
| **C** | Monoton slot dağılımı | $J_{max} = \|\Pi_{o,d,h}\|$ |
| **D** | Rakip yenme ve sıralama one-hot | Forward-only forcing |
| **A** | Uçak rotasyonu (OB→IB süre tutarlılığı) | $\tau=45$ dk |
| **G** | Günler arası düzenlilik | $X_{dev}=15$ dk |
| **E1** | Yönsel bağlantı sayısı dengesi | $\alpha=0.20$ |
| **E2** | İleri/geri en iyi yolculuk süresi farkı | $\Gamma=30$ dk |
| **F** | IST hub kova kapasitesi | 10 dk kova; dep=10, arr=15 |

Detaylı formülasyon: `docs/model.md`.

### 1.4 Nihai Sonuçlar (özet)

| Veri seti | Amaç değeri | Geçerli? | Not |
|-----------|-------------|----------|-----|
| **Sentetik fixture** | **668.75** | **Evet** | Brute-force oracle ile bağımsız doğrulandı |
| **Gerçek veri (full)** | — | **Hayır** | Tam reward modelinde geçerli incumbent üretilemedi |
| **Gerçek veri (warm-start kısmi)** | ~388.889 (elastic) | Hayır | 6839 bağlantı; E1/E2 ihlalli |

---

## 2. Formülasyon Gerekçeleri

### 2.1 Karar Değişkenleri

| Sembol | Tanım | Domain |
|--------|-------|--------|
| $t^{arr}_r, t^{dep}_r$ | Uçuş örneği $r$'nin IST varış/kalkış saati | Integer (dakika) |
| $x_\pi$ | Bağlantı $\pi$ sunuluyor mu | Binary (B ile türetilir) |
| $gap_\pi$ | $t^{dep}_{r_2} - t^{arr}_{r_1}$ | Integer |
| $s_{o,d,h,j}$ | Monoton slot göstergesi | $[0,1]$ sürekli |
| $beat_{\pi,k}, beaten, onehot$ | Rakip yenme / sıralama | Binary |

**Integer zaman:** B'nin backward-reifikasyonu $(L-1,L)$ ve $(U,U+1)$ bantları kullanır; continuous domain meşru kesirli-dakikalı çözümleri yasak bölgeye iter. Veri dakika hassasiyetinde olduğundan kayıpsız.

**Rol-namespaced ID:** Aynı uçuş numarası hem inbound hem outbound olabiliyor (gerçek veride 26 örnek); $r\_id = (\text{"IB"|"OB"}, flno, gun)$.

### 2.2 Kısıt Gerekçeleri (özet)

**B — Bağlantı uygunluğu:** $x_\pi=1 \Leftrightarrow gap_\pi \in [L,U]$. Tek yönlü reifikasyon yeterli değil; E1/E2 devreye girince solver geçerli bağlantıyı gizleyebilir. 4-kısıtlı interval reifikasyonu + yardımcı $y_\pi$.

**C — Monoton slot:** $\sum_j s_j = \sum_\pi x_\pi$, $s_{j+1} \le s_j$. Azalan getiri slot ağırlığıyla uyumlu; $J_{max}$ veri-türetilmiş (sabit tavan değil).

**D — Rakip yenme:** $beat_{\pi,k}=1 \Rightarrow J_\pi \le T^{comp}_k$. $W(r)$ monoton azaldığından forward-only forcing yeterli (820/820 grup doğrulandı). Rank one-hot **eşitsizlik** ($\ge$), eşitlik değil — $r=0$ tuzağı önlendi.

**A — Rotasyon:** $t^{arr}_{IB} \ge t^{dep}_{OB} + R_o + \tau$. Baseline kronoloji eşleştirmesi (VARSAYIM-10); fiziksel olarak imkansız çiftler muaf (VARSAYIM-11).

**G — Düzenlilik:** Küme-bazlı $X_{dev}$ bandı (VARSAYIM-9); gün-içi normalizasyon zorunlu.

**E1 — Yönsel denge:** $|n_{fwd}-n_{bwd}| \le \alpha(n_{fwd}+n_{bwd})$. Lineer, Big-M gerektirmez.

**E2 — JT farkı:** $|J^{best}_{fwd} - J^{best}_{bwd}| \le \Gamma$. Argmin sandviç (D'nin OR-aggregation deseni); $J_{best}$ domain **Reals** (VARSAYIM-13 — kesirli $K_{od}$ için zorunlu).

**F — Kapasite:** Pencere-ulaşılabilir kova kısıtı (144 sabit kova değil); bijective bucket-offset equality; kapsam-dışı TK uçuşları için rezidüel kapasite.

### 2.3 Big-M Disiplini

- **Per-candidate türetim** (`src/model/big_m.py`): Her adayın achievable range'inden; global sabit değil.
- **Otomatik assert:** $M \le 1440$.
- **F row-fix:** Per-bucket Big-M → bijective equality; satır sayısı %54 azaldı.

---

## 3. Varsayımlar

### 3.1 Özet Tablo

| # | Bulgu | Karar | Organizatör sorusu |
|---|-------|-------|-------------------|
| 1 | 12 duplicate (orig,dest) satır | $\rho$ toplanır | Duplicate anlamı? |
| 2 | 3 eksik-dest satır | `strict=False` ile atılır | Veri hatası mı? |
| 3 | Pencere genişliği belirsiz | ±180 dk | Resmi pencere? |
| 4 | Rakip tanımı | Taşıyıcı bazlı min-konsolidasyon | Itinerary sayımı? |
| 5 | Çok-duraklı rotasyonlar | Ara bacaklar kapsam dışı | Modelleme beklentisi? |
| 6 | E1 formülü | Bağıl denge, çift-yön pazarlar | Kesin formül? |
| 7 | Kapsam-dışı TK kapasitesi | Baseline'da sabit | Resmi kapasite verisi? |
| 8 | 575 pazar direct $K_{od}$ yok | LS tahmini fallback | Resmi $K_{od}$? |
| 9 | TK2841 G anomalisi (645 dk) | Küme-bazlı G | Veri hatası mı? |
| 10 | A "aynı gün" eşleştirmesi %54.7 uzlaştırılamaz | Baseline kronoloji | Resmi eşleştirme kuralı? |
| 11 | %24.3 rotasyon çifti fiziksel imkansız | Muaf tutulur | $R_o$ hatası mı? |
| 12 | Full-adjustable solve süresi | Teşhis tamamlandı | Zaman bütçesi/kısmi çözüm? |
| 13 | $J_{best}$ Integer domain | **Reals** (bug fix) | — |

Tam detay: `ASSUMPTIONS.md`, sorular: `docs/organizer_questions.md`.

### 3.2 Veri Kaynaklı Zorunlu Tasarım Kararları

Brief'in kendi tutarlılığı bizi şu kararlara zorladı (keyfi tercih değil):

1. **G küme-bazlı:** TK2841 baseline'da bile 645 dk > $2 \cdot X_{dev}$; koşulsuz G tüm full-data'yı infeasible kılardı (Helly-özelliği kanıtı).
2. **A kronoloji eşleştirmesi:** "Aynı gün" kuralı 1496 çiftin %54.7'sini uzlaştıramıyordu.
3. **Muaf rotasyon çiftleri:** Düzeltmeden sonra bile 382/1571 (%24.3) çift ayarlanabilir pencereyle bile karşılanamıyor.

### 3.3 Hub Yoğunluğu ve Ayrıştırılamazlık

Full-data'da bir fiziksel uçuş bacağı ortalama **4.4** farklı (o,d) pazarına katılıyor (maksimum 183). K-subset merdiveni yapısal olarak etkisiz bulundu: K=50'de bile candidate'ların %100'ü en az bir bacağı serbest kalıyor. IST hub gerçekten ayrıştırılamaz bir ağ.

---

## 4. Doğrusallaştırma Seçimleri

### 4.1 Big-M vs Sıkı-M

Global $M=1440$ yerine aday-bazlı $M^i_\pi$ kullanımı LP gevşekliğini sıkılaştırır. `tests/unit/test_big_m.py` ile doğrulandı.

### 4.2 E1 Lineer Form

$n_{fwd}, n_{bwd}$ doğrudan $\sum x_\pi$ — reifikasyon veya Big-M gerektirmez.

### 4.3 E2 Argmin Sandviç

D'nin OR-aggregation deseniyle aynı: $a_{dir}$, $w_\pi$ seçici, $J_{best}$ sandviç kısıtları. Singleton pazar-yönleri Expression'a katlandı (%51.4 binary azaltma).

### 4.4 F Kova Bağlama

- Pencere-ulaşılabilir kovalar (144 DEĞİL)
- Ayrı $z_{dep}$, $z_{arr}$ aileleri
- Bijective equality: $t = bucket\_start \cdot z + offset$ (Big-M yerine)
- Rezidüel kapasite precompute (kapsam-dışı TK bacakları)

---

## 5. Çözüm Kalitesi ve Performans

### 5.1 Sentetik Fixture (kanıtlanmış optimum)

```
python main.py --config src/config/standard.yaml --fixture
→ status=optimal  objective=668.75  selected=18  valid=True
```

Bağımsız doğrulama:
- `tests/slow/test_bruteforce_oracle.py` — 10 dk grid brute-force
- `independent_validator.py::recompute_objective()` — bileşen dökümü

Golden çıktı: `runs/fixture_golden.json`

### 5.2 Gerçek Veri — Model Boyutu

| Metrik | Değer |
|--------|-------|
| Aday bağlantı | 18.118 |
| $K_{od}$ direct / estimated | 754 / 571 |
| Rotasyon istasyonu | 240 |
| F row-fix sonrası satır (yaklaşık) | ~330.000 |
| Preprocessing | ~82 s |

### 5.3 Gerçek Veri — Baseline Teşhisi (MIP yok, 36 s)

Ham baseline bağımsız validator ile **2137 ihlal**:

| Kategori | İhlal | Oran |
|----------|-------|------|
| E2 | 1219 | %57 |
| E1 | 690 | %32 |
| A | 144 | %7 |
| G | 53 | %2 |
| F | 31 | %1 |

6873 bağlantı gap $[L,U]$ içinde olduğundan zorunlu seçili. Optimizasyonun amacı bu ihlalleri koordineli düzeltmek — tek kısıt değil, binlerce eş zamanlı ayarlama gerekiyor.

### 5.4 Çözüm Stratejisi Yolculuğu

| Deneme | Model boyutu | Sonuç |
|--------|-------------|-------|
| Reward, tam model (direct solve) | ~330K satır | `watchdog_killed`, incumbent yok |
| Warm A+G+F (step 1) | küçük alt-model | **optimal** (~280 s) |
| Warm elastic (step 2) | ~206K satır | incumbent **388.889**, 6839 bağlantı, **valid=False** |
| Warm reward (step 3) | ~330K satır | Tamamlanamadı (build timeout) |
| Statik E1/E2 sertifikaları | — | **0/0/0** — provably infeasible DEĞİL |
| Greedy repair (saf Python) | — | 2137→2380 (regresyon) |

**Yorum:** Formülasyon hatası değil; HiGHS'in bu problem sınıfında (yoğun Big-M zincirleri + bacak paylaşımı) kök düğümden dallanamaması. Warm-start altyapısı incumbent üretmeyi mümkün kıldı ancak E1/E2 dengesini sıfırlamaya yetmedi.

### 5.5 HiGHS Zaman Limiti Güvenilirliği

`appsi_highs`'ın `time_limit`'i büyük modellerde kök-düğüm cut turunu kesemiyor; dış subprocess watchdog (SIGTERM) zorunlu (`src/solve/subprocess_watchdog.py`).

### 5.6 Ölçeklenebilirlik

Solve merdiveni (`src/solve/ladder.py`): tam-ayarlanabilir → K-subset → dur+teşhis. K-subset yapısal olarak etkisiz bulundu; warm-start pipeline (A+G+F → elastic → reward) alternatif olarak eklendi.

---

## 6. Kod Kalitesi ve Sonuç Tartışması

### 6.1 Yeniden Üretilebilirlik

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py --config src/config/standard.yaml --fixture   # sentetik
python main.py --config src/config/standard.yaml --full-data # gerçek veri
pytest -m unit    # 140+ test, solver'sız
pytest -m solve   # 100+ test, fixture MIP
```

Deterministik seed: `config.seed=42`. 190+ otomatik test.

### 6.2 Bağımsız Validator

`src/validate/independent_validator.py` — `src.model.*` import ETMEZ. Çıktı JSON'dan gap, rank, kısıt ihlallerini bağımsız yeniden hesaplar. Model hatası ile validator hatasının aynı yönde yanılması yapısal olarak engellenir.

### 6.3 Kısıtların Etkileşimi

- **E2 dominant ihlal:** Baseline'da en büyük kategori; ileri/geri yön JT farkı koordineli ayarlama gerektirir.
- **E1 amaç-bastırıcı:** Tek yönlü pazarlarda denge bozukluğu bağlantı sayısını sınırlar.
- **F muhafazakâr:** Rezidüel kapasite precompute gerçekçi hub yükünü yansıtır.
- **Bacak paylaşımı:** Bir uçuş saati değişince ortalama 4.4 pazar etkilenir — ayrıştırma stratejileri sınırlı kazanç sağlar.

### 6.4 Sonuç

| Kriter | Değerlendirme |
|--------|---------------|
| Model doğruluğu (%30) | A–G tam formülasyon; fixture optimal; validator bağımsız |
| Çözüm kalitesi (%25) | Fixture kanıtlı; full-data geçerli çözüm yok |
| Performans (%15) | Teşhis kapsamlı; watchdog; warm-start kısmi ilerleme |
| Kod (%15) | 190+ test, milestone disiplini, dokümantasyon |
| Rapor (%10) | Bu belge |

**Dürüst sınırlama:** Gerçek veride strict A–G kısıtlarını aynı anda sağlayan, bağımsız validator'dan geçen bir çözüm üretilemedi. Sentetik fixture'da optimum kanıtlandı. Warm-start pipeline ile ~388k skorlu kısmi incumbent elde edildi (6839 bağlantı, E1/E2 ihlalli). Organizatöre VARSAYIM-9/10/12 soruları iletilmesi önerilir.

### 6.5 Sonraki Adımlar

Bkz. `docs/m6_recommendations.md`: Gurobi karşılaştırması, koordineli repair, elastic slack minimizasyonu, rapor PDF dönüşümü.

---

## Ek: Çalıştırma Kanıtları

| Dosya | İçerik |
|-------|--------|
| `runs/fixture_golden.json` | Fixture optimal çıktı |
| `runs/full_data_run_20260711T142544Z.log.json` | Ladder teşhis logu |
| `runs/baseline_feasibility_witness_20260711T144019Z.json` | Baseline 2137 ihlal |
| `docs/model.md` | Formel model |
| `ASSUMPTIONS.md` | VARSAYIM detayları |
| `docs/decisions.md` | Kronolojik karar günlüğü |

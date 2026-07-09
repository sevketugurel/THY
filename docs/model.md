# Matematiksel Model Dokümanı — Çalışma Sürümü

Bu dosya milestone milestone güncellenir; her milestone DoD'sinin bir parçasıdır.
Nihai teslim için PDF'e dönüştürülecek (§5 Teslim Edilecekler, brief). **Kod ile bu
dosya arasındaki her tutarsızlık diskalifiye/ağır puan kaybı riskidir** — bir kısıt
veya değişken burada değişirse, aynı commit içinde ilgili `src/model/*.py` da
güncellenmelidir (ve tersi).

Durum: **M0, M1, M2, M3 tamam.** M4 sırada.

---

## 1 · Kümeler

| Sembol | Tanım | Kaynak |
|---|---|---|
| $S$ | Dış istasyonlar (outstation) kümesi | O&D tablosu `Dep1`/`Arr2` kolonlarından türetilir |
| $F$ | TK uçuş numaraları | O&D tablosu `FlNo1`/`FlNo2` |
| $R$ | Uçuş örnekleri $r=(f,h)$ — bir uçuş numarasının belirli bir gündeki gerçekleşmesi | O&D tablosu (flno, gün) çiftleri |
| $R^{var}, R^{fix}$ | Ayarlanabilir / sabit uçuş örnekleri (Standard: $R^{var}=R$, config'ten override edilebilir) | `config.adjustable_set` |
| $H$ | Gün indeksi kümesi, $h\in\{1,\dots,7\}$ | O&D tablosu `Gün` kolonu |
| $\Pi$ | Aday bağlantılar $\pi=(r_1,r_2)$: $r_1$ TK inbound (o→IST), $r_2$ TK outbound (IST→d), aynı gün $h$ | `src/candidates/generate.py` — TK inbound×outbound cross-product, $[L,U]$ fizibilite kapısıyla budanmış (Modül-3 kapı 1) |
| $O\text{-}D$ | Sıralı $(o,d)$ pazar çiftleri, $o\ne d$ | Yolcu Verisi tablosu |

---

## 2 · Parametreler

| Sembol | Tanım | Kaynak / türetim |
|---|---|---|
| $\rho_{od}$ | O–D gelir ağırlığı | `Yolcu Verisi_masked.xlsx`. **Not**: 12 duplicate (orig,dest) satırı toplanıyor, 3 eksik-dest satırı reddediliyor — bkz. `ASSUMPTIONS.md` |
| $L, U$ | Bağlantı boşluğu alt/üst sınır (Standard: 60, 300 dk) | config |
| $\tau_o$ | Minimum yer süresi (Standard: 45 dk) | config |
| $K_{od} = T^{IB}_o + T^{OB}_d$ | Pazar bazlı yolculuk sabiti | `src/data/block_times.py::get_journey_constant` — geçerli-boşluklu ($[L,U]$) TK satırlarının medyanı (gate-to-gate − boşluk) |
| $R_o = T^{IB}_o + T^{OB}_o$ | İstasyon bazlı rotasyon sabiti | `src/data/block_times.py::get_rotation_constant` — bipartite least-squares, shift-invariant (bkz. `tests/unit/test_block_times.py` ve `ASSUMPTIONS.md`) |
| $T^{comp}_{od,h,k}, N_{od,h}$ | Rakip $k$'nin en iyi (min) yolculuk süresi, pazardaki distinct rakip (taşıyıcı) sayısı | `src/data/competitors.py::derive_rival_best_times` — bir "rakip" TEK BİR TAŞIYICI (Cr1); o taşıyıcının o (o,d,h)'deki TÜM itineraryleri min'e konsolide edilir (`ASSUMPTIONS.md` VARSAYIM-4) |
| $b_{od}$ | Taban (baseline) sıralama | `src/data/ranking.py::derive_b_od` — r'nin KENDİ formülünün baseline (optimizasyon-öncesi) zamana uygulanmış hali: $b_{od}=\max(1, N_{od}-$ baseline'da yenilen rakip sayısı$)$, D'nin AYNI $\le$ kuralıyla |
| $W^{(c)}_j = 2^{-(j-1)}$ | Azalan getiri slot ağırlığı (formül, veri değil) | Brief §3.1 |
| $W^{(r)}(N,b,r)$ | Sıralama ödülü lookup | `change_ranking_input.xlsx` (negatif değerler içerebilir) |
| $X_{dev}, \alpha, \Gamma$ | Gün-içi sapma / yönsel denge / JT farkı eşikleri (Standard: 15, 0.20, 30) | config |
| bucket boyutu, kapasite (kalkış/varış) | 10 dk, 10/15 (Standard) | config |

---

## 3 · Karar Değişkenleri (M1–M2)

| Sembol | Tanım | Domain |
|---|---|---|
| $t^{arr}_r, t^{dep}_r$ | Uçuş örneği $r$'nin IST varış/kalkış saati, **tam sayı dakika** (epoch: veri kümesindeki en erken tarihin gece yarısından itibaren) | Integer; $r\in R^{fix}$ için `.fix()` ile sabitlenir (aynı kod yolu, iki ayrı dal yok) |
| $x_\pi$ | Bağlantı $\pi$ sunuluyor mu | Binary — **serbest değil**, B ile türetilmiş göstergedir (aşağı bakınız) |
| $y_\pi$ | B'nin backward-reifikasyonunda hangi taraftan ($<L$ vs $>U$) ihlal edildiğini seçen yardımcı switch | Binary, yalnızca $x_\pi=0$ iken anlamlı |
| $gap_\pi$ | $t^{dep}_{r_2(\pi)} - t^{arr}_{r_1(\pi)}$ (eşitlikle tanımlı) | Integer |
| $s_{o,d,h,j}$ | Modül-5 slot göstergesi, $j=1,\dots,J_{max}(o,d,h)$ | $[0,1]$ **sürekli** — $J_{max}(o,d,h)=\lvert\Pi_{o,d,h}\rvert$ (veri-türetilmiş, config sabiti değil) |
| $beat_{\pi,k}$ | Bağlantı $\pi$, rakip $k$'yı yeniyor mu | Binary — forward-only zorlama (aşağı bakınız) |
| $beaten_{o,d,h,k}$ | Rakip $k$, o (o,d,h) pazarında yenildi mi (OR-aggregation) | Binary |
| $onehot_{o,d,h,r}$ | Güncellenen sıralama $r_{o,d,h}$'nin one-hot göstergesi, $r=1,\dots,N_{o,d,h}$ | Binary |

**Zaman temsili kararı**: integer domain (continuous değil). Gerekçe: B'nin
backward-reifikasyonu $(L-1,L)$ ve $(U,U+1)$ epsilon-bantları kullanır;
continuous zamanla bu bantlar TÜM meşru (kesirli dakikalı) tarifeleri modelin
erişemeyeceği bir "yasak bölge" haline getirirdi. Veri zaten dakika
hassasiyetinde olduğundan integer domain kayıpsız (bkz.
`tests/solve/test_m1_constraints_b.py::test_integer_boundary_*`).

**Uçuş-örneği paylaşımı**: birden fazla $\pi$ aynı $r$'yi referans edebilir
(ör. bir inbound uçuş birden çok outbound ile eşleşebilir) — bu yüzden
$t^{arr}_r,t^{dep}_r$ ROL-namespaced $r\_id=(\text{"IB"|"OB"}, flno, h)$ ile
indekslenir (aynı `flno`'nun hem inbound hem outbound rolünde görünebildiği
gerçek veride 26 örnek doğrulandı — namespace olmadan bu iki farklı zaman
değeri aynı Pyomo Var anahtarı altında çakışırdı).

## 4 · Amaç Fonksiyonu (M1 bağlantı-sayısı + M2 sıralama ödülü)

$$\max \underbrace{\sum_{o\ne d} \rho_{od} \sum_h \sum_j W^{(c)}_j \cdot s_{o,d,h,j}}_{\text{connection\_reward (M1)}} + \underbrace{\sum_{o\ne d} \rho_{od} \sum_h \sum_r W^{(r)}(N_{od,h},b_{od},r)\cdot onehot_{o,d,h,r}}_{\text{ranking\_reward (M2)}}$$

`model.connection_reward` ve `model.ranking_reward` ayrı Pyomo Expression'lar
olarak loglanır (amaç bileşen bileşen izlenebilir olsun diye).

## 5 · Kısıtlar

### B — Bağlantı Uygunluğu (M1)

**Doğruluk argümanı**: $x_\pi=1$ ancak ve ancak $gap_\pi\in[L,U]$.
Tek-yönlü (yalnızca $x=1\Rightarrow gap\in[L,U]$) yeterli DEĞİL — E1/E2 (M4)
devreye girince solver'a "gerçekten geçerli bir bağlantıyı gizle" motivasyonu
doğar (dengesizlik/JT-farkı cezasından kaçınmak için). Backward yön
($gap\in[L,U]\Rightarrow x=1$) bu açığı kapatır. Standart 4-kısıtlı interval
reifikasyonu, yardımcı $y_\pi$ ile:

$$\begin{aligned}
gap_\pi &\ge L - M^1_\pi(1-x_\pi) &&\text{(forward-lower)}\\
gap_\pi &\le U + M^2_\pi(1-x_\pi) &&\text{(forward-upper)}\\
gap_\pi &\le (L-1) + M^3_\pi(x_\pi+y_\pi) &&\text{(backward-below)}\\
gap_\pi &\ge (U+1) - M^4_\pi(x_\pi+(1-y_\pi)) &&\text{(backward-above)}
\end{aligned}$$

**Big-M türetimi** (`src/model/big_m.py`) — her adayın KENDİ achievable
range'inden ($gap_\pi\in[gap^{lo}_\pi,gap^{hi}_\pi]$, bağımsız hareket eden
$t^{arr},t^{dep}$'in interval-subtraction'ı), global sabit değil:

$$M^1_\pi=\max(0,L-gap^{lo}_\pi) \quad M^2_\pi=\max(0,gap^{hi}_\pi-U)$$
$$M^3_\pi=\max(0,gap^{hi}_\pi-(L-1)) \quad M^4_\pi=\max(0,(U+1)-gap^{lo}_\pi)$$

Model kurulumunda her $M$ **otomatik olarak $\le 1440$ assert edilir**
(`MAX_ALLOWED_BIG_M`); aşılırsa `ValueError` ile durur (plan'ın kendi Big-M
disiplini, market-bazlı sıkılaştırmayı M6'ya ertelemek yerine M1'den itibaren
uygulanıyor — daha basit VE daha sıkı).

**Adjustable window VARSAYIM** (`ASSUMPTIONS.md` VARSAYIM-3): $w=180$ dk
(720 değil) — $w$ büyüdükçe Big-M $O(4w)$ mertebesinde büyüyor; $w=720$ bazı
adaylarda $M>1440$'a çıkarıyordu.

### C — Bağlantı Seçimi ve Azalan Getiri (M1)

**Doğruluk argümanı**: $s\in[0,1]$ sürekli, $\sum_j s_j=\sum_\pi x_\pi$,
$s_{j+1}\le s_j$ (monoton), ve $W^{(c)}_j$ kesin azalan olduğundan, optimal
her zaman düşük-$j$ (yüksek ağırlıklı) slotları önce doldurur — sabit toplamı
korurken ağırlığı düşük-$j$'den yüksek-$j$'ye kaydırmak ödülü asla artıramaz.
Bu, LP optimumunu binary deklare etmeden integer köşeye oturtur (daha az
integer değişken → Performans, doğrulandı:
`test_slot_values_settle_at_integer_vertices_not_fractional`).

$$\sum_j s_{o,d,h,j} = \sum_{\pi\in\Pi_{o,d,h}} x_\pi \qquad s_{o,d,h,j+1}\le s_{o,d,h,j}$$

### D — Rakip Yenme ve Sıralama (M2)

**beat reifikasyonu — doğruluk argümanı**: $beat_{\pi,k}=1 \iff J_\pi\le T^{comp}_k$
($J_\pi = K_{od}+gap_\pi$). Gerçek `change_ranking_input.xlsx` tablosu
**monotonik** (sabit $(N,b)$ için $r$ arttıkça $W$ hiç artmıyor — 820 grupta
0 ihlal, `tests/unit/test_ranking.py`). Bu doğruyken **tek-yönlü (forward)**
zorlama yeterli:

$$J_\pi \le T^{comp}_k + M^{fwd}_{\pi,k}(1-beat_{\pi,k}) \qquad beat_{\pi,k}\le x_\pi$$

Backward yön ($J_\pi\le T^{comp}_k \Rightarrow beat_{\pi,k}=1$) gerekmiyor
çünkü $W$ monoton azalan olduğundan under-claim (yenilen bir rakibi
yenilmemiş göstermek) objektifi ASLA artıramaz — solver'ın bunu yapma
motivasyonu yok. **Monotonluk bozulursa** (`is_ranking_monotonic`
`False` dönerse) sistem otomatik `monotonic=False` moda geçer, tam
bidirectional forcing eklenir (ikisi de kodda hazır,
`src/model/constraints_competition.py::add_d_constraints`).

$$M^{fwd}_{\pi,k}=\max(0,J^{hi}_\pi-T^{comp}_k), \quad J^{hi}_\pi=K_{od}+gap^{hi}_\pi$$

**OR-aggregation** ($beaten_{o,d,h,k}$) HER ZAMAN iki yönlü — monotonluktan
bağımsız yapısal bir gereklilik (iç tutarlılık):

$$beaten_{o,d,h,k} \ge beat_{\pi,k} \;\forall\pi \qquad beaten_{o,d,h,k} \le \sum_\pi beat_{\pi,k}$$

$$r_{o,d,h} = N_{o,d,h} - \sum_k beaten_{o,d,h,k}$$

**Rank one-hot — kritik düzeltme (ultrathink + CLI end-to-end testiyle
yakalandı)**: $r=N-\text{beaten}$ formülü $[0,N]$ üretebilir ama gerçek
tabloda $r$ asla 0 değil (min gözlenen $r=1$, tüm $N$ için doğrulandı).
İlk tasarımda linking EŞİTLİK'ti (`sum(r·onehot_r)==r_{o,d,h}`) — bu, solver
beaten=N'e ulaştığında $r=0$ gerektiriyordu ama onehot'un $r=0$ karşılığı
YOKTU, yani solver YAPISAL OLARAK en az bir rakibi bedava olsa bile kasıtlı
yenilmemiş bırakmak ZORUNDA kalıyordu (infeasibility tuzağı). **Düzeltme**:
linking EŞİTSİZLİK yapıldı:

$$\sum_j j\cdot onehot_{o,d,h,j} \ge r_{o,d,h} \qquad \sum_j onehot_{o,d,h,j}=1$$

$onehot$'un kendi domain'i $[1,N]$ + $W$'nin monotonluğu, optimizer'ı
otomatik olarak $r=\max(1,N-\text{beaten})$'e oturtuyor (C'nin slot
argümanıyla AYNI mantık — max()/min() lineerleştirmesi gerekmedi).

**Under-claim toleransı**: forward-only forcing claimed_beaten'i HER ZAMAN
actual_beaten'in alt kümesi yapar (over-claim yapısal olarak imkansız) —
bu yüzden `src/validate/independent_validator.py` under-claim'i violation
olarak İŞARETLEMEZ (ödül asla şişirilmiyor, sadece eksik bilgi). Ayrıntı:
`tests/fixtures/README.md` "M2 eki", `docs/decisions.md` 2026-07-09.

### A — Zaman Sınırları ve Uçak Rotasyonu (M3)

**Doğruluk argümanı**: "Aynı uçak IST→o→IST iki bacaklı bir görevi
gerçekleştirir" — KOŞULSUZ bir operasyonel kural ($x_\pi$'den bağımsız,
hangi bağlantıların sunulduğundan etkilenmez, sadece fiziksel uçak
kısıtı). $R_o=T^{IB}_o+T^{OB}_o$ zaten TEK sağlayıcı çağrısıyla geliyor
(`block_times.get_rotation_constant`):

$$t^{arr}_{(\text{IB},flno_{dönüş},h)} \ge t^{dep}_{(\text{OB},flno_{gidiş},h)} + R_o + \tau_o$$

Big-M **gerekmiyor** (koşulsuz eşitsizlik, reifikasyon değil).

**Kapsam sınırlaması** (`ASSUMPTIONS.md` VARSAYIM-5): yalnızca Pair grubu
içindeki ARDIŞIK (Orig==IST → sonra Dest==IST) bacak çiftlerine uygulanır.
Gerçek veride 707 Pair grubundan 657'si tam 2-üyeli (doğrudan kapsanıyor);
50'si 3+ üyeli, bazıları IST'e değmeyen ara bacaklar içeriyor (ör.
IST→MEX→CUN→IST) — bu ara bacaklar modelin $t^{arr}/t^{dep}$ değişken
kapsamı DIŞINDA (yalnızca IST-tarafı zamanlar modelleniyor), o gruplar
için kısıt EKSİK kalıyor (bilinçli, dokümante edilmiş sınırlama).

### G — Tarife Düzenliliği (M3)

**Doğruluk argümanı — referans-zaman formülasyonu**: brief
"$\max(t_h)-\min(t_h)\le X_{dev}$" istiyor. Naif formülasyon HER GÜN ÇİFTİ
için $|t_{h_1}-t_{h_2}|\le X_{dev}$ kurar ($O(H^2)$ kısıt). Bunun yerine
serbest bir referans değişkeni $T_{role,flno}$ tanımlanır, her gün için:

$$T_{role,flno} \le t_{role,flno,h} \le T_{role,flno}+X_{dev} \qquad \forall h$$

**Eşdeğerlik kanıtı**: ($\Leftarrow$) Tüm $t_h$ aynı $X_{dev}$-genişlikli
pencerede ise herhangi iki günün farkı en fazla $X_{dev}$. ($\Rightarrow$)
$\max(t_h)-\min(t_h)\le X_{dev}$ ise $T=\min(t_h)$ seçilir; o zaman tüm
$t_h\le\max(t_h)\le\min(t_h)+X_{dev}=T+X_{dev}$ otomatik sağlanır, ve
$t_h\ge\min(t_h)=T$ zaten tanım gereği. Formülasyon TAM eşdeğer (gevşek
değil), $O(H)$ kısıtla ifade ediyor (H=gün sayısı) — daha sıkı LP
gevşetmesi, daha küçük branch-and-bound ağacı.

**Kritik düzeltme — gün-içi normalizasyon** (ilk solve denemesinde
infeasibility olarak yakalandı): $t_{role,flno,h}$'nin epoch değeri TEK bir
GLOBAL çapaya göre (`compute_epoch_anchor`, tüm veri kümesinin en erken
tarihinin gece yarısı) — farklı $h$ (gün) değerleri farklı TAKVİM günlerine
denk geldiğinden, epoch değerleri arasında ~1440dk'lık (bir gün) fark vardır,
saat-of-day AYNI olsa bile. Formülü ham epoch değerlerine doğrudan
uygulamak, saat-of-day'i tamamen uyumlu bir tarifeyi bile ~1440dk'lık SAHTE
bir ihlal olarak görür — $X_{dev}$ ile ASLA uzlaştırılamaz, model
infeasible olur. **Çözüm**: her $(role,flno,h)$ kendi takvim gününün gece
yarısına göre normalize edilir ($t - \text{day\_offset}(role,flno,h)$)
önce kısıta girer — $T_{role,flno}$ artık "gün-içi referans dakika" temsil
eder. `src/model/constraints_operations.py::_day_offsets`, aynı düzeltme
`independent_validator.py`'nin x_dev kontrolünde de tekrarlanır (aksi halde
GEÇERLİ bir çözüm bile validator tarafından yanlışlıkla reddedilirdi).

**Rol-ayrımı**: aynı `flno` hem IB hem OB rolünde görünebilir (M1'de 26
gerçek örnek doğrulandı) — her rol KENDİ ayrı $T_{role,flno}$'suna sahip
(brief "kalkış VE varış saatleri" diyerek zaten ayrı ele alıyor). Yalnızca
2+ farklı günde modelde bulunan (role,flno) çiftleri için kısıt kurulur.

### E, F

*(M4'te eklenecek — bkz. M4 tasarım notu.)*

# Matematiksel Model Dokümanı — Çalışma Sürümü

Bu dosya milestone milestone güncellenir; her milestone DoD'sinin bir parçasıdır.
Nihai teslim için PDF'e dönüştürülecek (§5 Teslim Edilecekler, brief). **Kod ile bu
dosya arasındaki her tutarsızlık diskalifiye/ağır puan kaybı riskidir** — bir kısıt
veya değişken burada değişirse, aynı commit içinde ilgili `src/model/*.py` da
güncellenmelidir (ve tersi).

Durum: **M0, M1, M2, M3 tamam.** M4 tamam (E1+E2+F, main.py'ye bağlandı,
CLI end-to-end valid=True). M4 kapanış ritüeli sırada.

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

**M5c D-folding** (`docs/lp_anatomy.md`): $beat_{\pi,k}$'ye HER ZAMAN bir
Binary değişken açılmaz — $J^{hi}_\pi\le T^{comp}_k$ ise $\pi$ pencerenin
TAMAMINDA rakip $k$'yı yeniyor (veri-gerçeği, $beat\equiv x_\pi$'ye
katlanır, değişken üretilmez); $J^{lo}_\pi>T^{comp}_k$ ise HİÇBİR zaman
yenmiyor ($beat\equiv 0$'a katlanır). Bu, monoton VE bidirectional-fallback
modlarının İKİSİNDE de geçerli (adayın penceresine dair bir veri-gerçeği,
zorlama yönünden bağımsız) — değişken/kısıt eklemek yerine ELEME, LP
gevşemesini de sıkılaştırır (fractionality full-data'da $beat$ için
%14→katlanan çiftler için 0).

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

**Eşleştirme kuralı — BASELINE KRONOLOJİSİ (M5 VARSAYIM-10)**: yukarıdaki
formülün $flno_{gidiş}$/$flno_{dönüş}$ eşleştirmesi (hangi OB kalkışının
hangi IB varışıyla eşleştiği) M3'te "AYNI GUN" varsayımıyla yapılıyordu.
Gerçek veride bu YANLIŞ: $R_o$ genellikle SAATLER mertebesinde (uzun
menzilde 6-21 saat) olduğundan, aynı gün'ün IB'si çoğu zaman GERÇEK dönüş
bacağı değil, TAMAMEN ALAKASIZ bir rotasyon. Full data'da 1496 rotasyon-çift
örneğinin 818'i (%54.7) baseline'da uzlaştırılamaz, %45.3'ü KRONOLOJİK
OLARAK TERS (IB varışı OB kalkışından ÖNCE) çıktı.

Düzeltme (`src/model/rotation_matching.py::match_rotation_legs`): her OB
kalkışının partneri, BASELINE saat-of-day'e göre KENDİSİNDEN SONRAKİ EN
YAKIN IB varışı — dairesel (Gün haftalık tekrarlanan desen, Gün=7'den
Gün=1'e sarar), açgözlü ve BİREBİR. Kısa menzilde (aynı gün içinde döner)
bu kural zaten "aynı gun" ile AYNI sonucu verir — M3 davranışı korunur.
Sarma (Gün=7→Gün=1) durumunda kısıtın ham epoch kıyası bir HAFTA
(`WEEK_PERIOD_MIN=10080`) ileri kaydırılır, aksi halde önceki haftanın
(yanlış) değeriyle kıyaslanır:

$$t^{arr}_{ib\_gun} + \text{week\_offset} \ge t^{dep}_{ob\_gun} + R_o + \tau_o$$

**Kalıcı istisna — VARSAYIM-11**: doğru eşleştirmeyle bile full data'nın
%24.3'ü (382/1571) KENDİ en-iyi-durum ayarlamasında bile uzlaştırılamaz
(G'nin TK2841 durumuyla AYNI yapısal senaryo). Bu çiftler, her bacağın
KENDİ $[t_{lo},t_{hi}]$ penceresi kullanılarak ($t^{arr}_{hi}+
\text{week\_offset} \ge t^{dep}_{lo}+R_o+\tau_o$ testiyle) tespit edilip A
kısıtından MUAF tutulur (loglanır, sessizce atlanmaz).

**Bağımsız doğrulama**: `independent_validator.py::_match_rotation_legs_independent`
AYNI algoritmayı bağımsız (import etmeden) yeniden uygular, baseline
kronolojisini ham TK tablosundan (raporlanan zamanlardan DEĞİL) türetir.

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

**İkinci kritik düzeltme — gece yarısı SARMASI (M4 "G check")**: yukarıdaki
düzeltme referans noktası olarak GERÇEK gece yarısını (00:00) kullanıyordu.
Bu, KENDİ saati gece yarısına YAKIN olan bir uçuş için hâlâ yanlış: 23:55
(gün-içi=1435) ile 00:05 (gün-içi=5) arasındaki GERÇEK fark 10 dakikadır,
ama gece-yarısı-çapalı temsilde $|1435-5|=1430$, X_dev ile ASLA
uzlaştırılamayan SAHTE bir ihlal. Çözüm: referans noktası her (role,flno)
çifti için, o uçuşun KENDİ baseline saatinin TAM 12 SAAT KARŞISINA
kaydırılıyor (`_flight_cut_points`, saat+720 mod 1440) — uçuşun ayarlanabilir
aralığı (Big-M disiplini gereği hiçbir zaman ±720dk'yı aşamaz) bu yeni
sınırdan ASLA taşamaz, sarma sorunu o uçuş için yapısal olarak imkansız
hale gelir. Elle doğrulandı ve `test_g_no_false_violation_at_midnight_wraparound`
(RED→GREEN) ile kanıtlandı. Validator'ın x_dev kontrolü BİREBİR aynı
mantığı tekrarlar.

**Üçüncü kritik düzeltme — KÜME-BAZLI G (M5 VARSAYIM-9)**: full-data solve
merdiveni tüm adımlarda HIZLI infeasible verdi (bkz. ASSUMPTIONS.md
VARSAYIM-9) — kök neden, gerçek TK2841 (TZX→IST) uçuşunun KENDİ baseline
tarifesinin bile G'nin koşulsuz ("tüm günler tek grup") okumasını tatmin
edemeyecek kadar günden güne değişmesi (4 günde 03:25, 1 günde 14:10,
645dk fark — $\pm180$dk pencere ile en fazla $2\times180+15=375$dk
uzlaştırılabilir, $645>375$). Katı okumada uzlaştırılabilir küme kümesi
BOŞ — tüm problem infeasible olurdu.

**Formel kanıt** (1D Helly özelliği, aralıklar için): bir grubun (aynı
role,flno'nun gün-örnekleri) tek bir ortak $T_{ref}$ ile uzlaştırılabilmesi

$$\iff \forall h:\ [baseline_h-w_h,\,baseline_h+w_h] \cap [T_{ref},\,T_{ref}+X_{dev}] \neq \emptyset$$
$$\iff T_{ref} \in \bigcap_h [baseline_h-w_h-X_{dev},\,baseline_h+w_h]$$
$$\iff \max_h(baseline_h-w_h) - \min_h(baseline_h+w_h) \le X_{dev}$$
$$\iff \max(baseline) - \min(baseline) \le w_{\min\text{-}\ddot{o}rnek} + w_{\max\text{-}\ddot{o}rnek} + X_{dev} \quad \text{(ÇAP koşulu)}$$

Bu bir **ÇAP** (diameter) koşuludur, ARDIŞIK-boşluk (single-linkage) koşulu
DEĞİL: 0dk/300dk/600dk'lık üç nokta ($w=0$, $X_{dev}=310$) ardışık bakışta
($300\le310$ her komşu çift için) tek kümeye yanlışlıkla birleşirdi, ama
0 ile 600 arasındaki GERÇEK 600dk'lık fark 310'u aşıyor — ortak bir
310dk'lık pencereye asla sığmazlar.

**Karar**: G artık FLIGHT bazında değil KÜME bazında uygulanıyor
(`src/model/day_clustering.py::cluster_flight_days`). Algoritma: (1)
dairesel eksende (mod 1440) EN BÜYÜK boşluktan kes (rastgele bir kesim
noktasının gerçek bir kümeyi bölmesini önler — gece yarısı sarmasıyla AYNI
motivasyon, `_flight_cut_points`'le tutarlı), (2) doğrusallaştırılmış
diziyi soldan sağa AÇGÖZLÜ ÇAP taraması: her nokta KÜME BAŞLANGICINA
(sıralı taramada her zaman en küçük tod'lu, ilk eklenen üye) göre
kontrol edilir, ARDIŞIK ÖĞEYE göre DEĞİL. Her döndürülen kümenin çap
koşulunu sağladığı invariant olarak assert edilir. Veri-türetilmiş ve
GENEL (belirli bir uçuş numarasına özel hiçbir şey hardcode edilmiyor —
gizli test seti güvenliği).

$$t_{f,h} \in [T_{ref}^{(f,c)},\, T_{ref}^{(f,c)}+X_{dev}] \qquad \forall h \in c$$

Tüm günler zaten uzlaştırılabilirse (yaygın durum — gerçek veride 460/461
çok-günlü IB uçuşu, 476/476 OB uçuşu) TEK küme oluşur = M3 davranışı
DEĞİŞMEDEN korunur; yalnızca TK2841 gibi yapısal aykırı değerler kendi
tekil kümelerine ayrılır. `independent_validator.py::_cluster_flight_days_independent`
AYNI algoritmayı bağımsız (import etmeden) yeniden uygular — yalnızca AYNI
kümenin İÇİNDEKİ raporlanan zamanlar X_dev'e tabi, kümeler arası
karşılaştırma yapılmaz.

**Rol-ayrımı**: aynı `flno` hem IB hem OB rolünde görünebilir (M1'de 26
gerçek örnek doğrulandı) — her rol KENDİ ayrı $T_{role,flno}$'suna sahip
(brief "kalkış VE varış saatleri" diyerek zaten ayrı ele alıyor). Yalnızca
2+ farklı günde modelde bulunan (role,flno) çiftleri için kısıt kurulur.

### E1 — Yönsel Sayı Dengesi (M4)

**Doğruluk argümanı**: $n_{fwd}=\sum_\pi x_\pi$ (o,d,h pazarı),
$n_{bwd}=\sum_\pi x_\pi$ (d,o,h pazarı) zaten LİNEER ifadeler (C'nin
market-grouping'inden) — reifikasyon/Big-M GEREKMİYOR:

$$n_{fwd}-n_{bwd}\le\alpha(n_{fwd}+n_{bwd}) \qquad n_{bwd}-n_{fwd}\le\alpha(n_{fwd}+n_{bwd})$$

İki yön de boş → $0\le0$ her ikisinde, otomatik sağlanır. Formül VARSAYIM
(`ASSUMPTIONS.md` VARSAYIM-6) — brief kesin formül vermiyor. Yalnızca HER
İKİ yönde de candidate'ı olan pazar çiftlerine uygulanır (tek-yönlü
pazarları zorlamak modelin KAPSAM sınırlamasından kaynaklanan yapay bir
kısıtlama olurdu).

**Kritik davranışsal etki**: B'nin "$gap\in[L,U]\Rightarrow x=1$ ZORUNLU"
kuralı, E1'i sağlamanın YEGANE yolunun bir bağlantıyı KISMEN gizlemek değil
(B tarafından yapısal olarak engelleniyor), zamanı kaydırıp $gap$'i
$[L,U]$ dışına iterek bağlantıyı TAMAMEN ÖLDÜRMEK olduğu anlamına gelir.
Küçük/asimetrik pazarlarda (ör. bir yönde zaten 1-2 candidate varsa) bu,
E1'i bir **amaç bastırıcı** yapabilir: solver tek bir fazla bağlantıyı
dengelemek yerine TÜM pazarı sıfırlamayı (n_fwd=n_bwd=0, kendiliğinden
sağlanan durum) tercih edebilir, eğer bu objektif açısından daha "ucuzsa".
`src/model/constraints_balance.py::e1_diagnostics` bu davranışı post-solve
izler (her pazar çifti için n_fwd/n_bwd + sıfıra-inme bayrağı, rapora
girecek metrik).

### E2 — Yön-Arası Seyahat Süresi Farkı (M4)

**Brief**: her iki yönde de en az bir bağlantı SUNULUYORSA, iki yönün EN İYİ
(minimum) seyahat sürelerinin farkı $\Gamma$ dakikayı aşmamalı. Bu, D'nin
OR-aggregation'ından (herhangi biri mi) yapısal olarak FARKLI bir talep:
pazarın "en iyi" $J$ değeri SEÇİLEBİLİR bir alt kümenin minimumu — MIP'in
doğal bir $\min(\cdot)$ operatörü yok, bu yüzden bir **argmin sandviç**
gerekiyor.

**Değişkenler** (her $(o,d,h)$ pazarı için):
- $a_{dir}\in\{0,1\}$: pazar aktif mi (en az bir $\pi$ sunuluyor mu) — D'nin
  `beaten_k` desenindeki OR-aggregation ile BİREBİR aynı yapı:
  $$a_{dir}\ge x_\pi\ \forall\pi \qquad a_{dir}\le\sum_\pi x_\pi$$
- $w_\pi\in\{0,1\}$ (her candidate için): $\pi$ pazarın argmin'i olarak
  SEÇİLDİ mi:
  $$w_\pi\le x_\pi\ \forall\pi \qquad \sum_\pi w_\pi=a_{dir}$$
  ($a_{dir}=1$ ise tam bir $\pi$ seçilir; $a_{dir}=0$ ise hiçbiri.)
- $J_{best}\in[JD_{lo},JD_{hi}]$: pazarın iddia edilen minimum seyahat
  süresi ($JD_{lo}/JD_{hi}$ = pazardaki TÜM candidate'ların
  $J_\pi=K_{od}+gap_\pi$ achievable aralığının min/max'ı — `derive_e2_candidate_big_ms`).

**Sandviç kısıtları** (her candidate $\pi$ için):
$$J_{best}\le J_\pi + M^{up}_\pi(1-x_\pi) \qquad J_{best}\ge J_\pi - M^{down}_\pi(1-w_\pi)$$

**Doğruluk argümanı** (adversarial: solver $J_{best}$'i sahte düşük
gösteremez): "$\le$" tek başına HER sunulan candidate için ayrı bir üst
sınır koyar ($x_\pi=1$ iken $M^{up}=0$'a kadar sıkışabilir, $J_{best}\le
J_\pi$ tam) — bu $J_{best}$'i gerçek minimumun ÜSTÜNE hiç çıkaramaz, ama
TEK BAŞINA altına indirmeyi de engellemez (pazardaki DİĞER, sunulmayan
candidate'ların geniş achievable aralığı $J_{best}$'in kendi
$[JD_{lo},JD_{hi}]$ sınırından ASLA taşamayacağı için, $w_\pi$ olmadan
$J_{best}$ pazarın en düşük olası $J$'sine — sunulmuş olsun olmasın —
serbestçe kayabilirdi). $w_\pi\le x_\pi$ + $\sum w_\pi=a_{dir}$ solver'ı
SADECE fiilen sunulan bir candidate'a $w=1$ vermeye zorlar; O candidate
için "$\ge$" $J_{best}$'i O'nun KENDİ $J_\pi$'sinin altına inmekten
yapısal olarak alıkoyar. İki yönün KESİŞİMİ (aynı anda hem üstten hem
alttan sıkışan $J_{best}$) yalnızca gerçek $\min(J_\pi:x_\pi=1)$
noktasında FEASIBLE'dır — sahte-düşük bir $J_{best}$ iddiası, seçilen
$w_\pi$'nin kendi $J_\pi$ değeriyle ÇELİŞEN bir "$\ge$" kısıtına çarpar
(bkz. `tests/solve/test_m4_constraints_e2.py::test_e2_sandwich_cannot_fabricate_jbest_below_true_min`,
pazarın diğer bir candidate'ının çok düşük achievable aralığı bilerek
$M^{down}$'ı ayartmaya çalışıyor ve başarısız oluyor).

**E2'nin kendisi** (fwd/bwd pazar çifti, aynı gün):
$$J_{best}^{fwd}-J_{best}^{bwd}\le\Gamma+M_{pair}(2-a_{fwd}-a_{bwd})$$
$$J_{best}^{bwd}-J_{best}^{fwd}\le\Gamma+M_{pair}(2-a_{fwd}-a_{bwd})$$

$M_{pair}=\max(0,JD_{hi}^{side}-JD_{lo}^{other}-\Gamma)$
(`derive_e2_pair_big_m`) tam olarak "iki yönün KENDİ ilan edilmiş
$J_{best}$ değişken sınırlarının izin verdiği en kötü fark $-\Gamma$" —
faktör 1 (tek yön aktif) veya 2 (hiçbiri aktif değil) olduğu an kısıt
$J_{best}$'in kendi bounds'u tarafından zaten sağlanan bir eşitsizliğe
gevşer (kanıt: $J_{best}^{side}\le JD_{hi}^{side}$ ve
$J_{best}^{other}\ge JD_{lo}^{other}$ HER ZAMAN, dolayısıyla fark hiçbir
zaman $JD_{hi}^{side}-JD_{lo}^{other}=\Gamma+M_{pair}$'i aşamaz — bu
Big-M'nin M'sinin "tam gevşetme" tanımının doğrudan sonucu). Yalnızca
$a_{fwd}=a_{bwd}=1$ (4 satırlık tablonun son satırı) iken kısıt gerçekten
BAĞLAYICI hale gelir.

**4 satırlık aktivasyon tablosu** — her satır ayrı test
(`tests/solve/test_m4_constraints_e2.py`):

| $a_{fwd}$ | $a_{bwd}$ | Beklenen davranış |
|---|---|---|
| 0 | 0 | E2 tamamen gevşek — $J_{best}$'ler kendi $[JD_{lo},JD_{hi}]$ aralığında serbest |
| 1 | 0 | E2 gevşek (karşılaştırılacak bir "diğer yön" yok), ama fwd'in $J_{best}$'i yine de DOĞRU (gerçek min) — pasif tarafın varlığı sandviçi bozmuyor |
| 0 | 1 | Simetrik (yukarısının aynası) |
| 1 | 1 | E2 BAĞLAYICI: $\lvert J_{best}^{fwd}-J_{best}^{bwd}\rvert\le\Gamma$ zorunlu |

**Bağımsız doğrulama**: `independent_validator.py`'nin `gamma` kontrolü
model kodundan hiç import almadan, SEÇİLMİŞ (offered) bağlantıların
raporlanan $gap$'lerinden Python `min()` ile $J_{best}^{fwd}/J_{best}^{bwd}$'i
yeniden hesaplar (argmin sandviç MIP mekanizmasına ihtiyaç yok — zaten
seçilmiş adaylar arasından minimum almak yeterli) ve $\Gamma$
eşitsizliğini bağımsız olarak assert eder.

### F — Hub Kova/Kapasite Bağlama (M4)

**Değişkenler**: her ayarlanabilir uçuş örneği (rol,flno,gün) için,
PENCERE-ULAŞILABİLİR kovalar üzerinde $z^{dep}_{r,b}/z^{arr}_{r,b}\in\{0,1\}$
(`derive_window_reachable_buckets` — $[k\Delta,(k+1)\Delta)$ ile $[t_{lo},t_{hi}]$'nin
kesiştiği TÜM $k$'lar, GÜNÜN TÜM kovaları (144, $\Delta=10$) DEĞİL — M5
ölçek performansı için kritik bir budama).

**Doğruluk argümanı**: her örnek x_\pi'den (bağlantı sunuluyor mu) bağımsız
olarak HER ZAMAN hub'da fiziksel bir kovaya denk gelir — bu yüzden $\sum_b
z_{r,b}=1$ KOŞULSUZ (D/E1/E2 gibi x_\pi'ye bağlı değil, F ARR/DEP_INSTANCES
üzerinde çalışır, CANDIDATES üzerinde değil). Kova-zaman bağlama, B/D'yle
AYNI candidate-bazlı Big-M reifikasyon deseni:

$$b\Delta - M^{lo}_{r,b}(1-z_{r,b}) \le t_r \le (b+1)\Delta-1+M^{hi}_{r,b}(1-z_{r,b})$$

$M^{lo}_{r,b}=\max(0,b\Delta-t_{r,lo})$, $M^{hi}_{r,b}=\max(0,t_{r,hi}-((b+1)\Delta-1))$
— her ikisi de $r$'nin KENDİ $[t_{lo},t_{hi}]$ Var bounds'undan türetilir.

**Kapasite** (ayrı departure/arrival aileleri, ayrı taban kapasiteler
10/15):
$$\sum_{r:\,b\text{ ulaşılabilir}} z^{dep}_{r,b} \le \text{residual}^{dep}_b \qquad \sum_{r:\,b\text{ ulaşılabilir}} z^{arr}_{r,b} \le \text{residual}^{arr}_b$$

**Rezidüel kapasite** (VARSAYIM-7, ASSUMPTIONS.md): modelin hiç değişkeni
olmayan (kapsam-dışı) TK bacakları kendi HAM baseline zamanında SABİT
işgal ettiği kabul edilir ve o kovanın kapasitesinden düşülür
(`compute_out_of_scope_baselines` — tam-tarama precompute, model
kurulmadan ÖNCE bir kez; `compute_residual_capacity` — kapasiteyi düşer,
0'ın altına inmez). A'nın rotasyon kısıtı da AYNI kapsam-dışı-baseline
kaynağını paylaşır (edge case: bir Flight Pair alt-çiftinin bacaklarından
biri kapsam dışıysa, in-scope bacağa yine de kapsam-dışı ortağın SABİT
baseline'ına karşı kısıt kurulur — `build_rotation_pairs`'in
`partial_pairs` çıktısı).

**Bağımsız doğrulama**: `independent_validator.py`'nin `bucket_size_min`
kontrolü, MIP z-binary mekanizmasına hiç ihtiyaç duymadan, `reported_times`
üzerinden doğrudan `t//bucket_size_min` sayarak kova-doluluğu yeniden
hesaplar; kapsam-dışı işgal AYNI mantıkla (raw TK tablosundan) bağımsız
olarak türetilir.

**Test kapsamı** (`tests/unit/test_capacity.py`, `tests/solve/test_m4_constraints_f.py`):
pencere-ulaşılabilir kova sayısının günün 144 kovasından ÇOK küçük kaldığı
doğrulanıyor, kapasite gevşekken bağlayıcı olmadığı, sıkı kapasitede iki
adayın FARKLI kovalara zorlandığı (`capacity_departure=1` fixture'ı),
kapsam-dışı bir uçuşun rezidüel kapasiteyi gerçekten düşürdüğü, ve
departure/arrival ailelerinin birbirinden BAĞIMSIZ olduğu (aynı sayısal
kova indeksini paylaşsalar bile rekabet etmiyorlar).

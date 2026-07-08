# Matematiksel Model Dokümanı — Çalışma Sürümü

Bu dosya milestone milestone güncellenir; her milestone DoD'sinin bir parçasıdır.
Nihai teslim için PDF'e dönüştürülecek (§5 Teslim Edilecekler, brief). **Kod ile bu
dosya arasındaki her tutarsızlık diskalifiye/ağır puan kaybı riskidir** — bir kısıt
veya değişken burada değişirse, aynı commit içinde ilgili `src/model/*.py` da
güncellenmelidir (ve tersi).

Durum: **M0, M1 tamam.** M2 sırada.

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
| $T^{comp}_{od,k}, N_{od}, b_{od}$ | Rakip yolculuk süresi, rakip sayısı, taban sıralama | O&D tablosu (TK-dışı satırlar). **AÇIK**: tam türetim kuralı netleşmedi (plan §7) — M2'de netleştirilecek |
| $W^{(c)}_j = 2^{-(j-1)}$ | Azalan getiri slot ağırlığı (formül, veri değil) | Brief §3.1 |
| $W^{(r)}(N,b,r)$ | Sıralama ödülü lookup | `change_ranking_input.xlsx` (negatif değerler içerebilir) |
| $X_{dev}, \alpha, \Gamma$ | Gün-içi sapma / yönsel denge / JT farkı eşikleri (Standard: 15, 0.20, 30) | config |
| bucket boyutu, kapasite (kalkış/varış) | 10 dk, 10/15 (Standard) | config |

---

## 3 · Karar Değişkenleri (M1)

| Sembol | Tanım | Domain |
|---|---|---|
| $t^{arr}_r, t^{dep}_r$ | Uçuş örneği $r$'nin IST varış/kalkış saati, **tam sayı dakika** (epoch: veri kümesindeki en erken tarihin gece yarısından itibaren) | Integer; $r\in R^{fix}$ için `.fix()` ile sabitlenir (aynı kod yolu, iki ayrı dal yok) |
| $x_\pi$ | Bağlantı $\pi$ sunuluyor mu | Binary — **serbest değil**, B ile türetilmiş göstergedir (aşağı bakınız) |
| $y_\pi$ | B'nin backward-reifikasyonunda hangi taraftan ($<L$ vs $>U$) ihlal edildiğini seçen yardımcı switch | Binary, yalnızca $x_\pi=0$ iken anlamlı |
| $gap_\pi$ | $t^{dep}_{r_2(\pi)} - t^{arr}_{r_1(\pi)}$ (eşitlikle tanımlı) | Integer |
| $s_{o,d,h,j}$ | Modül-5 slot göstergesi, $j=1,\dots,J_{max}(o,d,h)$ | $[0,1]$ **sürekli** — $J_{max}(o,d,h)=\lvert\Pi_{o,d,h}\rvert$ (veri-türetilmiş, config sabiti değil) |

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

## 4 · Amaç Fonksiyonu (M1: yalnızca bağlantı-sayısı ödülü)

$$\max \sum_{o\ne d} \rho_{od} \sum_h \sum_j W^{(c)}_j \cdot s_{o,d,h,j} \qquad (+ \text{sıralama ödülü, M2})$$

`model.connection_reward` ayrı bir Pyomo Expression olarak loglanır (amaç
bileşen bileşen izlenebilir olsun diye).

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

### A, D, E, F, G

*(M2–M4'te eklenecek.)*

# Matematiksel Model Dokümanı — Çalışma Sürümü

Bu dosya milestone milestone güncellenir; her milestone DoD'sinin bir parçasıdır.
Nihai teslim için PDF'e dönüştürülecek (§5 Teslim Edilecekler, brief). **Kod ile bu
dosya arasındaki her tutarsızlık diskalifiye/ağır puan kaybı riskidir** — bir kısıt
veya değişken burada değişirse, aynı commit içinde ilgili `src/model/*.py` da
güncellenmelidir (ve tersi).

Durum: **M0 tamam** (iskelet — gerçek karar değişkenleri/kısıtlar henüz yok, aşağıda
işaretli). M1 sırada.

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

## 3 · Karar Değişkenleri

*(M1'de doldurulacak — zaman değişkenleri, $x_\pi$, yardımcı reifikasyon
değişkenleri. Bkz. M1 tasarım notu.)*

## 4 · Amaç Fonksiyonu

*(M1'de bağlantı-sayısı ödülü bileşeni, M2'de sıralama ödülü bileşeni eklenecek.)*

## 5 · Kısıtlar

*(A–G, M1–M4 arasında milestone milestone eklenecek.)*

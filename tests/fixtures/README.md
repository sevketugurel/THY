# Sentetik Fixture — Elle Hesap Dokümantasyonu

4 dosya (`synthetic_od_table.xlsx`, `synthetic_yolcu_verisi.xlsx`,
`synthetic_change_ranking_input.xlsx`, `synthetic_flight_pairs.xlsx`) gerçek şemayla
birebir aynıdır ve `build_fixture.py` ile deterministik olarak üretilir (rastgelelik yok —
her değer elle seçildi ve bu dosyada elle doğrulandı). 2 outstation (ZZA, ZZB), 2 gün, IST
hub. **Tüm zamanlar dakika-since-midnight olarak referans alınır** (ör. 840dk = 14:00).

## Tasarım prensibi: iki ayrı test grubu

1. **Pazar/bağlantı testleri** (B, C, D — MI1,MI2,MO1,MO2,NI1,NI2,NO1,NO2): candidate
   generation, boşluk geçerliliği, J_π, slot doldurma, rakip yenme.
2. **Rotasyon-only testleri** (A — RA1,RA2,RB1,RB2): bilerek pazar-geçerli hiçbir
   bağlantı OLUŞTURMAYACAK şekilde zamanlanmış (aşağıdaki "çapraz-ürün doğrulaması"
   bölümünde her kombinasyon elle kontrol edildi), böylece rotasyon testleri pazar
   ödül hesabını bozmaz.

Bu ayrım gerekçesi: aday üretimi TÜM inbound×outbound **cross-product**'ı olduğu için
(plan §4), her yeni uçuş TÜM ilgili pazarlara otomatik dahil olur — rotasyon uçuşlarının
hiçbir pazarda yanlışlıkla geçerli bağlantı oluşturmadığı elle doğrulanmalıydı (aşağıda).

## Ground-truth blok süresi sabitleri (bu fixture için VARSAYILAN veri, LS ile türetilmedi)

Bu değerler model/constraint testlerinde `block_times` sağlayıcısının GERÇEK LS
algoritması yerine doğrudan enjekte edilir (dependency injection) — LS algoritmasının
kendisi ayrı, küçük ve bağlantılı bir grafikle `tests/unit/test_block_times.py`'de
test edilir (bu fixture ile İKİ istasyonlu bir grafik R_o'yu çözmeye yetmez — brief'in
kendi veri yapısı da aynı dejenerasyona sahip, bkz. plan §Context madde 3).

| İstasyon | T_IB_o | T_OB_o | R_o = T_IB+T_OB |
|---|---|---|---|
| ZZA | 120 | 130 | 250 |
| ZZB | 110 | 100 | 210 |

| Pazar (o,d) | K_od = T_IB_o + T_OB_d |
|---|---|
| ZZA→ZZB | 120+100 = **220** |
| ZZB→ZZA | 110+130 = **240** |

Sabitler: L=60, U=300, τ=45, X_dev=15, α=0.20, Γ=30 (Standard senaryo değerleri).

## Uçuş tablosu (Gün=1 baseline)

| Flight | Rol | FlNo | Gün1 | Gün2 |
|---|---|---|---|---|
| MI1 | ZZA→IST inbound | 9101 | arr 840 (14:00) | arr **815** (13:35) — G-testi: fark=25>X_dev, İHLAL |
| MI2 | ZZA→IST inbound | 9102 | arr 600 (10:00) | arr 600 (aynı) |
| MO1 | IST→ZZB outbound | 9111 | dep 480 (08:00) | dep 480 (aynı) |
| MO2 | IST→ZZB outbound | 9112 | dep 900 (15:00) | dep 900 (aynı) |
| NI1 | ZZB→IST inbound | 9201 | arr 795 (13:15) | arr **800** (13:20) — G-testi: fark=5≤X_dev, OK |
| NI2 | ZZB→IST inbound | 9202 | arr 500 (08:20) | arr 500 (aynı) |
| NO1 | IST→ZZA outbound | 9211 | dep 480 (08:00) | dep 480 (aynı) |
| NO2 | IST→ZZA outbound | 9212 | dep 1000 (16:40) | dep 1000 (aynı) |
| RA1 | IST→ZZA outbound (rotasyon-only) | 9311 | dep 200 (03:20) | dep 200 |
| RA2 | ZZA→IST inbound (rotasyon-only) | 9301 | arr 850 (14:10) | arr 850 |
| RB1 | IST→ZZB outbound (rotasyon-only) | 9411 | dep 300 (05:00) | dep 300 |
| RB2 | ZZB→IST inbound (rotasyon-only) | 9401 | arr 555 (09:15) | arr 555 |

`synthetic_od_table.xlsx`'teki geçersiz-boşluklu satırlar (ör. MI1×MO1) sadece uçuşun
**keşfedilebilir** olması için var — `Gate-to-Gate Uçuş Süresi` alanları bu satırlarda
**placeholder** (200dk, anlamsız) çünkü `block_times.get_journey_constant` yalnızca
geçerli-boşluklu satırları K_od medyanına dahil etmelidir (bu davranış
`test_block_times.py`'de ayrıca test edilir).

## Çapraz-ürün doğrulaması (her kombinasyon elle kontrol edildi)

Market ZZA→ZZB inbound havuzu = {MI1, MI2, RA2} (RA2 de ZZA-inbound!), outbound havuzu
= {MO1, MO2, RB1} (RB1 de ZZB-outbound!):

| inbound×outbound | gap | geçerli mi |
|---|---|---|
| MI1(840)×MO1(480) | -360 | ✗ |
| MI1(840)×MO2(900) | **60** | ✓ (sınır=L) |
| MI2(600)×MO1(480) | -120 | ✗ |
| MI2(600)×MO2(900) | **300** | ✓ (sınır=U) |
| RA2(850)×MO1(480) | -370 | ✗ |
| RA2(850)×MO2(900) | 50 | ✗ (<L) |
| MI1(840)×RB1(300) | -540 | ✗ |
| MI2(600)×RB1(300) | -300 | ✗ |
| RA2(850)×RB1(300) | -550 | ✗ |

→ Market ZZA→ZZB Gün1 **tam olarak 2 geçerli bağlantı**: π1=(MI1,MO2) J=220+60=**280**,
π2=(MI2,MO2) J=220+300=**520**.

Market ZZB→ZZA inbound havuzu = {NI1, NI2, RB2}, outbound havuzu = {NO1, NO2, RA1}:

| inbound×outbound | gap | geçerli mi |
|---|---|---|
| NI1(795)×NO1(480) | -315 | ✗ |
| NI1(795)×NO2(1000) | **205** | ✓ |
| NI2(500)×NO1(480) | -20 | ✗ |
| NI2(500)×NO2(1000) | 500 | ✗ (>U) |
| RB2(555)×NO1(480) | -75 | ✗ |
| RB2(555)×NO2(1000) | 445 | ✗ (>U) |
| NI1(795)×RA1(200) | -595 | ✗ |
| NI2(500)×RA1(200) | -300 | ✗ |
| RB2(555)×RA1(200) | -355 | ✗ |

→ Market ZZB→ZZA Gün1 **tam olarak 1 geçerli bağlantı**: π3=(NI1,NO2) J=240+205=**445**.

## Bağlantı-sayısı ödülü (Modül 5, W(c)_j = 2^-(j-1))

- Market ZZA→ZZB: 2 bağlantı sunuluyor → ödül = 1.0 + 0.5 = **1.5**
- Market ZZB→ZZA: 1 bağlantı sunuluyor → ödül = 1.0 = **1.0**

## Rakip yenme ve sıralama ödülü (Kısıt D)

Market ZZA→ZZB rakipleri: R1 (T_comp=300), R2 (T_comp=250).
- π1(J=280)≤300 → **R1 yenildi**. π1,π2 ≤250? Hayır → **R2 yenilmedi**.
- N=2, yenilen=1, r = 2−1 = **1**. b (taban, verilmiş) = 2.
- `W(N=2,b=2,r=1)` = **1.6321205588285577** (gerçek `change_ranking_input.xlsx`'ten
  birebir alınan değer).

Market ZZB→ZZA rakipleri: R3 (T_comp=500), R4 (T_comp=400), R5 (T_comp=445, **sınır**).
- π3(J=445)≤500 → **R3 yenildi**. ≤400? Hayır → **R4 yenilmedi**. ≤445 (sınır, ≤ dahil)
  → **R5 yenildi**.
- N=3, yenilen=2, r = 3−2 = **1**. b (taban) = 1 (sıralama değişmedi).
- `W(N=3,b=1,r=1)` = **0.0** (sentetik, "değişim yok → ödül yok" mantığı).

## Toplam amaç değeri (Gün=1)

ρ_ZZA-ZZB=100, ρ_ZZB-ZZA=50 (`synthetic_yolcu_verisi.xlsx`).

```
obj = 100 × (1.5 + 1.6321205588285577) + 50 × (1.0 + 0.0)
    = 100 × 3.1321205588285577 + 50
    = 313.21205588285577 + 50
    = 363.21205588285577
```

Bileşenler ayrı ayrı: bağlantı-ödülü bileşeni = 100×1.5+50×1.0 = **200.0**; sıralama-ödülü
bileşeni = 100×1.6321205588285577+50×0.0 = **163.21205588285577**.

## Rotasyon (Kısıt A) — `synthetic_flight_pairs.xlsx`

- **ROT-A** (RA1 dep=200, RA2 arr=850): gereken minimum = 200 + R_ZZA(250) + τ(45) = 495.
  Gerçek=850 → **slack=355dk, BAĞLAYICI DEĞİL**.
- **ROT-B** (RB1 dep=300, RB2 arr=555): gereken minimum = 300 + R_ZZB(210) + τ(45) = 555.
  Gerçek=555 → **slack=0, TAM BAĞLAYICI** (eşitlik).
- **İhlal senaryosu**: fixture verisinde YOK — validator testinde ROT-B'nin RB2 varışı
  elle 500'e düşürülerek (500 < 555 gerekli minimum) kasıtlı ihlal oluşturulur ve
  `independent_validator`'ın bunu yakaladığı doğrulanır.

## Test stratejisi notu — solve testleri neden zamanları SABİT tutar

`t_arr`/`t_dep` gerçek modelde **integer karar değişkenidir** (M1 kararı — bkz.
`docs/model.md` §3; VARSAYIM-3'e göre varsayılan pencere ±180dk, ilk planlanan
±720dk değil). M1–M3 solve testleri (henüz E1/E2/F devrede değilken) bu fixture'ı
**`adjustable_set: none`** (tüm TK uçuşları `Rfix`) config'iyle çalıştırır — böylece
yukarıdaki elle hesaplanan değer TEK feasible sonuçtur (x_π, beat, slot, indicator_r
zaten B/D/C reifikasyonlarıyla zamana göre tam belirlenir, optimizasyon serbestliği
yok) ve exact-value assert edilebilir. M4/M5'te (E1/E2 devreye girince) zamanlar
serbest bırakılır; o noktada Gün1 baseline sayıları (2 vs 1 bağlantı) E1'i (α=0.20)
**ihlal eder** (|2-1|=1 > 0.20×3=0.6) — bu KASITLI: gerçek modelde solver zamanları
kaydırarak dengeyi sağlamalıdır. M4/M5 testleri bu yüzden exact-value değil,
**feasibility + bilinen bir alt sınır** assert eder.

## M1 eki — CLI kabul testi (adjustable_set: all, insan doğrulaması BEKLİYOR)

`tests/solve/test_main_cli.py`, config'in gerçek varsayılanıyla (`adjustable_set:
all`, pencere=180dk) çalıştırıldığında objective=**568.75** buluyor (elle
optimize edilmiş bir değer DEĞİL — solver'ın bulduğu, bağımsız validator'dan
sıfır-ihlalle geçen bir sonuç). Bu sayı **insan doğrulaması bekliyor**: RB2×NO2 gibi
ham veride hiç birlikte listelenmemiş ama achievable-range'i [L,U] ile kesişen
sentezlenmiş adaylar da devrede (bkz. `docs/decisions.md` 2026-07-09,
"Independent validator'ın bağlantı-varlık kontrolü"), bu yüzden tam kombinasyon
elle çıkarılmadı. Test bu değeri **alt sınır olarak KULLANMIYOR** (>=400.0
assert ediyor, tam değeri değil) — 568.75'in kendisi doğrulanana kadar sadece
gözlemlenen/loglanan bir referans noktasıdır.

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

**Rakip tanımı düzeltmesi (M2, `docs/decisions.md` 2026-07-09)**: bir "rakip"
TEK BİR TAŞIYICI (Cr1), o taşıyıcının o (o,d,gün)'deki TÜM itineraryleri o
rakibin PARÇASI (min T_comp'a konsolide edilir), ayrı rakipler değil. Rival
satırları artık DİSTİNCT carrier kodlarıyla (`R1..R5`), R4 ayrıca İKİNCİ (daha
kötü) bir itinerary ile konsolidasyonu test ediyor (bkz.
`tests/unit/test_competitors.py`).

**b_od düzeltmesi**: b_od artık `src/data/ranking.py::derive_b_od` ile
TÜRETİLİYOR (M0'da elle seçilmiş b_od=2 değeri YANLIŞTI — sadece belirli bir
lookup satırını test etmek için hardcode edilmişti, gerçek formülle
tutarsızdı). Doğru formül: b_od = N − (TK'nin BASELINE en iyi itinerary'sinin
D'nin AYNI ≤ kuralıyla yendiği rakip sayısı) — r'nin kendisinin, optimizasyon
ÖNCESİ zamana uygulanmış hali, ayrı bir kural değil.

Market ZZA→ZZB rakipleri: R1 (T_comp=300), R2 (T_comp=250).
- Baseline en iyi = π1 (J=280). 280≤300 → **R1 baseline'da yenildi**. 280≤250? Hayır.
- b_od = N(2) − beaten_baseline(1) = **1** (M0'ın hardcode edilmiş 2 değeri değil).
- π1(J=280)≤300 → **R1 yenildi**. π1,π2 ≤250? Hayır → **R2 yenilmedi**.
- N=2, yenilen=1, r = 2−1 = **1**.
- `W(N=2,b=1,r=1)` = **1.0** (gerçek `change_ranking_input.xlsx`'ten birebir).

Market ZZB→ZZA rakipleri: R3 (T_comp=500), R4 (T_comp=400, 2 itinerary min),
R5 (T_comp=445, **sınır**).
- Baseline en iyi = π3 (J=445). 445≤500 → **R3 baseline'da yenildi**. ≤400? Hayır.
  ≤445 (sınır, ≤ dahil) → **R5 baseline'da yenildi**.
- b_od = N(3) − beaten_baseline(2) = **1**.
- π3(J=445)≤500 → **R3 yenildi**. ≤400? Hayır → **R4 yenilmedi**. ≤445 → **R5 yenildi**.
- N=3, yenilen=2, r = 3−2 = **1**.
- `W(N=3,b=1,r=1)` = **0.0** (sentetik, "değişim yok → ödül yok" mantığı).

## Toplam amaç değeri (Gün=1)

ρ_ZZA-ZZB=100, ρ_ZZB-ZZA=50 (`synthetic_yolcu_verisi.xlsx`).

```
obj = 100 × (1.5 + 1.0) + 50 × (1.0 + 0.0)
    = 100 × 2.5 + 50
    = 250.0 + 50
    = 300.0
```

Bileşenler ayrı ayrı: bağlantı-ödülü bileşeni = 100×1.5+50×1.0 = **200.0**; sıralama-ödülü
bileşeni = 100×1.0+50×0.0 = **100.0**.

**Not**: bu değer (300.0), `adjustable_set:none` (Rfix) senaryosunda hem B/C
hem D bileşenlerinin BİRLİKTE doğru bağlandığını kanıtlayan M2'nin birincil
solve-testinin beklenen değeridir (Rfix'te r=b_od her zaman, çünkü zaman
serbestliği yok — bkz. aşağıdaki "Test stratejisi" notu).

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

## M2 eki — D kısıtı, rank clamp düzeltmesi, under-claim toleransı

**Düzeltilmiş hand-calc** (`adjustable_set:none`, D dahil): bkz. yukarıdaki
"Rakip yenme ve sıralama ödülü" bölümü — Gün1 connection_reward=200.0,
ranking_reward=100.0. Gün1+Gün2 birlikte (M1'in 2-günlük yapısı korunuyor):
connection_reward=**400.0** (200×2), ranking_reward=**100.0** (rakip verisi
yalnızca Gün1'de var, Gün2 pazarları N=0 → katkı yok), **toplam=500.0**
(`tests/solve/test_m2_ranking_reward.py::test_fixture_objective_matches_corrected_hand_calc`
ile assert edildi).

**Kritik bulgu — rank clamp infeasibility tuzağı** (CLI end-to-end testiyle
yakalandı, `docs/decisions.md` 2026-07-09): r=N-beaten formülü [0,N] üretebilir
ama gerçek `change_ranking_input.xlsx`'te r asla 0 değil (min=1, doğrulandı).
İlk tasarımda rank-onehot linking'i EŞİTLİK (`sum(r·onehot_r)==rank`) olarak
kurulmuştu — bu, solver'ın beaten=N'e ulaşmasını YAPISAL OLARAK imkansız
kılıyordu (r=0'ın onehot karşılığı yok), yani solver en az bir rakibi BEDAVA
OLSA bile kasıtlı yenilmemiş bırakmak ZORUNDA kalıyordu. Düzeltme: linking
EŞİTSİZLİK yapıldı (`>=`), r'nin kendi domain'i [1,N] + W'nin monotonluğu
otomatik olarak r=max(1,N-beaten)'e oturuyor (C'nin slot argümanıyla aynı
mantık — max()/min() lineerleştirmesi gerekmedi).

**Under-claim toleransı** (kasıtlı tasarım kararı, validator'da dokümante):
forward-only D forcing (monotonik W varsayımı altında) claimed_beaten'i
HER ZAMAN actual_beaten'in bir ALT KÜMESİ yapar (over-claim yapısal olarak
imkansız) — bu yüzden under-claim (gerçekte yenilen ama raporlanmayan bir
rakip) hiçbir zaman ödülü ŞİŞİRMEZ, sadece bilgi eksikliğidir, diskalifiye
sebebi DEĞİLDİR. Validator bunu flag ETMEZ (bkz. `test_validate_allows_under_claimed_beaten_rivals`,
ZZB-ZZA pazarında NI1×NO2'nin serbest zamanlarla J=360 elde edip R3,R4,R5'in
ÜÇÜNÜ de yenebildiği ama sadece R3,R5'in claim edildiği elle-doğrulanmış bir
senaryo).

## M3 eki — gün-içi normalizasyon (KRİTİK, ilk solve denemesinde infeasibility olarak yakalandı)

A ve G kısıtları eklendiğinde ilk solve denemesi **infeasible** verdi.
Kaynak: `t_arr`/`t_dep` TEK bir GLOBAL `epoch_anchor`'a göre kurulu (tüm veri
kümesinin en erken tarihinin gece yarısı) — MI1'in Gün1 değeri (840, 14:00)
ile Gün2 değeri HAM epoch cinsinden **2255** (1440+815, çünkü Gün2 AYRI bir
takvim günü), 815 DEĞİL. G'nin `max(t)-min(t)<=X_dev` kontrolünü bu HAM
değerlere uygulamak, saat-of-day TAM uyumlu bir tarifeyi bile ~1440dk'lık
sahte bir ihlal olarak görüyordu — asla X_dev(15) ile uzlaştırılamaz,
model HER ZAMAN infeasible çıkıyordu.

**Tespit yöntemi** (izole etme): B+C alone → optimal. A alone → optimal.
B+C+A → **infeasible** (ayrı bir bug: `tests/solve/test_m3_constraints_a.py`'nin
test yardımcısındaki yanlış `gap_lo`/`gap_hi` hint'i, üretim kodunda değil —
bkz. `docs/decisions.md`). B+C+G → **infeasible** (gün-içi normalizasyon
eksikliği, gerçek üretim-kodu bug'ı). Düzeltme: `constraints_operations.py::_day_offsets`
her (role,flno,gun)'u KENDİ takvim gününün gece yarısına göre normalize
ediyor önce; `independent_validator.py`'nin x_dev kontrolü de AYNI
normalizasyonu tekrarlıyor (aksi halde GEÇERLİ bir çözüm bile validator
tarafından yanlışlıkla reddedilirdi — bu ikinci, sessiz bug hiçbir solve
hatası vermezdi, sadece validator'ı sürekli yanlış-pozitif üretir hale
getirirdi).

**CLI sonucu** (M3 dahil, `adjustable_set: all`): objective=**668.75**
(M2'yle AYNI — A/G kısıtları bu fixture için mevcut optimumu BOZMADI,
solver'ın zaten seçtiği tarife A/G'yi de sağlıyormuş).

## Doğrulama borcu eki — 668.75 ARTIK BAĞIMSIZ DOĞRULANDI (elle değil, kod ile)

`src/validate/independent_validator.py::recompute_objective` — CLI çıktısını
`src.model`/`src.candidates`'a hiç dokunmadan, ham veriden yeniden hesaplayan
bir fonksiyon — **668.75'i birebir doğruladı** (18 bağlantı: 4+4+5+5,
connection_reward=568.75, ranking_reward=100.0 — sadece ZZA-ZZB Gün1 katkı
veriyor, ZZB-ZZA Gün1 rank=1'e ulaşsa da b_od zaten 1 olduğundan ödül 0).
Bu, M1'den beri "insan doğrulaması bekliyor" etiketli 668.75 için **yeterli
bağımsız kanıt** sayılabilir — artık elle çarpı-yaz doğrulaması gerekmiyor.

Ayrıca `tests/slow/test_bruteforce_oracle.py`: B+C+D reifikasyonlarının
doğruluğunu, Pyomo'ya hiç dokunmayan saf-Python 10-dk grid brute-force ile
CAPRAZ doğruluyor (küçük, izole bir senaryo — ZZQ-IST tek pazar, tek aday,
2 rakip). Solver'a "t mod 10==0" ek kısıtıyla brute-force'la TAM eşleşme,
kısıtsız solver'la ≥ ilişkisi — ikisi de PASSED.

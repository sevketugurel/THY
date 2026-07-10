# Statik Fizibilite Sertifikaları (E1/E2) — 2026-07-10

`scripts/feasibility_certificates.py` — saf pandas/Python, MIP YOK, HiGHS YOK.
Beş bağımsız solve denemesinin hepsinin "hızlı yakınsa, sonra tam sessizlik,
sıfır incumbent" göstermesi üzerine kullanıcının redirect'i: kapanmadan önce
E1/E2'nin GERÇEKTEN provably infeasible olup olmadığını (solver sorunu değil,
formülasyon sorunu) kesin biçimde ELE.

## Forced-aday tanımı (B'nin bidirectional reifikasyonundan)

B'nin backward reifikasyonu ("gap∈[L,U] ⟹ x=1") ve forward reifikasyonu
("x=1 ⟹ gap∈[L,U]") birlikte üç durum üretir:

- **forced_on**: `gap_lo>=L VE gap_hi<=U` — gap HANGİ ayarlanabilir seçim
  yapılırsa yapılsın her zaman [L,U] içinde kalıyor → x KOŞULSUZ 1'e
  zorlanıyor. **ÖNEMLİ**: bu, `add_b_constraints`'in kendi `.fix()`
  mantığından (yalnızca `gap_lo==gap_hi` tekil-nokta durumunda ateşleniyor)
  DAHA GENİŞ bir küme — gerçekten ayarlanabilir ama TÜM penceresi [L,U]
  içinde kalan bir aday, model içinde serbest bir binary olarak kalıyor
  ama HER feasible çözümde 1'e sabitleniyor (solver'ın kendisi bunu
  reifikasyon yoluyla zorluyor, `.fix()` ile DEĞİL).
- **forced_off**: `gap_hi<L VEYA gap_lo>U` — gap hiçbir seçimde [L,U]'ya
  giremiyor → x KOŞULSUZ 0'a zorlanıyor.
- **undetermined**: pencere bir sınırı aşıyor — x'in değeri gerçek bir
  seçime bağlı, gerçekten serbest.

## Üç sertifika (her biri güvenli/gevşek dış-sınırla NECESSARY-condition testi)

1. **E1a**: `F→>=1` (ileri yönde en az bir forced-on aday var) VE `K←=0`
   (geri yönde HİÇ ham aday yok). Kod taraması ile çapraz kontrol edildi:
   `add_e1_constraints`'in `pairs` listesi yalnızca HER İKİ yönün de
   `groups`'ta (en az 1 ham aday) var olduğu çiftleri kuruyor — `K←=0`
   demek E1 o çift için HİÇ KURULMUYOR demek, yani bu senaryo mevcut
   implementasyon altında gerçek bir infeasibility ÜRETEMEZ.
2. **E1b**: E1'in GERÇEKTEN kurulduğu çiftlerde (her iki yönde de ≥1 ham
   aday), `[F→,K→]×[F←,K←]` kutusunda `|n→−n←|<=α(n→+n←)`'yi sağlayan
   HERHANGİ bir (n→,n←) çifti var mı? `K` (ham aday sayısı, forced-off'u
   DAHİ dahil eden gevşek üst sınır) kullanılıyor — bu, gerçek ulaşılabilir
   aralığın bir ÜST kümesi, yani kutu içinde HİÇ çözüm yoksa gerçek aralıkta
   da YOKTUR (ses geçirmez kanıt).
3. **E2**: her iki yönde de ≥1 forced-on aday olan çiftlerde, $J_{best}$ dış-
   sınır aralıkları ($[\min_{tüm} J_{lo}, \min_{forced} J_{hi}]$) fwd/bwd
   arasında en-iyi-durumda bile Γ'dan büyük bir boşluk bırakıyor mu?

## Sonuç: ÜÇÜ DE TEMİZ (2026-07-10 full-data koşusu)

```
n_candidates=18118, n_market_direction_groups=7642, n_market_pairs=4384
e1_code_scan: would_be_built=3258, not_built_no_reverse=1126
  (3258 doğrulaması: lp_anatomy.md'nin "e1_fwd: 3258, e1_bwd: 3258" satır
  sayısıyla BİREBİR eşleşiyor — bağımsız çapraz doğrulama)
cert_e1a_forced_on_vs_zero_reverse: count=0
cert_e1b_no_satisfying_pair_in_box: count=0
cert_e2_disjoint_jbest_ranges: count=0
```

**E1 ve E2, bu statik/gevşek analiz altında PROVABLY infeasible DEĞİL.**
Beş solve denemesinin ortak semptomu (hızlı yakınsa, sonra tam sessizlik,
sıfır incumbent) E1/E2'nin KENDİSİNDEN kaynaklanan basit bir yapısal
imkânsızlık DEĞİL — ya (a) gerçekten çok zor ama feasible bir kombinatoryal
problem, ya (b) A/F/G'den veya çok-kısıtlı ETKİLEŞİMDEN kaynaklanan (bu
sertifikaların kapsamadığı) bir infeasibility, ya da (c) HiGHS'in bu
problem sınıfındaki kesme-düzlemi davranışının kendine özgü bir sınırı.

**Not**: mevcut exempt+log mekanizması (`_is_fully_frozen`, `model.x[i].fixed`
kontrolü) bu daha GENİŞ forced-on kümesini GÖRMÜYOR — yalnızca `gap_lo==
gap_hi` tekil-nokta donmalarını yakalıyor. Bu sertifikalar TEMİZ çıktığı için
şu an pratik bir sonucu yok, ama gelecekte forced-on/forced-off kümesi
büyürse (ör. `adjustable_window_min` küçülürse) bu kör nokta gerçek bir
infeasibility'yi exempt+log'a YAKALATMADAN solver'a göndermeye devam eder —
ayrı bir iyileştirme fırsatı olarak not edildi (bu turda KOD DEĞİŞTİRİLMEDİ,
yalnızca analiz).

## Sıradaki adım (kullanıcı onaylı dallanma, branch 2)

Sertifikalar temiz olduğu için kullanıcının talimatı gereği "kurucu tanık"
denemesine geçildi: saf Python greedy repair (MIP yok), baseline'dan
başlayıp bağımsız validator'ı oracle olarak kullanarak ihlalleri onarmayı
dener (A için varışı geciktir, F için komşu kovaya kaydır, E1/E2 için
öldürülebilir bağlantıları pencere kenarına iterek kapat). Bkz.
`scripts/greedy_feasibility_witness.py` + `docs/decisions.md`.

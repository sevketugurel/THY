# KAPANIŞ PLANI — kapı/bütçe mantığıyla (2026-07-11)

Sabit kısıtlar (bu plan DEĞİŞTİREMEZ): teslim 16 Temmuz 2026 17:00;
Python+Pyomo; bağımsız doğrulama zincirinden (validator sıfır ihlal +
recompute == raporlanan) geçmeyen hiçbir sayı "sonuç" ilan edilmez;
ihlalli çözüm teslim edilmez; yarışma verisi repo'ya girmez; determinizm
iddiaları dürüst kalır; organizatör cevabı gelirse config-düzeyinde
entegrasyon.

Zaman çerçevesi (takvim değil kapı — ama iki sabit çivi):
**SOLVER DONDURMA = 2026-07-14 18:00** (o andan sonra hiçbir yeni solve
denemesi; eldeki en iyi doğrulanmış durumla Kapı-5/6'ya geçilir) ve
**PAKET HAZIR = 2026-07-16 12:00** (17:00 teslimden 5 saat tampon).

---

## KARAR-0 · E1 birincil formülasyonu: KOŞULLU AKTİVASYON (soru 1'in cevabı)

**Karar**: E1 artık yalnızca HER İKİ yön de AKTİFKEN (her yönde ≥1 sunulan
bağlantı) bağlayıcı. Literal (koşulsuz) okuma config bayrağıyla
(`e1_activation: conditional | unconditional`, varsayılan `conditional`)
DUYARLILIK ANALİZİ olarak korunur — rapor iki modun sayılarını yan yana verir.

**Brief-içi kanıt**: (a) Brief §7 modelleme ipucu: *"Koşullu (yalnızca her
iki yön aktifken bağlayıcı) kısıtları doğru kurun; aksi halde pasif yönler
dengeyi yapay olarak ihlal/zorlar"* — "denge" E-ailesinin kendi adı (§4.5
"Yönsel Denge"), tarif edilen patoloji birebir E1'in tek-yön-sıfır vakası.
(b) E1 metnindeki "iki yön de boşsa kendiliğinden sağlanır" cümlesi 0/0
belirsizliğini çözen bir dipnot olarak okunur; tek-yön-boş vakası metinde
AÇIKÇA ele alınmamış — ipucu §7 bu boşluğu dolduruyor. (c) Mevcut kodun
kendi sınır seçimi zaten yarı-koşullu (yapısal adayı olmayan yön çifti hiç
kurulmuyor, VARSAYIM-6 "yapay kısıtlama olurdu" gerekçesiyle) — aynı
gerekçe "yapısal aday var ama sunulan sıfır" durumuna da uzanır.

**Ampirik kanıt**: organizatörün KENDİ baseline'ı literal okumada 690
pair-gün ihlalli (v1=v2); ulaşılan HER noktada E1 fazlalık oranı
medyan=p90=max=0.800=1−α (ihlallerin ~tamamı tek-yön-sıfır vakası);
literal E1 belgeli "amaç bastırıcı" (VARSAYIM-6) — yarışmanın ilan edilmiş
amacıyla (cazip bağlantı sayısını ARTIRMAK) çelişen davranış üretiyor.
VARSAYIM-9/10/11'de kullanıcı onayıyla yerleşen ilkeyle aynı desen
("organizatör çözümsüz/kendi-verisiyle-çelişen problem tasarlamaz").

**Dürüst karşı-kanıt (raporda da yer alacak)**: E2 metni koşullu
aktivasyonu AÇIKÇA söylüyor, E1 metni söylemiyor — literal okuma metinsel
olarak savunulabilir ve her zaman tatmin edilebilir (pazarı tamamen
sıfırlayarak). Bu yüzden literal mod SİLİNMİYOR, bayrakla yaşıyor;
organizatöre soru (aşağıda) gidiyor.

**Uygulama**: E2'nin mevcut `a_dir` göstergeleri yeniden kullanılır:
`n_fwd−n_bwd ≤ α(n_fwd+n_bwd) + M(2−a_fwd−a_bwd)` (+ simetriği),
`M = (1−α)·max(|Π_fwd|,|Π_bwd|)` (veri-türetilmiş, küçük, ≤1440 doğal).
Elastik E1 slack'i de aynı kapıyla koşullanır.

**Hizalama listesi (validator/sertifikalar — soru 1'in son parçası)**:
1. `independent_validator.py` E1 kontrolü aynı bayrağı alır — koşullu
   modda yalnızca her iki yönde ≥1 SEÇİLİ bağlantı olan çiftler denetlenir
   (not: M5b'nin "kapsam düzeltmesi" literal moda göre yazılmıştı; koşullu
   modda ESKİ kapsam doğru kapsamdır — bu tarihçe raporda dürüstçe anlatılır).
2. `scripts/feasibility_certificates.py` E1a/E1b koşullu modda anlamını
   yitirir (tek-yön-sıfır artık meşru) — script bayrağı okuyup sertifika
   tanımını günceller, iki modda da koşar.
3. `scripts/baseline_feasibility_witness.py` / `analyze_violation_footprint.py`
   aynı bayrak; STATUS'a iki modlu tablo.
4. `ASSUMPTIONS.md`'ye VARSAYIM-16 (bu karar, kanıtlarıyla);
   `organizer_questions.md` #6 güncellenir (yanlış dosya yolu da düzelir).

## KARAR-0b · E2 statik-imkânsız çift muafiyeti (VARSAYIM-17)

`compute_gamma_infeasible_pairs`'ın STATİK kanıtladığı (journey-constant
asimetrisi en-iyi-durum gap seçiminde bile Γ'yı aşan) 63 çift (v2),
A/G'deki VARSAYIM-9/11 ilkesinin birebir uzantısıyla E2'den MUAF tutulur
(exempt+log, sessiz değil). Validator aynı statik testi bağımsız yeniden
uygular. Bu, "gerçekten düzeltilemez" ile "henüz bulunamadı"yı yapısal
olarak ayırır; Γ ölçeği sorusu (#12b) organizatörde kalır.

---

## Kapılar

### Kapı-0 · Hijyen + yeniden-doğrulama (solver YOK; ~1-2 saat iş)
Amaç: denetimin P0/P1 bulgularını kapatmak, mevcut sayıları yeniden teyit.
İşler: kök `conftest.py` (çıplak `pytest` düzelir) + README komut teyidi;
`requirements.txt` kesin pin (`pip freeze` tabanlı); fixture CLI yeniden
koş (668.75/valid=True teyidi); TAM suite koş ve sayıyı kaydet; model.md
durum satırı + organizer_questions #6 yolu düzelt; organizatör docx'ini
`data_raw/_organizer_source_package/`'a taşı (`git rm --cached`);
`warm_start_elastic.py` Adım-A bütçesini CLI'ya çıkar; `main.py`'ye
provenance loglama.
**DoD**: çıplak `pytest` VE `python -m pytest` yeşil (tam suite);
fixture 668.75 teyitli; commit.

### Kapı-1 · KARAR-0/0b implementasyonu (TDD; solver yalnızca fixture ölçeğinde)
İşler: koşullu E1 (model+elastik+validator+sertifika+witness, bayraklı);
E2 statik muafiyet (model+validator); fixture değeri koşullu modda
DEĞİŞEBİLİR → brute-force oracle YENİDEN koşulur ve yeni sertifikalı değer
türetilir (iki modun değeri de belgelenir); docs/model.md + ASSUMPTIONS.md
aynı commit'te.
**DoD**: tam suite yeşil (iki modda E1 testleri: bağlayıcı /
bağlayıcı-değil / kasıtlı-ihlal-yakalanıyor); oracle==CLI==recompute;
commit + tag `m5f-e1-conditional`.

### Kapı-2 · Yeniden ölçüm (MIP YOK; ~30 dk)
Witness + sertifikalar + footprint, koşullu modda. Beklenti: baseline E1
ihlal kütlesi ~tamamen düşer (690→her-iki-yön-aktif dengesizler, ~0-50);
E2 1222−63 muaf ≈ 1159; A/F/G değişmez (106/31/53).
**Karar kuralı**: E1 kütlesi beklendiği gibi çökerse Kapı-3'e; ÇÖKMEZSE
(koşullu modda >100 E1 ihlali kalırsa) bu YENİ bilgidir — yine Kapı-3'e
gidilir ama plato beklentisi ona göre raporlanır. Her iki durumda STATUS'a
tablo.

### Kapı-3 · Kampanya: ilk doğrulanmış full-data değeri (SOLVER BÜTÇESİ ≤3.5 saat)
Sıra (hepsi dış bekçili, `--max-improving-sols 1` temiz-dur hilesi açık):
- a) Elastik+warm-start, koşullu modda: 900s bütçe, en fazla 2 deneme.
- b) LNS component/fold: plato kuralı 20 iter, duvar ≤45 dk.
- c) (yalnızca b platoda kalır VE kalan Σslack yalnızca E2-dakikası ise)
  ÇOKLU-BİLEŞEN LNS: 2-3 bileşeni AYNI ANDA serbest bırak (M5d'nin
  "yerel düzeltme alanı boş" bulgusunun tek bilinen panzehiri), 600s/iter,
  duvar ≤45 dk, TEK deneme hakkı.
**Başarı yolu**: Σslack≈0 → strict nokta türet → validator SIFIR ihlal →
`recompute_objective` == raporlanan → `finalize_reported_objective` →
**İLK DOĞRULANMIŞ DEĞER** → commit + tag `m5f-first-verified` → Kapı-4.
**Durma kuralları**: (i) toplam bütçe dolunca; (ii) a'nın 2 denemesi de
incumbent'sız kalırsa mevcut v2 seed'iyle b'ye geç; (iii) c de platoda
kalırsa DUR → Branch B kesinleşir, kalan Σslack dökümü rapora girer.
Açık uçlu deney YOK — bu üç adım dışında hiçbir solve koşulmaz.

### Kapı-4 · Ödül tırmanışı (YALNIZCA Kapı-3 doğrulanmış değer verdiyse; ≤2.5 saat)
Feasible noktayı MIP-start vererek `build_model_m4` (koşullu E1) reward
amacıyla: 2×1800s bekçili deneme; ayrıca reward-LNS (bileşen serbest,
kısıtlar sert, reward maksimize) ≤1 saat. HER incumbent doğrulama
zincirinden geçer; yalnızca GEÇEN en iyi değer raporlanır (geçmeyen
incumbent = sadece log). **Dondurma**: 14 Temmuz 18:00'de ne varsa o.

### Kapı-5 · Üretim giriş noktası + gizli test dayanıklılığı (soru 4'ün cevabı)
`main.py --full-data` TEK KOMUTLA şu merdiveni koşar (config'ten bütçeli):
(1) tam model bütçeli solve → incumbent doğrulanırsa yaz;
(2) değilse elastik+LNS yolu → Σslack=0 noktası doğrulanırsa yaz;
(3) hiçbiri olmazsa GEÇERLİ-OLMAYAN tarife YAZMAZ — şema-uyumlu bir
"teşhis çıktısı" yazar (`objective_value: null`,
`solver_metrics.status: no_feasible_solution_found`, ihlalli tarife YOK)
ve sıfır-olmayan exit code döner.
Şema dayanıklılığı: loader'lar şema-doğrulamalı ve anlamlı hatayla düşer;
v1/v2 şema otomatik algılanıyor (Elapsed kolon varlığı); ölçek büyürse
bütçeler config'ten. Golden test + temiz-klon smoke testi.
**DoD**: fixture'da merdiven (1)'den, full-data'da en az (2)/(3)'ten
deterministik biçimde geçer; README tek komutu belgeler.

### Kapı-6 · Teslimat üretimi (soru 5'in cevabı — üretim adımı + kalite kapısı)
| Teslimat | Üretim adımı | Kalite kapısı |
|---|---|---|
| Model PDF | model.md güncelle → pandoc (yoksa Chrome print-to-PDF) | Kod↔doküman denetim tablosu (aşağıda) SIFIR sapma |
| Çalışan kod | Kapı-0/5 çıktısı | Temiz venv'de tek komut smoke + tam suite yeşil |
| Çıktı dosyası | Branch A: doğrulanmış nokta; Branch B: teşhis çıktısı + fixture çıktısı örnek olarak | Validator sıfır ihlal ŞARTI (Branch A) / ihlalli tarife içermeme ŞARTI (Branch B) |
| Teknik rapor ≤6 sf | report_outline.md'den yaz; iki dallı sonuç bölümü | Rubrik haritası tam; her sayı runs/ artefaktına referanslı |
| README | pin'li kurulum + tek komut + determinizm ifadesi | Temiz-klon prova |
Son adım: final commit + tag `v1.0-submission` + zip; teslim
kullanıcıda.

**Kod↔model-dokümanı denetim yöntemi (soru 6'nın cevabı)**: A,B,C,D,E1,
E2,F,G + amaç fonksiyonu için 9 satırlık izlenebilirlik tablosu —
model.md formülü ↔ `src/model/constraints_*.py` fonksiyonu ↔ validator
kontrolü ↔ test dosyası; her hücre commit'te elle işaretlenir, sapma =
teslim engeli. Tablo rapora ek olarak da girer (Kriter 1 kanıtı).

---

## İki dallı son (soru 2'nin cevabı)

**Branch A — doğrulanmış değer VAR**: çıktı dosyası doğrulanmış noktadan;
rapor "objective=X (bağımsız recompute ile birebir), validator sıfır
ihlal" ile açılır; duyarlılık bölümü literal-E1 modunun sayılarını verir;
Kapı-4 iyileştirmesi varsa o değer. Hikâye: "zor bir instance'ta kanıtlı
feasible + iki bağımsız doğrulama katmanı".

**Branch B — doğrulanmış değer YOK**: teslim edilen çıktı ASLA ihlalli
tarife içermez — Kapı-5(3) teşhis çıktısı + fixture'ın tam-doğrulanmış
örnek çıktısı (pipeline'ın doğruluğunun kanıtı). Rapor hikâyesi: fixture
zincirinin tam doğruluğu + full-data'da 8-satırlık deneme tablosu
(report_outline'daki) + baseline'ın kendisinin literal okumalarda ihlalli
olduğu kanıtı + koşullu-E1 kararı ve kalan Σslack dökümü + organizatör
soruları. "İhlalli çıktı teslim edilmez" kuralıyla çelişki YOK çünkü
ihlalli hiçbir tarife pakete girmiyor; Kriter 2 kaybı açıkça kabul edilir
(dürüstlük > şişirme).

## Kalan solver çalışması özeti (soru 3'ün cevabı)
Kapı-3a/b/c + Kapı-4 = TOPLAM ≤6 saat duvar-saati, her deneyin gerekçesi
ve beklenen bilgi kazancı yukarıda; dondurma 14 Temmuz 18:00; bu listenin
dışında deney yok (Gurobi yok — lisans kanıtlanmış şekilde yetersiz).

## Çıktı formatı kararı (soru 7'nin cevabı)
Resmî şema yok → `docs/output_format.md`'deki JSON şeması (brief madde
7'nin 4 gereksinimine birebir eşlenmiş, determinizm testli) NİHAİ karar;
organizatöre soruldu (cevapsız); cevap gelirse yalnızca `writer.py` +
eşleme tablosu değişir (tek nokta). Rapor bu kararı 2 cümleyle belgeler.

## Risk kaydı (soru 8'in cevabı — en olası 5 başarısızlık modu + önlem)
1. **Kapı-3 platoda kalır (Branch B)** → önlem: Branch B paketi baştan
   tam tanımlı (yukarıda); dondurma tarihi teslim kalitesini korur.
2. **Koşullu E1 organizatör niyetiyle çelişir** → önlem: bayraklı çift
   mod + duyarlılık tablosu + organizatör sorusu; cevap gelirse config
   değişikliğiyle yeniden koşu (Kapı-5 merdiveni otomatik).
3. **Gizli test şema/ölçek sürprizi** → önlem: şema-doğrulamalı loader +
   v1/v2 otomatik algı + bütçeli merdiven + teşhis çıktısı garantisi;
   temiz-klon smoke.
4. **HiGHS zaman-limit güvenilmezliği / incumbent kaybı** → önlem: dış
   bekçi + `mip_max_improving_sols=1` temiz-dur (ikisi de kanıtlı çalışıyor).
5. **Model↔kod/dok. sapması veya ihlalli dosyanın yanlışlıkla paketlenmesi**
   → önlem: Kapı-6 izlenebilirlik tablosu + paket adımında validator'ı
   ZORUNLU çalıştıran tek script (`scripts/package_submission.py`).
Ek: rapor/PDF zaman aşımı → 15 Temmuz tamamen dokümana ayrılmış;
determinizm iddiası → yalnızca output_format.md'deki dürüst ifade.

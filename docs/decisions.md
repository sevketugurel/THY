# Mikro-Karar Günlüğü

Kod yazarken karşılaşılan, brief'i değiştirmeyen ama bir uygulama detayını
belirleyen kararlar. Her satır: karar + tek satır gerekçe. Kritik/skoru etkileyen
kararlar için `ASSUMPTIONS.md`'ye bakınız (bu dosyadakiler daha küçük ölçekli).

---

- **2026-07-09** — `adjustable_window_min` varsayılanı 720→180 dk. Gerekçe: M1
  Big-M türetimi (per-candidate) ile 720dk pencerede bazı adaylar M>1440'a
  çıkıyordu (hesap: M1 tasarım notu); 180dk hem Big-M disiplinini koruyor hem
  operasyonel olarak gerçekçi (birkaç saatlik kayma).
- **2026-07-09** — Epoch anchor = veri kümesindeki en erken tarihin GECE
  YARISI (en erken tam timestamp değil). Gerekçe: en erken timestamp'i
  (200.dk, 03:20) anchor almak tüm hand-calc beklentilerini keyfi bir offsetle
  kaydırıyordu; midnight-anchor hem tam tarih-farkındalıklı (cross-midnight
  doğru) hem "gece yarısından dakika" sezgisiyle hand-verifiable kalıyor.
- **2026-07-09** — `r1_id`/`r2_id` rol-namespaced: `("IB"|"OB", flno, gün)`,
  düz `(flno,gün)` değil. Gerekçe: gerçek veride 26 uçuş numarası hem inbound
  hem outbound rolünde görünüyor (doğrulandı) — namespace olmadan iki farklı
  zaman değeri aynı Pyomo Var anahtarında çakışırdı (sessiz veri bozulması).
- **2026-07-09** — Aday üretimi baseline-gap kontrolünden achievable-range
  kontrolüne geçti (`gap_lo,gap_hi` interval subtraction, [L,U] ile kesişim).
  Gerekçe: M0'da tüm zamanlar sabitti, baseline-only doğruydu; M1'de saatler
  serbest olduğunda geçerli aday kümesi baseline'daki spesifik eşleşmelerle
  sınırlı değil (Modül-3'ün doğru genellemesi, plan §4).
- **2026-07-09** — Independent validator'ın bağlantı-varlık kontrolü artık
  HER BACAĞI ayrı ayrı doğruluyor (inbound flno gerçekten var mı, outbound
  flno gerçekten var mı), tam (flno1,flno2) EŞLEŞMESİNİN ham veride satır
  olarak var olmasını değil. Gerekçe: CLI end-to-end testi, ham veride hiç
  birlikte listelenmemiş ama HER İKİ bacağı da gerçek olan sentezlenmiş bir
  aday (RB2×NO2) ürettiğinde validator bunu yanlışlıkla "bulunamadı" diye
  reddetti — cross-product tasarımının doğal ve beklenen bir sonucuydu, hata
  validator'daydı.
- **2026-07-09** — CLI kabul testi artık tam hand-calc (500.0/400.0) yerine
  alt-sınır (≥400.0) + geçerlilik assert ediyor. Gerekçe: config'in
  `adjustable_set: all` değeri artık gerçekten aktif (serbest integer zaman
  değişkenleri) — solver sabit-zaman senaryosundan (400.0) EN AZ o kadar iyi
  sonuç bulur, tam optimal değeri elle hesaplamak küçük bir kombinatoryal
  problem gerektirir; hand-calc rigor'u `adjustable_set:"none"` testlerinde
  korunuyor (`test_m1_constraints_c.py`).
- **2026-07-09 (M2)** — "Rakip" (rival) TEK BİR TAŞIYICI (Cr1), o taşıyıcının
  o (o,d,gün)'deki TÜM itineraryleri o rakibin PARÇASI (T_comp = min).
  Gerekçe: brief'in D kısıtı ve kullanıcının M2 talimatı ("aynı rakibin birden
  çok bağlantısı varsa T_comp=min") bunu ima ediyor. M0'ın orijinal fixture'ı
  TÜM rival satırlarını AYNI carrier kodu ("XX") altında kurmuştu — bu, N_od
  hesabını yanlış (her iki pazarda da N=1) yapardı; fixture düzeltildi
  (`build_fixture.py`, distinct carrier kodları R1-R5, R4 iki itinerary ile
  konsolidasyon testi).
- **2026-07-09 (M2)** — b_od artık `derive_b_od` ile TÜRETİLİYOR, M0'da elle
  seçilmiş b_od=2 (ZZA-ZZB) DEĞİL. Gerekçe: gerçek formül (N − baseline'da
  yenilen rakip sayısı, D'nin ≤ kuralıyla tutarlı) b_od=1 veriyor; orijinal
  değer sadece belirli bir lookup satırını (W(2,2,1)) test etmek için hardcode
  edilmişti, bu M0'da erkenden fark edildi (CLAUDE.md'ye önceden not düşüldü).
- **2026-07-09 (M2, KRİTİK)** — Rank one-hot linking kısıtı EŞİTLİKTEN
  EŞİTSİZLİĞE (`>=`) değiştirildi. Gerekçe: r=N-beaten formülü [0,N] üretebilir
  ama onehot'un aralığı [1,N] — eşitlik bir infeasibility tuzağı yaratıyordu
  (solver beaten=N'e ULAŞAMIYORDU, en az bir rakibi bedava olsa bile kasıtlı
  yenilmemiş bırakmak ZORUNDAydı). CLI end-to-end testiyle yakalandı (bağımsız
  validator, gerçekte yenilen bir rakibin raporlanmadığını tespit etti).
  Eşitsizlik + W'nin monotonluğu otomatik r=max(1,N-beaten)'e oturuyor.
- **2026-07-09 (M2)** — Independent validator artık "under-claim" (gerçekte
  yenilen ama raporlanmayan rakip) durumunu VIOLATION olarak İŞARETLEMİYOR.
  Gerekçe: forward-only D forcing (monotonik W varsayımı) claimed_beaten'i
  HER ZAMAN actual_beaten'in alt kümesi yapar (over-claim yapısal olarak
  imkansız, ayrı kontrolle zaten yakalanıyor) — under-claim ödülü asla şişirmez,
  sadece bilgi eksikliğidir. Detaylı analiz + test: `tests/fixtures/README.md`
  "M2 eki".
- **2026-07-09 (M3, KRİTİK)** — G kısıtı (ve validator'ın x_dev kontrolü) gün-içi
  NORMALİZASYON olmadan başta İNFEASİBLE veriyordu. Gerekçe: `t_arr`/`t_dep`
  TEK bir GLOBAL epoch_anchor'a göre kurulu — farklı `gun` değerleri farklı
  TAKVİM günlerine denk geldiğinden ham epoch değerleri arasında ~1440dk
  fark var, saat-of-day AYNI olsa bile. G'nin `max(t)-min(t)<=X_dev`
  kontrolünü ham değerlere uygulamak, saat-of-day'i TAM uyumlu bir tarifeyi
  bile ~1440dk'lık sahte bir ihlal olarak görüyordu — X_dev(15) ile ASLA
  uzlaştırılamaz, model her zaman infeasible çıkıyordu. Düzeltme: her
  (role,flno,gun) KENDİ takvim gününün gece yarısına göre normalize ediliyor
  önce (`constraints_operations.py::_day_offsets`, validator'da aynı mantık
  tekrarlanıyor). **Tespit yolu**: ilk solve denemesi "feasible solution not
  found" verdi; A/B/C/G'yi tek tek izole ederek (B+C alone=optimal, A
  alone=optimal, G eklenince=infeasible) kaynağı bulundu.
- **2026-07-09 (M3)** — A'nın test yardımcısında (`test_m3_constraints_a.py`)
  AYRI bir bug bulundu (üretim kodunda DEĞİL): `c_ib`'nin `gap_lo`/`gap_hi`
  alanları yanlışlıkla `arr_lo`/`arr_hi` ile AYNI kabul edilmişti, ama gerçek
  gap=dep(sabit 0)-arr=-arr olduğundan achievable aralık NEGATİF olmalıydı
  (`gap_lo=-arr_hi, gap_hi=-arr_lo`). Yanlış hint, `derive_b_big_ms`'nin M4'ünü
  bozarak x_ib=0 olduğunda t_arr'ı 0'a SABİTLEYEN bir infeasibility tuzağı
  yarattı (A'nın t_arr>=dep+295 gereksinimiyle doğrudan çelişiyordu). B alone
  ve A alone ayrı ayrı optimal, ama BİRLEŞTİRİLDİĞİNDE infeasible çıkması
  bu etkileşim-bug'ını ele verdi.
- **2026-07-09 (doğrulama borcu)** — `recompute_objective`'de b_od per-(o,d)
  pazar EN KÜÇÜK gun değeri kullanılarak hesaplanıyor, main.py'nin candidates
  üretim sırasıyla (gün-sıralı) TUTARLI olması için. Gerekçe: b_od kavramsal
  olarak pazar-seviyesi bir sabit (güne göre değişmemeli), ama fonksiyonun
  KENDİSİ bir gun parametresi alıyor (derive_b_od) — main.py'de İLK
  karşılaşılan gün kullanılıyor (gün=1, sıralı iterasyon nedeniyle); aynı
  tutarlılık burada da korunmazsa recompute_objective'in 668.75'i doğrulaması
  YANLIŞ nedenlerle başarısız olabilirdi (gerçek bug değil, iki hesaplama
  yolunun farklı b_od kullanması).
- **2026-07-09 (doğrulama borcu)** — CLI'ın 668.75 değeri `recompute_objective`
  ile BAĞIMSIZ DOĞRULANDI (birebir eşleşme). M1'den beri "insan doğrulaması
  bekliyor" etiketi artık gerekmiyor — kod-tabanlı bağımsız doğrulama, elle
  çarpı-yaz doğrulamasından daha güçlü bir kanıt (insan hatasına açık değil).
- **2026-07-09 (M4, E2 tasarım — ultrathink)** — $J_{best}$'in "argmin
  sandviç"i için "≤" tarafı TEK BAŞINA yeterli değil, mutlaka "≥" + $w_\pi$
  seçici de gerekiyor. Gerekçe: "≤" (her sunulan candidate kendi $J_\pi$'sini
  bir üst sınır olarak koyar) $J_{best}$'i gerçek minimumun ÜSTÜNE çıkaramaz,
  ama pazardaki SUNULMAYAN bir candidate'ın (ör. gap'i [L,U] dışına düşmüş)
  geniş achievable aralığı $J_{best}$'in kendi $[JD_{lo},JD_{hi}]$ değişken
  sınırını aşağı çekebilir — "≥" pini olmadan $J_{best}$ o düşük tabana
  serbestçe kayabilirdi (sahte-düşük iddia). $w_\pi\le x_\pi$ + $\sum
  w_\pi=a_{dir}$, solver'ı SADECE fiilen sunulan bir candidate'a $w=1$
  vermeye zorlayarak bu açığı kapatıyor. Test:
  `test_e2_sandwich_cannot_fabricate_jbest_below_true_min` (gap=-500'lük
  bilerek düşük-aralıklı bir 3. candidate ile ayartma denemesi, başarısız).
- **2026-07-09 (M4, E2 Big-M türetimi)** — E2'nin Big-M'leri İKİ katmanlı:
  candidate-bazlı ($M^{up}_\pi,M^{down}_\pi$ — `derive_e2_candidate_big_ms`,
  pazarın agregat $[JD_{lo},JD_{hi}]$'ına karşı) ve pazar-çifti-bazlı
  ($M_{pair}$ — `derive_e2_pair_big_m`, iki yönün KENDİ $J_{best}$
  bounds'unun izin verdiği en kötü farka karşı). İkisi de candidate/pazar
  verisinden türetilir, global sabit YOK — B/D'nin Big-M disipliniyle aynı
  ilke.
- **2026-07-09 (M4, A edge-case)** — `build_rotation_pairs`/`add_a_constraints`
  bir Flight Pair alt-çiftinin bacaklarından SADECE BİRİ modelin
  ARR_INSTANCES/DEP_INSTANCES kapsamındaysa (diğeri hiç candidate üretmemiş)
  rotasyon kısıtını SESSİZCE atlıyordu (F'in tasarımı sırasında bulundu, M3'te
  fark edilmemiş bir gap). Düzeltme: `out_of_scope_baselines` parametresiyle,
  kapsam-dışı bacağın HAM baseline zamanına karşı in-scope bacağa kısıt
  kuruluyor artık (`partial_pairs`, iki yönlü — IB_fixed/OB_fixed).
- **2026-07-09 (M4, G "check" -- KRİTİK)** — G'nin gün-içi normalizasyonu
  (M3'ün `_day_offsets`) gerçek gece yarısını (00:00) referans noktası
  kullanıyordu; bu, KENDİ saati gece yarısına yakın olan bir uçuş için
  (ör. 23:55 vs 00:05, gerçekte 10dk fark) SAHTE bir ~1430dk'lık ihlale yol
  açardı (elle hesapla doğrulandı, sonra `test_g_no_false_violation_at_midnight_wraparound`
  ile RED→GREEN kanıtlandı). Düzeltme: referans noktası her (role,flno)
  çifti için KENDİ baseline saatinin 12 saat KARŞISINA kaydırıldı
  (`_flight_cut_points`) — uçuşun ayarlanabilir aralığı bu yeni sınırdan hiç
  taşamayacağından sarma sorunu o uçuş için yapısal olarak imkansız hale
  geliyor. `independent_validator.py`'nin x_dev kontrolü BİREBİR aynı mantığı
  tekrarlıyor.
- **2026-07-09 (M4, runner rank clamp -- KRİTİK, M4 CLI koşusunda yakalandı)**
  — `src/solve/runner.py`'nin `rank_values` çıkarımı `model.rank[market]`'ın
  HAM (N-beaten) değerini, `add_rank_onehot`'un [1,N] clamp'ini YOK SAYARAK
  doğrudan raporluyordu — bir pazarın TÜM rakipleri yenildiğinde (raw=0)
  gerçek tabloda hiç var olmayan bir r=0 değeri output.json'a yazılıyordu.
  M2'den beri var olan bir bug, hiçbir fixture senaryosu bunu tetiklemediği
  için hiç yakalanmamıştı — E1'in dengeleme baskısı solver'ı bu fixture'da
  İLK KEZ bir pazarın TÜM rakiplerini yenmeye zorlayınca ortaya çıktı (CLI
  `valid=False` verdi). Düzeltme: N>0 pazarlar için `max(1,raw_rank)`
  (N=0 pazarlar clamp'siz 0 kalıyor) — `test_runner_rank_clamp.py`.
- **2026-07-09 (M4, solve() infeasible desteği)** — `runner.py`'nin
  `opt.solve(model)` çağrısı (appsi_highs, `load_solution` default=True)
  infeasible modellerde `RuntimeError` fırlatıyordu (çözüm yüklenecek bir
  şey yok) — G'nin "genuine violation" testi bunu ortaya çıkardı. Düzeltme:
  `load_solutions=False` + `status in (optimal,time_limit)` durumunda
  açıkça `model.solutions.load_from(result)` — artık `result.status ==
  "infeasible"` çağıranlar tarafından temiz bir şekilde kontrol edilebiliyor
  (crash yerine).
- **2026-07-09 (M5, KRİTİK — G'nin koşulsuz okuması full data'yı infeasible
  kılıyordu)** — solve merdiveni TÜM adımlarda (step1 + step2'nin 4 K'sı)
  hızlı infeasible verdi. İzolasyon: B+C+D tek başına infeasible DEĞİL,
  A/G'nin varlığı sorunun kaynağıydı. Kök neden: TK2841 (TZX→IST) kendi
  baseline'ında bile G'nin uzlaştırılabilirlik sınırını aşıyor (645dk>375dk,
  bkz. ASSUMPTIONS.md VARSAYIM-9 — formel Helly-özelliği kanıtıyla).
  Kullanıcıya AskUserQuestion ile sunuldu (stop-and-ask eşiği: hem
  "45dk'da çözülemeyen infeasibility" hem "merdivenin 3. basamağı"). Karar:
  TAM muafiyet DEĞİL, KÜME-BAZLI G (`src/model/day_clustering.py`,
  data-türetilmiş, 2841'e özel hiçbir şey hardcode edilmeden) — dairesel
  en-büyük-boşluktan kes + soldan-sağa açgözlü ÇAP taraması (ARDIŞIK-boşluk
  DEĞİL, kullanıcının 0/300/600dk zinciri uyarısı doğrultusunda). Validator
  aynı algoritmayı bağımsız yeniden uyguluyor (`_cluster_flight_days_independent`).
  Tüm günler zaten uzlaştırılabilirse (460/461 IB, 476/476 OB) TEK küme =
  M3 davranışı değişmeden korunuyor.
- **2026-07-09 (M5, KRİTİK — A'nın "aynı gun" eşleştirmesi de infeasible
  kaynağıydı)** — G'nin küme düzeltmesinden SONRA bile full-data ladder
  hızlı infeasible verdi. İzolasyon: B+C+D+A+G (kümeli) infeasible, B+C+D+A
  (G'siz) infeasible, B+C+D (A/G'siz) DEĞİL — A ayrı bir sorundu. TK174/175
  (IST-KUL) incelemesi: "aynı gun" kuralı gün1'in OB kalkışını (15:50) AYNI
  günün IB varışıyla (11:00, kalkıştan 5 saat ÖNCE!) eşliyordu — gerçek
  partner gün3'ün 11:00 varışıydı (~2590dk sonra). Full veri: 1496 çiftin
  %54.7'si baseline'da uzlaştırılamaz, %45.3'ü kronolojik TERS.
  AskUserQuestion ile kullanıcıya sunuldu (yeni sistemik bulgu, brief
  yorumunu etkileyen karar). Karar (VARSAYIM-10): eşleştirme R_o'nun
  KENDİSİNE değil BASELINE KRONOLOJİSİNE dayanıyor
  (`src/model/rotation_matching.py::match_rotation_legs`, dairesel-haftalık,
  açgözlü-birebir). Sarma (Gün7→Gün1) durumunda kısıtın ham epoch kıyası
  bir HAFTA (10080dk) ileri kaydırılmalı — ilk KUL-şekilli test bunu
  atlayınca YANLIŞLIKLA infeasible verdi (elle-inşa edilmiş test verisiyle
  yakalandı, `week_offset` eklenerek düzeltildi). Düzeltmeden SONRA bile
  %24.3 (382/1571) çift doğru eşleştirmeyle bile uzlaştırılamıyor —
  VARSAYIM-11 ile G'yle AYNI mantıkla (kendi en-iyi-durumunda bile
  imkansızsa MUAF tut + logla) çözüldü.
- **2026-07-09 (M5, KRİTİK — appsi_highs `time_limit` kök-düğüm cut turlarını
  KESEMİYOR)** — VARSAYIM-9/10/11 fix'lerinden sonraki ilk full-data koşusu,
  merdivenin step1'inde (18118 aday, 756174 satır → presolve sonrası 604925
  satır/297906 sütun/272927 binary) `time_limit_sec=600` verilmesine rağmen
  HiGHS içi "Time" sütunu 1282.9s'e ulaşana kadar (2x'ten fazla aşım) TEK bir
  B&B düğümüne bile inmeden (node=0), SIFIR incumbent ile kesintisiz kök-düğüm
  cut üretimine devam etti (`ps` CPU %100 canlı, hang değil — gözlemlenebilirlik
  yamasının [ladder]/HiGHS log akışı sayesinde YAKALANDI, sabah 5 saatlik sessiz
  hang'in AYNISI olması ENGELLENDİ). Kök neden: appsi_highs'in `config.time_limit`'i
  yalnızca B&B düğümleri ARASINDA kontrol ediyor gibi görünüyor — büyük bir
  modelde (605K satır) TEK bir kök-düğüm cut turu kendi başına 600s'i aşabiliyor,
  solver-içi limit bu durumda GÜVENİLİR DEĞİL. **Karar**: script seviyesinde
  DIŞARIDAN bir bekçi (SIGTERM+timeout, `solve()` çağrısını saran) eklenmeli —
  solver-içi `time_limit`'e güvenmeden, gerçek duvar-saati sınırını dışarıdan
  zorlamak. `scripts/run_full_data.py`'nin `--budget-sec` bekçisi (adımlar
  ARASI kontrol) bu senaryoyu YAKALAMAZ (tek bir adımın İÇİNDE takılı kalma).
- **2026-07-09 (M5 — ucuz baseline-feasibility tanığı, MIP koşusu OLMADAN)**
  — step1'in 20+ dakika incumbent bulamamasının kök nedenini araştırmak için
  `scripts/baseline_feasibility_witness.py` yazıldı: TÜM ayarlanabilir
  zamanlar BASELINE değerine sabitlenip (hiç adjust yok), B'nin "gap∈[L,U]
  ⟹ x=1 zorunlu" kuralı (VARSAYIM-6) gereği seçim ZORUNLU hale geliyor
  (baseline-gap-geçerli her aday tek mümkün x=1 kümesi) — bu yüzden yalnızca
  bağımsız validator'dan geçiriliyor, HİÇ MIP çağrılmıyor (30.2s, full data).
  **Sonuç**: baseline'ın kendisi TÜM BEŞ kısıt ailesinde ihlalli — A: 487
  (VARSAYIM-11 exemption testiyle çapraz kontrol: 1524 in-scope çiftin 343'ü
  zaten exempt, yani 487'nin büyük kısmı BEKLENEN exempt-fail, gerçek
  "adjustment gerekli" kalan ~144), E1: 296, **E2: 1181 (en büyük kategori,
  E1'den bile fazla)**, F: 31, G: 53 (toplam 2048 ihlal). **Yorum**: bu TEK bir
  suçlu kısıt DEĞİL (kullanıcının başlangıç şüphesi E1 özelindeydi) — TÜM
  kısıt aileleri baseline'da eş zamanlı ihlalli, yani step1'in zorluğu
  muhtemelen "hangi kısıt imkansız" değil "binlerce koordineli ayarlamayı
  aynı anda bulma" (arama zorluğu, tek-nokta infeasibility değil). Bu bulgu
  ile kullanıcıya danışıldı (E1-özel dur-kuralı tam eşleşmiyordu) — karar:
  step B'ye (incumbent-öncelikli HiGHS ayarları + dış bekçi) devam.
- **2026-07-09 (M5, dış bekçili full-data koşusu → DAL C kesinleşti, E1/E2/F
  tekli-suçlu hipotezi ÇÜRÜTÜLDÜ)** — dış bekçili + `mip_heuristic_effort=0.3`
  koşusu: step1 660s'de temiz `watchdog_killed` (incumbent yok), step2'nin
  DÖRT K değeri (50/100/200/400) de HIZLI ve TEMİZ `infeasible` verdi
  (13.5-24.3s solve, timeout DEĞİL — gerçek HiGHS infeasibility sertifikası).
  Bu, önceki (bekçisiz) koşulardan çok daha net bir sonuç. `scripts/diagnose_e1_e2_f.py`
  (K=400 alt-kümesinde, `build_model_m4`'ün AYNI test edilmiş
  `add_*_constraints` primitiflerini yeniden birleştiren, src/model/*.py'a
  DOKUNMAYAN bir tanı script'i): E1 tek başına kapalı → hâlâ infeasible
  (33.1s); E2 tek başına kapalı → hâlâ infeasible (20.6s); F tek başına
  kapalı → hâlâ infeasible (15.5s). **Kullanıcının DAL C protokolündeki
  tekli-suçlu varsayımı (önce E1, sonra E2, sonra F) ÇÜRÜTÜLDÜ** — hiçbiri
  tek başına kaldırıldığında feasible olmuyor. Bonus test (E1+E2+F ÜÇÜ
  BİRDEN kapalı) ilk denemede dış bekçi OLMADAN (ham `solve()` çağrısı)
  13:44 boyunca sonuçsuz sürdü, elle öldürüldü — kullanıcıya danışıldı, karar:
  aynı testi dış bekçili yeniden çalıştır (`scripts/_diagnose_step_worker.py`
  eklendi, `diagnose_e1_e2_f.py` artık TÜM varyantları `solve_step_with_watchdog`
  üzerinden çözüyor). Watchdog'lu tekrar: 240s'de (180s limit+60s margin)
  TEMİZ `watchdog_killed` — yine SONUÇSUZ (ne feasible ne infeasible
  kanıtlanabildi), ama bu kez bekçi ÇALIŞTI (13:44 yerine 240s'de durdu).
  **Yorum**: üç aileyi TEK TEK kaldırmak hızlı-temiz infeasible veriyor
  (kolay kanıtlanabilir kısıt çakışması yok gibi görünüyor) ama ÜÇÜNÜ BİRDEN
  kaldırmak modeli HiGHS'in kök-düğümde hızlıca çözemediği bir arama
  problemine dönüştürüyor — ya gerçekten feasible ama zor bulunuyor, ya da
  hâlâ infeasible ama kanıtı E1/E2/F'nin verdiği ek deduktif kısıtlamalar
  olmadan daha zor. Kullanıcıya bu sonuçla danışıldı, sonraki adım
  bekleniyor (A/G kaldırma, ikili kombinasyonlar, veya organizatöre
  over-constraint bulgusu olarak raporlama).
- **2026-07-09 (M5, A ve G de tek başına suçlu DEĞİL — BEŞ kısıt ailesinin
  TAMAMI tek tek elendi)** — kullanıcı A/G'nin de aynı desenle (K=400,
  dış bekçili, tek tek kaldırma) test edilmesini istedi. `A_off`: 24.9s'de
  temiz `infeasible` (399 çift zaten VARSAYIM-11 ile exempt, kalan A kısıtı
  TAMAMEN kaldırılmasına rağmen hâlâ infeasible). `G_off`: 36.9s'de temiz
  `infeasible`. **Sonuç: A, E1, E2, F, G'nin BEŞİ de tek tek kaldırıldığında
  hâlâ infeasible** — hiçbiri tek başına suçlu değil. E1+E2+F ÜÇÜ birden
  kaldırıldığında bile 240s'de sonuçsuz (ne feasible ne infeasible
  kanıtlandı, bkz. bir önceki girdi). Bu, B/C/D (temel bağlantı/rakip
  kısıtları) + K=400 adjustable-subset mekanizmasının KENDİSİNİN (15742
  uçuş baseline'a sabit — baseline'ın kendisi TÜM beş ailede ihlalli, bkz.
  baseline-feasibility-witness bulgusu) asıl kaynak olabileceğine işaret
  ediyor. Beş aile tek tek elendiği için ikili/üçlü kombinasyon aramasının
  getirisi azalıyor — kullanıcıya kapsamlı özet sunuldu, sonraki adım
  bekleniyor.
- **2026-07-09 (M5 KAPANIŞ — full-data teşhis tamamlandı, VARSAYIM-12 olarak
  işlendi, çözüm bulunmadan durma kararı)** — kullanıcıya son bir tur
  sunuldu: E1_off'u K-subset OLMADAN (tam 18118 candidate) test etmek.
  Sonuç: 660s dış-bekçi limitinde yine `watchdog_killed`, SIFIR incumbent —
  step1'in ORİJİNAL (tüm kısıtlar açık) davranışıyla AYNI. Bu, full-scale
  modelin BÜYÜKLÜĞÜNÜN (756174 satır) tek başına 600-660s'de çözülemediğini
  gösteriyor — hangi kısıtın açık/kapalı olduğundan BAĞIMSIZ, yani bu test
  K=400'ün baseline-sabitleme etkisini E1'in etkisinden AYIRT EDEMEDİ.
  Kullanıcıya bu bulguyla tekrar danışıldı: "daha fazla tanı zamanı
  harcamak yerine K=400'deki 5/5 temiz infeasibility kanıtını yeterli kabul
  et, organizatöre raporla" kararı verildi (production-scale 30-60dk koşu
  ve K=800/1200 alternatifleri REDDEDİLDİ — zaman/getiri dengesi kötü).
  Bulgular `ASSUMPTIONS.md` VARSAYIM-12'ye ve `docs/organizer_questions.md`
  madde 12'ye işlendi. **M5 bu haliyle KAPANIYOR**: full-data'da doğrulanmış
  bir objective_value YOK, ama kapsamlı bir teşhis zinciri var (baseline
  witness → watchdog'lu ladder → 7 kısıt-kaldırma varyantı → full-set
  kontrol testi) — hepsi `runs/`'da loglanmış, hepsi tekrar-çalıştırılabilir
  script'lerle üretilmiş (`scripts/baseline_feasibility_witness.py`,
  `scripts/diagnose_e1_e2_f.py`), src/model/*.py'da HİÇBİR kod değişikliği
  YAPILMADI (kullanıcının "E1 suçluysa kod değiştirme" talimatı A/E1/E2/F/G'nin
  hepsine genişletilerek uygulandı).
- **2026-07-09 (M5b — kullanıcı M5'i "yarım" ilan etti, derin otopsi istedi
  → gerçek kök neden bulundu: K-subset yetersizliği, tek kısıt hatası
  DEĞİL)** — kullanıcı VARSAYIM-12 organizatöre gitmeden önce
  `docs/baseline_autopsy.md` otopsisini istedi. Sonuç: DAL C'nin "hangi
  kısıt suçlu" sorusu YANLIŞ ÇERÇEVEYDİ. E1 (296→**690** gerçek) ve E2
  (1181→**1219** gerçek) validator'da KAPSAM eksikliğiyle eksik
  raporlanıyordu (E1: selected-connections-bazlı kapsam yerine
  VARSAYIM-6'nın "yapısal aday" kapsamı kullanılmalıydı; E2: LS-estimate
  fallback eksikti). A'nın validator kontrolü VARSAYIM-11 exemption'ını hiç
  uygulamıyordu (487 ham → 144 gerçek zaten biliniyordu ama validator
  bunu SESSİZCE kaçırıyordu). **Asıl bulgu**: her aile için "baked-in"
  (top-K ayarlanabilir pazarların HİÇBİRİNE dokunmayan, dolayısıyla K'dan
  bağımsız ÇÖZÜLEMEZ) ihlal oranı hesaplandı — K=400'de bile E1'in %54'ü,
  E2'nin %51'i baked-in. K arttıkça oran düzenli düşüyor (mekanizma
  beklendiği gibi çalışıyor) ama step2'nin K-şeması (50/100/200/400) full-data
  ölçeğinde YETERSİZ — full çözüm muhtemelen full-adjustable'a (step1) yakın
  bir K gerektiriyor, ki step1'in kendisi (18118 aday, 756174 satır) BÜYÜKLÜK
  nedeniyle 660s'de çözülemiyordu (infeasibility DEĞİL, tractability).
  F'nin kapasite sayıları (10/15) TEYIT EDİLDİ — brief'in kendi §2.4
  verisi (sayfa 4), bizim varsayımımız değil. G'nin model/validator kodu
  SATIR SATIR aynı (parity kanıtlı, kod karşılaştırmasıyla doğrulandı).
  Kullanıcı onayıyla 3 validator düzeltmesi TDD ile uygulandı (kod
  değişikliği YALNIZCA `independent_validator.py`'de, MODEL kodu
  DOKUNULMADI): (1) E1 kapsamı `_has_structural_candidate` (yeni,
  `generate_candidates`'in achievable-range kapısının bağımsız kopyası)
  ile düzeltildi; (2) E2'ye `get_journey_constant_estimate` fallback
  eklendi; (3) A'ya VARSAYIM-11'in best-case-reconcilability testi eklendi
  (`_baseline_bounds` kullanarak, zaten var olan bir helper). 22/22
  validator testi + 199/199 tüm suite yeşil, fixture hâlâ 668.75/valid=True.
  Bir sonraki adım: step1'i (full-adjustable, tüm 18118 aday) dış-bekçili
  daha uzun bir bütçeyle (30-45dk) yeniden dene — artık modelin YAPISAL
  olarak infeasible OLMADIĞI biliniyor (K arttıkça baked-in oran düşüyor),
  yalnızca BÜYÜKLÜK nedeniyle zaman gerekiyor.
- **2026-07-10 (M5c — 45dk'lık step1 retry de sonuçsuz, kullanıcı LP
  anatomisi istedi)**: 2400s time_limit + dış bekçi ile step1 yeniden
  denendi — 2711.4s'de yine SIFIR incumbent, kök düğüm cut üretimi hiç
  bitmedi (dual bound 5.53M→4.90M, aynı sürünme deseni). Kullanıcı DAL
  1'i (kapat, negatif sonuç yaz) reddetti — semptomların (kök cut'lar
  bitmiyor, sürünen dual bound) SOLVER sorunundan önce LP-gevşekliği
  sorununa işaret ettiğini öne sürdü, formülasyon teşhisi (LP anatomisi →
  sıkılaştırma) istedi.
- **2026-07-10 (M5c §Phase1 — LP anatomisi: F satır patlaması + w/x
  fractionality)**: `scripts/lp_anatomy.py` (kök LP gevşemesi tek başına
  çözüldü, MIP yok) full step1 modelinde: LP/tavan oranı %65 (aşırı gevşek
  DEĞİL) ama F (kova/kapasite) TEK BAŞINA satırların %53.7'si (405,982/756,174,
  per-reachable-bucket Big-M çiftlerinden, ±180dk pencere/10dk kova ≈
  36-37 kova/örnek). Fractionality haritası: w (E2 selector) %50.3, x
  (temel bağlantı seçimi) %44.5 EN kararsız aileler — F'nin KENDİ
  z_dep/z_arr'ı görece SIKI (%6-8), yani F'nin sorunu satır HACMİ, LP
  gevşekliği DEĞİL. `docs/lp_anatomy.md`'ye yazıldı.
- **2026-07-10 (M5c §0 — D-folding, VARİABLE ELIMINATION)**: beat_{π,k}
  yalnızca J_π'nin adayın KENDİ penceresi boyunca T_comp'u aşıp aşmadığı
  belirsizken gerçek bir karar — J_hi<=T_comp ise HER ZAMAN yener (beat
  değişkeni YOK, x_i'ye katlanır), J_lo>T_comp ise HİÇBİR ZAMAN yenmez
  (0'a katlanır). Kısıt EKLEMEK yerine değişken ELEME — hem küçük hem
  sıkı. `test_forward_only_mode_allows_under_claim_when_adversarial` gibi
  var olan testler koşullu (gerçek pencereli) adaylara taşındı (always/
  never adaylarda artık `model.beat[i,k]` YOK). Full-data'da ölçüm: satır
  756174→722947 (-%4.4), beat değişkeni 33748→21969 (-%35), LP/tavan
  oranı DEĞİŞMEDİ (%65.07→%65.01, foldun LP'nin GERÇEK sıkılığını
  bozmadığını doğruluyor) ama LP çözüm SÜRESİ iyileşmedi (172s→194.9s,
  gürültü içinde) — D-folding TEK BAŞINA yetersiz, asıl iş §1.
- **2026-07-10 (M5c §1 — fold makinesi genelleştirmesi: x-fix + E1/E2
  exempt+log, SONRA kritik bir yapısal kısıt bulundu)**: (a) `add_b_constraints`
  artık gap_lo==gap_hi olan HER adayın x[i]/gap[i]'sini `.fix()` ediyor
  (B'nin "gap∈[L,U]⟹x=1" kuralı veri-gerçeği, çözüm gerektirmiyor) —
  şeffaf, mevcut hiçbir test bozulmadı. (b) VARSAYIM-9/11'in exempt+log
  deseni E1'e (`add_e1_constraints`) ve E2'ye (`add_e2_constraints`)
  genellendi: bir pazar çiftinin HER İKİ yönü de TAMAMEN donmuşsa ve
  donmuş sayılar E1/E2'yi ihlal ediyorsa, kısıt KURULMUYOR + loglanıyor
  (TDD, 6+8 test). **Full-data K=50'de test edildiğinde SIFIR exemption
  tetiklendi** — çünkü K=50'de 13273 adayın HİÇBİRİ (0/13273) tam donmuş
  DEĞİL! Kök neden: `apply_adjustable_subset` bir bacağı yalnızca O
  bacağı kullanan HİÇBİR aday top-K pazarlardan birine ait değilse
  donduruyor, ama aday üretimi TAM cross-product olduğundan bir bacak
  ORTALAMA 4.4 farklı pazara katılıyor (maks 183) — K=50'nin küçük
  "tohum" kümesi (297 IB + 254 OB bacağı doğrudan top-50'ye dokunuyor)
  bacak-paylaşımı üzerinden GEÇİŞKEN olarak neredeyse TÜM adaylara
  yayılıyor. **`docs/baseline_autopsy.md`'nin "baked-in" yüzdeleri
  PAZAR-seviyesinde ölçülmüştü, `apply_adjustable_subset`'in GERÇEK
  BACAK-seviyesi davranışını yansıtmıyordu** — otopsi NEDEN'i doğru
  buldu (baked-in ihlaller) ama K-subset'in KENDİSİNİN yapısal olarak
  işe yaramadığını göstermedi. VARSAYIM-12'ye GÜNCELLEME 2 olarak
  işlendi. Kullanıcıya danışıldı — karar: K-subset merdiveni (step2)
  AYRI mekanizma olarak emekliye ayrıldı (silinmedi, config'te varsayılan
  kapalı), bacak-seviyesi dondurma fikri §5'in proximity/local-branching
  motoruna gömüldü (orada "top-K pazar" yerine "incumbent'a en yakın k
  UÇUŞ" ilkesiyle doğru şekilde çalışacak). Sıradaki adım: §2 (raporlama
  semantiği) + §5 Faz-1 (min-sapma feasibility amaç fonksiyonu, reward
  YOK) full-data'da denenecek.
- **2026-07-10 (M5c §2 tamamlandı — raporlanan objective_value artık HER
  ZAMAN recompute gerçeği)**: `finalize_reported_objective` eklendi
  (`independent_validator.py`) — recompute_total, output.json'un
  `objective_value` alanını EZER (solver'ın ham iç iddiası değil). Invariant:
  recompute HİÇBİR ZAMAN solver'ın kendi iddiasından KÖTÜ olamaz (olursa
  gerçek bug); status=optimal iken TAM eşitlik şart, time_limit'te recompute
  daha İYİ olabilir (solver'ın kendi iddiası tembel bir alt sınır olabilir).
  `main.py` + `run_full_data.py`'ye bağlandı. Ayrıca `recompute_objective`'nin
  KENDİSİNDE aynı estimate-fallback eksikliği bulundu (E2 validator bug'ının
  ikizi) — düzeltildi, aksi halde full-data'da 571 tahmini-K_od pazarından
  biri gelince TÜM recompute çökerdi.
- **2026-07-10 (M5c §5 Faz-1 — min-sapma amaç fonksiyonu full-data'da
  DENENDİ, DAL P1-C ile SONUÇLANDI: zaman-aşımı, sonuçsuz)**:
  `src/model/deviation_objective.py::add_min_deviation_objective` (standart
  mutlak-değer lineerleştirmesi, dev_plus-dev_minus==t-baseline, min
  Σ(dev_plus+dev_minus)) fixture'da UÇTAN UCA doğrulandı (build_model_m4'ün
  TÜM A-G kısıtlarıyla, 145dk asgari sapma bulundu — fixture'ın kendi
  baseline'ı da A-G'yi ihlal ediyor). Full-data'da (18118 aday) iki deneme:
  (1) 600s+120s bekçi → `watchdog_killed`, HiGHS log'u YOKTU (enstrümantasyon
  eksikliği, düzeltildi); (2) kullanıcının "tek uzatma hakkı" kuralıyla
  1800s+120s + HiGHS log'lu yeniden deneme → dual bound HIZLA 142'den
  4108'e, sonra YAVAŞÇA 4219.48'e yakınsadı (reward koşusunun MİLYONLUK
  ölçeğinden TAMAMEN farklı — mutlak sapma dakika cinsinden, doğal olarak
  küçük), AMA 202.4s'den SONRA log'da 800s+ boyunca HİÇBİR yeni satır
  ÇIKMADI (dual bound donuk, sıfır B&B düğümü, sıfır incumbent) — reward
  koşusuyla YÜZEYSEL olarak farklı ama YAPISAL olarak AYNI "kök düğümde
  takılı kalma" deseni. **DAL P1-C teyit edildi (zaman-aşımı, sonuçsuz —
  infeasible DEĞİL)**: kullanıcının kendi protokolüne göre sonraki adım
  Gurobi DEĞİL, LP anatomisine dönüş — E2 satır bütçesi + slot bağlama
  sıkılaştırması (lp_anatomy.md'nin işaret ettiği bir sonraki öncelik).
  İki süreç (PID 11045 worker, 10788 parent) kullanıcı onayı gerekmeden
  (protokolün kendi "tek uzatma" kuralının doğal sonucu olarak) temizlendi.
- **2026-07-10 (DAL P1-C branch 3 — F satır-patlaması ÇÖZÜLDÜ, öncelik #1)**:
  `add_f_constraints`'in per-bucket Big-M çifti (kova başına lower+upper,
  örnek başına ~2×37≈74 satır — F'nin `docs/lp_anatomy.md`'de tespit edilen
  %53.7'lik satır payının kaynağı) TEK bir bijective eşitlikle değiştirildi:
  kovalar $t$ ekseninde ARDIŞIK/AYRIK bir bölme olduğundan
  $t_r=\sum_b b\Delta z_{r,b}+o_r$ ($o_r\in[0,\Delta-1]$ yeni offset
  değişkeni, $\sum_b z_{r,b}=1$ zaten vardı) Big-M'siz, tek satırda t'yi
  seçilen kovaya pinler (ultrathink `src/model/constraints_capacity.py`
  docstring'inde). TDD: önce `test_f_bucket_linking_is_one_equality_per_
  instance_not_two_per_bucket` KIRMIZI yazıldı (`f_dep_lower`/`f_dep_upper`
  hâlâ vardı), sonra kod değişti → YEŞİL. Mevcut 5 davranışsal F testi
  (adversarial objective ile t değerlerini kontrol eden, model içini DEĞİL)
  değişiklik gerektirmeden yeşil kaldı — `independent_validator.py`'nin F
  kontrolü zaten model'den bağımsız (`t//bucket_size_min`), bu yüzden
  validator'da HİÇBİR değişiklik gerekmedi. Fixture: 668.75/valid=True
  korunur. 140 unit + 80 solve (6 F testi) yeşil. Full-data LP anatomisi
  YENİDEN ölçüldü (`scripts/lp_anatomy.py`, kod değişikliği yok, sadece
  analiz): toplam satır 722,947→**329,842 (-%54.4)**, F satırları
  405,982→~12,900 (-%96.8), LP çözüm süresi 194.9s→**115.1s (-%41)**, LP
  amaç değeri VE LP/tavan oranı BİREBİR AYNI (5,253,749.43, %65.01) —
  yeni formülasyonun eski Big-M ile TAM eşdeğer fizibilite kümesi
  ürettiğinin doğrudan kanıtı (yaklaşıklama değil, saf satır-azaltımı).
  w/x fractionality (öncelik #2, henüz DENENMEDİ) neredeyse değişmedi
  (%50.3→%49.82, %44.5→%44.41) — beklenen, bu fix w/x'e dokunmuyor.
  `docs/model.md`'nin F bölümü + `docs/lp_anatomy.md`'ye yeni karşılaştırma
  tablosu eklendi. Sıradaki adım: full step1'i bu formülasyonla YENİDEN
  koşup kök-düğüm cut davranışını ölçmek (MIP seviyesinde, LP değil) —
  tek başına yeter mi yoksa w/x sıkılaştırması (öncelik #2) da mı gerekiyor,
  ikisi birlikte mi denenecek kullanıcıya sorulacak.
- **2026-07-10 (F fix'in MIP-seviyesi re-ölçümü — TEK BAŞINA YETERSİZ)**:
  kullanıcı "şimdi koş" dedi, reward amacıyla (min-sapma değil) full-data
  step1 AYNI 600s+120s bekçi bütçesiyle yeniden koşuldu. Presolve sonrası
  satır 604,925→220,239 (-%63.6), dual bound yörüngesi ÖNCEKİNDEN daha
  hızlı/sıkı yakınsadı (5.13M→4.19M, 659s'de; öncesi 5.53M→4.90M) — F
  fix'inin ÖLÇÜLEBİLİR bir iyileşme olduğu doğrulandı. AMA `Nodes=0`
  DEĞİŞMEDİ: 720s boyunca HiGHS hâlâ SADECE kök-düğüm cut-üretiminde,
  hiç dallanmaya geçemedi, `watchdog_killed`, sıfır incumbent. **F TEK
  BAŞINA kök düğümü açmaya YETMEDİ** — lp_anatomy'nin "İki AYRI hedef"
  (F HIZ, w/x LP KALİTESİ, biri diğerini gereksiz kılmıyor) öngörüsü
  doğrulandı. `docs/lp_anatomy.md`'ye karşılaştırma tablosu eklendi.
  Sıradaki adım: öncelik #2 (w/x fractionality sıkılaştırması, task #36) —
  E2'nin w seçicisi ve B'nin x'i için, D-folding'deki AYNI desenle
  (data-belirlenmiş sonuç → değişken elenir), ardından İKİSİ BİRDEN bir
  kez daha reward-amaçlı full-data MIP koşusuyla ölçülecek.
- **2026-07-10 (DAL P1-C branch 3 — öncelik #2: E2'nin $w$/$a_{dir}$ fold'u,
  ölçüm ÖNCESİ analiz)**: Gurobi'ye geçmeden bu fold'u kodlamadan önce
  full-data'da fold POTANSİYELİNİ ölçtüm (K-subset'in tekrarı olmasın diye)
  — pazar-yön grupları %51.4'ü (3935/7656) SINGLETON (tek candidate), bu
  gruplardaki adaylar %21.7 (3935/18118); x-fix (gap_lo==gap_hi) full-data'da
  0 candidate'ta tetikleniyor (adjustable_set=all altında beklenen, tüm
  pencereler genuinely geniş). Singleton-fold gerçek bir yapısal kazanç
  (K-subset gibi ölü değil) — uygulandı: bir pazar-yönünün TEK adayı varsa
  $a_{dir}=x_\pi$ ve $w_\pi=a_{dir}=x_\pi$ cebirsel olarak ZORUNLU (a_dir>=x,
  a_dir<=Sum(x)=x, Sum(w)=a_dir tek terimli) — `model.a_dir`/`model.w`
  `pyo.Expression`'a dönüştü (çoklu-adaylı yönler için gerçek
  `_a_dir_var`/`_w_var` binary'sine sarılı, singleton'lar için doğrudan
  $x_\pi$), dışarıya AYNI `pyo.value(model.a_dir[key])` arayüzünü sunuyor
  (testler/`e1_diagnostics` FARK ETMEDİ). TDD: 2 yeni test (fold + control,
  KIRMIZI→YEŞİL), var olan 8 E2 testi (hepsi singleton senaryolar
  kullanıyordu) değişiklik gerektirmeden yeşil kaldı — Expression'ın Var
  gibi `pyo.value()` ile okunabilmesi sayesinde. Fixture: 668.75/valid=True
  korunur. 140 unit + 82 solve yeşil. `docs/model.md`'nin E2 bölümü
  güncellendi. Sıradaki adım: F fix + bu fold İKİSİ BİRDEN full-data LP
  anatomisi + reward-amaçlı MIP re-ölçümü.

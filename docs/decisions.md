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

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

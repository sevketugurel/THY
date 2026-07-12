# Residual Conflict Repair Engine — Tasarım Spec'i

Tarih: 2026-07-12 (akşam) · Durum: **kullanıcı onaylı** · Tur adı: M5i
Dondurma: 2026-07-14 18:00 · Teslim: 2026-07-16 17:00

## 0. Karar özeti (kullanıcı onaylı, normatif)

1. **C1 "under-claim floor" sigorta olarak üretilir** — teslim paketine ana
   çözüm olarak GİRMEZ; rapora ancak şeffaf "fallback" notuyla, B-semantiği
   riski açık yazılarak girebilir. Üretiminden önce Adım-0 teşhisi zorunlu.
2. **Ana bütçe dürüst residual-repair hattında**: bu gece 4h solver bütçesi
   (Adım-0 + C1 script işi bütçe dışı), sabah değerlendirme.
3. **Kampanya mekaniği: A başla, gerekirse B'ye geç** (kural §4.5'te).
4. **Keep-best persist zorunlu**: her tur diske yazılır, başarısız turun
   kapatmaları geri alınır.
5. **valid=True çıkarsa anında dur ve raporla** — sonuç kullanıcıya
   gösterilmeden `outputs/full_data_output.json` ASLA yazılmaz.

## 1. Bağlam ve hedef

Başlangıç noktası: `runs/lns_best_partial_20260712T150223Z.json`
(Σslack=10944.0; 106 E1 çifti + 221 E2 çifti ihlalli; 63 çift Γ-muaf;
kaynak: `runs/lns_summary_20260712T150223Z.log.json`). Full-data'da bugüne
dek validator-clean objective_value yok (VARSAYIM-12 zinciri). Hedef:
ihlalli çiftleri hedefli yön-kapatmayla kırarak Σslack'i sıfıra indirmek ve
İLK strict-valid full-data çıktısını üretmek; paralelde C1 sigortası.

## 2. Tasarımı şekillendiren doğrulanmış kod gerçekleri

- **Yön kapatma ucuz değil**: D1 semantiği (`src/model/deactivation.py:1-18`)
  x'i fix(0)'lar ve B'nin backward reifikasyonu gap'i [L,U] DIŞINA iter —
  kapatılan aday başına yeni bir aktif disjunction. Level 0.4 (~%40 kenar
  kapsama) net kazançtı; level 0.7 (833 yön) sıfır incumbent verdi
  (`runs/warm_start_elastic_level07.log`). "Daha çok kapat → daha kolay"
  YANLIŞ; optimal bir kapatma bütçesi var → küçük artımlar.
- **Warm-start kabulü ayırt edici değil**: level 0.4 elastiğinde de
  `warm_start_confirmed_in_log=false` ama incumbent geldi
  (`runs/warm_start_elastic_20260712T141226Z.log.json`). Fark saf model
  zorluğu → tur tasarımında warm-start onarımı kritik-yol değil.
- **Conflict graph = perfect matching**: her kenar bir (o,d,gun) çiftinin
  iki yönünü bağlar, her yön tam bir çifte ait
  (`src/model/deactivation.py:53-65`) → ağırlıklı vertex cover kenar başına
  bağımsız "ucuz ucu seç" kararına çöker; `greedy_cover` bu yapıda exact.
  Master problem için SCIP/CP-SAT gereksiz.
- **LNS kapatmaları kendisi gerçekleştirir**: öldürülen-ama-henüz-itilmemiş
  çiftler slack'te görünmeye devam eder → worst-pair seçiminde doğal hedef
  olur → alt-model (200-800 instance) zamanları pencere dışına küçük ölçekte
  iter. Tam-model elastiğe tur başına girmeye gerek yok → 0.7-tipi kök-düğüm
  ölümü yapısal olarak baypas.
- **Validator'ın E1/E2 aktivasyonu seçim-bazlı**
  (`src/validate/independent_validator.py:311-338` E1-koşullu sayımlar,
  `:354-377` E2 Jbest'i yalnız `selected_connections`'tan; bir tarafı boş
  çift atlanır) ve **ters-B kontrolü yok** (achievable-ama-seçilmemiş
  bağlantı ihlal sayılmıyor) → C1 mekanik olarak mümkün. Ancak bu,
  `docs/model.md`'nin B semantiğiyle (çift yönlü reifikasyon, "uygun olan
  sunulmak zorunda") çelişir — D1 kararı tam da bunu reddetmek için verildi.
  C1 bu yüzden yalnızca sigorta (bkz. §0.1).
- **`compute_pair_slack` KARAR-0/0b hizalı** (`src/model/lns.py`):
  conditional E1 + Γ-muaf dışlama; x'i zamanlardan türetir (B semantiği).
  Kampanyanın kanonik Σslack metriği budur.
- **`run_lns.py` başlangıcı sabit** (`run_lns.py:72`,
  `runs/warm_start_elastic_output.json`) → `--reference` bayrağı gerekli.
  `--deactivation-file` her iki script'te mevcut (M5h Kapı-1/2).

## 3. Bileşenler

Model çekirdeğine dokunulmaz; tüm iş `scripts/` + bir CLI bayrağı.

### 3.1 `scripts/diagnose_residual_repair.py` (Adım-0, salt-okunur)

Girdi: en-iyi partial + tek candidate build. Her ihlalli çift için:
- E1/E2 slack dökümü; iki yönün D2-killability'si (`is_direction_killable`);
- `n_candidates`, `n_selected`, rho;
- **yön-başına gerçek yerel ödül katkısı**: slot zinciri Σ rho·w_c(j)
  (seçili bağlantı sayısından) + rank katkısı rho·W(r) (output'un
  `ranking_results`'ından). Bu tanım hem C1'in "hangi yönü düşür" hem
  kampanyanın "hangi yönü kapat" maliyeti — D4 proxy'sinden daha doğru.

Toplamlar: both-unkillable çift sayısı (dürüst yolun tavanı — >%30 ise
raporda açıkça işaretlenir), forced-on aday içeren yön sayısı, C1 toplam
ödül kaybı tahmini, killable-cover kapsam oranı, istasyon kümeleri
(VCE/PEK/AMS...) dökümü. Çıktı: `runs/residual_repair_diagnosis.json` +
konsol özeti.

### 3.2 `scripts/make_underclaim_floor.py` (C1 sigortası)

Adım-0'dan sonra, kampanyadan önce koşulur. Her ihlalli çiftte
düşük-ödül-katkılı yönün `selected_connections` girdileri + o
(o,d,gun)'un `ranking_results` girdisi düşülür → `recompute_objective` ile
objective yeniden hesaplanıp yazılır → strict `validate_output`.

- Çıktı: `runs/underclaim_floor_output.json` + sidecar
  `runs/underclaim_floor_note.json` (düşen bağlantı sayısı, önce/sonra
  objective, kırılan çift sayısı, B-semantiği risk paragrafı).
- **`outputs/` dizinine ASLA yazmaz** (§0.5 ile tutarlı).
- valid=False çıkarsa ihlal listesiyle raporlanır (beklenmiyor: zamanlar
  elastik-feasible noktadan geliyor — A/G/F elastik modelde HARD'dı ve
  zamanlar değişmiyor; E1/E2 muafiyeti validator'ın seçim-bazlı
  aktivasyonundan).
- Not: düşülen yönlerin pencere-içi bağlantıları tarifede fiziksel olarak
  uçmaya devam eder — under-claim'in tanımı budur; sidecar not bunu açık
  yazar.

### 3.3 `run_lns.py --reference <path>` bayrağı

Verilen output-şemalı JSON'dan başlangıç referansını yükler; bayrak
verilmezse bugünkü davranış (`STARTING_INCUMBENT`) bire bir korunur.

### 3.4 `scripts/run_residual_repair.py` (kampanya orkestratörü)

Tur döngüsü, A/B eskalasyonu, log ve keep-best; solve'ları
`run_lns.py`/`warm_start_elastic.py` subprocess'leri olarak koşar
(mevcut `subprocess_watchdog` deseni). `--dry-run` modu solver'sız tüm
karar mantığını (cover seçimi, dosya üretimi, eskalasyon, keep-best) işletir.

## 4. Kampanya protokolü (normatif)

Toplam bütçe: **4 saat duvar-saati** (bu gece). Başlangıç referansı:
`runs/lns_best_partial_20260712T150223Z.json`. Başlangıç kapatma seti:
`runs/conflict_deactivation_level04_directions.json`. Config: tüm adımlar
`src/config/standard.yaml` + `src/config/paths.py` full-data yollarıyla
(adjustable_window_min=180, `e1_activation: conditional`, KARAR-0b muafiyeti)
— önceki kampanyalarla bire bir karşılaştırılabilirlik için hiçbir düğme
değiştirilmez.

### 4.1 Tur yapısı (A modu)

1. Referanstan residual hesapla: `compute_pair_slack` (conditional,
   Γ-muaf hariç), halihazırda kapatılmış çiftler düşülür.
2. **Worst-K=30** çift (toplam slack'e göre; E2 dakika-ağırlıklı olduğundan
   doğal öncelik onlarda): her çiftte killable yönlerden düşük-ödül-katkılı
   olanı kapat. Both-unkillable çiftler K'ya sayılmaz, "equalization-only"
   listesinde raporlanır.
3. Kapatma dosyası: en-iyi-bilinen set ∪ bu turun eklemeleri →
   `runs/residual_repair_round<N>_directions.json`.
4. `run_lns --reference <en-iyi-partial> --deactivation-file <roundN>
   --selection component --builder fix --max-wall-sec 2400` (40 dk;
   diğer düğmeler default, seed=42; builder seçimi için §4.8).
5. Tur sonu ölçüm + log + keep-best kararı.

### 4.2 Tur logu (her tur, diske anında)

`runs/residual_repair_campaign_<ts>/round_<N>.json` + konsolide
`campaign_log.json`. Alanlar (kullanıcının yedi zorunlu alanı + iki döküm):

- `sigma_slack` (kanonik metrik) ve iki dökümü: kapatılmış-ama-henüz-
  itilmemiş çiftlerdeki slack / açık çiftlerdeki slack
- `e1_pairs_violated`, `e2_pairs_violated`
- `killed_direction_count` (kümülatif + bu tur)
- `reward_loss_estimate` (kümülatif, §3.1 yerel-katkı tanımıyla)
- `validator_status` (Σslack=0 ise strict koşulur; değilse `"not-run"`)
- `partial_output_path` (bu turun en-iyi partial'ı)
- `next_repair_decision` (devam-A / eskalasyon-B / dur + gerekçe)

### 4.3 Keep-best

Tur Σslack'i iyileştirmediyse: referans DEĞİŞMEZ ve **turun kapatma
eklemeleri geri alınır** — kapatma seti yalnızca başarı üzerinden monoton
büyür. İyileştirdiyse: yeni partial referans olur, eklemeler kalıcılaşır.

### 4.4 Adaptif K (A ile devam edilirse)

Tur-başı düşüş mevcut Σslack'in ≥%8'i ise K iki katına (tavan 100);
değilse K sabit.

### 4.5 A→B eskalasyon kuralı (ilk 2 tur sonunda)

Kullanıcının iki talimatının uzlaştırılması (bütçe cevabındaki "hiç düşüş
yoksa erken dur" + yaklaşım cevabındaki "düşüş yok/çok küçükse B'ye geç"):

- Toplam düşüş **≥ %5** (Σslack ≤ 10396.8): **A ile devam** (§4.4 adaptif K).
- Toplam düşüş **0 < düşüş < %5**: kalan bütçenin tamamı **B moduna**.
- Toplam düşüş **= 0 (hiç)**: önce mekanik sağlamlık kontrolü (kapatmalar
  gerçekten uygulanmış mı, LNS alt-çözümleri koşmuş mu). Mekanik SAĞLAMSA
  "çok küçük" muamelesi → B'ye geç; mekanik BOZUKSA **erken dur** + teşhis
  raporu kullanıcıya.

### 4.6 B modu

Killable-kapsanabilir TÜM residual çiftler tek sette kapatılır →
`warm_start_elastic --deactivation-file <B-seti> --time-limit-sec 900` →
kalan bütçenin tamamı `run_lns` (aynı set, `--reference` en-iyi partial).
warm_start_elastic watchdog'a takılırsa (0.7 riski) atlanır ve doğrudan
LNS-only devam edilir (B'nin kendi Plan-B'si).

### 4.7 Genel dur koşulları ve validator smoke (kullanıcı düzeltmesi #2)

- **Σslack = 0** → strict `validate_output` → **valid=True ise DUR**:
  kullanıcıya rapor; `outputs/full_data_output.json` yazılmaz, onay beklenir.
  (Σslack=0 ⇒ strict-valid beklenir; yine de tek otorite validator'dır.)
- **Smoke koşusu**: keep-best anlamlı düştüğünde (§4.4 ile aynı eşik: tur
  düşüşü mevcut Σslack'in ≥%8'i) strict validator o turun partial'ında
  OPSİYONEL olarak koşulur ve sonucu tur loguna yazılır
  (`validator_status: "smoke:invalid(E1=..,E2=..,diğer=..)"`). Amaç
  E1/E2 dışı ailelerde (A/G/F/pencere/rank) sürpriz olmadığını erkenden
  teyit etmek — böylece "Σslack=0 ⇒ valid" çıkarımı güvenli kalır. Nihai
  başarı kriteri DEĞİŞMEZ: valid=True şart + kullanıcıya rapor olmadan
  `outputs/` yazılmaz.
- **4h duvar** → sabah-değerlendirme raporu (kampanya logu + öneri).
- §4.5'in erken-dur dalı.

### 4.8 Builder politikası (kullanıcı düzeltmesi #1)

Kullanıcı direktifi: fix'e kör bağlı kalınmaz; folded'ın hız avantajı
(iterasyon başına çok daha küçük model) mümkün olan her yerde kullanılır.
Kod gerçeği: `--deactivation-file` bugün `--builder folded` ile
BİRLEŞTİRİLEMİYOR (`run_lns.py:216-218` hard error) — folded builder donuk
adaylara gerçek `x` değişkeni vermez, donuk bir kill edilmiş yönün x=0'ı
oraya işlenemez. Not: en güncel büyük kazanım (14100→10944, M5h level04)
fix+deactivation ile geldi; folded'ın kazanımları deactivation'sız
kampanyalardandı (M5e-3b, M5h Kapı-3b). Politika:

- **Kill içeren turlar** (kampanyanın normali): `--builder fix` (zorunlu).
- **Round-1 fallback**: ilk tur yavaş/ilerlemesiz biterse (mekanik sağlam),
  AYNI referanstan bir kez `--builder folded` İLE ve bu turun kill'leri
  OLMADAN (folded kill taşıyamadığından saf-yoğunlaştırma) yeniden denenir —
  bu bir A/B teşhisi: folded-kill'siz kazanıyorsa kaldıraç kill değildir,
  sabah raporuna "mekanik pivot" önerisi düşülür.
- **Folded+deactivation desteği** (sabah opsiyonu, gece kapsam dışı):
  doğru semantik "kill edilen yönün instance'ları free-set'e zorla dahil"
  gerektirir — aksi halde donuk killed adaylar sahte x=0 sabitiyle kanonik
  Σslack muhasebesinden sapar (bkz. §8).

## 5. Hata durumları

- run_lns/warm_start_elastic subprocess çökmesi veya watchdog: tur
  `"failed"` loglanır, referans ve kapatma seti korunur, sonraki tur devam.
- Γ-muaf çift seti tur başında bir kez hesaplanır, kampanya boyunca sabit.
- Determinizm: seed=42 sabit; cover eşitlik-kırıcıları D4 deseniyle
  deterministik.
- Tüm ara durum diske persist — süreç ölse bile kampanya son turdan devam
  edebilir (`campaign_log.json` kaldığı yeri bilir).

## 6. Test planı (TDD; mevcut 380+ test yeşil kalır)

- `--reference`: (a) bayraksız davranış bire bir eski hali, (b) verilen
  dosyadan yükleme, (c) olmayan dosya → net hata.
- Teşhis: sentetik mini-fixture'da bilinen killability/ödül-katkı değerleri.
- C1: sentetik mini-output'ta — düşürme sonrası validator'ın E1/E2'yi
  atladığı, objective recompute tutarlılığı, sidecar not üretimi,
  `outputs/`'a yazmadığı.
- Orkestratör: `--dry-run` ile cover seçimi / eskalasyon kuralı (üç dal:
  ≥%5, 0<x<%5, =0) / keep-best geri-alma / log alanlarının tamlığı.

## 7. Kapsam dışı (bilinçli)

- Rapor/STATUS.md entegrasyonu: sabah değerlendirmesinden sonra ayrı iş.
- SCIP portfolio denemesi: bu gecenin bütçesinde değil (sabah opsiyonu).
- Folded builder'a deactivation desteği: sabah opsiyonu (§4.8) — gece
  kampanyası buna gate'lenmez.
- ML katmanı yok: §3.1'in deterministic ödül-katkı skoru maliyet tanımıdır;
  rapor anlatısında "AI-assisted prioritization" ancak bu haliyle ve
  dürüstçe anlatılır.
- Gurobi: lisans engeli değişmedi (M5c bulgusu).

## 8. Riskler ve açık noktalar

- **Both-unkillable oranı bilinmiyor** — Adım-0 ölçer. Yüksekse dürüst
  yolun tavanı Σslack>0'da kalır; o durumda kalan çiftler için tek yol
  LNS'in zaman-eşitlemesi, o da bugüne dek plato yaptı → sabah kararı.
- **C1'in yorumsal kırılganlığı**: organizatör değerlendirmeyi zamanlardan
  türetirse C1 çıktısı onların gözünde ihlallidir; bu risk sidecar notta ve
  (girerse) raporda açık yazılır. C1 hiçbir koşulda "ana çözüm" diye
  sunulmaz.
- **E1-only çiftler** (küçük, sayı-bazlı slack): worst-K sıralamasında sona
  kalırlar; kampanya E2'yi bitirip onlara ulaşamadan 4h dolabilir — sabah
  raporunda kalan-iş olarak görünür.
- **Folded+kill semantik tuzağı**: donuk killed adayı x=0 SABİTİ yapmak,
  zamanı pencere-içindeyken "sunulmuyor" saymaktır — sub-model içi
  under-claim. compute_pair_slack (x'i ZAMANDAN türetir) bunu reddeder;
  keep-best sahte iyileşmeleri zaten eler ama turlar boşa yanar. Bu yüzden
  §4.8'in "free-set'e zorla dahil" semantiği olmadan folded'a kill
  bağlanmayacak.

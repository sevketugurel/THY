# LP Anatomisi (2026-07-09/10, M5c)

Full-data step1 modelinin (18118 aday, tüm A-G aktif) KÖK LP gevşemesi
(tüm Binary/Integer domain'ler continuous'a gevşetildi, aynı bounds) tek
başına çözüldü — `scripts/lp_anatomy.py`, kod değişikliği YOK, yalnızca
analiz. Amaç: MIP'in kök-düğümde cut üretimine takılıp kalmasının (dual
bound 5.53M→4.90M sürünerek, sıfır incumbent) bir SOLVER sınırlaması mı
yoksa bir FORMÜLASYON gevşekliği/boyutu sorunu mu olduğunu ayırt etmek.

## Özet sayılar

| Metrik | Değer |
|---|---|
| LP çözüm süresi | 172.0s |
| LP amaç değeri | 5,258,422.37 |
| Teorik tavan (veri-only, çözümsüz) | 8,081,699.10 |
| **LP/tavan oranı** | **%65.07** |
| Toplam kısıt satırı | 756,174 |
| Model kurulum süresi | 27.5s |

**LP/tavan oranı %65** — AŞIRI gevşek değil (bir "kayıp" formülasyon %95+
gösterirdi), ama MIP'in kendi kök-düğüm cut'larıyla ulaştığı sınır (~4.90M)
LP değerinden (5.26M) zaten daha düşük — yani MIP'in cut süreci ÇALIŞIYOR,
sadece ÇOK YAVAŞ. Bu, LP'nin "aşırı gevşek" olmaktan çok, **modelin
BÜYÜKLÜĞÜNÜN** (satır sayısı) kök-düğüm cut üretimini yavaşlattığına işaret
ediyor.

## Satır sayısı ailesi bazında — F BASKIN (bulgunun kalbi)

| Aile | Satır | Toplam içindeki pay |
|---|---|---|
| **F (kova/kapasite)** | **405,982** | **%53.7** |
| D (rakip yenme/sıralama) | 128,813 | %17.0 |
| E2 (JT-farkı) | 94,272 | %12.5 |
| B (bağlantı uygunluğu) | 72,472 | %9.6 |
| C (monoton slot) | 18,118 | %2.4 |
| gap_definition | 18,118 | %2.4 |
| G (düzenlilik) | 10,688 | %1.4 |
| E1 (yönsel denge) | 6,516 | %0.9 |
| A (rotasyon) | 1,195 | %0.2 |

**F TEK BAŞINA modelin satırlarının %53.7'sini oluşturuyor** — özellikle
`f_dep_lower`/`f_dep_upper`/`f_arr_lower`/`f_arr_upper` (toplam 398,490 satır,
F'nin İÇİNDE bile %98'i). Bu dört kısıt ailesi, HER (role,flno,gun) uçuş
örneği için, o örneğin ±180dk ayarlanabilir penceresinin ULAŞABİLDİĞİ HER
10-dakikalık kovaya (`derive_window_reachable_buckets`) AYRI bir Big-M
kısıtı kuruyor — ±180dk pencere / 10dk kova ≈ 36-37 ulaşılabilir kova, her
biri 2 kısıt (lower+upper) × 2 yön (dep+arr) = uçuş örneği başına ~140-150
satır. 2688 dep + 2697 arr örneğiyle çarpınca ~400K satır ortaya çıkıyor.

**Yorum**: HiGHS'in kök-düğümde binlerce cut turu üretip hiçbir B&B
düğümüne inememesi, muhtemelen bu 400K satırlık F alt-modelinin cut
üretimini domine etmesinden kaynaklanıyor — F'nin kendisi YANLIŞ değil
(brief'in "her ayarlanabilir kalkış/varış tam olarak bir kovaya atanmalı"
gereğini doğru karşılıyor, `docs/baseline_autopsy.md` §3), ama
per-reachable-bucket Big-M kodlaması ÇOK FAZLA satır üretiyor.

## Fractionality haritası (LP çözümünde hangi Binary ailesi en kararsız)

| Aile | Fractional oran | n_fractional / n_total | Anlam |
|---|---|---|---|
| **w (E2 selector)** | **%50.3** | 9107/18118 | E2'nin "hangi aday Jbest'i belirliyor" seçici değişkeni — LP'de neredeyse YARISI kararsız |
| **x (bağlantı seçimi)** | **%44.5** | 8055/18118 | Temel "bu bağlantı sunuluyor mu" kararı bile LP'de büyük ölçüde belirsiz |
| a_dir (E2 aktivasyon) | %22.3 | 1702/7642 | Orta düzey kararsız |
| beat (D) | %14.0 | 4731/33748 | Orta-düşük |
| beaten (D OR-agg) | %10.2 | 1798/17607 | Düşük |
| z_dep (F kova-dep) | %8.2 | 8118/99456 | Düşük (F satır sayısı yüksek ama kendisi göreceli KARARLI) |
| z_arr (F kova-arr) | %6.1 | 6048/99789 | Düşük |
| y (B backward) | %2.6 | 469/18118 | Çok düşük (B'nin reifikasyonu LP'de zaten sıkı) |
| rank_onehot (D) | %0.5 | 94/17607 | Neredeyse tamamen sıkı |

**En kararsız ikili: w (%50.3) ve x (%44.5)** — E2'nin argmin-sandviç
seçicisi ve temel bağlantı-seçim değişkeni. F'nin z_dep/z_arr'ı (satır
sayısı en yüksek aile) aslında NİSPETEN kararlı (%6-8) — yani F'nin sorunu
LP GEVŞEKLİĞİ değil, SAF SATIR HACMİ (cut üretimi yavaşlatıyor).

## Sonuç — iki AYRI, TAMAMLAYICI tightening hedefi

1. **F'nin satır patlaması (öncelik #1, HIZ için)**: 400K satırlık
   per-reachable-bucket Big-M kodlamasını küçültmek doğrudan kök-düğüm
   cut süresini azaltabilir. Aday: ulaşılabilir kova sayısını azaltan bir
   ön-filtre (ör. yalnızca GERÇEKTEN rekabetçi/sıkışık kovalar için tam
   Big-M kur, geri kalanı gevşek bırak) — dikkatli tasarım gerekir
   (yanlış budama gerçek kapasite ihlallerini kaçırabilir).
2. **w/x'in fractionality'si (öncelik #2, LP KALİTESİ için)**: E2'nin w
   seçicisi ve temel x'in LP'de bu kadar kararsız olması, kullanıcının
   önerdiği "sabit-sonuçlu beat'leri veriye katla" (D için) VE benzer bir
   "sabit-sonuçlu w/x'i veriye katla" fikrini haklı çıkarıyor — bir adayın
   J_hi/J_lo'su Jbest bounds'una göre zaten belirliyse (asla seçici
   olamaz/her zaman seçici), w'yi sabitlemek LP'yi sıkılaştırabilir.

**Bu iki hedef BAĞIMSIZ ve TAMAMLAYICI** — F satır azaltımı HIZI, w/x
sıkılaştırması LP KALİTESİNİ (ve dolayısıyla dolaylı olarak hızı) hedefliyor.
İkisi birden denenecek, fixture'da 668.75 korunarak.

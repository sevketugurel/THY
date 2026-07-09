# Çıktı Formatı — Brief §5 Madde 7 Karşılama Checklist'i

Brief'in §5 "Teslim Edilecekler" madde 7'si: *"Çıktı dosyası: seçilen bağlantılar,
ayarlanan IST saatleri, O–D bazında yenilen rakipler ve toplam amaç değeri
(belirtilen formatta)."* Brief kesin bir şema VERMİYOR (plan §7 "Açık Sorular" —
organizatöre soruldu, cevap gelmedi, M1'de makul bir JSON varsayıldı; bkz.
`src/output/writer.py` docstring). Bu dosya, o varsayılan şemanın brief'in 4
gereksinimini eksiksiz karşıladığını gösteren tek-tek eşleme tablosudur.

Üretici: `src/output/writer.py::write_output`. Tüketici: `src/validate/independent_validator.py`
(kendi bağımsız yeniden-hesaplamasıyla bu dosyayı doğrular).

## Brief madde 7 ↔ şema alanı eşlemesi

| Brief gereksinimi | JSON alanı | Kaynak |
|---|---|---|
| Toplam amaç değeri | `objective_value` | `SolveResult.objective_value` |
| Seçilen bağlantılar | `selected_connections[]` — `{od, flno1, flno2, gun, gap_min}` | `SolveResult.selected` (x=1 olanlar), `gap_values` (gerçek çözülmüş gap, statik baseline DEĞİL — M1 kararı) |
| Ayarlanan IST saatleri | `adjusted_flight_times[]` — `{role, flno, gun, time_min}` | `SolveResult.arr_times` + `dep_times` |
| O–D bazında yenilen rakipler | `ranking_results[]` — `{o, d, gun, rank, beaten_rivals}` | `SolveResult.rank_values` + `beaten_rivals` (M2, D kısıtı) |

## Ek alanlar (brief tarafından İSTENMEMİŞ, şeffaflık için eklendi)

| Alan | Amaç |
|---|---|
| `k_od_sources[]` — `{o, d, source}` | M5: her pazarın $K_{od}$'unun doğrudan gözlemden mi (`"direct"`) yoksa LS-tahmininden mi (`"estimated"`) geldiğini raporlar (VARSAYIM-8) — bir rapor okuyucusunun hangi sayıların daha ince veriye dayandığını görmesini sağlar. |
| `solver_metrics` — `{status, solve_time_sec}` | Çözüm durumu (optimal/time_limit) + süre — §6 kriter 3 "Hesaplama Performansı" için kanıt. |

## Determinizm

Tüm liste alanları doğal anahtarlarına göre sıralanır (`selected_connections`:
`(od,flno1,flno2)`, `adjusted_flight_times`: `(role,flno,gun)`, `ranking_results`:
`(o,d,gun)`, `k_od_sources`: `(o,d)`) — aynı girdi + aynı seed için byte-özdeşlik
(brief madde 9 "deterministik ... çalıştırma" + §6 kriter 4 "tekrar üretilebilir
sonuçlar"). `tests/unit/test_output_writer.py::test_write_output_is_deterministic`
bunu doğrular. **Not**: bu byte-özdeşlik garantisi yalnızca fixture/küçük
solve'lar için geçerli — zaman-limitli paralel MIP'te (full-data production
koşusu) solver'ın kendi iç dallanma sırası thread zamanlamasına bağlı
olabileceğinden objective_value'nin KENDİSİ deterministik olsa bile (aynı
gap toleransında aynı veya daha iyi bulunur), hangi ALTERNATİF optimal çözümün
seçildiği garanti edilmez (bkz. CLAUDE.md "Aktif Otonom Tur #2" §DAL A/B notu).

## Validator ile ilişki

`independent_validator.py`, `src.model.*`/`src.candidates.*`'tan import ALMAZ —
bu dosyanın KENDİ raporladığı `adjusted_flight_times`'tan gap/rotasyon/düzenlilik/kapasite
ihlallerini bağımsız yeniden hesaplar. Yani bu şema yalnızca bir "sonuç raporu"
değil, aynı zamanda validator'ın TEK girdisi — şemadaki her alan doğrulanabilir
olmak zorunda (rastgele/insan-okunur metin değil, yapılandırılmış veri).

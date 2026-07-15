# Çıktı Formatı — Brief §5 Madde 7 Karşılama Checklist'i

Brief'in §5 "Teslim Edilecekler" madde 7'si: *"Çıktı dosyası: seçilen bağlantılar,
ayarlanan IST saatleri, O–D bazında yenilen rakipler ve toplam amaç değeri
(belirtilen formatta)."* Brief kesin bir şema VERMİYOR (plan §7 "Açık Sorular" —
organizatöre soruldu, cevap gelmedi, M1'de makul bir JSON varsayıldı; bkz.
`src/output/writer.py` docstring). Bu dosya, o varsayılan şemanın brief'in 4
gereksinimini eksiksiz karşıladığını gösteren tek-tek eşleme tablosudur.

Üreticiler: strict yol için `src/output/writer.py::write_output`, benchmark
yolu için `src/benchmark/writer.py::write_benchmark_output`. Tüketici:
`src/validate/independent_validator.py` (kendi bağımsız yeniden-hesaplamasıyla
bu dosyayı doğrular).

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
| `solver_metrics` — `{status, solve_time_sec}` | Çözüm durumu (optimal/time_limit) + süre — §6 kriter 3 "Hesaplama Performansı" için kanıt. Kapı-5 (M5f): `status` ayrıca `"no_feasible_solution_found"` da olabilir — üretim merdiveninin (`main.py --full-data`) HİÇBİR adımı bağımsız validator'dan geçen bir nokta bulamadığında yazılan teşhis çıktısı; bu durumda `objective_value: null` ve `selected_connections`/`adjusted_flight_times`/`ranking_results` HEPSİ boş liste — hiçbir ihlalli tarife dosyaya yazılmaz (bkz. `docs/STATUS.md` Kapı-5). |
| `diagnostics` | Benchmark-safe `--full-data` yolunda eklenir: `mode`, `strict_feasible`, `claim_complete`, `claim_check.{missing_claims,extra_claims}`, `strict_violations.{total,total_pairs,by_family,examples}`, `selection_priority`, `seed`, `baseline_reference`, `constraint_interpretation`. Strict-clean olmayan benchmark çıktısı bu alanla açık teşhis taşır; exit 0 fizibilite garantisi değildir. |

## Benchmark status sözlüğü

| `solver_metrics.status` | Anlamı |
|---|---|
| `baseline_floor_with_strict_violations` | Floor emniyet çıktısı; final ancak seed/improve yoksa fallback olarak kalır. |
| `heuristic_incumbent_with_strict_violations` | Beklenen full-data benchmark finali: claim-complete, recompute-objective'li, hard-family temiz seed-derived incumbent; strict E1/E2 ihlalleri diagnostics'te açıktır. |
| `strict_feasible_incumbent` | Improve aşaması strict-clean bir incumbent bulup seçim sırasını iyileştirdi. |
| `no_feasible_solution_found` | `--strict-gate` yolunun eski null-teşhis davranışı; benchmark varsayılanı değildir. |

Terminoloji kuralı: strict-clean olmayan benchmark çıktısı fizibilite iddiası
taşımaz. `valid=True` yalnız fixture/strict-gate gibi gerçekten strict-clean
yollar için meşrudur.

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

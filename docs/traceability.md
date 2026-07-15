# Kod↔Model-Dokümanı İzlenebilirlik Tablosu

`docs/CLOSING_PLAN.md` Kapı-6 (soru 6'nın cevabı): A, B, C, D, E1, E2, F, G
+ amaç fonksiyonu için — `docs/model.md` formülü ↔ `src/model/constraints_*.py`
fonksiyonu ↔ bağımsız validator kontrolü ↔ test dosyası. Her hücre bu
commit'te elle doğrulandı; bir sonraki kısıt/kod değişikliğinde bu tablo
AYNI commit'te güncellenmelidir (sapma = teslim engeli, `CLAUDE.md`
Milestone Disiplini).

| # | Aile | `docs/model.md` bölümü | Model kodu | Bağımsız validator kontrolü | Test dosyası |
|---|---|---|---|---|---|
| 1 | A (rotasyon) | §3 "A — Zaman Sınırları ve Uçak Rotasyonu" | `src/model/constraints_operations.py::add_a_constraints` | `independent_validator.py` — `"rotation FlNo"` prefix'li ihlaller, `_match_rotation_legs_independent` (VARSAYIM-10/11 bağımsız yeniden-uygulaması) | `tests/solve/test_m3_constraints_a.py` |
| 2 | B (bağlantı uygunluğu) | §2 "B — Bağlantı Uygunluğu" | `src/model/constraints_selection.py::add_b_constraints` | `independent_validator.py` — `"adjusted_flight_times entry"` (pencere sınırı) + `"connection"` (gap∈[L,U] + varlık) prefix'li ihlaller | `tests/solve/test_m1_constraints_b.py` |
| 3 | C (azalan getiri) | §2 "C — Bağlantı Seçimi ve Azalan Getiri" | `src/model/constraints_selection.py::add_c_constraints` | Doğrudan kısıt kontrolü YOK — C, x/gap üzerinde bir kısıt KURMUYOR (yalnızca ödül hesaplama), `recompute_objective`'in bağlantı-sayısı bileşeni C'nin ödül mantığını bağımsız yeniden hesaplar | `tests/solve/test_m1_constraints_c.py` |
| 4 | D (rakip yenme + sıralama) | §2 "D — Rakip Yenme ve Sıralama" | `src/model/constraints_competition.py::add_d_constraints` + `add_rank_onehot` | `independent_validator.py` — `"ranking_results"` prefix'li ihlaller (rank/beaten_rivals bağımsız yeniden-türetimi) | `tests/solve/test_m2_constraints_d.py`, `tests/solve/test_m2_ranking_reward.py` |
| 5 | E1 (yönsel sayı dengesi) | §3 "E1 — Yönsel Sayı Dengesi (KARAR-0 koşullu aktivasyon)" | `src/model/constraints_balance.py::add_e1_constraints` (+ `constraints_elastic.py::add_elastic_e1_constraints`/`_folded`) | `independent_validator.py` — `"E1"` prefix'li ihlaller, `e1_activation` parametresiyle koşullu/literal modu ayırt eder | `tests/solve/test_m4_constraints_e1.py` (her iki mod da), `tests/unit/test_big_m.py` (`derive_e1_pair_big_m`) |
| 6 | E2 (yön-arası JT farkı) | §3 "E2 — Yön-Arası Seyahat Süresi Farkı" | `src/model/constraints_balance.py::add_e2_constraints` (+ `constraints_elastic.py::add_elastic_e2_constraints`/`_folded`) | `independent_validator.py` — `"E2"` prefix'li ihlaller; KARAR-0b statik muafiyeti `_is_gamma_statically_infeasible`/`_structural_j_best_case_range` ile bağımsız yeniden-uygulanır | `tests/solve/test_m4_constraints_e2.py` (KARAR-0b testleri dahil) |
| 7 | F (hub kova/kapasite) | §3 "F — Hub Kova/Kapasite Bağlama" | `src/model/constraints_capacity.py::add_f_constraints` | `independent_validator.py` — `"F kova"` prefix'li ihlaller (bağımsız kova-sayım) | `tests/solve/test_m4_constraints_f.py` |
| 8 | G (düzenlilik) | §3 "G — Tarife Düzenliliği" | `src/model/constraints_operations.py::add_g_constraints` (+ `add_g_constraints_folded`) | `independent_validator.py` — `"regularity (x_dev)"` prefix'li ihlaller, `_cluster_flight_days_independent` (VARSAYIM-9 bağımsız yeniden-uygulaması) | `tests/solve/test_m3_constraints_g.py` |
| 9 | Amaç fonksiyonu (C + D ödülleri) | §4 "Amaç Fonksiyonu" | `src/model/objective.py::add_connection_reward_objective` + `add_ranking_reward_objective` | `independent_validator.py::recompute_objective` (`src.model`/`src.candidates` import ETMEZ, raporlanan `selected_connections`/`ranking_results`'tan bağımsız yeniden hesaplar) + `finalize_reported_objective` (resmi değer HER ZAMAN recompute, solver'ın kendi iddiası DEĞİL) | `tests/slow/test_bruteforce_oracle.py` (saf-Python brute-force, B+C+D), `tests/unit/test_validator.py` (`finalize_reported_objective` testleri) |

**Sapma taraması (bu commit)**: 9 satırın hepsi elle karşılaştırıldı —
kod↔doküman arasında formül/parametre uyuşmazlığı bulunmadı. E1/E2'nin
KARAR-0/KARAR-0b sonrası formülleri hem `docs/model.md`'de hem kodda
`M5f`/`KARAR-0`/`VARSAYIM-16`/`VARSAYIM-17` etiketleriyle çapraz
referanslı; validator'ın koşullu/statik-muafiyet mantığı model kodundan
BAĞIMSIZ olarak (aynı mantığı KOPYALAYARAK, import ETMEDEN) ayrı ayrı
uygulanmış durumda — bkz. her iki dosyanın kendi docstring'leri.

**2026-07-16 benchmark-safe notu**: `src/benchmark/*` üretim-yolu
orkestrasyonudur; `docs/model.md`'deki matematiksel modele dokunmaz. Improve
aşaması hâlâ aynı strict `build_model_m4`/ladder hattını kullanır; varsayılan
`--full-data` final seçimi ise `diagnostics` hard-family profiline göre
seed-derived incumbent'ı yayınlar.

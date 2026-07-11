# PROJE DENETİMİ (PROJECT AUDIT) — 2026-07-11

Kapsam/yöntem: CLAUDE.md; docs/ altındaki HER dosya (STATUS, decisions.md'nin
1190 satırının tamamı, ASSUMPTIONS.md 819 satır, model.md, report_outline,
organizer_questions, output_format, lp_anatomy, feasibility_certificates,
baseline_autopsy, block_time_cross_validation); brief PDF (7 sayfa, baştan
taze gözle yeniden okundu) + kick-off sunumu (11 sayfa); main.py +
src/ (30 modül) + tests/ (49 test dosyası) + scripts/ (29 script) envanteri;
git durumu (9 tag, izlenen dosyalar, ignore'lar, remote); runs/ envanteri
(140+ koşu artefaktı). Test koşusu bu oturumda kısmen yapılabildi (§3 —
harness'ın Bash onay sınıflandırıcısı aralıklı kesildi; bulunan KRİTİK
test-runner sorunu yine de kayda geçti).

---

## 1 · Tek bakışta: ne bitti / ne açık / ne riskli

| Alan | Durum | Kanıt |
|---|---|---|
| A–G tam formülasyon + lineerleştirme | ✅ Bitti | `build_model_m4`, tag zinciri m0→m5e-remeasured (9 tag) |
| Fixture doğrulama zinciri | ✅ Bitti | 668.75 = CLI = bağımsız `recompute_objective` = saf-Python brute-force oracle (`tests/slow/test_bruteforce_oracle.py`) |
| Bağımsız validator | ✅ Bitti | `src.model` import ETMEZ; M5b'de 3 kapsam düzeltmesi (E1 kapsam, E2 estimate-fallback, A exemption) |
| Veri v2 entegrasyonu (wrap-fix, Elapsed→K_od/R_o) | ✅ Bitti | `m5e-data-v2`, `m5e-remeasured`, VARSAYIM-14/15, provenance loglama |
| Solve altyapısı (dış bekçi, warm-start, elastik, LNS, fold) | ✅ Bitti ve kanıtlı | `subprocess_watchdog`, "MIP start solution is feasible" log kanıtı, LNS %9.7 gerçek azalma |
| **Full-data'da DOĞRULANMIŞ objective_value** | ❌ **YOK** | Projenin tek büyük açığı — tüm M5/M5c/M5d/M5e kampanyaları |
| Kök neden anlayışı | ✅ Çok açılı | 7+ bağımsız deneme aynı semptom; statik sertifikalar temiz; ihlal ayak izi ağın %85'i; **ana şüpheli artık formülasyon YORUMU (E1) + Γ ölçeği (E2)** — §8 |
| Teslimat paketleri (PDF/rapor/README/çıktı) | ⚠️ Yarım | §4 |

## 2 · Kanıt zinciri (tag'ler)

`m0-walking-skeleton` → `m1-core-objective` → `m2-competition` →
`m3-operations` → `m4-directional-capacity` → `m5-full-data` →
`m5c-diagnosis-closed` → `m5e-data-v2` → `m5e-remeasured`.
Hedeflenen `m5d-first-incumbent` / `m5e-first-incumbent` tag'leri
ÜRETİLEMEDİ (Σslack≈0'a ulaşılamadı). Working tree temiz, branch=main,
remote=github.com/sevketugurel/THY.git.

## 3 · Bu oturumda doğrulananlar / doğrulanamayanlar (dürüstlük kaydı)

**Doğrulandı:**
- `python -m pytest -m unit` → **186 passed** (1.89s).
- **KRİTİK BULGU: çıplak `pytest` KIRIK** — 49 collection error
  (`ModuleNotFoundError: No module named 'src'`). Kök neden: repo kökünde
  `conftest.py` YOK; `.venv/bin/pytest` CWD'yi `sys.path`'e koymaz,
  `python -m pytest` koyar. README ve CLAUDE.md "pytest" komutunu
  öğütlüyor — jüri bunu çalıştırırsa "çalışmayan kod" izlenimi doğar
  (Kriter 2 = 0 eşiği!). Düzeltme trivial (kök `conftest.py` veya
  `pytest.ini`'ye `pythonpath = .`), Kapı-0'da.
- Git hijyeni: yarışma VERİ dosyaları izlenmiyor (yalnızca sentetik
  fixture'lar izleniyor — doğru); `data_raw/` + koşu artefaktları ignore'lu.

**Bu oturumda doğrulanamadı (Kapı-0'ın ilk işi):**
- Tam suite (unit+solve+slow) yeniden koşusu — son commit'in iddiası
  141 unit + 106 solve + slow (≈313). Harness'ın Bash sınıflandırıcısı
  arızası nedeniyle arka plan koşusu başlatılamadı.
- Fixture CLI'ının (668.75, valid=True) yeniden koşusu — aynı neden.

## 4 · Brief §5 beş teslimat — durum + eksik listesi

| # | Teslimat | Durum | Eksikler |
|---|---|---|---|
| 5 | Matematiksel model dokümanı (PDF) | %80 | `docs/model.md` güncel ve formel; AMA (a) başlıktaki durum satırı bayat ("M4 kapanış ritüeli sırada"), (b) PDF'e dönüştürülmedi, (c) E1 kararı (bkz. §8) işlenecek |
| 6 | Çalışan kod (uçtan uca) | %70 | Fixture yolu uçtan uca kanıtlı; full-data yolu ÇALIŞIYOR ama feasible sonuç üretmiyor (aşağıda); çıplak `pytest` kırık (§3); üretim giriş noktası "her zaman geçerli çıktı ya da açık teşhisle sonlanır" garantisi VERMİYOR (time_limit'te ihlalli çıktı yazıp valid=False dönüyor) |
| 7 | Çıktı dosyası (belirtilen format) | %50 | Şema + writer + determinizm testi + brief-madde-7 eşleme tablosu var (`docs/output_format.md`); full-data için GEÇERLİ bir çıktı YOK (fixture çıktısı var) |
| 8 | Teknik rapor (≤6 sayfa) | %30 | Rubrik-haritalı iskelet hazır (`docs/report_outline.md`); metin yazılmadı; sonuç bölümü Kapı-3/4 sonucuna bağlı (iki dallı) |
| 9 | README (bağımlılık + tek komut + determinizm) | %60 | Var ve doğru yönde; AMA test komutu kırık haliyle belgelenmiş, `requirements.txt` pin'siz (`>=`), determinizm ifadesi README'de eksik (output_format.md'de dürüst hali var) |

## 5 · Eşik kuralları karşısında konum — "bugün teslim etsek ne olur"

| Eşik | Bugünkü dürüst cevap |
|---|---|
| Kod çalışmıyor / çıktı üretmiyor → Kriter 2 = 0 | `main.py --fixture` çalışıyor ve geçerli çıktı üretiyor. `--full-data` uçtan uca KOŞUYOR ama 1800s bütçede incumbent'sız kalır → çıktı `objective=None` olur. Jüri "pytest" koşarsa collection hatası görür. **Bugün: Kriter 2 fiilen 0.** |
| Örnek/gizli testte feasible çözüm yok → Kriter 2 = 0 | Full-data'da doğrulanmış feasible çözüm YOK. **Bugün: 0/25. En büyük tek risk ve kapanış planının ana hedefi.** |
| Kısıt ihlalli çıktı → diskalifiye | İhlalli hiçbir şey "sonuç" olarak işaretlenmiş değil (LNS partial'ları açıkça "teslim edilemez" etiketli). Üretim yolu time_limit'te ihlalli çıktıyı DOSYAYA yazıyor (valid=False raporluyor) — teslim paketine asla ihlalli dosya girmemesi Kapı-6'da yapısal hale getirilecek. **Bugün: diskalifiye riski yok, ama koruma insan disiplinine dayalı.** |
| Model↔kod tutarsızlığı → diskalifiye | Öz (kısıt formülleri) senkron görünüyor; kozmetik sapmalar var: model.md'nin durum satırı bayat; organizer_questions.md #6 `constraints_e1.py` diye VAR OLMAYAN dosyaya işaret ediyor (gerçek: `constraints_balance.py`). **Madde-madde denetim Kapı-6'da formel yapılacak.** |

## 6 · Rubrik haritası (6 kriter × güçlü/zayıf + tahmini konum)

| Kriter (ağırlık) | Güçlü yan | Zayıf yan | Tahmin |
|---|---|---|---|
| 1 Model doğruluğu (%30) | A–G tam, her kısıtta yazılı doğruluk argümanı, Big-M disiplini (≤1440 assert), 15 VARSAYIM belgeli, validator bağımsız | E1 yorumu hâlâ tek-okumalı (literal); VARSAYIM-5 (çok duraklı rotasyon) kapsam boşluğu | 22–26/30 |
| 2 Çözüm kalitesi (%25) | Fixture bağımsız-oracle'lı; elastik/LNS makinesi kanıtlı | **Full-data doğrulanmış değer YOK** | Bugün 0 → Branch A ile 15–20 |
| 3 Hesaplama perf. (%15) | F satır -%96.8, fold'lar, ladder, dış bekçi, LP anatomisi — güçlü ölçekleme hikâyesi | Kök-düğüm açılamadı; HiGHS time_limit güvenilmezliği (belgeli) | 8–11 |
| 4 Kod kalitesi (%15) | TDD (≈313 test), tek komut, determinizm testi, provenance | çıplak pytest kırık; pin'siz bağımlılıklar; 29 script'in 13'ü provenance'sız teşhis kalıntısı | düzeltmelerle 10–13 |
| 5 Teknik rapor (%10) | Rubrik-haritalı iskelet + zengin kanıt tablosu hazır | Metin yok | yazılınca 6–8 |
| 6 Yenilik (%5) | Statik fizibilite sertifikaları, component/fold LNS, bijective kova eşitliği, wrap-fix oracle | — | 3–4 |

## 7 · Kod-kalitesi bulguları (öncelikli liste)

**P0 (teslim engeli):**
1. Çıplak `pytest` collection hatası (§3) — kök `conftest.py` ekle; README/CLAUDE.md komutlarını doğrula.
2. `requirements.txt` pin'siz (`>=`) — teslimde `pip freeze` tabanlı kesin pin (tekrar üretilebilirlik, Kriter 4).
3. Üretim giriş noktası garantisi: `main.py --full-data` 1800s'te incumbent'sız kalırsa çıktısı işe yaramaz; "üretim merdiveni" (bkz. CLOSING_PLAN Kapı-5) main.py'ye bağlanmalı — gizli test dayanıklılığının kalbi.

**P1 (puan kaybettirir):**
4. `docs/model.md` durum satırı bayat; organizer_questions #6'daki dosya yolu yanlış.
5. `docs/README_full_data_input_dosyalari (1).docx` (organizatör veri paketinin README'si) git'te İZLENİYOR — "yarışma verisi repo'ya girmez" kuralının gri bölgesi; `data_raw/_organizer_source_package/`'a taşı + `git rm --cached` (brief/sunum PDF'leri "Genel (Public)" damgalı, kalabilir).
6. `main.py` provenance loglamıyor (6 kampanya script'i logluyor) — üretim yoluna da ekle.
7. `warm_start_elastic.py` Adım A bütçesi hardcoded 600s (3d'de keşfedildi) — CLI'ya çıkar.

**P2 (hijyen):**
8. scripts/ 29 dosya; ~13'ü M5c-öncesi teşhis kalıntısı — `scripts/diagnostics/` altına taşı veya README-scripts tablosuyla işaretle (silme — rapor kanıt zinciri).
9. `runs/` 140+ artefakt (gitignored, sorun değil) — kapanışta rapora girecek koşuların listesi sabitlenmeli.

## 8 · E1 durumu — denetim bulgusu (karar CLOSING_PLAN'da)

Mevcut kod E1'i KOŞULSUZ okur (yalnızca her iki yönde de yapısal aday
varsa kurulur; ama bir yön 0-SUNUMLU ise kısıt ihlal olur). Kanıt seti:
- Organizatörün KENDİ baseline'ı bu okumada **690 pair-gün ihlalli**
  (v1=v2, blok süresinden bağımsız).
- Ulaşılan her noktada E1 fazlalık oranı **medyan=p90=max=0.800 = 1−α**
  → ihlallerin ~tamamı "tek yön sıfır-sunum" vakası.
- Brief §7 ipucu: *"Koşullu (yalnızca her iki yön aktifken bağlayıcı)
  kısıtları doğru kurun; aksi halde pasif yönler DENGEYİ yapay olarak
  ihlal/zorlar"* — "denge" E-ailesinin adı; tarif edilen patoloji birebir
  E1'in tek-yön-sıfır vakası.
- Karşı kanıt (dürüstlük): E1 metninde E2'deki açık "koşullu aktivasyon"
  ifadesi YOK; literal okuma metinsel olarak savunulabilir ve HER ZAMAN
  tatmin edilebilir (iki yönü de sıfırlayarak) — yani infeasibility değil,
  belgeli "amaç bastırıcı" (VARSAYIM-6) ve Σslack kütlesinin ana kaynağı.
Karar + duyarlılık + hizalama planı: `docs/CLOSING_PLAN.md` Karar-0.

## 9 · Açık organizatör soruları

15 maddeden 2'si "veri ile çözüldü" (8, 14). Kritik açıklar: E1 formülü
(#6), Γ ölçeği (#12b), full-ölçek çözüm süresi beklentisi (#12), çıktı
formatı (output_format.md). Soru-cevap penceresi 16 Temmuz'a kadar açık —
kapanış planı cevap gelirse config-düzeyinde entegrasyon yolunu içeriyor.

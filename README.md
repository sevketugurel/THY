# THY IST Hub Tarife Optimizasyonu

TEKNOFEST "Yapay Zeka Destekli Havayolu Optimizasyonu" yarışması için Pyomo/HiGHS MIP.
Detaylı durum ve mimari kararlar için `CLAUDE.md`, matematiksel model için
`docs/model.md`, veri-kalitesi varsayımları için `ASSUMPTIONS.md`, teknik
rapor için `docs/report.md`, kod↔model izlenebilirliği için
`docs/traceability.md`.

## Veri

`data_raw/` klasörü yarışmanın gerçek girdi dosyalarını içerir (O&D bağlantı
tablosu, yolcu verisi, ranking ağırlıkları, flight pairs). **Bu dosyalar
repo'ya dahil değildir** (`.gitignore`'da hariç tutulmuştur) — veri kullanım
koşulları yeniden dağıtımı yasaklıyor. Çalıştırmak için 4 dosyayı `data_raw/`
altına yerel olarak yerleştirin (dosya adları için `CLAUDE.md`'ye bakın).

`tests/fixtures/` altındaki sentetik veri gerçek şemalarla birebir aynıdır ve
serbestçe paylaşılabilir; `--fixture` modu bunu kullanır, gerçek veri gerektirmez.

## Kurulum ve Çalıştırma

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python main.py --config src/config/standard.yaml --fixture   # sentetik veri
python main.py --config src/config/standard.yaml --full-data  # gerçek veri (data_raw/ gerekli)

pytest              # tüm testler
pytest -m unit      # solver'sız, <1sn
pytest -m solve     # küçük HiGHS solve, <60sn
```

## Üretim merdiveni ve garanti (`--full-data`)

`main.py --full-data` tek komutla bir merdiven koşar (`src/solve/ladder.py::solve_with_ladder`):
1. tam model (A–G), `config.time_limit_sec` bütçeli solve;
2. başarısızsa TEK bir elastik (A/B/E1/E2/F/G, slack-relaxed) solve denemesi,
   `config.elastic_time_limit_sec` bütçeli — Σslack≈0 ise strict-feasible nokta;
3. ikisi de olmazsa **hiçbir ihlalli tarife dosyaya YAZILMAZ** — şema-uyumlu
   bir teşhis çıktısı (`objective_value: null`, `solver_metrics.status:
   "no_feasible_solution_found"`, boş tarife) yazılır ve komut sıfır-olmayan
   bir çıkış koduyla döner.

Her adımın sonucu, dosyaya yazılmadan ÖNCE bağımsız validator'dan
(`src/validate/independent_validator.py`) sıfır ihlalle geçmek ZORUNDADIR —
bir adımın MIP çözücüsünden "optimal"/"feasible" durumu almış olması TEK
BAŞINA yeterli değildir. Not: adım 2, `scripts/run_lns.py`'nin çok-iterasyonlu
(dakikalarca süren) LNS kampanyasının yerine geçmez — o, ayrı ve daha uzun
soluklu bir keşif/teşhis aracı olarak kalır (bkz. `docs/STATUS.md` Kapı-3).

## Paketlenmiş çıktılar (`outputs/`)

Komutları yeniden koşmadan sonuçları incelemek için: `outputs/fixture_output.json`
(sentetik demo referansı) ve `outputs/full_data_output.json` (**resmî
full-data teslim çıktısı, Γ=30** — gerçek ölçülmüş koşu, şema-uyumlu teşhis,
`objective_value: null`, ihlalli tarife YOK). `outputs/GAMMA_SENSITIVITY_STATIC_SCAN.json`
raporun bir EKİDİR, resmî sonucu değiştirmez — ayrıntı `KURULUM.md` §4b.

## Determinizm

Aynı girdi + aynı seed için `objective_value` ve tüm liste alanları
byte-özdeştir (`tests/solve/test_main_cli.py::test_main_cli_is_deterministic_excluding_wall_clock`,
`tests/unit/test_output_writer.py`) — yalnızca `solver_metrics.solve_time_sec`
(duvar-saati) her koşuda farklı olabilir. Full-data'da zaman-limitli paralel
MIP'te `objective_value`'nin kendisi deterministik kalır (aynı gap
toleransında aynı veya daha iyi bulunur) ama hangi ALTERNATİF optimal
çözümün seçildiği garanti edilmez (bkz. `docs/output_format.md`).

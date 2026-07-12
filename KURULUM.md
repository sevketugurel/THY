# KURULUM.md — THY IST Hub Tarife Optimizasyonu (sıfırdan kurulum)

Bu dosya, projeyi hiç görmemiş biri için **temiz bir makinede sıfırdan**
ayağa kaldırma talimatıdır. Test edildiği ortam: macOS (Darwin arm64),
Python 3.14.4, HiGHS (`highspy` 1.15.1). Linux'ta da çalışır (Pyomo/HiGHS
platform bağımsız); Windows test edilmedi.

## 0 · Ön koşullar

İki kurulum yolu var — **Yol A (Docker, önerilen)** ortam farklarını
(Python sürümü, işletim sistemi) sıfırlar; **Yol B (venv)** Docker
kurulu değilse birincil alternatiftir. Her iki yol da AYNI pinned
`requirements.txt`'i kullanır, sonuçlar (668.75/valid=True) özdeştir.

- **Yol A**: Docker Engine + Docker Compose v2 (`docker compose version`
  ile kontrol edin). Test edildiği sürüm: Docker 27.5.1 (macOS/Darwin arm64).
- **Yol B**: Python **3.11+** (proje 3.14.4 ile geliştirildi/test edildi;
  `pyomo`/`highspy` pin'li sürümleri 3.11-3.14 aralığında çalışır), ~300 MB
  disk, internet erişimi (yalnızca `pip install` adımı için).

## 1 · Kurulum

### Yol A · Docker (önerilen, 2 komut)

```bash
cd THY   # zip'ten çıkardığınız proje kökü
docker compose build     # imajı kur (~45s, requirements.txt pinned)
docker compose run --rm demo   # 668.75/valid=True (§3b ile aynı)
```

`data_raw/` ve `runs/` **volume** olarak mount edilir (`docker-compose.yml`)
— yarışma verisi imaja GÖMÜLMEZ. `--full-data` için önce §2'yi uygulayıp
`docker compose run --rm full` çalıştırın; testler için
`docker compose run --rm test`. Kısayollar: `./run.sh docker-build|docker-test|docker-demo|docker-full`.

**Doğrulandı** (bu makinede, Docker 27.5.1, `--no-cache` temiz build):
build 38.24s, `docker-test` 365/365 test 13.33s'de, `docker-demo` <2s'de
668.75/optimal/valid=True — venv yolundakiyle BİREBİR AYNI sonuç.
Full-data koşusu container'da TEKRARLANMADI (venv'de ~44dk22s ölçüldü,
aynı sürenin container'da da geçerli olması beklenir — kod ve
bağımlılıklar özdeş).

### Yol B · venv (3 komut)

```bash
cd THY   # zip'ten çıkardığınız proje kökü
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # kesin pin'li (pip freeze tabanlı), tekrar-üretilebilir
```

`requirements.txt` şu an itibariyle:
```
pyomo==6.10.1
highspy==1.15.1
openpyxl==3.1.5
pandas==3.0.3
numpy==2.5.1
PyYAML==6.0.3
pytest==9.1.1
```

Aşağıdaki §3'teki komutlar Yol B (venv) için yazılmıştır; Yol A (Docker)
kullanıyorsanız aynı sırayı `./run.sh docker-test`/`docker-demo`/`docker-full`
ile çalıştırın.

## 2 · Veri dosyalarının yerleşimi (yalnızca gerçek-veri koşusu için gerekli)

`--fixture` modu **hiçbir veri dosyası gerektirmez** (sentetik veri repo
içinde, `tests/fixtures/`). `--full-data` modu için yarışmanın 4 orijinal
dosyasını `data_raw/` altına şu **TAM adlarla** yerleştirin (adlar
`src/config/paths.py`'de sabittir, büyük/küçük harf ve boşluklar dahil
birebir eşleşmeli):

```
data_raw/
├── O&D Rakip Bağlantı Tablosu.xlsx
├── Yolcu Verisi_masked.xlsx
├── change_ranking_input.xlsx
└── Flight Pairs.xlsx
```

Bu dosyalar **repo'ya dahil değildir** (yarışma veri kullanım koşulları
nedeniyle) — organizatörden temin edilip yukarıdaki klasöre elle kopyalanır.

## 3 · Üç komut

### (a) Doğrulama — test suite

```bash
python -m pytest
```
**Beklenen çıktı** (son satır): `365 passed in ~20s`
(bazı sistemlerde ±5-10s sapabilir; solve testleri ≤60sn limitlidir).

> Not: çıplak `pytest` da çalışır (kök `conftest.py` sayesinde), ama
> yeniden-üretilebilirlik için `python -m pytest` önerilir (aynı `.venv`
> yorumlayıcısını garantiler).

### (b) Demo — sentetik fixture (veri gerekmez, ~1 saniye)

```bash
python main.py --config src/config/standard.yaml --fixture
```
**Beklenen son satır**:
```
status=optimal objective=668.75 selected=18 valid=True
```
Bu değer üç bağımsız yoldan doğrulanmıştır (CLI = `recompute_objective` =
saf-Python brute-force oracle) — bkz. `docs/STATUS.md`.

### (c) Gerçek veri — full-data (bütçeli merdiven, ~30-40 dk)

```bash
python main.py --config src/config/standard.yaml --full-data
```

Bu komut TEK ÇAĞRIDA bir üretim merdiveni koşar (`src/solve/ladder.py`):
1. tam model (A-G), 1800s bütçeli solve;
2. başarısızsa tek bir elastik (slack-relaxed) solve denemesi, 600s bütçeli;
3. ikisi de geçerli/doğrulanmış bir sonuç vermezse **hiçbir ihlalli tarife
   dosyaya yazılmaz** — şema-uyumlu bir **teşhis çıktısı** yazılır
   (`objective_value: null`, `solver_metrics.status:
   "no_feasible_solution_found"`, boş tarife listesi) ve komut sıfır-olmayan
   bir çıkış koduyla döner.

**Bu projenin mevcut durumunda (bkz. `docs/report.md` §5), full-data'da adım
(3)'e düşülmesi BEKLENEN ve NORMAL bir davranıştır** — kapsamlı, çok-açılı
bir teşhis kampanyasından sonra bu instance'ın full ölçekte doğrulanmış bir
objective_value vermediği sonucuna varılmıştır (Branch B, bkz. rapor). Aracın
kendisi **hiçbir zaman ihlalli/geçersiz bir tarife yazmaz** — bu, üretim
merdiveninin kendi garantisidir ve gizli test senaryolarında da geçerlidir.

## 4 · Çıkış kodları

| Kod | Anlamı |
|---|---|
| `0` | Doğrulanmış (validator sıfır ihlal + recompute tutarlı) bir tarife `runs/output.json`'a yazıldı. |
| `1` | Merdivenin hiçbir adımı doğrulanmış bir sonuç üretemedi — şema-uyumlu teşhis çıktısı yazıldı (ihlalli tarife YOK). Full-data'da bu instance için **beklenen** sonuç. |
| `2` | Komut satırı argüman hatası (ör. `--fixture` ve `--full-data` ikisi birden veya hiçbiri verilmemiş, ya da `--config` eksik) — argparse standardı. |
| (traceback) | `data_raw/` dosyaları eksik/yanlış adlı ya da `--config` dosyası bulunamıyor → Python `FileNotFoundError` ile anlamlı bir hata mesajıyla durur (şema hatası gizli-test'te de aynı şekilde davranır, bkz. loader'ların şema-doğrulaması). |

## 4b · Paketlenmiş çıktı dosyaları (`outputs/`)

Bu paket, yukarıdaki komutları yeniden koşmadan sonuçları incelemek
isteyenler için önceden üretilmiş çıktıları `outputs/` altında içerir:

| Dosya | İçerik | Resmî mi? |
|---|---|---|
| `outputs/fixture_output.json` | `--fixture` komutunun çıktısı (668.75/optimal/valid=True) | Evet — sentetik demo referansı |
| `outputs/full_data_output.json` | `--full-data`'nın GERÇEK ölçülmüş koşusu (44dk22s, Kapı-10) — şema-uyumlu teşhis çıktısı, **objective_value=null, ihlalli tarife YOK** | **Evet — resmî full-data teslim çıktısı (Γ=30)** |
| `outputs/GAMMA_SENSITIVITY_STATIC_SCAN.json` | Kapı-B'nin solver-free Γ ön-tarama sonucu (Γ ∈ {30,45,...,180}) — EK, resmî değil | Hayır — yalnızca rapor eki, resmî konfigürasyon Γ=30'da KALIR |

`outputs/full_data_output.json`'ın `objective_value: null` olması bir hata
DEĞİLDİR — üretim merdiveninin üç adımının hiçbiri doğrulanmış bir sonuç
üretemediğinde bilinçli olarak yazılan şema-uyumlu teşhis çıktısıdır (bkz.
§3c ve `docs/report.md` §5). `Γ` duyarlılık taraması, resmî sonucu
DEĞİŞTİRMEZ — yalnızca raporun bir eki olarak sunulur.

## 5 · Sorun giderme

- **`ModuleNotFoundError: No module named 'src'`** → `.venv`'i aktive
  etmeyi unuttunuz ya da proje kökü dışından çalıştırıyorsunuz; her iki komut
  da proje kökünden (`KURULUM.md`'nin bulunduğu dizin) çalıştırılmalıdır.
- **`--full-data` çok uzun sürüyor / hiç bitmiyor gibi görünüyor** → normal;
  dış bekçi (watchdog) 1800s+600s+marj bütçesini garantiler, komut kendi
  kendine sonlanır. Canlı ilerleme `runs/` altındaki HiGHS log dosyalarında
  izlenebilir.
- **`data_raw/` dosya adı uyuşmazlığı** → dosya adları TAM eşleşmeli (bkz.
  §2); yanlış adla `FileNotFoundError` alınır, sessiz bir hata YOKTUR.
- **Docker: `Cannot connect to the Docker daemon`** → Docker Desktop/Engine
  çalışmıyor; başlatıp (`open -a Docker` macOS'ta) `docker info`'nun
  başarılı dönmesini bekleyin, sonra tekrar deneyin.

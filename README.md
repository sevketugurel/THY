# THY IST Hub Tarife Optimizasyonu

TEKNOFEST "Yapay Zeka Destekli Havayolu Optimizasyonu" yarışması için Pyomo/HiGHS MIP.
Detaylı durum ve mimari kararlar için `CLAUDE.md`, matematiksel model için
`docs/model.md`, veri-kalitesi varsayımları için `ASSUMPTIONS.md`.

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

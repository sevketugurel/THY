# THY IST Hub Tarife Optimizasyonu — teslim imajı (Kapı-D2).
# Yarışma verisi (data_raw/) İMAJA GÖMÜLMEZ — docker-compose.yml volume ile
# mount edilir. Sonuçlar (runs/) de volume — imaj salt-okunur kod+bağımlılık
# taşır.
FROM python:3.14-slim

WORKDIR /app

# HiGHS (highspy) ve pandas/numpy wheel'leri manylinux -- derleyici gerekmez,
# ama pip'in kendisini güncel tutmak kurulum hatalarını azaltıyor.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY main.py pytest.ini conftest.py ./
COPY src ./src
COPY tests ./tests
COPY scripts ./scripts
COPY docs ./docs

# data_raw/ ve runs/ İMAJA KOPYALANMAZ (yarışma verisi + solve çıktıları,
# docker-compose.yml'da volume). Boş runs/ mkdir -- --fixture bile
# runs/output.json'a yazmayı dener.
RUN mkdir -p runs data_raw

ENTRYPOINT ["python", "main.py"]
CMD ["--config", "src/config/standard.yaml", "--fixture"]

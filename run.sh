#!/usr/bin/env bash
# THY IST Hub Tarife Optimizasyonu — tek-komutluk kısayollar.
# Ayrıntılı talimat: KURULUM.md. Kullanım: ./run.sh <hedef>
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

usage() {
  echo "Kullanım: ./run.sh {setup|test|demo|full}"
  echo "  setup  - venv oluştur + pinned bağımlılıkları kur"
  echo "  test   - tüm test suite'i çalıştır (python -m pytest)"
  echo "  demo   - sentetik fixture ile CLI (~1sn, veri gerekmez)"
  echo "  full   - gerçek veri ile üretim merdiveni (~30-40dk, data_raw/ gerekir)"
  exit 1
}

[ $# -eq 1 ] || usage

case "$1" in
  setup)
    python3 -m venv .venv
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install -r requirements.txt
    ;;
  test)
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pytest
    ;;
  demo)
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python main.py --config src/config/standard.yaml --fixture
    ;;
  full)
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python main.py --config src/config/standard.yaml --full-data
    ;;
  *)
    usage
    ;;
esac

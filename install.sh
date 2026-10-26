#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
echo "Kurulum tamamlandi. ./run.sh ile baslatin."
echo "Ilk model indirmesi icin internet baglantisi gerekir."

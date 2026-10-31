#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN=""

find_supported_python() {
  local candidate version
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      version=$("$candidate" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)
      if [[ "$version" =~ ^3\.(10|11|12|13|14)$ ]]; then
        PYTHON_BIN="$(command -v "$candidate")"
        return 0
      fi
    fi
  done
  return 1
}

run_as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "Python kurulumu icin sudo veya root yetkisi gerekiyor." >&2
    exit 1
  fi
}

install_python() {
  if [[ -f /etc/debian_version ]] && command -v apt-get >/dev/null 2>&1; then
    run_as_root apt-get update
    run_as_root apt-get install -y python3 python3-venv
  elif [[ -f /etc/fedora-release ]] && command -v dnf >/dev/null 2>&1; then
    run_as_root dnf install -y python3
  elif [[ -f /etc/arch-release ]] && command -v pacman >/dev/null 2>&1; then
    run_as_root pacman -Sy --noconfirm python python-pip
  elif [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    brew install python@3.12
    PATH="$(brew --prefix python@3.12)/bin:$PATH"
    export PATH
  else
    echo "Desteklenen bir Python kurulum araci bulunamadi." >&2
    echo "Python 3.10-3.14 ve venv destegini manuel olarak kurup tekrar deneyin." >&2
    exit 1
  fi
}

install_venv_support() {
  if [[ -f /etc/debian_version ]] && command -v apt-get >/dev/null 2>&1; then
    run_as_root apt-get update
    run_as_root apt-get install -y python3-venv
  elif [[ -f /etc/fedora-release ]] && command -v dnf >/dev/null 2>&1; then
    run_as_root dnf install -y python3
  elif [[ -f /etc/arch-release ]] && command -v pacman >/dev/null 2>&1; then
    run_as_root pacman -Sy --noconfirm python
  else
    echo "Python venv destegi otomatik kurulamadi." >&2
    echo "python3-venv paketini kurup install.sh dosyasini tekrar calistirin." >&2
    exit 1
  fi
}

if ! find_supported_python; then
  echo "Python 3.10-3.14 bulunamadi. Kuruluyor..."
  install_python
  if ! find_supported_python; then
    echo "Python kurulumu tamamlanamadi veya desteklenen bir surum bulunamadi." >&2
    exit 1
  fi
fi

echo "Python bulundu: $("$PYTHON_BIN" --version)"
if [[ ! -x .venv/bin/python ]]; then
  if ! "$PYTHON_BIN" -m venv .venv; then
    echo "Python venv destegi bulunamadi. Kuruluyor..."
    install_venv_support
    rm -rf .venv
    "$PYTHON_BIN" -m venv .venv
  fi
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
echo "Kurulum tamamlandi. ./run.sh ile baslatin."
echo "Ilk model indirmesi icin internet baglantisi gerekir."

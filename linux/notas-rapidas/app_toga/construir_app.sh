#!/usr/bin/env bash
# Construye la app de Toga con Briefcase (Linux: Debian, Ubuntu y Linux Mint).
# Uso:  ./construir_app.sh dev        ejecuta en modo desarrollo (sin construir)
#       ./construir_app.sh            crea/actualiza y construye la app (por defecto)
#       ./construir_app.sh run        ejecuta la app construida
#       ./construir_app.sh package    además genera un paquete .deb en dist/
#
# Requisitos del sistema (Debian/Ubuntu/Mint), para compilar PyGObject y pycairo:
#   sudo apt install build-essential pkg-config python3-dev python3-venv libcairo2-dev \
#        libgirepository1.0-dev gir1.2-gtk-3.0 libcanberra-gtk3-module
# (En Debian 13 / Ubuntu 25.04 o posteriores puede hacer falta libgirepository-2.0-dev.)
# `briefcase create` comprueba estos paquetes y ofrece instalar los que falten.
set -euo pipefail
cd "$(dirname "$0")"

python3 -c "import venv, ensurepip" 2>/dev/null || {
  echo "Falta python3-venv:  sudo apt install python3-venv" >&2; exit 1; }

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

case "${1:-build}" in
  dev)
    briefcase dev
    ;;
  run)
    briefcase run linux system
    ;;
  build|package)
    if [ -d "build/notas-rapidas-toga/linux" ]; then
      briefcase update linux system
    else
      briefcase create linux system
    fi
    briefcase build linux system
    if [ "${1:-build}" = "package" ]; then
      briefcase package linux system
      echo "Paquete en dist/ (instálalo con: sudo apt install ./dist/*.deb)"
    fi
    echo
    echo "Listo. Para ejecutarla:  ./construir_app.sh run"
    ;;
  *)
    echo "Uso: $0 [dev|build|run|package]" >&2; exit 2
    ;;
esac

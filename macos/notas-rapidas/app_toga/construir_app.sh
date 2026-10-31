#!/usr/bin/env bash
# Construye la app de Toga con Briefcase (BeeWare) en macOS.
# Uso:  ./construir_app.sh dev        ejecuta en modo desarrollo (sin construir el .app)
#       ./construir_app.sh            crea/actualiza y construye el .app (por defecto)
#       ./construir_app.sh package    además genera un instalador .dmg en dist/
set -euo pipefail
cd "$(dirname "$0")"

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

APP_DIR="build/notas-rapidas-toga/macos/app"
case "${1:-build}" in
  dev)
    briefcase dev
    ;;
  build|package)
    if [ -d "$APP_DIR" ]; then briefcase update macOS; else briefcase create macOS; fi
    briefcase build macOS
    echo
    echo "Listo: $APP_DIR/Notas Rápidas Toga.app"
    if [ "${1:-build}" = "package" ]; then
      briefcase package macOS --adhoc-sign       # sin cuenta de desarrollador
      echo "Instalador en dist/"
    fi
    open "$APP_DIR" 2>/dev/null || true
    ;;
  *)
    echo "Uso: $0 [dev|build|package]" >&2; exit 2
    ;;
esac

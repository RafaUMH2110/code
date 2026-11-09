#!/usr/bin/env bash
# Ejecuta la aplicación desde el código fuente, creando el entorno virtual la primera vez.
#   ./scripts/ejecutar.sh            arranca la aplicación
#   ./scripts/ejecutar.sh --pruebas  ejecuta las pruebas (pytest)
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck source=_python.sh
source scripts/_python.sh

if [ ! -x .venv/bin/python ]; then
  echo "Creando el entorno virtual .venv con $PYTHON_BASE (solo la primera vez)…"
  rm -rf .venv   # por si quedó a medias de un intento anterior
  "$PYTHON_BASE" -m venv .venv
  # Si la instalación falla se borra el entorno, para no dejarlo a medias.
  if ! { .venv/bin/python3 -m pip install --upgrade pip >/dev/null \
         && .venv/bin/python3 -m pip install -r requirements-dev.txt; }; then
    rm -rf .venv
    echo "ERROR: falló la instalación de dependencias; se ha borrado .venv." >&2
    exit 1
  fi
fi

if [ "${1:-}" = "--pruebas" ]; then
  exec .venv/bin/python3 -m pytest -q
fi
exec .venv/bin/python3 lanzador.py "$@"

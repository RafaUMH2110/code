#!/usr/bin/env bash
# Ejecuta la aplicación desde el código fuente, creando el entorno virtual la primera vez.
#   ./scripts/ejecutar.sh            arranca la aplicación
#   ./scripts/ejecutar.sh --pruebas  ejecuta las pruebas (pytest)
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  echo "Creando el entorno virtual .venv (solo la primera vez)…"
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements-dev.txt
fi

if [ "${1:-}" = "--pruebas" ]; then
  exec .venv/bin/python -m pytest -q
fi
exec .venv/bin/python lanzador.py "$@"

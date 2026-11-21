#!/usr/bin/env bash
# Doble clic en Finder: abre TeleHome Enchufes y la interfaz en el navegador.
cd "$(dirname "$0")/.." || exit 1
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; else PY="$(command -v python3)"; fi
exec "$PY" -m telehome_enchufes serve "$@"

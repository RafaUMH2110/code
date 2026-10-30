#!/usr/bin/env bash
# Construye "Notas Rápidas Web.app" en macOS.
# Uso:  chmod +x construir_app_web.sh && ./construir_app_web.sh
set -euo pipefail
cd "$(dirname "$0")"

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip py2app pywebview

# Icono: icono.png (1024x1024) -> icono.icns
if [ -f icono.png ] && [ ! -f icono.icns ]; then
  rm -rf icono.iconset && mkdir icono.iconset
  for s in 16 32 128 256 512; do
    sips -z $s $s             icono.png --out "icono.iconset/icon_${s}x${s}.png"      >/dev/null
    sips -z $((s*2)) $((s*2)) icono.png --out "icono.iconset/icon_${s}x${s}@2x.png"   >/dev/null
  done
  iconutil -c icns icono.iconset -o icono.icns
  rm -rf icono.iconset
fi

rm -rf build dist
python setup_web.py py2app
codesign --force --deep --sign - "dist/Notas Rápidas Web.app"

echo "Listo: dist/Notas Rápidas Web.app"
open dist

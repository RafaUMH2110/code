#!/usr/bin/env bash
# Construye "Notas Rápidas.app" en macOS.
# Uso:  chmod +x construir_app.sh && ./construir_app.sh
set -euo pipefail
cd "$(dirname "$0")"

# 1) Entorno virtual con py2app
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install --quiet --upgrade pip py2app

# 2) Icono: si existe icono.png (1024x1024) se convierte a .icns
if [ -f icono.png ] && [ ! -f icono.icns ]; then
  echo "Generando icono.icns…"
  rm -rf icono.iconset && mkdir icono.iconset
  for s in 16 32 128 256 512; do
    sips -z $s $s           icono.png --out "icono.iconset/icon_${s}x${s}.png"      >/dev/null
    sips -z $((s*2)) $((s*2)) icono.png --out "icono.iconset/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns icono.iconset -o icono.icns
  rm -rf icono.iconset
fi

# 3) Limpiar y construir
rm -rf build dist
python setup.py py2app

# 4) Firma ad-hoc (suficiente para ejecutarla en ESTE Mac)
codesign --force --deep --sign - "dist/Notas Rápidas.app"

echo
echo "Listo: dist/Notas Rápidas.app"
echo "Arrástrala a /Aplicaciones o ábrela con doble clic."
open dist

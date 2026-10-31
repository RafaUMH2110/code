#!/usr/bin/env bash
# Construye "Notas Rapidas Qt.app" (PySide6) con PyInstaller en macOS.
# Uso:  chmod +x construir_app.sh && ./construir_app.sh
set -euo pipefail
cd "$(dirname "$0")"

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt pyinstaller

# icono.icns ya incluido; si faltara, se genera desde icono.png
if [ ! -f icono.icns ] && [ -f icono.png ]; then
  rm -rf icono.iconset && mkdir icono.iconset
  for s in 16 32 128 256 512; do
    sips -z $s $s             icono.png --out "icono.iconset/icon_${s}x${s}.png"    >/dev/null
    sips -z $((s*2)) $((s*2)) icono.png --out "icono.iconset/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns icono.iconset -o icono.icns && rm -rf icono.iconset
fi

rm -rf build dist ./*.spec
pyinstaller --noconfirm --clean --windowed \
  --name "Notas Rapidas Qt" \
  --icon icono.icns \
  --osx-bundle-identifier com.ejemplo.notasrapidas.pyside6 \
  notas_pyside6.py

# Firma ad-hoc: suficiente para ejecutarla en ESTE Mac
codesign --force --deep --sign - "dist/Notas Rapidas Qt.app"

echo
echo "Listo: dist/Notas Rapidas Qt.app"
open dist

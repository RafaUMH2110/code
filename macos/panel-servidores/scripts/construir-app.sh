#!/usr/bin/env bash
# Construye «Panel de Servidores.app» (macOS) con PyInstaller.
#   ./scripts/construir-app.sh            construye dist/Panel\ de\ Servidores.app
#   ./scripts/construir-app.sh --dmg      además crea un .dmg
# Requiere macOS, Python 3.10+ y las herramientas de línea de comandos (iconutil, codesign, hdiutil).
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(uname)" = "Darwin" ] || { echo "Este script solo funciona en macOS." >&2; exit 1; }
NOMBRE="Panel de Servidores"

if [ ! -x .venv-build/bin/python ]; then
  python3 -m venv .venv-build
  .venv-build/bin/python -m pip install --upgrade pip >/dev/null
  .venv-build/bin/python -m pip install -r requirements-dev.txt
fi
PY=.venv-build/bin/python

echo "== Icono"
$PY scripts/crear-icono.py
iconutil -c icns icono.iconset -o icono.icns

echo "== PyInstaller"
rm -rf build dist
$PY -m PyInstaller --noconfirm --clean --windowed \
  --name "$NOMBRE" \
  --icon icono.icns \
  --osx-bundle-identifier es.umh.panel-servidores \
  --paths src \
  --add-data "src/panel_servidores/recursos:panel_servidores/recursos" \
  --add-data "src/panel_servidores/icono.png:panel_servidores" \
  --hidden-import keyring.backends.macOS \
  lanzador.py

echo "== Firma ad-hoc (suficiente para uso local; para repartir hace falta un Developer ID)"
codesign --force --deep --sign - "dist/$NOMBRE.app"

if [ "${1:-}" = "--dmg" ]; then
  echo "== DMG"
  hdiutil create -volname "$NOMBRE" -srcfolder "dist/$NOMBRE.app" -ov -format UDZO "dist/$NOMBRE.dmg"
fi
echo "Listo: dist/$NOMBRE.app"
echo "Primera vez: clic derecho → Abrir (Gatekeeper). Si macOS lo bloquea: xattr -dr com.apple.quarantine \"dist/$NOMBRE.app\""

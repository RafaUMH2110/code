#!/usr/bin/env bash
# EXPERIMENTAL: binario con PyInstaller de la variante pywebview (Debian, Ubuntu, Mint).
# Uso:  ./construir_app_web.sh              -> dist/notas-rapidas-web/notas-rapidas-web
#       ./construir_app_web.sh --onefile    -> un solo fichero (arranque más lento)
#
# Aviso: pywebview en Linux usa GTK + WebKitGTK del SISTEMA a través de PyGObject, y empaquetarlos
# con PyInstaller es frágil (typelibs, procesos auxiliares de WebKit). Para distribuir esta
# variante es más fiable el paquete .deb (crear_deb.sh) o la instalación local (instalar_local.sh).
# Además el binario depende de la glibc del equipo de construcción (ver construir_app.sh de app_tk).
set -euo pipefail
cd "$(dirname "$0")"

ONEFILE=()
for a in "$@"; do
  case "$a" in
    --onefile|--un-solo-binario) ONEFILE=(--onefile) ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $a" >&2; exit 2 ;;
  esac
done

faltan=()
python3 -c "import venv, ensurepip" 2>/dev/null || faltan+=(python3-venv)
python3 -c "import gi" 2>/dev/null               || faltan+=(python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1)
command -v objdump >/dev/null                    || faltan+=(binutils)
if [ "${#faltan[@]}" -gt 0 ]; then
  echo "Faltan paquetes del sistema: ${faltan[*]}" >&2
  echo "Instálalos con:  sudo apt install ${faltan[*]}" >&2
  echo "(Ubuntu 20.04 / Mint 20: gir1.2-webkit2-4.0 en lugar de 4.1)" >&2
  exit 1
fi

# --system-site-packages: el venv necesita ver el módulo «gi» instalado con apt
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --quiet --upgrade pip pyinstaller pywebview

rm -rf build dist ./*.spec
.venv/bin/python -m PyInstaller --noconfirm --clean \
  --name notas-rapidas-web \
  --add-data "ui:ui" \
  --add-data "icono.png:." \
  --collect-all webview \
  --hidden-import gi \
  "${ONEFILE[@]}" \
  notas_web.py

if [ "${#ONEFILE[@]}" -gt 0 ]; then salida="dist/notas-rapidas-web"; else salida="dist/notas-rapidas-web/notas-rapidas-web"; fi
echo
echo "Listo: $salida"
echo "Si no arranca, ejecútalo desde un terminal para ver el error y revisa ~/.local/state/notas-rapidas-web/app.log"

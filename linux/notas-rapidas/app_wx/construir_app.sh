#!/usr/bin/env bash
# EXPERIMENTAL: binario (wxPython/GTK) con PyInstaller (Debian, Ubuntu, Linux Mint).
# wxGTK depende de bibliotecas GTK del sistema; para distribuir es más fiable el .deb.
# Uso:  ./construir_app.sh              -> dist/notas-rapidas-wx/notas-rapidas-wx (carpeta)
#       ./construir_app.sh --onefile    -> dist/notas-rapidas-wx (un solo fichero, arranque más lento)
#
# IMPORTANTE: el binario enlaza con la glibc del equipo donde se construye y NO funciona
# en distribuciones con una glibc más antigua. Construye en la distro más antigua que
# quieras soportar (por ejemplo Ubuntu 22.04 / Mint 21) o usa el paquete .deb (crear_deb.sh),
# que no tiene esta limitación.
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

# 1) Dependencias del sistema
faltan=()
python3 -c "import wx" 2>/dev/null               || faltan+=(python3-wxgtk4.0)
python3 -c "import venv, ensurepip" 2>/dev/null || faltan+=(python3-venv)
command -v objdump >/dev/null                   || faltan+=(binutils)
if [ "${#faltan[@]}" -gt 0 ]; then
  echo "Faltan paquetes del sistema: ${faltan[*]}" >&2
  echo "Instálalos con:  sudo apt install ${faltan[*]}" >&2
  exit 1
fi

# 2) Entorno virtual con PyInstaller (necesario: Debian 12+, Ubuntu 24.04 y Mint 22
#    impiden `pip install` fuera de un venv, PEP 668)
# --system-site-packages: el venv necesita ver el wxPython instalado con apt
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --quiet --upgrade pip pyinstaller

# 3) Construir (en Linux el separador de --add-data es «:»)
rm -rf build dist ./*.spec
.venv/bin/python -m PyInstaller --noconfirm --clean \
  --name notas-rapidas-wx \
  --add-data "icono_256.png:." \
  "${ONEFILE[@]}" \
  notas_wx.py

if [ "${#ONEFILE[@]}" -gt 0 ]; then salida="dist/notas-rapidas-wx"; else salida="dist/notas-rapidas-wx/notas-rapidas-wx"; fi
echo
echo "Listo: $salida"
echo "glibc del equipo de construcción: $(ldd --version | head -n1 | awk '{print $NF}') (el binario requiere esa versión o superior)"

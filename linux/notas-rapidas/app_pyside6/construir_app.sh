#!/usr/bin/env bash
# Construye un binario independiente (PySide6) con PyInstaller (Debian, Ubuntu, Linux Mint).
# Uso:  ./construir_app.sh              -> dist/notas-rapidas-pyside6/notas-rapidas-pyside6 (carpeta)
#       ./construir_app.sh --onefile    -> dist/notas-rapidas-pyside6 (un solo fichero, arranque más lento)
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
python3 -c "import venv, ensurepip" 2>/dev/null || faltan+=(python3-venv)
command -v objdump >/dev/null                   || faltan+=(binutils)
if [ "${#faltan[@]}" -gt 0 ]; then
  echo "Faltan paquetes del sistema: ${faltan[*]}" >&2
  echo "Instálalos con:  sudo apt install ${faltan[*]}" >&2
  exit 1
fi

# 2) Entorno virtual con PyInstaller (necesario: Debian 12+, Ubuntu 24.04 y Mint 22
#    impiden `pip install` fuera de un venv, PEP 668)
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip pyinstaller -r requirements.txt

# 3) Construir (en Linux el separador de --add-data es «:»)
rm -rf build dist ./*.spec
.venv/bin/python -m PyInstaller --noconfirm --clean \
  --name notas-rapidas-pyside6 \
  --add-data "icono_256.png:." \
  "${ONEFILE[@]}" \
  notas_pyside6.py

if [ "${#ONEFILE[@]}" -gt 0 ]; then salida="dist/notas-rapidas-pyside6"; else salida="dist/notas-rapidas-pyside6/notas-rapidas-pyside6"; fi
echo
echo "Listo: $salida"
echo "glibc del equipo de construcción: $(ldd --version | head -n1 | awk '{print $NF}') (el binario requiere esa versión o superior)"

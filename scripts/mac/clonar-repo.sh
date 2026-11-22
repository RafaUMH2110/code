#!/usr/bin/env bash
# clonar-repo.sh — Clona (o actualiza) un repositorio de GitHub en /Users/rafa/Repos
#
# Uso:
#   ./clonar-repo.sh                    # clona RafaUMH2110/code
#   ./clonar-repo.sh RafaUMH2110/apps   # clona otro repositorio (propietario/nombre)
#
# Si el repositorio ya existe en el destino, hace "git pull" en lugar de clonar.
# Si gh (GitHub CLI) está instalado y autenticado lo usa (sirve para repos privados
# sin pegar ningún token); si no, usa git por HTTPS.

set -euo pipefail

REPO="${1:-RafaUMH2110/code}"
DESTINO="/Users/rafa/Repos"
NOMBRE="${REPO##*/}"
RUTA="$DESTINO/$NOMBRE"

mkdir -p "$DESTINO"

if [ -d "$RUTA/.git" ]; then
  echo "▶ $RUTA ya existe; actualizando con git pull…"
  git -C "$RUTA" pull --ff-only
  echo "✔ Repositorio actualizado en $RUTA"
  exit 0
fi

if [ -e "$RUTA" ]; then
  echo "✘ $RUTA existe pero no es un repositorio git. Muévelo o bórralo y vuelve a ejecutar." >&2
  exit 1
fi

echo "▶ Clonando $REPO en $RUTA…"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh repo clone "$REPO" "$RUTA"
elif command -v git >/dev/null 2>&1; then
  git clone "https://github.com/$REPO.git" "$RUTA"
else
  echo "✘ No se encontró git ni gh. Instala Xcode Command Line Tools: xcode-select --install" >&2
  exit 1
fi

echo "✔ Clonado en $RUTA"

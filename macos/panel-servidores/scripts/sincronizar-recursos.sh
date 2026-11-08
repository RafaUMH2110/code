#!/usr/bin/env bash
# Copia a la aplicación los scripts y el portal del repositorio «code».
#   ./scripts/sincronizar-recursos.sh [ruta-al-repo]
# Por defecto usa el repositorio que contiene esta carpeta (../..). Úsalo cuando cambies un script
# del repo y quieras que la aplicación lo lleve incluido. OJO: copia lo que haya en la rama que tengas
# activa en ese repo (haz «git checkout» de la rama correcta antes) y SOBRESCRIBE los scripts incluidos. (Alternativa sin recompilar: Preferencias →
# «Actualizar desde GitHub», o una «Carpeta de scripts propios».)
set -euo pipefail
AQUI="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${1:-$(cd "$AQUI/../.." && pwd)}"
DEST="$AQUI/src/panel_servidores/recursos"
mkdir -p "$DEST"

copiar() { # origen destino-nombre
  [ -f "$1" ] || { echo "FALTA: $1" >&2; exit 1; }
  install -m 644 "$1" "$DEST/$2"
  echo "  $2"
}

echo "Sincronizando desde $REPO"
for f in instalar-todo.sh instalar-todo-isa.sh; do
  copiar "$REPO/scripts/instalar-todo/$f" "$f"; chmod 755 "$DEST/$f"
done
for f in index.html favicon.svg favicon.ico apple-touch-icon.png; do
  copiar "$REPO/scripts/instalar-todo/$f" "$f"
done
copiar "$REPO/scripts/telemet-collector-info/telemet-collector-info.py" telemet-collector-info.py
for f in instalar-todo.sh instalar-todo-isa.sh; do bash -n "$DEST/$f" && echo "  (sintaxis de $f correcta)"; done
echo "Hecho."

#!/usr/bin/env bash
# Pone la «Última modificación» que muestra Acerca de a la fecha y hora actuales (hora de España).
# Ejecútalo antes de cada commit que cambie la aplicación:   ./scripts/marcar-modificacion.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ahora="$(TZ=Europe/Madrid date '+%Y-%m-%d %H:%M')"
fichero=src/panel_servidores/__init__.py
# sed -i difiere entre macOS y Linux; con un fichero temporal funciona igual en los dos.
sed "s/^ULTIMA_MODIFICACION = .*/ULTIMA_MODIFICACION = \"$ahora\"/" "$fichero" > "$fichero.tmp"
mv "$fichero.tmp" "$fichero"
echo "Última modificación: $ahora"

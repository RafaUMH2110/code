#!/usr/bin/env bash
# Instala la app SOLO para tu usuario (sin sudo): menú de aplicaciones, comando e icono.
# Funciona igual en Debian, Ubuntu y Linux Mint.
#
# Uso:  ./instalar_local.sh                 instala
#       ./instalar_local.sh --escritorio    instala y crea un icono en el Escritorio
#       ./instalar_local.sh --desinstalar   elimina todo lo instalado
set -euo pipefail
cd "$(dirname "$0")"

APP="notas-rapidas"
DATOS="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$DATOS/$APP"
BIN="$HOME/.local/bin"
APPS="$DATOS/applications"
ICONOS="$DATOS/icons/hicolor"

actualizar_cache() {
  command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
  command -v gtk-update-icon-cache  >/dev/null && gtk-update-icon-cache -q -t "$ICONOS" 2>/dev/null || true
}

escritorio() { command -v xdg-user-dir >/dev/null && xdg-user-dir DESKTOP || echo "$HOME/Desktop"; }

MODO="instalar"; CON_ESCRITORIO=0
for a in "$@"; do
  case "$a" in
    --desinstalar) MODO="desinstalar" ;;
    --escritorio)  CON_ESCRITORIO=1 ;;
    -h|--help)     sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $a" >&2; exit 2 ;;
  esac
done

if [ "$MODO" = "desinstalar" ]; then
  rm -rf "$DEST" "$BIN/$APP" "$APPS/$APP.desktop" "$(escritorio)/$APP.desktop" \
         "$ICONOS/256x256/apps/$APP.png" "$ICONOS/48x48/apps/$APP.png"
  actualizar_cache
  echo "Desinstalada."
  exit 0
fi

python3 -c "import tkinter" 2>/dev/null || {
  echo "Falta Tkinter. Instálalo con:  sudo apt install python3-tk" >&2; exit 1; }

install -d "$DEST" "$BIN" "$APPS" "$ICONOS/256x256/apps" "$ICONOS/48x48/apps"
install -m644 notas_app.py icono.png "$DEST/"
install -m644 icono_256.png "$ICONOS/256x256/apps/$APP.png"
install -m644 icono_48.png  "$ICONOS/48x48/apps/$APP.png"

cat > "$BIN/$APP" <<LANZADOR
#!/bin/sh
exec /usr/bin/python3 "$DEST/notas_app.py" "\$@"
LANZADOR
chmod 755 "$BIN/$APP"

# .desktop con rutas absolutas (el PATH del menú no siempre incluye ~/.local/bin)
sed -e "s|^Exec=.*|Exec=$BIN/$APP %F|" -e "s|^Icon=.*|Icon=$APP|" "$APP.desktop" > "$APPS/$APP.desktop"
chmod 644 "$APPS/$APP.desktop"

if [ "$CON_ESCRITORIO" -eq 1 ]; then
  ESC="$(escritorio)"; mkdir -p "$ESC"
  cp "$APPS/$APP.desktop" "$ESC/$APP.desktop"
  chmod 755 "$ESC/$APP.desktop"
  # GNOME (Debian/Ubuntu) pide «permitir lanzar»; esto lo marca como de confianza
  command -v gio >/dev/null && gio set "$ESC/$APP.desktop" metadata::trusted true 2>/dev/null || true
fi

actualizar_cache
echo "Instalada en $DEST"
echo "Búscala en el menú de aplicaciones como «Notas Rápidas» o ejecuta: $APP"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "Aviso: $BIN no está en tu PATH (cierra sesión y vuelve a entrar, o añádelo en ~/.profile)." ;; esac

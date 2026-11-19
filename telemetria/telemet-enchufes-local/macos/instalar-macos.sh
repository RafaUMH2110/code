#!/usr/bin/env bash
# TeleMet Enchufes - instalador para macOS
#   ./macos/instalar-macos.sh                 crea .venv e instala dependencias
#   ./macos/instalar-macos.sh --launchd       además arranca la app al iniciar sesión (LaunchAgent)
#   ./macos/instalar-macos.sh --quitar-launchd  elimina el LaunchAgent
#   ./macos/instalar-macos.sh --solo-plist    imprime el .plist y sale (sin instalar nada)
# Opciones: --puerto N (8765 por defecto)
set -euo pipefail

LABEL="es.umh.telemet-enchufes"
PUERTO=8765
ACCION="instalar"
USAR_LAUNCHD=0

while [ $# -gt 0 ]; do
  case "$1" in
    --launchd) USAR_LAUNCHD=1 ;;
    --quitar-launchd) ACCION="quitar" ;;
    --solo-plist) ACCION="plist" ;;
    --puerto) shift; PUERTO="${1:?Falta el número de puerto}" ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $1" >&2; exit 2 ;;
  esac
  shift
done

case "$PUERTO" in ''|*[!0-9]*) echo "El puerto debe ser un número" >&2; exit 2 ;; esac

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$AQUI/.." && pwd)"
VENV="$REPO/.venv"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/telemet-enchufes.log"
UID_NUM="$(id -u)"

xml_escape() { local s="$1"; s="${s//&/&amp;}"; s="${s//</&lt;}"; s="${s//>/&gt;}"; printf '%s' "$s"; }

generar_plist() {
  cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$(xml_escape "$VENV/bin/python")</string>
    <string>-m</string>
    <string>telemet_enchufes</string>
    <string>serve</string>
    <string>--no-browser</string>
    <string>--port</string>
    <string>$PUERTO</string>
  </array>
  <key>WorkingDirectory</key><string>$(xml_escape "$REPO")</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$(xml_escape "$LOG")</string>
  <key>StandardErrorPath</key><string>$(xml_escape "$LOG")</string>
</dict>
</plist>
PLIST
}

if [ "$ACCION" = "plist" ]; then generar_plist; exit 0; fi

if [ "$ACCION" = "quitar" ]; then
  launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "LaunchAgent eliminado. Los datos (histórico y configuración) se conservan."
  exit 0
fi

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Aviso: este instalador está pensado para macOS (detectado: $(uname -s))." >&2
fi

# 1) Python >= 3.9
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "No se encuentra python3. Instala las herramientas de línea de órdenes (xcode-select --install) o Homebrew (brew install python)." >&2
  exit 1
fi
"$PY" - <<'PYCHK' || { echo "Se necesita Python 3.9 o superior." >&2; exit 1; }
import sys
sys.exit(0 if sys.version_info >= (3, 9) else 1)
PYCHK
echo "Python: $("$PY" --version)"

# 2) Entorno virtual y dependencias
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creando entorno virtual en $VENV ..."
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$REPO/requirements.txt"
chmod +x "$AQUI/iniciar-telemet-enchufes.command" "$AQUI/instalar-macos.sh" 2>/dev/null || true
echo "Dependencias instaladas."

# 3) LaunchAgent (opcional)
if [ "$USAR_LAUNCHD" = "1" ]; then
  mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
  launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
  generar_plist > "$PLIST"
  launchctl bootstrap "gui/$UID_NUM" "$PLIST"
  echo "Servicio instalado: arranca al iniciar sesión. Interfaz: http://127.0.0.1:$PUERTO/"
  echo "Registro: $LOG"
fi

cat <<FIN

Listo. Para empezar:
  - Doble clic en  macos/iniciar-telemet-enchufes.command
    o bien:  $VENV/bin/python -m telemet_enchufes
  - Prueba sin enchufes reales:  $VENV/bin/python -m telemet_enchufes serve --simulate 4

Importante (macOS reciente): la primera vez, permite en la ventana emergente que Python
acceda a la «Red local»; sin ese permiso no podrá hablar con los enchufes.
FIN

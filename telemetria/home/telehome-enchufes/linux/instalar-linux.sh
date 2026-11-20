#!/usr/bin/env bash
# TeleHome Enchufes - instalador para Linux (servicio systemd)
#   sudo ./linux/instalar-linux.sh                    instala o actualiza y arranca el servicio
#   sudo ./linux/instalar-linux.sh --quitar           detiene y elimina el servicio (conserva los datos)
#   ./linux/instalar-linux.sh --solo-servicio         imprime la unidad systemd y sale
# Opciones: --puerto N (8765) · --host DIR (127.0.0.1) · --allow-host NOMBRE (repetible, para un proxy inverso)
#           --allow-origin ORIGEN (repetible, p. ej. https://usuario.github.io: permite usar la API desde esa web)
set -euo pipefail

SERVICIO="telehome-enchufes"
USUARIO="telehome-enchufes"
DESTINO="/opt/telehome-enchufes"
DATOS="/var/lib/telehome-enchufes"
UNIDAD="/etc/systemd/system/$SERVICIO.service"
ENVOLTORIO="/usr/local/bin/telehome-enchufes"
PUERTO=8765
HOST="127.0.0.1"
EXTRA=()
ORIGENES=()
ACCION="instalar"

while [ $# -gt 0 ]; do
  case "$1" in
    --puerto) shift; PUERTO="${1:?Falta el puerto}" ;;
    --host) shift; HOST="${1:?Falta la dirección}" ;;
    --allow-host) shift; EXTRA+=("${1:?Falta el nombre}") ;;
    --allow-origin) shift; ORIGENES+=("${1:?Falta el origen}") ;;
    --quitar) ACCION="quitar" ;;
    --solo-servicio) ACCION="unidad" ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $1" >&2; exit 2 ;;
  esac
  shift
done

case "$PUERTO" in ''|*[!0-9]*) echo "El puerto debe ser un número" >&2; exit 2 ;; esac
case "$HOST" in *[!0-9A-Za-z.:-]*) echo "Dirección no válida: $HOST" >&2; exit 2 ;; esac
for h in "${EXTRA[@]+"${EXTRA[@]}"}"; do
  case "$h" in ''|*[!0-9A-Za-z.-]*) echo "Nombre de host no válido: $h" >&2; exit 2 ;; esac
done

for o in "${ORIGENES[@]+"${ORIGENES[@]}"}"; do
  case "$o" in http://*|https://*) ;; *) echo "Origen no válido (usa http(s)://dominio[:puerto]): $o" >&2; exit 2 ;; esac
  case "$o" in *[!0-9A-Za-z.:/-]*) echo "Origen no válido: $o" >&2; exit 2 ;; esac
done

generar_unidad() {
  local extra=""
  for h in "${EXTRA[@]+"${EXTRA[@]}"}"; do extra="$extra --allow-host $h"; done
  for o in "${ORIGENES[@]+"${ORIGENES[@]}"}"; do extra="$extra --allow-origin $o"; done
  cat <<UNIT
[Unit]
Description=TeleHome Enchufes (telemetría de enchufes Tuya)
After=network-online.target
Wants=network-online.target

[Service]
User=$USUARIO
Group=$USUARIO
Environment=TELEHOME_ENCHUFES_DIR=$DATOS
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=$DESTINO
ExecStart=$DESTINO/.venv/bin/python -m telehome_enchufes serve --no-browser --host $HOST --port $PUERTO$extra
Restart=on-failure
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=$DATOS

[Install]
WantedBy=multi-user.target
UNIT
}

if [ "$ACCION" = "unidad" ]; then generar_unidad; exit 0; fi
if [ "$(id -u)" -ne 0 ]; then echo "Ejecuta con sudo." >&2; exit 1; fi

if [ "$ACCION" = "quitar" ]; then
  systemctl disable --now "$SERVICIO" 2>/dev/null || true
  rm -f "$UNIDAD" "$ENVOLTORIO"
  systemctl daemon-reload
  echo "Servicio eliminado. Se conservan $DESTINO y los datos de $DATOS."
  exit 0
fi

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$AQUI/.." && pwd)"

# 1) Python >= 3.9 con venv
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then echo "Falta python3 (Debian/Ubuntu: apt install python3 python3-venv)." >&2; exit 1; fi
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || { echo "Se necesita Python 3.9 o superior." >&2; exit 1; }
"$PY" -c 'import venv, ensurepip' 2>/dev/null || { echo "Falta el módulo venv (Debian/Ubuntu: apt install python3-venv)." >&2; exit 1; }

# 2) Usuario de servicio y carpetas
if ! id "$USUARIO" >/dev/null 2>&1; then
  useradd --system --home-dir "$DATOS" --shell /usr/sbin/nologin "$USUARIO"
fi
install -d -m 0750 -o "$USUARIO" -g "$USUARIO" "$DATOS"
install -d -m 0755 "$DESTINO"

# 3) Código y dependencias
rm -rf /opt/telehome-enchufes/telehome_enchufes
cp -a "$REPO/telehome_enchufes" "$DESTINO/"
cp "$REPO/requirements.txt" "$DESTINO/"
find "$DESTINO/telehome_enchufes" -name __pycache__ -prune -exec rm -r {} +
[ -x "$DESTINO/.venv/bin/python" ] || "$PY" -m venv "$DESTINO/.venv"
"$DESTINO/.venv/bin/python" -m pip install --quiet --upgrade pip
"$DESTINO/.venv/bin/python" -m pip install --quiet -r "$DESTINO/requirements.txt"

# 4) Orden «telehome-enchufes» que actúa como el usuario del servicio
cat > "$ENVOLTORIO" <<WRAP
#!/bin/sh
# Ejecuta TeleHome Enchufes sobre los datos del servicio (p. ej. cloud-setup, cloud-import, password, list)
if [ "\$(id -un)" = "$USUARIO" ]; then
  exec env TELEHOME_ENCHUFES_DIR=$DATOS $DESTINO/.venv/bin/python -m telehome_enchufes "\$@"
fi
cd $DESTINO && exec sudo -u $USUARIO env TELEHOME_ENCHUFES_DIR=$DATOS $DESTINO/.venv/bin/python -m telehome_enchufes "\$@"
WRAP
chmod 0755 "$ENVOLTORIO"

# 5) Servicio
generar_unidad > "$UNIDAD"
systemctl daemon-reload
systemctl enable "$SERVICIO" >/dev/null
systemctl restart "$SERVICIO"
sleep 2
systemctl --no-pager --lines=5 status "$SERVICIO" || true

cat <<FIN

Instalado. Interfaz en http://$HOST:$PUERTO/ (servicio «$SERVICIO», datos en $DATOS).

Siguientes pasos (modo nube):
  sudo telehome-enchufes cloud-setup --region eu --access-id TU_ACCESS_ID   # pide el Access Secret
  sudo telehome-enchufes cloud-import                                       # añade tus enchufes (máx. 7)
  sudo telehome-enchufes password                                           # recomendable

Para verla desde tu ordenador sin abrir puertos:
  ssh -L $PUERTO:127.0.0.1:$PUERTO usuario@tu-vm   y abre http://127.0.0.1:$PUERTO/
Registro:  journalctl -u $SERVICIO -f
FIN

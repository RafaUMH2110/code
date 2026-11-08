#!/usr/bin/env bash
# Despliega en el directorio de documentos de Apache el contenido de los repos
# ya clonados de RafaUMH2110, conservando la estructura de directorios.
#
# Resultado:   <DESTINO>/<repo>/<estructura original del repo>
#              <DESTINO>/index.html   (índice con enlaces a todas las apps HTML)
#
# Uso: ./desplegar-apache.sh [-o ORIGEN] [-d DESTINO] [--solo-html] [--sin-indice] [-n]
#   -o ORIGEN       Directorio con los repos clonados   (def.: ~/RafaUMH2110)
#   -d DESTINO      Directorio de Apache                (def.: /var/www/html/rafa)
#   --solo-html     Copia solo *.html/*.htm (por defecto copia todo el contenido del repo)
#   --sin-indice    No genera el index.html de la raíz
#   -n              Simulación (no modifica nada)
set -euo pipefail

ORIGEN="$HOME/RafaUMH2110"
DESTINO="/var/www/html/rafa"
SOLO_HTML=0
INDICE=1
SIMULAR=0
USUARIO_WEB="www-data"

while [ $# -gt 0 ]; do
  case "$1" in
    -o) ORIGEN="$2"; shift 2 ;;
    -d) DESTINO="$2"; shift 2 ;;
    --solo-html) SOLO_HTML=1; shift ;;
    --sin-indice) INDICE=0; shift ;;
    -n) SIMULAR=1; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $1" >&2; exit 1 ;;
  esac
done

# --- Comprobaciones ---------------------------------------------------------
command -v rsync >/dev/null || { echo "Falta rsync. Instala con: sudo apt install -y rsync" >&2; exit 1; }
[ -d "$ORIGEN" ] || { echo "No existe el origen: $ORIGEN (¿has clonado ya los repos?)" >&2; exit 1; }
case "$DESTINO" in
  ""|"/"|"/var"|"/var/www"|"/var/www/") echo "Destino peligroso: '$DESTINO'" >&2; exit 1 ;;
esac

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null || { echo "Ejecuta como root o instala sudo." >&2; exit 1; }
  SUDO="sudo"
fi

ORIGEN="$(cd "$ORIGEN" && pwd)"
$SUDO mkdir -p "$DESTINO"
LOG="$ORIGEN/desplegar.log"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

RSYNC_OPTS=(-a --delete --exclude='.git' --exclude='.github' --exclude='.gitignore')
[ "$SIMULAR" -eq 1 ] && RSYNC_OPTS+=(--dry-run -v)
if [ "$SOLO_HTML" -eq 1 ]; then
  RSYNC_OPTS+=(--prune-empty-dirs --include='*/' --include='*.html' --include='*.htm' --exclude='*')
fi

log "Despliegue: $ORIGEN -> $DESTINO (solo_html=$SOLO_HTML, simulación=$SIMULAR)"

# --- Copia de cada repositorio ----------------------------------------------
total=0; fallos=0
for dir in "$ORIGEN"/*/; do
  repo="$(basename "$dir")"
  [ -d "$dir/.git" ] || [ -f "$dir/.git" ] || continue   # solo repos git
  if $SUDO rsync "${RSYNC_OPTS[@]}" "$dir" "$DESTINO/$repo/"; then
    log "Copiado: $repo"; total=$((total+1))
  else
    log "ERROR copiando: $repo"; fallos=$((fallos+1))
  fi
done

# --- Índice -----------------------------------------------------------------
if [ "$INDICE" -eq 1 ] && [ "$SIMULAR" -eq 0 ]; then
  tmp="$(mktemp)"
  {
    echo '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
    echo '<meta name="viewport" content="width=device-width,initial-scale=1">'
    echo '<title>Aplicaciones RafaUMH2110</title>'
    echo '<style>body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222}'
    echo 'h1{font-size:1.5rem}h2{margin-top:1.6rem;font-size:1.1rem;border-bottom:1px solid #ddd}'
    echo 'ul{line-height:1.7}a{color:#0b5ed7;text-decoration:none}a:hover{text-decoration:underline}'
    echo 'small{color:#777}</style></head><body>'
    echo '<h1>Aplicaciones HTML</h1>'
    echo "<small>Actualizado: $(date '+%d/%m/%Y %H:%M')</small>"
    for dir in "$ORIGEN"/*/; do
      repo="$(basename "$dir")"
      [ -d "$DESTINO/$repo" ] || continue
      mapfile -t files < <(cd "$DESTINO/$repo" && find . -type f \( -iname '*.html' -o -iname '*.htm' \) \
                            ! -path './node_modules/*' | sed 's|^\./||' | sort)
      [ "${#files[@]}" -gt 0 ] || continue
      echo "<h2>$repo</h2><ul>"
      for f in "${files[@]}"; do
        url="${repo// /%20}/${f// /%20}"
        echo "<li><a href=\"$url\">$f</a></li>"
      done
      echo '</ul>'
    done
    echo '</body></html>'
  } > "$tmp"
  $SUDO install -m 644 "$tmp" "$DESTINO/index.html"
  rm -f "$tmp"
  log "Índice generado: $DESTINO/index.html"
fi

# --- Permisos ---------------------------------------------------------------
if [ "$SIMULAR" -eq 0 ]; then
  $SUDO chown -R "$USUARIO_WEB:$USUARIO_WEB" "$DESTINO"
  $SUDO find "$DESTINO" -type d -exec chmod 755 {} +
  $SUDO find "$DESTINO" -type f -exec chmod 644 {} +
  log "Permisos aplicados ($USUARIO_WEB)"
fi

log "Fin. Repos copiados: $total | Errores: $fallos"
[ "$fallos" -eq 0 ]

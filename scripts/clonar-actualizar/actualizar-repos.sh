#!/usr/bin/env bash
# Actualiza (git pull) los repos públicos de RafaUMH2110, clona los nuevos
# y copia todos los archivos .html al directorio de documentos de Apache.
#
# Uso: ./actualizar-repos.sh [directorio_repos] [directorio_apache]
#   directorio_repos   por defecto: $HOME/RafaUMH2110
#   directorio_apache  por defecto: /var/www/html/rafa
set -euo pipefail

USUARIO="RafaUMH2110"
DESTINO="${1:-$HOME/$USUARIO}"
APACHE_DIR="${2:-/var/www/html/rafa}"
LOG="$DESTINO/actualizar.log"

for cmd in git curl jq rsync; do
  command -v "$cmd" >/dev/null || { echo "Falta '$cmd'. Instala con: sudo apt install -y git curl jq rsync" >&2; exit 1; }
done

mkdir -p "$DESTINO"
cd "$DESTINO"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "Inicio de sincronización de $USUARIO en $DESTINO"
nuevos=0; actualizados=0; errores=0
page=1
lista_repos=()

while :; do
  respuesta=$(curl -sf "https://api.github.com/users/$USUARIO/repos?type=public&per_page=100&page=$page") \
    || { log "ERROR: fallo al consultar la API de GitHub (¿límite de peticiones?)"; exit 1; }
  repos=$(echo "$respuesta" | jq -r '.[].name')
  [ -z "$repos" ] && break

  for r in $repos; do
    lista_repos+=("$r")
    if [ -d "$r/.git" ]; then
      if git -C "$r" pull --ff-only --quiet; then
        log "Actualizado: $r"; actualizados=$((actualizados+1))
      else
        log "ERROR actualizando: $r"; errores=$((errores+1))
      fi
    else
      if git clone --quiet "https://github.com/$USUARIO/$r.git"; then
        log "Clonado (nuevo): $r"; nuevos=$((nuevos+1))
      else
        log "ERROR clonando: $r"; errores=$((errores+1))
      fi
    fi
  done
  page=$((page+1))
done

# --- Copia de las apps HTML al directorio de documentos de Apache ---
# Mantiene la estructura <repo>/<subcarpetas>/archivo.html y excluye .git.
if [ ! -d "$APACHE_DIR" ] || [ ! -w "$APACHE_DIR" ]; then
  log "ERROR: '$APACHE_DIR' no existe o no tiene permiso de escritura (ver guía, sección 'Apache')"
  errores=$((errores+1))
else
  for r in "${lista_repos[@]}"; do
    [ -d "$r" ] || continue
    if rsync -a --prune-empty-dirs --chmod=D755,F644 \
         --include='*/' --include='*.html' --exclude='.git/' --exclude='*' \
         "$r/" "$APACHE_DIR/$r/"; then
      n=$(find "$APACHE_DIR/$r" -type f -name '*.html' | wc -l)
      log "Copiadas a Apache: $r ($n html)"
    else
      log "ERROR copiando a Apache: $r"; errores=$((errores+1))
    fi
  done
fi

log "Fin. Nuevos: $nuevos | Actualizados: $actualizados | Errores: $errores"

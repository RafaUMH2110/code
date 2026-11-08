#!/usr/bin/env bash
# =============================================================================
# instalar-todo.sh  ·  Todo en uno para el servidor local Debian 13
#
#   1. Instala dependencias (apache2, git, curl, jq, rsync, python3)
#   2. Elige qué repos/apps clonar (todos, lista, menú interactivo) y los
#      clona o actualiza; permite clonar solo algunas carpetas de un repo
#   3. Despliega en Apache solo lo que se sirve por web (HTML, CSS, JS,
#      imágenes…), genera apps.json e instala el portal index.html
#   4. (Opcional) Instala el colector de telemetría como servicio systemd
#   5. Fija la entrada del servidor en  http://<IP>/rafa/
#   6. Comprueba el resultado (y, opcionalmente, programa la tarea en cron)
#
# Ayuda completa:  ./instalar-todo.sh -h
# Es idempotente: se puede ejecutar de nuevo para actualizar todo.
# =============================================================================
set -euo pipefail

USUARIO_GH="RafaUMH2110"
ORIGEN="$HOME/RafaUMH2110"
DESTINO=""
DOCROOT="/var/www/html"
FORZAR=0
USUARIO_WEB="www-data"
MODO="web"
INDICE=1
CRON_EXPR=""
INTERACTIVO=0
LISTAR=0
TODOS=0
REPOS_CLI=""
EXCLUIR_CLI=""
COLECTOR=0

uso() {
cat <<'EOF'
Uso: ./instalar-todo.sh [opciones]

Origen y destino
  -u USUARIO       Cuenta de GitHub                     (def.: RafaUMH2110)
  -o ORIGEN        Dónde se clonan los repos            (def.: ~/RafaUMH2110)
  -d DESTINO       Directorio de Apache para las apps   (def.: <docroot>/rafa)
  --docroot DIR    DocumentRoot de Apache               (def.: /var/www/html)
  --forzar         No pedir confirmación si DESTINO ya tiene contenido ajeno

Qué clonar (la selección se guarda en ORIGEN/.seleccion y se reutiliza,
también en cron, hasta que cambies de selección o uses --todos)
  -i, --interactivo   Menú para elegir repos y, dentro de cada uno, carpetas
  --repos LISTA       Lista separada por comas. Cada elemento es un repo o
                      repo/carpeta. Ej.: --repos "apps/telemetria,apps/moda,code/linux"
  --excluir LISTA     Todos los repos públicos menos estos. Ej.: --excluir "apps-pro,Artifacts"
  --todos             Olvida la selección guardada y vuelve a clonar todo
  --listar            Muestra los repos y carpetas disponibles y la selección actual

Qué se publica en Apache
  --modo web          (def.) Solo ficheros web: html, css, js, json, imágenes,
                      fuentes, audio/vídeo, pdf. Excluye .py, .ini, .service, .md,
                      .env, claves y config*.json
  --modo html         Solo *.html / *.htm      (alias: --solo-html)
  --modo todo         Todo el contenido del repo (excepto .git, .github y secretos)
  --sin-indice        No instalar el portal index.html (apps.json se genera siempre)

Telemetría
  --colector          Instala el colector (telemetcolector) como servicio systemd.
                      Credenciales: variables TELEMET_STATION_ID y TELEMET_API_KEY,
                      o se piden por terminal. Sin ellas deja el servicio preparado
                      pero sin arrancar.

Otros
  --cron "EXPR"       Programa la tarea en cron, p. ej. --cron "0 3 * * *"
  -h, --help          Esta ayuda
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -u) USUARIO_GH="$2"; shift 2 ;;
    -o) ORIGEN="$2"; shift 2 ;;
    -d) DESTINO="$2"; shift 2 ;;
    --docroot) DOCROOT="${2%/}"; shift 2 ;;
    --forzar) FORZAR=1; shift ;;
    --modo) MODO="$2"; shift 2 ;;
    --solo-html) MODO="html"; shift ;;
    --sin-indice) INDICE=0; shift ;;
    --cron) CRON_EXPR="$2"; shift 2 ;;
    -i|--interactivo) INTERACTIVO=1; shift ;;
    --repos) REPOS_CLI="$2"; shift 2 ;;
    --excluir) EXCLUIR_CLI="$2"; shift 2 ;;
    --todos) TODOS=1; shift ;;
    --listar) LISTAR=1; shift ;;
    --colector) COLECTOR=1; shift ;;
    -h|--help) uso; exit 0 ;;
    *) echo "Opción desconocida: $1  (usa -h para ver la ayuda)" >&2; exit 1 ;;
  esac
done

case "$MODO" in web|html|todo) ;; *) echo "--modo debe ser web, html o todo" >&2; exit 1 ;; esac
[ -n "$DESTINO" ] || DESTINO="$DOCROOT/rafa"

case "$DESTINO" in
  ""|"/"|"/var"|"/var/www"|"/var/www/"|"$DOCROOT"|"$DOCROOT/")
    echo "Destino no permitido: '$DESTINO' (usa una subcarpeta, p. ej. $DOCROOT/rafa)" >&2; exit 1 ;;
esac
case "$DESTINO" in
  "$DOCROOT"/*) ENTRADA="/${DESTINO#$DOCROOT/}/" ;;
  *) echo "El destino debe estar dentro de $DOCROOT (usa --docroot si tu Apache sirve otra carpeta)." >&2; exit 1 ;;
esac
ENTRADA="${ENTRADA//\/\//\/}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null || { echo "Ejecuta como root o instala sudo." >&2; exit 1; }
  SUDO="sudo"
fi

SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
SEL_FILE="$ORIGEN/.seleccion"

# ------------------------------- GitHub ---------------------------------------
REPO_NAMES=(); declare -A REPO_INFO=() REAL=()

obtener_repos() {
  local page=1 resp lineas name lang size
  REPO_NAMES=(); REPO_INFO=(); REAL=()
  while :; do
    resp=$(curl -sf --retry 3 "https://api.github.com/users/$USUARIO_GH/repos?type=public&per_page=100&page=$page") \
      || { echo "ERROR: fallo al consultar la API de GitHub (¿límite de 60 peticiones/hora o sin red?)" >&2; return 1; }
    lineas=$(echo "$resp" | jq -r '.[] | [.name, (.language // "-"), (.size|tostring)] | @tsv') \
      || { echo "ERROR: respuesta inesperada de la API de GitHub" >&2; return 1; }
    [ -z "$lineas" ] && break
    while IFS=$'\t' read -r name lang size; do
      REPO_NAMES+=("$name"); REPO_INFO[$name]="$lang, $size KB"; REAL[${name,,}]="$name"
    done <<< "$lineas"
    page=$((page+1))
  done
  [ "${#REPO_NAMES[@]}" -gt 0 ] || { echo "No hay repos públicos para $USUARIO_GH" >&2; return 1; }
}

carpetas_repo() {   # carpetas de primer nivel de un repo
  curl -sf --retry 2 "https://api.github.com/repos/$USUARIO_GH/$1/contents" 2>/dev/null \
    | jq -r '.[] | select(.type=="dir") | .name | select(startswith(".")|not)' 2>/dev/null || true
}

# ------------------------------ Selección -------------------------------------
declare -A SEL_SET=() SEL_FULL=() SEL_DIRS=() EXCL=()
POS=0
LINEAS=()

cargar_item() {
  local it="$1" neg=0 repo dir real
  it="${it//[$'\r ']/}"
  [ -n "$it" ] || return 0
  case "$it" in \#*) return 0 ;; esac
  if [[ "$it" == -* ]]; then neg=1; it="${it#-}"; fi
  repo="${it%%/*}"; dir=""
  [[ "$it" == */* ]] && dir="${it#*/}"
  dir="${dir%/}"
  real="${REAL[${repo,,}]:-}"
  if [ -z "$real" ]; then
    echo "AVISO: '$repo' no es un repo público de $USUARIO_GH; se ignora" >&2
    return 0
  fi
  if [ "$neg" -eq 1 ]; then EXCL[$real]=1; return 0; fi
  POS=1; SEL_SET[$real]=1
  if [ -z "$dir" ]; then SEL_FULL[$real]=1; else SEL_DIRS[$real]="${SEL_DIRS[$real]:-} $dir"; fi
}

repo_incluido() {
  local r="$1"
  [ -z "${EXCL[$r]:-}" ] || return 1
  if [ "$POS" -eq 1 ]; then [ -n "${SEL_SET[$r]:-}" ]; else return 0; fi
}

menu_multi() {   # menu_multi "Título" item1 item2 …  → MENU_OUT
  local titulo="$1"; shift
  local items=("$@") n=$# i resp tok ok a b
  echo; echo "$titulo"
  for ((i=0; i<n; i++)); do printf '  %2d) %s\n' $((i+1)) "${items[i]}"; done
  while :; do
    resp=""
    read -r -p "Elige (números o rangos 1-3 separados por espacios; Enter = todos; n = ninguno): " resp </dev/tty || resp=""
    MENU_OUT=()
    if [ -z "$resp" ] || [[ "$resp" =~ ^[tTaA] ]]; then MENU_OUT=("${items[@]}"); return 0; fi
    if [[ "$resp" =~ ^[nN] ]]; then return 0; fi
    ok=1; unset seen; declare -A seen=()
    for tok in ${resp//,/ }; do
      if [[ "$tok" =~ ^[0-9]+$ ]] && [ "$tok" -ge 1 ] && [ "$tok" -le "$n" ]; then
        seen[$tok]=1
      elif [[ "$tok" =~ ^([0-9]+)-([0-9]+)$ ]]; then
        a="${BASH_REMATCH[1]}"; b="${BASH_REMATCH[2]}"
        if [ "$a" -ge 1 ] && [ "$b" -le "$n" ] && [ "$a" -le "$b" ]; then
          for ((i=a; i<=b; i++)); do seen[$i]=1; done
        else ok=0; break; fi
      else ok=0; break; fi
    done
    if [ "$ok" -eq 1 ]; then
      for ((i=1; i<=n; i++)); do [ -z "${seen[$i]:-}" ] || MENU_OUT+=("${items[i-1]}"); done
      return 0
    fi
    echo "Entrada no válida."
  done
}

seleccion_interactiva() {
  [ -t 0 ] || { echo "El modo interactivo necesita una terminal." >&2; exit 1; }
  local etiquetas=() elegidos=() r e d resp
  local -a dirs
  for r in "${REPO_NAMES[@]}"; do etiquetas+=("$(printf '%-18s %s' "$r" "${REPO_INFO[$r]}")"); done
  menu_multi "Repositorios públicos de $USUARIO_GH:" "${etiquetas[@]}"
  [ "${#MENU_OUT[@]}" -gt 0 ] || { echo "No has elegido ningún repositorio." >&2; exit 1; }
  for e in "${MENU_OUT[@]}"; do elegidos+=("${e%% *}"); done
  LINEAS=()
  for r in "${elegidos[@]}"; do
    mapfile -t dirs < <(carpetas_repo "$r")
    if [ "${#dirs[@]}" -gt 0 ]; then
      resp=""
      read -r -p "· $r: ¿todo el contenido (T) o elegir carpetas (c)? [T/c] " resp </dev/tty || resp=""
      if [[ "$resp" =~ ^[cC] ]]; then
        menu_multi "Carpetas de $r:" "${dirs[@]}"
        if [ "${#MENU_OUT[@]}" -eq 0 ]; then echo "  (ninguna carpeta elegida: se omite $r)"; continue; fi
        if [ "${#MENU_OUT[@]}" -eq "${#dirs[@]}" ]; then
          LINEAS+=("$r")
        else
          for d in "${MENU_OUT[@]}"; do LINEAS+=("$r/$d"); done
        fi
        continue
      fi
    fi
    LINEAS+=("$r")
  done
}

csv_a_lineas() {   # csv_a_lineas "a,b/c" "prefijo"
  local csv="$1" pre="$2" it
  IFS=',' read -ra _items <<< "$csv"
  for it in "${_items[@]}"; do
    it="${it// /}"
    [ -n "$it" ] && LINEAS+=("$pre$it")
  done
  return 0
}

guardar_seleccion() {
  if [ "${#LINEAS[@]}" -gt 0 ]; then
    printf '%s\n' "${LINEAS[@]}" > "$SEL_FILE"
  else
    rm -f "$SEL_FILE"
  fi
}

mostrar_seleccion() {   # para --listar
  local r d marca dirs
  local -a cur=()
  [ -f "$SEL_FILE" ] && mapfile -t cur < "$SEL_FILE"
  for l in "${cur[@]}"; do cargar_item "$l" 2>/dev/null; done
  echo "Repos públicos de $USUARIO_GH  ([x] = se clonará con la selección actual)"
  [ "${#cur[@]}" -eq 0 ] && echo "(sin selección guardada: se clonan todos)"
  for r in "${REPO_NAMES[@]}"; do
    marca="[ ]"; repo_incluido "$r" && marca="[x]"
    printf '%s %-18s %s\n' "$marca" "$r" "${REPO_INFO[$r]}"
    dirs=$(carpetas_repo "$r" | tr '\n' ' ')
    [ -n "$dirs" ] && echo "      carpetas: $dirs"
    [ -z "${SEL_DIRS[$r]:-}" ] || echo "      seleccionadas:${SEL_DIRS[$r]}"
  done
  return 0
}

# ------------------------------ Modo --listar ---------------------------------
if [ "$LISTAR" -eq 1 ]; then
  for c in curl jq; do command -v "$c" >/dev/null || { echo "Falta '$c' (sudo apt install -y curl jq)" >&2; exit 1; }; done
  obtener_repos || exit 1
  mostrar_seleccion
  exit 0
fi

mkdir -p "$ORIGEN"
LOG="$ORIGEN/instalar-todo.log"
log()  { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# humano BYTES -> "812 B" / "34.5 KB" / "1.2 MB"
humano() { awk -v b="${1:-0}" 'BEGIN{ if(b<1024) printf "%d B",b; else if(b<1048576) printf "%.1f KB",b/1024; else printf "%.1f MB",b/1048576 }'; }

# listar_cambios FICHERO_ITEMIZE -> primeras líneas de la salida de rsync -i (+ nuevo, ~ modificado, - borrado)
listar_cambios() {
  awk -v max=6 '
    function emit(s, p) { if (++n <= max) print s " " p }
    /^>f/ { p = $0; sub(/^[^ ]+ /, "", p); emit(($0 ~ /^>f\+\+\+\+\+\+\+\+\+/) ? "+" : "~", p) }
    /^\*deleting/ { p = $0; sub(/^\*deleting +/, "", p); if (p !~ /\/$/) emit("-", p) }
    END { if (n > max) print "… (+" n - max ")" }
  ' "$1" | while IFS= read -r l; do log "      $l"; done
}
paso() { echo | tee -a "$LOG"; log "=== $* ==="; }

# -----------------------------------------------------------------------------
paso "1/6 Dependencias"
FALTAN=()
for p in apache2 git curl jq rsync python3; do
  dpkg -s "$p" >/dev/null 2>&1 || FALTAN+=("$p")
done
if [ "${#FALTAN[@]}" -gt 0 ]; then
  log "Instalando: ${FALTAN[*]}"
  $SUDO apt-get update -qq
  $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${FALTAN[@]}"
else
  log "Todas las dependencias ya están instaladas"
fi
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  $SUDO systemctl enable --now apache2 >/dev/null 2>&1 || log "AVISO: no se pudo activar apache2 con systemctl"
fi

# -----------------------------------------------------------------------------
paso "2/6 Selección y clonado de repos públicos de $USUARIO_GH"
nuevos=0; actualizados=0; errores=0; sin_cambios=0
g_commits=0; g_add=0; g_mod=0; g_del=0; g_ins=0; g_rem=0; g_bytes=0
obtener_repos || { log "ERROR: no se pudo obtener la lista de repos"; exit 1; }

if [ "$TODOS" -eq 1 ]; then
  rm -f "$SEL_FILE"; log "Selección guardada eliminada: se usarán todos los repos públicos"
fi
if [ "$INTERACTIVO" -eq 1 ]; then
  seleccion_interactiva; guardar_seleccion; log "Selección guardada en $SEL_FILE"
elif [ -n "$REPOS_CLI$EXCLUIR_CLI" ]; then
  LINEAS=()
  [ -n "$REPOS_CLI" ]   && csv_a_lineas "$REPOS_CLI" ""
  [ -n "$EXCLUIR_CLI" ] && csv_a_lineas "$EXCLUIR_CLI" "-"
  guardar_seleccion; log "Selección guardada en $SEL_FILE"
elif [ "$TODOS" -eq 0 ] && [ -f "$SEL_FILE" ]; then
  mapfile -t LINEAS < "$SEL_FILE"; log "Usando la selección guardada ($SEL_FILE)"
else
  LINEAS=()
fi
for l in "${LINEAS[@]}"; do cargar_item "$l"; done

sincronizar_repo() {   # sincronizar_repo repo "carpetas"
  local r="$1" dirs="$2" old new kb0 kb1 dl n_commits a m d ins del nf
  if [ -d "$ORIGEN/$r/.git" ]; then
    if [ -n "$dirs" ]; then
      git -C "$ORIGEN/$r" sparse-checkout set --cone $dirs >/dev/null 2>&1 \
        || { log "ERROR configurando carpetas de $r"; errores=$((errores+1)); return 0; }
    elif [ "$(git -C "$ORIGEN/$r" config --get core.sparseCheckout 2>/dev/null || true)" = "true" ]; then
      git -C "$ORIGEN/$r" sparse-checkout disable >/dev/null 2>&1 || true
    fi
    old="$(git -C "$ORIGEN/$r" rev-parse HEAD 2>/dev/null || true)"
    kb0="$(du -sk "$ORIGEN/$r/.git" 2>/dev/null | cut -f1)"
    if git -C "$ORIGEN/$r" pull --ff-only --quiet; then
      actualizados=$((actualizados+1))
      new="$(git -C "$ORIGEN/$r" rev-parse HEAD 2>/dev/null || true)"
      if [ "$old" = "$new" ]; then
        log "Sin cambios: $r${dirs:+  [carpetas:$dirs]}"; sin_cambios=$((sin_cambios+1))
      else
        n_commits="$(git -C "$ORIGEN/$r" rev-list --count "$old..$new" 2>/dev/null || echo 0)"
        read -r a m d < <(git -C "$ORIGEN/$r" diff --name-status "$old" "$new" ${dirs:+-- $dirs} \
          | awk '{c=substr($1,1,1)} c=="A"{a++} c=="D"{d++} c!="A"&&c!="D"{m++} END{print a+0,m+0,d+0}')
        read -r ins del < <(git -C "$ORIGEN/$r" diff --numstat "$old" "$new" ${dirs:+-- $dirs} \
          | awk '$1~/^[0-9]+$/{i+=$1} $2~/^[0-9]+$/{x+=$2} END{print i+0,x+0}')
        kb1="$(du -sk "$ORIGEN/$r/.git" 2>/dev/null | cut -f1)"
        dl=$(( (${kb1:-0} - ${kb0:-0}) * 1024 )); if [ "$dl" -lt 0 ]; then dl=0; fi
        log "Actualizado: $r${dirs:+  [carpetas:$dirs]}  ·  +$n_commits commits  ·  ficheros: $((a+m+d)) ($a nuevos, $m modificados, $d borrados)  ·  líneas +$ins/-$del  ·  descarga ≈ $(humano $dl)"
        git -C "$ORIGEN/$r" diff --name-status "$old" "$new" ${dirs:+-- $dirs} \
          | awk -v max=6 '{c=substr($1,1,1); s=(c=="A")?"+":(c=="D")?"-":"~"; if(++n<=max) print s " " $NF} END{if(n>max) print "… (+" n-max ")"}' \
          | while IFS= read -r l; do log "      $l"; done
        g_commits=$((g_commits+n_commits)); g_add=$((g_add+a)); g_mod=$((g_mod+m)); g_del=$((g_del+d))
        g_ins=$((g_ins+ins)); g_rem=$((g_rem+del)); g_bytes=$((g_bytes+dl))
      fi
    else
      log "ERROR actualizando: $r"; errores=$((errores+1))
    fi
  else
    if [ -n "$dirs" ]; then
      if git clone --quiet --filter=blob:none --sparse "https://github.com/$USUARIO_GH/$r.git" "$ORIGEN/$r" \
         && git -C "$ORIGEN/$r" sparse-checkout set --cone $dirs >/dev/null 2>&1; then
        nuevos=$((nuevos+1))
        nf="$(find "$ORIGEN/$r" -path "$ORIGEN/$r/.git" -prune -o -type f -print | wc -l | tr -d ' ')"
        dl=$(( $(du -sk "$ORIGEN/$r/.git" | cut -f1) * 1024 ))
        g_add=$((g_add+nf)); g_bytes=$((g_bytes+dl))
        log "Clonado (nuevo): $r  [carpetas:$dirs]  ·  ficheros: $nf  ·  descarga ≈ $(humano $dl)"
      else
        log "ERROR clonando: $r"; errores=$((errores+1))
      fi
    else
      if git clone --quiet "https://github.com/$USUARIO_GH/$r.git" "$ORIGEN/$r"; then
        nuevos=$((nuevos+1))
        nf="$(find "$ORIGEN/$r" -path "$ORIGEN/$r/.git" -prune -o -type f -print | wc -l | tr -d ' ')"
        dl=$(( $(du -sk "$ORIGEN/$r/.git" | cut -f1) * 1024 ))
        g_add=$((g_add+nf)); g_bytes=$((g_bytes+dl))
        log "Clonado (nuevo): $r  ·  ficheros: $nf  ·  descarga ≈ $(humano $dl)"
      else
        log "ERROR clonando: $r"; errores=$((errores+1))
      fi
    fi
  fi
}

SEL_REPOS=(); omitidos=()
for r in "${REPO_NAMES[@]}"; do
  if repo_incluido "$r"; then
    SEL_REPOS+=("$r")
    dirs=""; [ -z "${SEL_FULL[$r]:-}" ] && dirs="${SEL_DIRS[$r]:-}"
    sincronizar_repo "$r" "$dirs"
  else
    omitidos+=("$r")
  fi
done
log "Repos -> nuevos: $nuevos | actualizados: $actualizados (con cambios: $((actualizados-sin_cambios)), sin cambios: $sin_cambios) | errores: $errores"
log "Resumen git -> commits: $g_commits | ficheros: +$g_add ~$g_mod -$g_del | líneas: +$g_ins/-$g_rem | descarga ≈ $(humano $g_bytes)"
[ "${#omitidos[@]}" -gt 0 ] && log "No seleccionados: ${omitidos[*]}"

# -----------------------------------------------------------------------------
paso "3/6 Desplegar en Apache ($DESTINO) · modo $MODO"
MARCA="$DESTINO/.instalar-todo"
PRIMERA=0; BKP=""
if $SUDO test -d "$DESTINO" && ! $SUDO test -f "$MARCA" && ! $SUDO test -f "$DESTINO/.instalar_todo" && [ -n "$($SUDO ls -A "$DESTINO" 2>/dev/null)" ]; then
  PRIMERA=1
  echo
  echo "AVISO: $DESTINO ya tiene contenido que no fue creado por este script:"
  { $SUDO ls -A "$DESTINO" | head -25 | sed 's/^/    /'; } || true
  echo "  El despliegue sustituirá index.html y apps.json, y hará un espejo de cada repo"
  echo "  (borra, dentro de <repo>/, lo que no esté en el repositorio)."
  if [ "$FORZAR" -ne 1 ]; then
    if [ -t 0 ]; then
      read -r -p "  ¿Continuar? Se guardará una copia de lo sustituido o borrado [s/N] " resp </dev/tty || resp=""
      [[ "$resp" =~ ^[sSyY] ]] || { log "Cancelado por el usuario: no se ha modificado $DESTINO"; exit 1; }
    else
      log "ERROR: $DESTINO tiene contenido ajeno y no hay terminal para confirmar. Usa --forzar o revisa el directorio."
      exit 1
    fi
  fi
  BKP="/var/backups/instalar-todo-$(date +%Y%m%d-%H%M%S)"
  $SUDO mkdir -p "$BKP"
  log "Copia de seguridad de lo que se sustituya o borre: $BKP"
  for f in index.html apps.json; do
    if $SUDO test -f "$DESTINO/$f"; then $SUDO cp -a "$DESTINO/$f" "$BKP/$f"; fi
  done
fi
$SUDO mkdir -p "$DESTINO"

EXT_WEB=(html htm css js mjs json webmanifest svg png jpg jpeg gif webp avif ico bmp woff woff2 ttf otf eot mp3 mp4 webm ogg wav pdf xml csv)
SECRETOS=(--exclude='.env*' --exclude='*.key' --exclude='*.pem' --exclude='*secret*' --exclude='*credential*' --exclude='config.ini')
# 'datos/' se protege: ahí escribe el colector de telemetría (historial.json)
RSYNC_OPTS=(-a --delete --delete-excluded --filter='P datos/' --exclude='.git/' --exclude='.github/' "${SECRETOS[@]}")
case "$MODO" in
  web)
    RSYNC_OPTS+=(--prune-empty-dirs --exclude='.*' --exclude='node_modules/' --exclude='package*.json' --exclude='tsconfig*.json' --exclude='*config*.json' --include='*/')
    for e in "${EXT_WEB[@]}"; do RSYNC_OPTS+=(--include="*.$e"); done
    RSYNC_OPTS+=(--exclude='*') ;;
  html)
    RSYNC_OPTS+=(--prune-empty-dirs --exclude='.*' --include='*/' --include='*.html' --include='*.htm' --exclude='*') ;;
  todo)
    RSYNC_OPTS+=(--exclude='.gitignore') ;;
esac

copiados=0; d_new=0; d_mod=0; d_del=0; d_bytes=0
for r in "${SEL_REPOS[@]}"; do
  [ -d "$ORIGEN/$r/.git" ] || [ -f "$ORIGEN/$r/.git" ] || continue
  extra=()
  [ -n "$BKP" ] && extra=(--backup --backup-dir="$BKP/$r")
  salida_rs="$(mktemp)"
  if $SUDO env LC_ALL=C rsync "${RSYNC_OPTS[@]}" "${extra[@]}" -i --stats "$ORIGEN/$r/" "$DESTINO/$r/" >"$salida_rs" 2>&1; then
    copiados=$((copiados+1))
    read -r n m d < <(awk '/^>f\+\+\+\+\+\+\+\+\+/{n++} /^>f/ && !/^>f\+\+\+\+\+\+\+\+\+/{m++} /^\*deleting/ && !/\/$/{d++} END{print n+0,m+0,d+0}' "$salida_rs")
    bytes="$(sed -nE 's/^Total transferred file size: ([0-9,.]+) bytes.*/\1/p' "$salida_rs" | tr -d ',.')"; bytes="${bytes:-0}"
    d_new=$((d_new+n)); d_mod=$((d_mod+m)); d_del=$((d_del+d)); d_bytes=$((d_bytes+bytes))
    if [ $((n+m+d)) -eq 0 ]; then
      log "Desplegado: $r  ·  sin cambios"
    else
      log "Desplegado: $r  ·  $n nuevos  ·  $m modificados  ·  $d borrados  ·  transferido $(humano $bytes)"
      listar_cambios "$salida_rs"
    fi
  else
    log "ERROR copiando: $r"; tail -n 5 "$salida_rs" | tee -a "$LOG"; errores=$((errores+1))
  fi
  rm -f "$salida_rs"
done
for r in "${SEL_REPOS[@]}"; do
  [ -d "$DESTINO/$r" ] && $SUDO find "$DESTINO/$r" -type d -empty ! -name datos -delete 2>/dev/null
done
log "Repos desplegados: $copiados"
log "Resumen despliegue -> nuevos: $d_new | modificados: $d_mod | borrados: $d_del | transferido $(humano $d_bytes)"

# Retirar del despliegue los repos que ya no están seleccionados
for d in "$DESTINO"/*/; do
  n="$(basename "$d")"
  [ -d "$ORIGEN/$n/.git" ] || [ -f "$ORIGEN/$n/.git" ] || continue
  esta=0; for r in "${SEL_REPOS[@]}"; do [ "$r" = "$n" ] && esta=1; done
  if [ "$esta" -eq 0 ]; then $SUDO rm -rf "$DESTINO/$n"; log "Retirado del despliegue (no seleccionado): $n"; fi
done

# Catálogo apps.json: lo lee la página de entrada (index.html) para listar las apps.
# Por cada HTML recoge título, descripción, tamaño, fecha del último commit y el
# README más cercano (proyecto y resumen).
tmp_json="$(mktemp)"
python3 -I - "$ORIGEN" "$DESTINO" "$tmp_json" "$HOME" "$USUARIO_GH" >/dev/null <<'PYEOF'
import sys, os, re, json, subprocess, html, datetime

origen, destino, salida = sys.argv[1], sys.argv[2], sys.argv[3]
SKIP = {'.git', 'node_modules', '.github'}

def leer(p, n=65536):
    with open(p, 'rb') as f:
        return f.read(n).decode('utf-8', 'replace')

def limpio(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', s))).strip()

def meta_html(txt):
    t = re.search(r'<title[^>]*>(.*?)</title>', txt, re.I | re.S)
    d = (re.search(r'<meta[^>]+name=["\']description["\'][^>]*content=["\'](.*?)["\']', txt, re.I | re.S)
         or re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]*name=["\']description["\']', txt, re.I | re.S))
    return (limpio(t.group(1)) if t else ''), (limpio(d.group(1)) if d else '')

def md_plano(s):
    s = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', s)
    s = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', s)
    s = re.sub(r'[*_`]+', '', s)
    return re.sub(r'\s+', ' ', s).strip()

def corta(s, n=200):
    if len(s) <= n:
        return s
    return s[:n].rsplit(' ', 1)[0].rstrip(',;:.') + '…'

def readme(path):
    titulo, parrafo, buf = '', '', []
    en_codigo = False
    for linea in leer(path, 20000).splitlines():
        l = linea.strip()
        if l.startswith('```'):
            en_codigo = not en_codigo
            continue
        if en_codigo:
            continue
        if not titulo and l.startswith('# '):
            titulo = md_plano(l[2:]); continue
        if not l:
            if buf:
                break
            continue
        if l[0] in '#|>-*<![`' or re.match(r'^\d+\.', l):
            if buf:
                break
            continue
        buf.append(l)
    parrafo = corta(md_plano(' '.join(buf)))
    return titulo, parrafo

cache_readme = {}
def readme_cercano(repo_dir, rel_dir):
    d = rel_dir
    while d and d != '.':
        p = os.path.join(repo_dir, d, 'README.md')
        if os.path.isfile(p):
            if p not in cache_readme:
                cache_readme[p] = readme(p)
            return cache_readme[p]
        d = os.path.dirname(d)
    return '', ''

def fecha_git(repo_dir, rel):
    try:
        out = subprocess.run(['git', '-C', repo_dir, 'log', '-1', '--format=%cs', '--', rel],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return ''

# Carpetas donde puede haber clones: la de este script y las vecinas del mismo usuario
# (p. ej. ~/RafaUMH2110 si también se usa el instalar-todo completo). Así la página de
# entrada lista TODAS las apps clonadas y desplegadas, no solo las de esta ejecución.
home, user = sys.argv[4], sys.argv[5]
origins = [origen]
for base in (os.path.dirname(os.path.abspath(origen)), home):
    try:
        for n in sorted(os.listdir(base)):
            p = os.path.join(base, n)
            if (n == user or n.startswith(user + '-')) and os.path.isdir(p) and p not in origins:
                origins.append(p)
    except OSError:
        pass

apps = []
for repo in sorted(os.listdir(destino)):
    repo_dest = os.path.join(destino, repo)
    if repo.startswith('.') or not os.path.isdir(repo_dest):
        continue
    clones = [os.path.join(o, repo) for o in origins if os.path.exists(os.path.join(o, repo, '.git'))]
    if not clones:
        continue
    for root_dir, dirs, filenames in os.walk(repo_dest):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for f in sorted(filenames):
            if not f.lower().endswith(('.html', '.htm')):
                continue
            full = os.path.join(root_dir, f)
            rel = os.path.relpath(full, repo_dest).replace(os.sep, '/')
            # clon que contiene este fichero (el de esta ejecución puede ser parcial)
            clone = next((c for c in clones if os.path.exists(os.path.join(c, rel))), None)
            title, desc = meta_html(leer(full))
            project_name, summary_text = readme_cercano(clone, os.path.dirname(rel)) if clone else ('', '')
            date_str = fecha_git(clone, rel) if clone else ''
            if not date_str:
                date_str = datetime.date.fromtimestamp(os.path.getmtime(full)).isoformat()
            apps.append({'repo': repo, 'path': rel, 'title': title, 'description': desc,
                         'project': project_name, 'summary': summary_text,
                         'size': os.path.getsize(full), 'updated': date_str})

with open(salida, 'w', encoding='utf-8') as fh:
    json.dump({'generated': datetime.datetime.now().strftime('%d/%m/%Y %H:%M'), 'apps': apps},
              fh, ensure_ascii=False, indent=1)
print(len(apps))
PYEOF
$SUDO install -m 644 "$tmp_json" "$DESTINO/apps.json"
rm -f "$tmp_json"
log "Catálogo generado: $DESTINO/apps.json ($(jq '.apps|length' "$DESTINO/apps.json") apps)"

# Página de entrada: plantilla index.html junto a este script (portal visual)
PLANTILLA="$(dirname "$SCRIPT_ABS")/index.html"
if [ "$INDICE" -eq 1 ] && [ -f "$PLANTILLA" ]; then
  $SUDO install -m 644 "$PLANTILLA" "$DESTINO/index.html"
  for _f in favicon.svg favicon.ico apple-touch-icon.png; do
    if [ -f "$(dirname "$PLANTILLA")/$_f" ]; then $SUDO install -m 644 "$(dirname "$PLANTILLA")/$_f" "$DESTINO/$_f"; fi
  done
  log "Portal instalado: $DESTINO/index.html"
elif [ "$INDICE" -eq 1 ]; then
  log "AVISO: no se encontró la plantilla $PLANTILLA; se genera un índice simple"
  tmp="$(mktemp)"
  {
    echo '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
    echo '<meta name="viewport" content="width=device-width,initial-scale=1">'
    echo "<title>Aplicaciones $USUARIO_GH</title>"
    echo '<style>body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222}'
    echo 'h1{font-size:1.5rem}h2{margin-top:1.6rem;font-size:1.1rem;border-bottom:1px solid #ddd}'
    echo 'ul{line-height:1.7}a{color:#0b5ed7;text-decoration:none}a:hover{text-decoration:underline}'
    echo 'small{color:#777}</style></head><body>'
    echo '<h1>Aplicaciones HTML</h1>'
    echo "<small>Actualizado: $(date '+%d/%m/%Y %H:%M')</small>"
    for r in "${SEL_REPOS[@]}"; do
      [ -d "$DESTINO/$r" ] || continue
      mapfile -t files < <(cd "$DESTINO/$r" && find . -type f \( -iname '*.html' -o -iname '*.htm' \) \
                            | sed 's|^\./||' | sort)
      [ "${#files[@]}" -gt 0 ] || continue
      echo "<h2>$r</h2><ul>"
      for f in "${files[@]}"; do
        echo "<li><a href=\"${r// /%20}/${f// /%20}\">$f</a></li>"
      done
      echo '</ul>'
    done
    echo '</body></html>'
  } > "$tmp"
  $SUDO install -m 644 "$tmp" "$DESTINO/index.html"
  rm -f "$tmp"
  log "Índice generado: $DESTINO/index.html"
fi

# Permisos solo sobre lo que gestiona el script (no sobre contenido ajeno de DESTINO)
for item in "$DESTINO/index.html" "$DESTINO/apps.json" "$DESTINO/favicon.svg" "$DESTINO/favicon.ico" "$DESTINO/apple-touch-icon.png"; do
  $SUDO test -f "$item" && $SUDO chown "$USUARIO_WEB:$USUARIO_WEB" "$item"
done
for r in "${SEL_REPOS[@]}"; do
  [ -d "$DESTINO/$r" ] || continue
  $SUDO chown -R "$USUARIO_WEB:$USUARIO_WEB" "$DESTINO/$r"
  $SUDO find "$DESTINO/$r" -type d -exec chmod 755 {} +
  $SUDO find "$DESTINO/$r" -type f -exec chmod 644 {} +
done
$SUDO touch "$MARCA"

# La carpeta donde el colector escribe el JSON debe seguir siendo suya
COLECTOR_DIR="/opt/telemet-colector"
fijar_dir_colector() {
  local cfg="$COLECTOR_DIR/config.ini" ruta
  id telemet >/dev/null 2>&1 || return 0
  $SUDO test -f "$cfg" || return 0
  ruta="$($SUDO sed -nE 's/^[[:space:]]*ruta_json[[:space:]]*=[[:space:]]*([^[:space:]]+).*/\1/p' "$cfg" | head -1)"
  [ -n "$ruta" ] || return 0
  case "$ruta" in "$DESTINO"/*) ;; *) return 0 ;; esac
  # Si la carpeta no existe (config.ini con la ruta por defecto, p. ej.), no hay nada que ajustar
  $SUDO test -d "$(dirname "$ruta")" || { log "AVISO: la carpeta del JSON del colector no existe: $(dirname "$ruta") (se ignora; revisa ruta_json en $cfg)"; return 0; }
  $SUDO chown -R telemet:telemet "$(dirname "$ruta")" || log "AVISO: no se pudo ajustar el propietario de $(dirname "$ruta")"
  return 0
}
fijar_dir_colector
log "Permisos aplicados ($USUARIO_WEB)"

# -----------------------------------------------------------------------------
paso "4/6 Colector de telemetría"
HEADERS_CONF=0

ini_set() {   # ini_set clave valor fichero  (el valor viaja por entorno, no por la línea de comandos)
  local k="$1" v="$2" f="$3" tmp act
  tmp="$(mktemp)"
  # Si la clave ya está activa se sustituye esa línea; solo si no lo está se usa la
  # primera línea comentada (así no se tocan los ejemplos de la plantilla)
  # (también se elimina un BOM UTF-8 inicial, que rompe configparser)
  act=0; $SUDO grep -qE "^[[:space:]]*$k[[:space:]]*=" "$f" && act=1
  $SUDO cat "$f" | sed '1s/^\xEF\xBB\xBF//' | K="$k" V="$v" ACT="$act" awk '
    BEGIN { k = ENVIRON["K"]; v = ENVIRON["V"]; pre = (ENVIRON["ACT"] == "1") ? "^[ \t]*" : "^[;# \t]*"; done = 0 }
    { if (!done && match($0, pre k "[ \t]*=")) { print k " = " v; done = 1 } else print }' > "$tmp"
  $SUDO install -m 600 "$tmp" "$f"
  rm -f "$tmp"
}

instalar_colector() {
  local src src_dir historial json_dir unit tmp station key resp pend=0
  src="$(find "$ORIGEN" -type f -path '*/telemetcolector/telemet_colector.py' 2>/dev/null | head -1)"
  if [ -z "$src" ]; then
    log "AVISO: no se encontró telemetcolector en los repos clonados (¿está seleccionado apps/telemetria?)"
    return 0
  fi
  src_dir="$(dirname "$src")"

  # Dónde publica el JSON: junto a la app TeleMet Historial desplegada
  historial="$(find "$DESTINO" -type f -path '*/telemet/historial/index.html' 2>/dev/null | head -1)"
  if [ -n "$historial" ]; then json_dir="$(dirname "$historial")/datos"; else json_dir="$DESTINO/telemethistorial/datos"; fi

  id telemet >/dev/null 2>&1 || {
    $SUDO useradd --system --home-dir "$COLECTOR_DIR" --shell /usr/sbin/nologin telemet
    log "Usuario de servicio 'telemet' creado"
  }
  $SUDO mkdir -p "$COLECTOR_DIR/datos"
  $SUDO install -m 644 "$src_dir/telemet_colector.py" "$COLECTOR_DIR/telemet_colector.py"
  $SUDO install -m 644 "$src_dir/config.example.ini" "$COLECTOR_DIR/config.example.ini"
  if ! $SUDO test -f "$COLECTOR_DIR/config.ini"; then
    $SUDO install -m 600 "$src_dir/config.example.ini" "$COLECTOR_DIR/config.ini"
    log "Creado $COLECTOR_DIR/config.ini a partir de la plantilla"
  fi
  $SUDO install -d -o telemet -g telemet -m 755 "$json_dir"
  ini_set ruta_json "$json_dir/historial.json" "$COLECTOR_DIR/config.ini"

  # Credenciales (solo si siguen siendo los marcadores de la plantilla)
  if $SUDO grep -qE '^[[:space:]]*(station_id|api_key)[[:space:]]*=[[:space:]]*(TU_STATION_ID|TU_API_KEY)' "$COLECTOR_DIR/config.ini"; then
    station="${TELEMET_STATION_ID:-}"; key="${TELEMET_API_KEY:-}"
    if [ -z "$station$key" ] && [ -t 0 ]; then
      read -r -p "Station ID de Weather Underground (Enter = configurar más tarde): " station </dev/tty || station=""
      if [ -n "$station" ]; then read -r -s -p "API Key (no se muestra): " key </dev/tty || key=""; echo; fi
    fi
    if [ -n "$station" ] && [ -n "$key" ]; then
      ini_set station_id "$station" "$COLECTOR_DIR/config.ini"
      ini_set api_key "$key" "$COLECTOR_DIR/config.ini"
      log "Credenciales guardadas en $COLECTOR_DIR/config.ini (permisos 600)"
    fi
  fi
  $SUDO grep -qE '^[[:space:]]*(station_id|api_key)[[:space:]]*=[[:space:]]*(TU_STATION_ID|TU_API_KEY)' "$COLECTOR_DIR/config.ini" && pend=1

  $SUDO chown -R telemet:telemet "$COLECTOR_DIR"
  $SUDO chmod 600 "$COLECTOR_DIR/config.ini"
  $SUDO chown -R telemet:telemet "$json_dir"

  # Servicio systemd: el del repo, con la carpeta del JSON adaptada
  tmp="$(mktemp)"
  if [ -f "$src_dir/telemet-colector.service" ]; then
    sed "s|/var/www/htdocs/rafa/telemethistorial/datos|$json_dir|g" "$src_dir/telemet-colector.service" > "$tmp"
  else
    cat > "$tmp" <<UNIT
[Unit]
Description=TeleMet Colector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=telemet
Group=telemet
WorkingDirectory=$COLECTOR_DIR
ExecStart=/usr/bin/python3 $COLECTOR_DIR/telemet_colector.py -c $COLECTOR_DIR/config.ini
Restart=always
RestartSec=10
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$COLECTOR_DIR/datos $json_dir

[Install]
WantedBy=multi-user.target
UNIT
  fi
  grep -qF "$json_dir" "$tmp" || sed -i "/^ReadWritePaths=/a ReadWritePaths=$json_dir" "$tmp"
  $SUDO install -m 644 "$tmp" /etc/systemd/system/telemet-colector.service
  rm -f "$tmp"
  log "Servicio instalado: /etc/systemd/system/telemet-colector.service (JSON en $json_dir/historial.json)"

  # Apache: que el navegador no guarde en caché el JSON
  $SUDO a2enmod headers >/dev/null 2>&1 || true
  $SUDO tee /etc/apache2/conf-available/telemet-historial.conf >/dev/null <<EOF
<Directory "$json_dir">
    <FilesMatch "\.json\$">
        Header set Cache-Control "no-store"
    </FilesMatch>
</Directory>
EOF
  $SUDO a2enconf telemet-historial >/dev/null
  HEADERS_CONF=1

  if [ "$pend" -eq 1 ]; then
    log "AVISO: faltan station_id y api_key. Para terminar:"
    log "   sudo nano $COLECTOR_DIR/config.ini"
    log "   sudo -u telemet python3 $COLECTOR_DIR/telemet_colector.py -c $COLECTOR_DIR/config.ini --probar"
    log "   sudo systemctl enable --now telemet-colector"
  fi
  if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    $SUDO systemctl daemon-reload
    if [ "$pend" -eq 0 ]; then
      $SUDO systemctl enable telemet-colector >/dev/null 2>&1
      $SUDO systemctl restart telemet-colector
      sleep 2
      log "Servicio telemet-colector: $($SUDO systemctl is-active telemet-colector || true)"
    fi
  else
    log "AVISO: systemd no está activo en este sistema; el servicio queda instalado sin arrancar"
  fi
}

if [ "$COLECTOR" -eq 1 ]; then
  instalar_colector
else
  log "No solicitado (usa --colector para instalarlo)"
fi

# -----------------------------------------------------------------------------
paso "5/6 Fijar la entrada en $ENTRADA"
TS="$(date +%Y%m%d-%H%M%S)"
COPIA="/var/backups/entrada-apache-$TS"
$SUDO mkdir -p "$COPIA"
cambios=()

# 5a) Anular Redirect/Rewrite hacia /moda/ y DocumentRoot en .../moda
mapfile -t CANDIDATOS < <($SUDO grep -rliE "^[[:space:]]*(Redirect|RedirectMatch|RedirectPermanent|RewriteRule|DocumentRoot).*moda" \
    /etc/apache2/sites-available /etc/apache2/conf-available /etc/apache2/apache2.conf \
    "$DOCROOT/.htaccess" 2>/dev/null || true)
for f in "${CANDIDATOS[@]}"; do
  [ -n "$f" ] || continue
  $SUDO cp -a --parents "$f" "$COPIA"
  $SUDO sed -i --follow-symlinks -E \
    -e "s|^([[:space:]]*)(Redirect[A-Za-z]*[[:space:]].*[Mm][Oo][Dd][Aa].*)$|\1# [anulado $TS] \2|" \
    -e "s|^([[:space:]]*)(RewriteRule[[:space:]].*[Mm][Oo][Dd][Aa].*)$|\1# [anulado $TS] \2|" \
    -e "s|^([[:space:]]*)DocumentRoot[[:space:]]+\"?[^[:space:]\"]*[Mm][Oo][Dd][Aa]/?\"?[[:space:]]*$|\1DocumentRoot $DOCROOT|" \
    "$f"
  cambios+=("$f")
  log "Reglas hacia /moda/ anuladas en: $f"
done

# 5b) index.html de la raíz que apunte a /moda/ -> sustituir por redirección
if [ -f "$DOCROOT/index.html" ] && $SUDO grep -qiE "moda" "$DOCROOT/index.html"; then
  $SUDO cp -a --parents "$DOCROOT/index.html" "$COPIA"
  cambios+=("$DOCROOT/index.html")
  log "Sustituido $DOCROOT/index.html (apuntaba a /moda/)"
  printf '%s\n' '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">' \
    "<meta http-equiv=\"refresh\" content=\"0; url=$ENTRADA\"><title>Redirigiendo…</title></head>" \
    "<body><a href=\"$ENTRADA\">Ir a $ENTRADA</a></body></html>" \
    | $SUDO tee "$DOCROOT/index.html" >/dev/null
fi

# 5c) Regla de entrada: la raíz redirige a /rafa/ (relativa: vale con localhost, IP o nombre)
$SUDO a2enmod alias >/dev/null 2>&1 || true
$SUDO tee /etc/apache2/conf-available/entrada-rafa.conf >/dev/null <<EOF
# Entrada por defecto del servidor: la raíz redirige a $ENTRADA
RedirectMatch ^/\$ $ENTRADA
EOF
$SUDO a2enconf entrada-rafa >/dev/null

if $SUDO apache2ctl configtest >>"$LOG" 2>&1; then
  if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    $SUDO systemctl reload apache2
  else
    $SUDO apache2ctl graceful || $SUDO apache2ctl start
  fi
  log "Apache recargado con la entrada $ENTRADA"
else
  log "ERROR en la configuración de Apache: restaurando copia de seguridad"
  $SUDO a2disconf entrada-rafa >/dev/null 2>&1 || true
  [ "$HEADERS_CONF" -eq 1 ] && $SUDO a2disconf telemet-historial >/dev/null 2>&1 || true
  for f in "${cambios[@]}"; do $SUDO cp -a "$COPIA$f" "$f"; done
  log "Restaurado desde $COPIA. Revisa: sudo apache2ctl configtest"
  exit 1
fi

# 5d) Avisos: menciones a /moda/ que no se han podido anular automáticamente
RESTOS=$($SUDO grep -rniE "(Redirect|RewriteRule|DocumentRoot|DirectoryIndex|Alias).*moda" /etc/apache2 2>/dev/null | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' || true)
if [ -n "$RESTOS" ]; then
  log "AVISO: quedan referencias a 'moda' en la configuración; revísalas:"
  echo "$RESTOS" | tee -a "$LOG"
fi

# -----------------------------------------------------------------------------
paso "6/6 Comprobación"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; IP="${IP:-localhost}"
cod_raiz=$(curl -s -o /dev/null -w '%{http_code} -> %{redirect_url}' "http://localhost/" || echo "sin respuesta")
cod_rafa=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost$ENTRADA" || echo "sin respuesta")
log "http://localhost/        : $cod_raiz"
log "http://localhost$ENTRADA : $cod_rafa"
if [ "$COLECTOR" -eq 1 ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  log "telemet-colector         : $(systemctl is-active telemet-colector 2>/dev/null || true)"
fi

if [ -n "$CRON_EXPR" ]; then
  linea="$CRON_EXPR $SCRIPT_ABS -u $USUARIO_GH -o $ORIGEN -d $DESTINO"
  [ "$MODO" != "web" ] && linea="$linea --modo $MODO"
  [ "$INDICE" -eq 0 ]  && linea="$linea --sin-indice"
  [ "$COLECTOR" -eq 1 ] && linea="$linea --colector"
  linea="$linea >/dev/null 2>&1"
  ( crontab -l 2>/dev/null | grep -vF "$SCRIPT_ABS" ; echo "$linea" ) | crontab -
  log "Cron programado: $CRON_EXPR (usa la selección guardada en $SEL_FILE)"
fi

echo | tee -a "$LOG"
log "FIN. Entrada: http://$IP$ENTRADA  |  Errores: $errores  |  Duración: ${SECONDS}s  |  Copia de seguridad: $COPIA"
[ "$errores" -eq 0 ]

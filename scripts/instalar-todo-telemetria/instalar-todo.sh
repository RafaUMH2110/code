#!/usr/bin/env bash
# =============================================================================
# instalar-todo.sh  ·  Apps de telemetría + telemet-colector (Debian 13)
#
# Versión reducida de instalar-todo: solo trabaja con las apps de telemetría
# (repo apps, carpeta telemetria/), que incluye los dos colectores
# (telemetcolector en español y telemetcollector en inglés).
#
#   1. Instala dependencias (apache2, git, curl, jq, rsync, python3)
#   2. Clona o actualiza SOLO apps/telemetria (clonado parcial)
#   3. Despliega en Apache solo lo que se sirve por web (HTML, CSS, JS,
#      imágenes…), genera apps.json e instala el portal index.html
#   4. (A elegir) Instala telemet-colector (versión española) como servicio systemd.
#      La versión inglesa, telemet-collector, la instala install-all.sh
#   5. Fija la entrada del servidor en  http://<IP>/rafa/
#   6. Comprueba el resultado (y, opcionalmente, programa la tarea en cron)
#
# Ayuda completa:  ./instalar-todo.sh -h
# Es idempotente: se puede ejecutar de nuevo para actualizar todo.
# =============================================================================
set -euo pipefail

USUARIO_GH="RafaUMH2110"
REPO="apps"
FOLDER="telemetria"
ORIGEN="$HOME/RafaUMH2110-telemetria"
DESTINO=""
DOCROOT="/var/www/html"
FORZAR=0
USUARIO_WEB="www-data"
MODO="web"
INDICE=1
CRON_EXPR=""
COLECTOR=""        # vacío = preguntar (si hay terminal) · 1 = instalar · 0 = no instalar

uso() {
cat <<'EOF'
Uso: ./instalar-todo.sh [opciones]

Clona solo las apps de telemetría (RafaUMH2110/apps, carpeta telemetria/, que
incluye telemetcolector y telemetcollector), las publica en Apache y, si lo
eliges, instala telemet-colector (colector en español) como servicio systemd.

Origen y destino
  -u USUARIO       Cuenta de GitHub                     (def.: RafaUMH2110)
  -o ORIGEN        Dónde se clona el repo               (def.: ~/RafaUMH2110-telemetria)
  -d DESTINO       Directorio de Apache para las apps   (def.: <docroot>/rafa)
  --docroot DIR    DocumentRoot de Apache               (def.: /var/www/html)
  --forzar         No pedir confirmación si DESTINO ya tiene contenido ajeno

Qué se publica en Apache
  --modo web          (def.) Solo ficheros web: html, css, js, json, imágenes,
                      fuentes, audio/vídeo, pdf. Excluye .py, .ini, .service, .md,
                      .env, claves y config*.json
  --modo html         Solo *.html / *.htm      (alias: --solo-html)
  --modo todo         Todo el contenido (excepto .git, .github y secretos)
  --sin-indice        No instalar el portal index.html (apps.json se genera siempre)

Colector (telemet-colector, versión española)
  --colector          Instalarlo como servicio systemd (/opt/telemet-colector).
                      Credenciales: variables TELEMET_STATION_ID y TELEMET_API_KEY,
                      o se piden por terminal. Sin ellas deja el servicio preparado
                      pero sin arrancar.
  --sin-colector      No instalarlo
  (sin ninguna de las dos: se pregunta si hay terminal; si no, no se instala.
   La versión inglesa, telemet-collector, la instala install-all.sh)

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
    --colector) COLECTOR=1; shift ;;
    --sin-colector) COLECTOR=0; shift ;;
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

# ¿Instalar el colector? Si no se ha indicado, se pregunta (solo con terminal)
if [ -z "$COLECTOR" ]; then
  if [ -t 0 ]; then
    read -r -p "¿Instalar telemet-colector (colector en español) como servicio systemd? [s/N] " _resp </dev/tty || _resp=""
    if [[ "$_resp" =~ ^[sSyY] ]]; then COLECTOR=1; else COLECTOR=0; fi
  else
    COLECTOR=0
  fi
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
paso "2/6 Clonado de las apps de telemetría ($USUARIO_GH/$REPO · carpeta $FOLDER)"
nuevos=0; actualizados=0; errores=0; sin_cambios=0
g_commits=0; g_add=0; g_mod=0; g_del=0; g_ins=0; g_rem=0; g_bytes=0

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

SEL_REPOS=("$REPO")
sincronizar_repo "$REPO" "$FOLDER"
for _c in telemetcolector telemetcollector; do
  if [ -d "$ORIGEN/$REPO/$FOLDER/$_c" ]; then log "Colector disponible: $FOLDER/$_c"; else log "AVISO: no se encontró $FOLDER/$_c en el repo clonado"; fi
done
log "Repos -> nuevos: $nuevos | actualizados: $actualizados (con cambios: $((actualizados-sin_cambios)), sin cambios: $sin_cambios) | errores: $errores"
log "Resumen git -> commits: $g_commits | ficheros: +$g_add ~$g_mod -$g_del | líneas: +$g_ins/-$g_rem | descarga ≈ $(humano $g_bytes)"

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
# 'datos/' y 'data/' se protegen: ahí escribe el colector de telemetría (historial.json / history.json)
RSYNC_OPTS=(-a --delete --delete-excluded --filter='P datos/' --filter='P data/' --exclude='.git/' --exclude='.github/' "${SECRETOS[@]}")
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
  [ -d "$DESTINO/$r" ] && $SUDO find "$DESTINO/$r" -type d -empty ! -name datos ! -name data -delete 2>/dev/null
done
log "Repos desplegados: $copiados"
log "Resumen despliegue -> nuevos: $d_new | modificados: $d_mod | borrados: $d_del | transferido $(humano $d_bytes)"

# Catálogo apps.json: lo lee la página de entrada (index.html) para listar las apps.
# Por cada HTML recoge título, descripción, tamaño, fecha del último commit y el
# README más cercano (proyecto y resumen).
tmp_json="$(mktemp)"
python3 -I - "$ORIGEN" "$DESTINO" "$tmp_json" >/dev/null <<'PYEOF'
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

apps = []
for repo in sorted(os.listdir(origen)):
    repo_origen = os.path.join(origen, repo)
    repo_dest = os.path.join(destino, repo)
    if not (os.path.exists(os.path.join(repo_origen, '.git')) and os.path.isdir(repo_dest)):
        continue
    for raiz, dirs, ficheros in os.walk(repo_dest):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for f in sorted(ficheros):
            if not f.lower().endswith(('.html', '.htm')):
                continue
            full = os.path.join(raiz, f)
            rel = os.path.relpath(full, repo_dest).replace(os.sep, '/')
            titulo, desc = meta_html(leer(full))
            proyecto, resumen = readme_cercano(repo_origen, os.path.dirname(rel))
            fecha = fecha_git(repo_origen, rel)
            if not fecha:
                fecha = datetime.date.fromtimestamp(os.path.getmtime(full)).isoformat()
            apps.append({'repo': repo, 'path': rel, 'title': titulo, 'description': desc,
                         'project': proyecto, 'summary': resumen,
                         'size': os.path.getsize(full), 'updated': fecha})

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
for item in "$DESTINO/index.html" "$DESTINO/apps.json"; do
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
paso "4/6 TeleMet Colector (telemet-colector)"
HEADERS_CONF=0

ini_set() {   # ini_set clave valor fichero  (el valor viaja por entorno, no por la línea de comandos)
  local k="$1" v="$2" f="$3" tmp act
  tmp="$(mktemp)"
  # Solo se sustituye la PRIMERA línea activa de esa clave (o, si no hay ninguna, la primera comentada):
  # así no se descomentan los ejemplos de la plantilla ni se duplica la clave.
  # (también se elimina un BOM UTF-8 inicial, que rompe configparser)
  act=0; $SUDO grep -qE "^[[:space:]]*$k[[:space:]]*=" "$f" && act=1
  $SUDO cat "$f" | sed '1s/^\xEF\xBB\xBF//' | K="$k" V="$v" ACT="$act" awk '
    BEGIN { k = ENVIRON["K"]; v = ENVIRON["V"]; pre = (ENVIRON["ACT"] == "1") ? "^[ \t]*" : "^[;# \t]*"; done = 0 }
    { if (!done && match($0, pre k "[ \t]*=")) { print k " = " v; done = 1 } else print }' > "$tmp"
  $SUDO install -m 600 "$tmp" "$f"
  rm -f "$tmp"
}

instalar_colector() {
  local src_dir app json_dir tmp station key pend=0
  src_dir="$ORIGEN/$REPO/$FOLDER/telemetcolector"
  if [ ! -f "$src_dir/telemet_colector.py" ]; then
    log "AVISO: no se encontró $src_dir/telemet_colector.py (¿se ha clonado bien apps/$FOLDER?)"
    return 0
  fi
  if [ -f "/etc/systemd/system/telemet-collector.service" ]; then
    log "AVISO: también hay instalado el servicio telemet-collector.service (la otra versión del colector); si lee la misma estación, conviene dejar solo uno"
  fi

  # Dónde publica el JSON: junto a la app TeleMet Historial desplegada
  app="$(find "$DESTINO" -type f -path '*/telemet/historial/index.html' 2>/dev/null | head -1)"
  if [ -n "$app" ]; then json_dir="$(dirname "$app")/datos"; else json_dir="$DESTINO/$REPO/$FOLDER/telemet/historial/datos"; fi

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
  log "Colector: no instalado (usa --colector para instalarlo)"
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
  if [ "$COLECTOR" -eq 1 ]; then linea="$linea --colector"; else linea="$linea --sin-colector"; fi
  linea="$linea >/dev/null 2>&1"
  ( crontab -l 2>/dev/null | grep -vF "$SCRIPT_ABS" ; echo "$linea" ) | crontab -
  log "Cron programado: $CRON_EXPR"
fi

echo | tee -a "$LOG"
log "FIN. Entrada: http://$IP$ENTRADA  |  Errores: $errores  |  Duración: ${SECONDS}s  |  Copia de seguridad: $COPIA"
[ "$errores" -eq 0 ]

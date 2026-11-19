#!/usr/bin/env bash
# =============================================================================
# clonar-code.sh  ·  Clona o actualiza el repo COMPLETO RafaUMH2110/code
#
# Trae TODOS los directorios del repo, incluidos los nuevos
# (telemetria/meteo/, telemetria/home/, telemetria/home/telehome-enchufes-*/, generador-apps/…),
# sin clonado parcial. Si ya tenías un clon parcial (sparse-checkout), lo
# completa. Al terminar informa de qué ha cambiado y comprueba que existen los
# directorios exigidos.
#
#   1. Clona (o actualiza con fetch + fast-forward) el repo entero
#   2. Informa: commits, ficheros nuevos/modificados/borrados, líneas,
#      descarga aproximada y DIRECTORIOS NUEVOS
#   3. Comprueba que existen los directorios exigidos (def.: los de la lista
#      EXIGIR_DEF, entre ellos telemetria/home)
#   4. Resume el contenido por directorio de primer nivel
#   5. (Opcional) programa la actualización periódica en cron
#
# Ayuda completa:  ./clonar-code.sh -h
# Es idempotente: se puede ejecutar de nuevo para actualizar.
# =============================================================================
set -euo pipefail

USUARIO_GH="RafaUMH2110"
REPO="code"
ORIGEN="$HOME/RafaUMH2110"
RAMA=""
FORZAR=0
ARBOL=0
COMPROBAR=1
CRON_EXPR=""
EXIGIR_DEF="telemetria/meteo,telemetria/home/telehome-enchufes-local,telemetria/home/telehome-enchufes-nube,telemetria/home/telehome-enchufes-vscode,generador-apps,linux,macos,windows,scripts"
EXIGIR="$EXIGIR_DEF"

uso() {
cat <<'EOF'
Uso: ./clonar-code.sh [opciones]

Clona (o actualiza) el repo completo RafaUMH2110/code, con todos sus
directorios, y muestra qué ha cambiado.

Origen
  -u USUARIO       Cuenta de GitHub                  (def.: RafaUMH2110)
  -r REPO          Repositorio                       (def.: code)
  -o ORIGEN        Carpeta que contendrá el clon     (def.: ~/RafaUMH2110)
                   El repo queda en ORIGEN/REPO, p. ej. ~/RafaUMH2110/code
  -b RAMA          Rama a seguir                     (def.: la rama por defecto del repo)

Comprobación
  --exigir LISTA   Directorios que deben existir tras clonar, separados por comas
                   (def.: telemetria/meteo, telemetria/home/telehome-enchufes-local,
                   telemetria/home/telehome-enchufes-nube, telemetria/home/telehome-enchufes-vscode,
                   generador-apps, linux, macos, windows, scripts)
  --sin-comprobar  No comprobar directorios (desactiva --exigir)
  --arbol          Mostrar también los subdirectorios de segundo nivel

Actualización
  --forzar         Si el clon tiene cambios locales o no puede avanzar (fast-forward),
                   guarda una copia (.patch y rama copia-…) y lo iguala al remoto

Otros
  --cron "EXPR"    Programar la actualización en cron, p. ej. --cron "0 3 * * *"
  -h, --help       Esta ayuda

Códigos de salida: 0 = correcto · 1 = error o falta algún directorio exigido
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -u) USUARIO_GH="$2"; shift 2 ;;
    -r) REPO="$2"; shift 2 ;;
    -o) ORIGEN="${2%/}"; shift 2 ;;
    -b) RAMA="$2"; shift 2 ;;
    --exigir) EXIGIR="$2"; shift 2 ;;
    --sin-comprobar) COMPROBAR=0; shift ;;
    --arbol) ARBOL=1; shift ;;
    --forzar) FORZAR=1; shift ;;
    --cron) CRON_EXPR="$2"; shift 2 ;;
    -h|--help) uso; exit 0 ;;
    *) echo "Opción desconocida: $1  (usa -h para ver la ayuda)" >&2; exit 1 ;;
  esac
done

command -v git >/dev/null 2>&1 || { echo "Falta git (sudo apt install -y git)" >&2; exit 1; }

DEST="$ORIGEN/$REPO"
URL="https://github.com/$USUARIO_GH/$REPO.git"
SCRIPT_ABS="$(readlink -f "$0")"
mkdir -p "$ORIGEN"
LOG="$ORIGEN/clonar-code.log"
SECONDS=0
errores=0

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# humano BYTES -> "812 B" / "34.5 KB" / "1.2 MB"
humano() { awk -v b="${1:-0}" 'BEGIN{ if(b<1024) printf "%d B",b; else if(b<1048576) printf "%.1f KB",b/1024; else printf "%.1f MB",b/1048576 }'; }

# dirs_de COMMIT -> directorios (hasta 3 niveles) que contienen ficheros en ese commit
dirs_de() {
  git -C "$DEST" ls-tree -r --name-only "$1" \
    | awk -F/ 'NF>1{ d=$1; print d; for(i=2;i<NF&&i<=3;i++){ d=d"/"$i; print d } }' | sort -u
}

# nficheros DIR -> número de ficheros (sin .git)
nficheros() { find "$1" -path "$1/.git" -prune -o -type f -print 2>/dev/null | wc -l | tr -d ' '; }

# -----------------------------------------------------------------------------
log "=== 1/4 Clonado de $USUARIO_GH/$REPO en $DEST ==="
if [ -z "$RAMA" ]; then
  RAMA="$(git ls-remote --symref "$URL" HEAD 2>/dev/null | awk '/^ref:/{sub("refs/heads/","",$2); print $2; exit}' || true)"
fi
[ -n "$RAMA" ] || { log "ERROR: no se pudo consultar $URL (¿sin red o el repo no es público?)"; exit 1; }
log "Rama: $RAMA"

if [ -d "$DEST/.git" ]; then
  # --- clon existente: completar si es parcial, avisar de cambios locales, avanzar
  if [ "$(git -C "$DEST" config --get core.sparseCheckout 2>/dev/null || true)" = "true" ]; then
    antes="$(nficheros "$DEST")"
    git -C "$DEST" sparse-checkout disable >/dev/null 2>&1 || true
    despues="$(nficheros "$DEST")"
    log "Clon parcial detectado: se desactiva el sparse-checkout y se completa  ·  ficheros: $antes -> $despues (+$((despues-antes)))"
  fi
  actual="$(git -C "$DEST" remote get-url origin 2>/dev/null || true)"
  [ "$actual" = "$URL" ] || log "AVISO: el remoto origin es '$actual' (se esperaba $URL)"

  TS="$(date +%Y%m%d-%H%M%S)"
  sucios="$(git -C "$DEST" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$sucios" -gt 0 ]; then
    if [ "$FORZAR" -eq 1 ]; then
      mkdir -p "$ORIGEN/copias-clonar-code"
      git -C "$DEST" diff HEAD > "$ORIGEN/copias-clonar-code/$REPO-$TS.patch" || true
      log "Cambios locales ($sucios ficheros) guardados en $ORIGEN/copias-clonar-code/$REPO-$TS.patch"
      git -C "$DEST" reset --hard --quiet HEAD
    else
      log "AVISO: el clon tiene $sucios ficheros con cambios locales (si no se puede actualizar, usa --forzar)"
    fi
  fi

  old="$(git -C "$DEST" rev-parse HEAD)"
  kb0="$(du -sk "$DEST/.git" 2>/dev/null | cut -f1)"
  if ! git -C "$DEST" fetch --quiet --prune origin "$RAMA"; then
    log "ERROR: fallo al consultar $URL"; exit 1
  fi
  new="$(git -C "$DEST" rev-parse FETCH_HEAD)"

  if [ "$old" = "$new" ]; then
    log "Sin cambios: $REPO ya está en la última versión ($(git -C "$DEST" rev-parse --short HEAD))"
  else
    if [ "$(git -C "$DEST" rev-parse --abbrev-ref HEAD)" != "$RAMA" ]; then
      git -C "$DEST" checkout --quiet "$RAMA" 2>/dev/null || log "AVISO: no se pudo cambiar a la rama $RAMA"
    fi
    if ! git -C "$DEST" merge --ff-only --quiet FETCH_HEAD 2>/dev/null; then
      if [ "$FORZAR" -eq 1 ]; then
        git -C "$DEST" branch "copia-antes-de-forzar-$TS" "$old" >/dev/null 2>&1 || true
        git -C "$DEST" reset --hard --quiet FETCH_HEAD
        log "AVISO: no se podía avanzar (fast-forward); igualado al remoto. Versión anterior en la rama copia-antes-de-forzar-$TS"
      else
        log "ERROR: no se puede avanzar (fast-forward). Revisa el clon o usa --forzar"; exit 1
      fi
    fi
    n_commits="$(git -C "$DEST" rev-list --count "$old..$new" 2>/dev/null || echo 0)"
    read -r a m d < <(git -C "$DEST" diff --name-status "$old" "$new" \
      | awk '{c=substr($1,1,1)} c=="A"{a++} c=="D"{d++} c!="A"&&c!="D"{m++} END{print a+0,m+0,d+0}')
    read -r ins del < <(git -C "$DEST" diff --numstat "$old" "$new" \
      | awk '$1~/^[0-9]+$/{i+=$1} $2~/^[0-9]+$/{x+=$2} END{print i+0,x+0}')
    kb1="$(du -sk "$DEST/.git" 2>/dev/null | cut -f1)"
    dl=$(( (${kb1:-0} - ${kb0:-0}) * 1024 )); if [ "$dl" -lt 0 ]; then dl=0; fi
    log "Actualizado: $REPO  ·  +$n_commits commits  ·  ficheros: $((a+m+d)) ($a nuevos, $m modificados, $d borrados)  ·  líneas +$ins/-$del  ·  descarga ≈ $(humano $dl)"
    git -C "$DEST" diff --name-status "$old" "$new" \
      | awk -v max=8 '{c=substr($1,1,1); s=(c=="A")?"+":(c=="D")?"-":"~"; if(++n<=max) print s " " $NF} END{if(n>max) print "… (+" n-max ")"}' \
      | while IFS= read -r l; do log "      $l"; done

    # directorios nuevos entre las dos versiones
    nuevos="$(comm -13 <(dirs_de "$old") <(dirs_de "$new") || true)"
    if [ -n "$nuevos" ]; then
      log "Directorios nuevos: $(echo "$nuevos" | wc -l | tr -d ' ')"
      echo "$nuevos" | awk -v max=15 'NR<=max{print "      + " $0} END{if(NR>max) print "      … (+" NR-max ")"}' | tee -a "$LOG"
    else
      log "Directorios nuevos: ninguno"
    fi
  fi
else
  # --- clon nuevo: completo, sin filtros ni sparse
  if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
    log "ERROR: $DEST existe y no es un repositorio git; muévelo o usa otro -o"; exit 1
  fi
  if git clone --quiet --branch "$RAMA" "$URL" "$DEST"; then
    nf="$(nficheros "$DEST")"
    dl=$(( $(du -sk "$DEST/.git" | cut -f1) * 1024 ))
    nd="$(dirs_de HEAD | wc -l | tr -d ' ')"
    log "Clonado (nuevo): $REPO  ·  ficheros: $nf  ·  directorios: $nd  ·  descarga ≈ $(humano $dl)"
    log "Directorios de primer y segundo nivel:"
    dirs_de HEAD | awk -F/ 'NF<=2{print "      + " $0}' | tee -a "$LOG"
  else
    log "ERROR clonando $URL"; exit 1
  fi
fi
log "Versión: $(git -C "$DEST" log -1 --format='%h  %ad  %s' --date=short)"

# -----------------------------------------------------------------------------
log "=== 2/4 Comprobación de directorios ==="
if [ "$COMPROBAR" -eq 1 ]; then
  IFS=',' read -r -a req <<< "$EXIGIR"
  faltan=0
  for p in "${req[@]}"; do
    p="${p//[[:space:]]/}"; p="${p%/}"; [ -n "$p" ] || continue
    if [ -d "$DEST/$p" ] && [ -n "$(find "$DEST/$p" -type f -print -quit 2>/dev/null)" ]; then
      log "  OK     $p  ($(nficheros "$DEST/$p") ficheros)"
    else
      log "  FALTA  $p"; faltan=$((faltan+1))
    fi
  done
  if [ "$faltan" -gt 0 ]; then errores=$((errores+faltan)); log "ERROR: faltan $faltan directorios exigidos"; fi
else
  log "Comprobación desactivada (--sin-comprobar)"
fi

# -----------------------------------------------------------------------------
log "=== 3/4 Contenido por directorio ==="
printf '%-26s %9s %10s\n' "directorio" "ficheros" "tamaño" | tee -a "$LOG"
total_f=0
for d in "$DEST"/*/; do
  n="$(basename "$d")"
  f="$(nficheros "$d")"; kb="$(du -sk "$d" | cut -f1)"; total_f=$((total_f+f))
  printf '%-26s %9s %10s\n' "$n/" "$f" "$(humano $((kb*1024)))" | tee -a "$LOG"
  if [ "$ARBOL" -eq 1 ]; then
    for s in "$d"*/; do
      [ -d "$s" ] || continue
      printf '  %-24s %9s %10s\n' "$(basename "$s")/" "$(nficheros "$s")" "$(humano $(( $(du -sk "$s" | cut -f1) * 1024 )))" | tee -a "$LOG"
    done
  fi
done
log "Total: $total_f ficheros (más los de la raíz del repo)"

# -----------------------------------------------------------------------------
log "=== 4/4 Programación ==="
if [ -n "$CRON_EXPR" ]; then
  linea="$CRON_EXPR $SCRIPT_ABS -u $USUARIO_GH -r $REPO -o $ORIGEN"
  [ -n "${RAMA:-}" ] && linea="$linea -b $RAMA"
  [ "$COMPROBAR" -eq 0 ] && linea="$linea --sin-comprobar"
  [ "$EXIGIR" != "$EXIGIR_DEF" ] && [ "$COMPROBAR" -eq 1 ] && linea="$linea --exigir '$EXIGIR'"
  [ "$FORZAR" -eq 1 ] && linea="$linea --forzar"
  linea="$linea >/dev/null 2>&1"
  ( crontab -l 2>/dev/null | grep -vF "$SCRIPT_ABS" ; echo "$linea" ) | crontab -
  log "Cron programado: $CRON_EXPR"
else
  log "Sin programar (usa --cron \"0 3 * * *\" para actualizar cada día)"
fi

echo | tee -a "$LOG"
log "FIN. Repo: $DEST  |  Errores: $errores  |  Duración: ${SECONDS}s"
[ "$errores" -eq 0 ]

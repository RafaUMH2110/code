#!/usr/bin/env bash
# =============================================================================
#  install-all-isa.sh  ·  All-in-one installer for https://isa.umh.es (Debian 13)
#  Apache DocumentRoot: /var/www/htdocs  ·  content in /var/www/htdocs/rafa
#
#  Production variant of the installer: it does NOT modify apache2.conf, does NOT
#  touch the /moda alias or existing rules, does NOT change the server front page
#  unless --root-entry is given and respects an already installed telemetry collector.
#
#  Steps: 1 dependencies · 2 selection and cloning · 3 deployment to Apache ·
#         4 collector (optional) · 5 Apache (only if needed) · 6 check
#
# Full help:  ./install-all-isa.sh -h
# It is idempotent: running it again updates everything.
# =============================================================================
set -euo pipefail

GH_USER="RafaUMH2110"
SOURCE="$HOME/RafaUMH2110"
DEST=""
DOCROOT="/var/www/htdocs"
URL_BASE="https://isa.umh.es"
ROOT_ENTRY=0
JSON_DIR_CLI=""
FORCE=0
WEB_USER="www-data"
MODE="web"
INDEX=1
CRON_EXPR=""
INTERACTIVE=0
LIST=0
ALL=0
REPOS_CLI=""
EXCLUDE_CLI=""
COLLECTOR=0

usage() {
cat <<'EOF'
Usage: ./install-all-isa.sh [options]

Source and destination
  -u USER          GitHub account                       (def.: RafaUMH2110)
  -o SOURCE        Where the repos are cloned           (def.: ~/RafaUMH2110)
  -d DEST          Apache directory for the apps        (def.: <docroot>/rafa)
  --docroot DIR    Apache DocumentRoot                  (def.: /var/www/htdocs)
  --url URL        Public URL of the server             (def.: https://isa.umh.es)
  --force          Do not ask for confirmation if DEST already has foreign content

What to clone (the selection is saved in SOURCE/.selection and reused,
also by cron, until you change the selection or use --all)
  -i, --interactive   Menu to choose repos and, inside each one, folders
  --repos LIST        Comma-separated list. Each item is a repo or
                      repo/folder. E.g.: --repos "apps/telemetria,apps/moda,code/linux"
  --exclude LIST      All public repos except these. E.g.: --exclude "apps-pro,Artifacts"
  --all               Forget the saved selection and clone everything again
  --list              Show the available repos and folders and the current selection

What is published to Apache
  --mode web          (def.) Web files only: html, css, js, json, images,
                      fonts, audio/video, pdf. Excludes .py, .ini, .service, .md,
                      .env, keys and config*.json
  --mode html         Only *.html / *.htm      (alias: --html-only)
  --mode all          Whole repo content (except .git, .github and secrets)
  --no-index          Do not install the index.html portal (apps.json is always generated)
  --root-entry        Also make the server root redirect to /rafa/.
                      NOT done by default: it changes the isa.umh.es front page.

Telemetry
  --collector         Installs the collector (telemetcollector) as a systemd service.
                      Credentials: variables TELEMET_STATION_ID and TELEMET_API_KEY,
                      or asked on the terminal. Without them the service is left
                      ready but not started. If a collector is already installed,
                      its config.ini, its service and its JSON path are kept.
  --json-dir DIR      Folder where the collector publishes history.json (default:
                      the one in its current config.ini or <dest>/telemethistory/data)

Other
  --cron "EXPR"       Schedule the task in cron, e.g. --cron "0 3 * * *"
  -h, --help          This help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -u) GH_USER="$2"; shift 2 ;;
    -o) SOURCE="$2"; shift 2 ;;
    -d) DEST="$2"; shift 2 ;;
    --docroot) DOCROOT="${2%/}"; shift 2 ;;
    --url) URL_BASE="${2%/}"; shift 2 ;;
    --entrada-root_dir) ROOT_ENTRY=1; shift ;;
    --json-dir) JSON_DIR_CLI="${2%/}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --mode) MODE="$2"; shift 2 ;;
    --html-only) MODE="html"; shift ;;
    --no-index) INDEX=0; shift ;;
    --cron) CRON_EXPR="$2"; shift 2 ;;
    -i|--interactive) INTERACTIVE=1; shift ;;
    --repos) REPOS_CLI="$2"; shift 2 ;;
    --exclude) EXCLUDE_CLI="$2"; shift 2 ;;
    --all) ALL=1; shift ;;
    --list) LIST=1; shift ;;
    --collector) COLLECTOR=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1  (use -h for help)" >&2; exit 1 ;;
  esac
done

case "$MODE" in web|html|all) ;; *) echo "--mode must be web, html or all" >&2; exit 1 ;; esac
[ -n "$DEST" ] || DEST="$DOCROOT/rafa"

case "$DEST" in
  ""|"/"|"/var"|"/var/www"|"/var/www/"|"$DOCROOT"|"$DOCROOT/")
    echo "Destination not allowed: '$DEST' (use a subfolder, e.g. $DOCROOT/rafa)" >&2; exit 1 ;;
esac
case "$DEST" in
  "$DOCROOT"/*) ENTRY="/${DEST#$DOCROOT/}/" ;;
  *) echo "The destination must be inside $DOCROOT (use --docroot if your Apache serves another folder)." >&2; exit 1 ;;
esac
ENTRY="${ENTRY//\/\//\/}"
WEB_HOST="${URL_BASE#*://}"; WEB_HOST="${WEB_HOST%%/*}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null || { echo "Run as root or install sudo." >&2; exit 1; }
  SUDO="sudo"
fi

SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
SEL_FILE="$SOURCE/.selection"

# ------------------------------- GitHub ---------------------------------------
REPO_NAMES=(); declare -A REPO_INFO=() REAL=()

get_repos() {
  local page=1 resp out_lines name lang size
  REPO_NAMES=(); REPO_INFO=(); REAL=()
  while :; do
    resp=$(curl -sf --retry 3 "https://api.github.com/users/$GH_USER/repos?type=public&per_page=100&page=$page") \
      || { echo "ERROR: GitHub API query failed (60 requests/hour limit or no network?)" >&2; return 1; }
    out_lines=$(echo "$resp" | jq -r '.[] | [.name, (.language // "-"), (.size|tostring)] | @tsv') \
      || { echo "ERROR: unexpected response from the GitHub API" >&2; return 1; }
    [ -z "$out_lines" ] && break
    while IFS=$'\t' read -r name lang size; do
      REPO_NAMES+=("$name"); REPO_INFO[$name]="$lang, $size KB"; REAL[${name,,}]="$name"
    done <<< "$out_lines"
    page=$((page+1))
  done
  [ "${#REPO_NAMES[@]}" -gt 0 ] || { echo "No public repos for $GH_USER" >&2; return 1; }
}

repo_folders() {   # first-level folders of a repo
  curl -sf --retry 2 "https://api.github.com/repos/$GH_USER/$1/contents" 2>/dev/null \
    | jq -r '.[] | select(.type=="dir") | .name | select(startswith(".")|not)' 2>/dev/null || true
}

# ------------------------------ Selection -------------------------------------
declare -A SEL_SET=() SEL_FULL=() SEL_DIRS=() EXCL=()
POS=0
LINES=()

load_item() {
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
    echo "WARNING: '$repo' is not a public repo of $GH_USER; ignored" >&2
    return 0
  fi
  if [ "$neg" -eq 1 ]; then EXCL[$real]=1; return 0; fi
  POS=1; SEL_SET[$real]=1
  if [ -z "$dir" ]; then SEL_FULL[$real]=1; else SEL_DIRS[$real]="${SEL_DIRS[$real]:-} $dir"; fi
}

repo_included() {
  local r="$1"
  [ -z "${EXCL[$r]:-}" ] || return 1
  if [ "$POS" -eq 1 ]; then [ -n "${SEL_SET[$r]:-}" ]; else return 0; fi
}

multi_menu() {   # multi_menu "Title" item1 item2 …  → MENU_OUT
  local title="$1"; shift
  local items=("$@") n=$# i resp tok ok a b
  echo; echo "$title"
  for ((i=0; i<n; i++)); do printf '  %2d) %s\n' $((i+1)) "${items[i]}"; done
  while :; do
    resp=""
    read -r -p "Choose (numbers or ranges like 1-3 separated by spaces; Enter = all; n = none): " resp </dev/tty || resp=""
    MENU_OUT=()
    if [ -z "$resp" ] || [[ "$resp" =~ ^[aA] ]]; then MENU_OUT=("${items[@]}"); return 0; fi
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
    echo "Invalid input."
  done
}

interactive_selection() {
  [ -t 0 ] || { echo "Interactive mode needs a terminal." >&2; exit 1; }
  local labels=() chosen=() r e d resp
  local -a dirs
  for r in "${REPO_NAMES[@]}"; do labels+=("$(printf '%-18s %s' "$r" "${REPO_INFO[$r]}")"); done
  multi_menu "Public repositories of $GH_USER:" "${labels[@]}"
  [ "${#MENU_OUT[@]}" -gt 0 ] || { echo "You have not chosen any repository." >&2; exit 1; }
  for e in "${MENU_OUT[@]}"; do chosen+=("${e%% *}"); done
  LINES=()
  for r in "${chosen[@]}"; do
    mapfile -t dirs < <(repo_folders "$r")
    if [ "${#dirs[@]}" -gt 0 ]; then
      resp=""
      read -r -p "· $r: all content (A) or choose folders (c)? [A/c] " resp </dev/tty || resp=""
      if [[ "$resp" =~ ^[cC] ]]; then
        multi_menu "Folders of $r:" "${dirs[@]}"
        if [ "${#MENU_OUT[@]}" -eq 0 ]; then echo "  (no folder chosen: $r is skipped)"; continue; fi
        if [ "${#MENU_OUT[@]}" -eq "${#dirs[@]}" ]; then
          LINES+=("$r")
        else
          for d in "${MENU_OUT[@]}"; do LINES+=("$r/$d"); done
        fi
        continue
      fi
    fi
    LINES+=("$r")
  done
}

csv_to_lines() {   # csv_to_lines "a,b/c" "prefix"
  local csv="$1" pre="$2" it
  IFS=',' read -ra _items <<< "$csv"
  for it in "${_items[@]}"; do
    it="${it// /}"
    [ -n "$it" ] && LINES+=("$pre$it")
  done
  return 0
}

save_selection() {
  if [ "${#LINES[@]}" -gt 0 ]; then
    printf '%s\n' "${LINES[@]}" > "$SEL_FILE"
  else
    rm -f "$SEL_FILE"
  fi
}

show_selection() {   # for --list
  local r d mark dirs
  local -a cur=()
  [ -f "$SEL_FILE" ] && mapfile -t cur < "$SEL_FILE"
  for l in "${cur[@]}"; do load_item "$l" 2>/dev/null; done
  echo "Public repos of $GH_USER  ([x] = will be cloned with the current selection)"
  [ "${#cur[@]}" -eq 0 ] && echo "(no saved selection: all are cloned)"
  for r in "${REPO_NAMES[@]}"; do
    mark="[ ]"; repo_included "$r" && mark="[x]"
    printf '%s %-18s %s\n' "$mark" "$r" "${REPO_INFO[$r]}"
    dirs=$(repo_folders "$r" | tr '\n' ' ')
    [ -n "$dirs" ] && echo "      folders: $dirs"
    [ -z "${SEL_DIRS[$r]:-}" ] || echo "      selected:${SEL_DIRS[$r]}"
  done
  return 0
}

# ------------------------------ --list mode -----------------------------------
if [ "$LIST" -eq 1 ]; then
  for c in curl jq; do command -v "$c" >/dev/null || { echo "Missing '$c' (sudo apt install -y curl jq)" >&2; exit 1; }; done
  get_repos || exit 1
  show_selection
  exit 0
fi

mkdir -p "$SOURCE"
LOG="$SOURCE/install-all.log"
log()  { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# human_size BYTES -> "812 B" / "34.5 KB" / "1.2 MB"
human_size() { awk -v b="${1:-0}" 'BEGIN{ if(b<1024) printf "%d B",b; else if(b<1048576) printf "%.1f KB",b/1024; else printf "%.1f MB",b/1048576 }'; }

# list_changes ITEMIZE_FILE -> first lines of the rsync -i output (+ new, ~ modified, - deleted)
list_changes() {
  awk -v max=6 '
    function emit(s, p) { if (++n <= max) print s " " p }
    /^>f/ { p = $0; sub(/^[^ ]+ /, "", p); emit(($0 ~ /^>f\+\+\+\+\+\+\+\+\+/) ? "+" : "~", p) }
    /^\*deleting/ { p = $0; sub(/^\*deleting +/, "", p); if (p !~ /\/$/) emit("-", p) }
    END { if (n > max) print "… (+" n - max ")" }
  ' "$1" | while IFS= read -r l; do log "      $l"; done
}
step() { echo | tee -a "$LOG"; log "=== $* ==="; }

# -----------------------------------------------------------------------------
step "1/6 Dependencies"
MISSING=()
for p in apache2 git curl jq rsync python3; do
  dpkg -s "$p" >/dev/null 2>&1 || MISSING+=("$p")
done
if [ "${#MISSING[@]}" -gt 0 ]; then
  log "Installing: ${MISSING[*]}"
  $SUDO apt-get update -qq
  $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${MISSING[@]}"
else
  log "All dependencies are already installed"
fi
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  $SUDO systemctl enable --now apache2 >/dev/null 2>&1 || log "WARNING: could not enable apache2 with systemctl"
fi

# -----------------------------------------------------------------------------
step "2/6 Selection and cloning of the public repos of $GH_USER"
created=0; updated=0; errors=0; unchanged=0
g_commits=0; g_add=0; g_mod=0; g_del=0; g_ins=0; g_rem=0; g_bytes=0
get_repos || { log "ERROR: could not get the repo list"; exit 1; }

if [ "$ALL" -eq 1 ]; then
  rm -f "$SEL_FILE"; log "Saved selection removed: all public repos will be used"
fi
if [ "$INTERACTIVE" -eq 1 ]; then
  interactive_selection; save_selection; log "Selection saved in $SEL_FILE"
elif [ -n "$REPOS_CLI$EXCLUDE_CLI" ]; then
  LINES=()
  [ -n "$REPOS_CLI" ]   && csv_to_lines "$REPOS_CLI" ""
  [ -n "$EXCLUDE_CLI" ] && csv_to_lines "$EXCLUDE_CLI" "-"
  save_selection; log "Selection saved in $SEL_FILE"
elif [ "$ALL" -eq 0 ] && [ -f "$SEL_FILE" ]; then
  mapfile -t LINES < "$SEL_FILE"; log "Using the saved selection ($SEL_FILE)"
else
  LINES=()
fi
for l in "${LINES[@]}"; do load_item "$l"; done

sync_repo() {   # sync_repo repo "folders"
  local r="$1" dirs="$2" old new kb0 kb1 dl n_commits a m d ins del nf
  if [ -d "$SOURCE/$r/.git" ]; then
    if [ -n "$dirs" ]; then
      git -C "$SOURCE/$r" sparse-checkout set --cone $dirs >/dev/null 2>&1 \
        || { log "ERROR configuring folders of $r"; errors=$((errors+1)); return 0; }
    elif [ "$(git -C "$SOURCE/$r" config --get core.sparseCheckout 2>/dev/null || true)" = "true" ]; then
      git -C "$SOURCE/$r" sparse-checkout disable >/dev/null 2>&1 || true
    fi
    old="$(git -C "$SOURCE/$r" rev-parse HEAD 2>/dev/null || true)"
    kb0="$(du -sk "$SOURCE/$r/.git" 2>/dev/null | cut -f1)"
    if git -C "$SOURCE/$r" pull --ff-only --quiet; then
      updated=$((updated+1))
      new="$(git -C "$SOURCE/$r" rev-parse HEAD 2>/dev/null || true)"
      if [ "$old" = "$new" ]; then
        log "No changes: $r${dirs:+  [folders:$dirs]}"; unchanged=$((unchanged+1))
      else
        n_commits="$(git -C "$SOURCE/$r" rev-list --count "$old..$new" 2>/dev/null || echo 0)"
        read -r a m d < <(git -C "$SOURCE/$r" diff --name-status "$old" "$new" ${dirs:+-- $dirs} \
          | awk '{c=substr($1,1,1)} c=="A"{a++} c=="D"{d++} c!="A"&&c!="D"{m++} END{print a+0,m+0,d+0}')
        read -r ins del < <(git -C "$SOURCE/$r" diff --numstat "$old" "$new" ${dirs:+-- $dirs} \
          | awk '$1~/^[0-9]+$/{i+=$1} $2~/^[0-9]+$/{x+=$2} END{print i+0,x+0}')
        kb1="$(du -sk "$SOURCE/$r/.git" 2>/dev/null | cut -f1)"
        dl=$(( (${kb1:-0} - ${kb0:-0}) * 1024 )); if [ "$dl" -lt 0 ]; then dl=0; fi
        log "Updated: $r${dirs:+  [folders:$dirs]}  ·  +$n_commits commits  ·  files: $((a+m+d)) ($a new, $m modified, $d deleted)  ·  lines +$ins/-$del  ·  download ≈ $(human_size $dl)"
        git -C "$SOURCE/$r" diff --name-status "$old" "$new" ${dirs:+-- $dirs} \
          | awk -v max=6 '{c=substr($1,1,1); s=(c=="A")?"+":(c=="D")?"-":"~"; if(++n<=max) print s " " $NF} END{if(n>max) print "… (+" n-max ")"}' \
          | while IFS= read -r l; do log "      $l"; done
        g_commits=$((g_commits+n_commits)); g_add=$((g_add+a)); g_mod=$((g_mod+m)); g_del=$((g_del+d))
        g_ins=$((g_ins+ins)); g_rem=$((g_rem+del)); g_bytes=$((g_bytes+dl))
      fi
    else
      log "ERROR updating: $r"; errors=$((errors+1))
    fi
  else
    if [ -n "$dirs" ]; then
      if git clone --quiet --filter=blob:none --sparse "https://github.com/$GH_USER/$r.git" "$SOURCE/$r" \
         && git -C "$SOURCE/$r" sparse-checkout set --cone $dirs >/dev/null 2>&1; then
        created=$((created+1))
        nf="$(find "$SOURCE/$r" -path "$SOURCE/$r/.git" -prune -o -type f -print | wc -l | tr -d ' ')"
        dl=$(( $(du -sk "$SOURCE/$r/.git" | cut -f1) * 1024 ))
        g_add=$((g_add+nf)); g_bytes=$((g_bytes+dl))
        log "Cloned (new): $r  [folders:$dirs]  ·  files: $nf  ·  download ≈ $(human_size $dl)"
      else
        log "ERROR cloning: $r"; errors=$((errors+1))
      fi
    else
      if git clone --quiet "https://github.com/$GH_USER/$r.git" "$SOURCE/$r"; then
        created=$((created+1))
        nf="$(find "$SOURCE/$r" -path "$SOURCE/$r/.git" -prune -o -type f -print | wc -l | tr -d ' ')"
        dl=$(( $(du -sk "$SOURCE/$r/.git" | cut -f1) * 1024 ))
        g_add=$((g_add+nf)); g_bytes=$((g_bytes+dl))
        log "Cloned (new): $r  ·  files: $nf  ·  download ≈ $(human_size $dl)"
      else
        log "ERROR cloning: $r"; errors=$((errors+1))
      fi
    fi
  fi
}

SEL_REPOS=(); skipped=()
for r in "${REPO_NAMES[@]}"; do
  if repo_included "$r"; then
    SEL_REPOS+=("$r")
    dirs=""; [ -z "${SEL_FULL[$r]:-}" ] && dirs="${SEL_DIRS[$r]:-}"
    sync_repo "$r" "$dirs"
  else
    skipped+=("$r")
  fi
done
log "Repos -> new: $created | updated: $updated (with changes: $((updated-unchanged)), unchanged: $unchanged) | errors: $errors"
log "Git summary -> commits: $g_commits | files: +$g_add ~$g_mod -$g_del | lines: +$g_ins/-$g_rem | download ≈ $(human_size $g_bytes)"
[ "${#skipped[@]}" -gt 0 ] && log "Not selected: ${skipped[*]}"

# -----------------------------------------------------------------------------
step "3/6 Deploy to Apache ($DEST) · mode $MODE"
MARKER="$DEST/.install-all"
FIRST_RUN=0; BACKUP_DIR=""
if $SUDO test -d "$DEST" && ! $SUDO test -f "$MARKER" && ! $SUDO test -f "$DEST/.install_all" && [ -n "$($SUDO ls -A "$DEST" 2>/dev/null)" ]; then
  FIRST_RUN=1
  echo
  echo "WARNING: $DEST already has content that was not created by this script:"
  { $SUDO ls -A "$DEST" | head -25 | sed 's/^/    /'; } || true
  echo "  The deployment will replace index.html and apps.json, and mirror each repo"
  echo "  (inside <repo>/ it deletes whatever is not in the repository)."
  if [ "$FORCE" -ne 1 ]; then
    if [ -t 0 ]; then
      read -r -p "  Continue? A copy of whatever is replaced or deleted will be kept [y/N] " resp </dev/tty || resp=""
      [[ "$resp" =~ ^[yY] ]] || { log "Cancelled by the user: $DEST has not been modified"; exit 1; }
    else
      log "ERROR: $DEST has foreign content and there is no terminal to confirm. Use --force or review the directory."
      exit 1
    fi
  fi
  BACKUP_DIR="/var/backups/install-all-$(date +%Y%m%d-%H%M%S)"
  $SUDO mkdir -p "$BACKUP_DIR"
  log "Backup of whatever is replaced or deleted: $BACKUP_DIR"
  for f in index.html apps.json; do
    if $SUDO test -f "$DEST/$f"; then $SUDO cp -a "$DEST/$f" "$BACKUP_DIR/$f"; fi
  done
fi
$SUDO mkdir -p "$DEST"

WEB_EXT=(html htm css js mjs json webmanifest svg png jpg jpeg gif webp avif ico bmp woff woff2 ttf otf eot mp3 mp4 webm ogg wav pdf xml csv)
SECRETS=(--exclude='.env*' --exclude='*.key' --exclude='*.pem' --exclude='*secret*' --exclude='*credential*' --exclude='config.ini')
# 'datos/' and 'data/' are protected: the telemetry collectors write there (historial.json / history.json)
RSYNC_OPTS=(-a --delete --delete-excluded --filter='P datos/' --filter='P data/' --exclude='.git/' --exclude='.github/' "${SECRETS[@]}")
case "$MODE" in
  web)
    RSYNC_OPTS+=(--prune-empty-dirs --exclude='.*' --exclude='node_modules/' --exclude='package*.json' --exclude='tsconfig*.json' --exclude='*config*.json' --include='*/')
    for e in "${WEB_EXT[@]}"; do RSYNC_OPTS+=(--include="*.$e"); done
    RSYNC_OPTS+=(--exclude='*') ;;
  html)
    RSYNC_OPTS+=(--prune-empty-dirs --exclude='.*' --include='*/' --include='*.html' --include='*.htm' --exclude='*') ;;
  all)
    RSYNC_OPTS+=(--exclude='.gitignore') ;;
esac

copied=0; d_new=0; d_mod=0; d_del=0; d_bytes=0
for r in "${SEL_REPOS[@]}"; do
  [ -d "$SOURCE/$r/.git" ] || [ -f "$SOURCE/$r/.git" ] || continue
  extra=()
  [ -n "$BACKUP_DIR" ] && extra=(--backup --backup-dir="$BACKUP_DIR/$r")
  rsync_out="$(mktemp)"
  if $SUDO env LC_ALL=C rsync "${RSYNC_OPTS[@]}" "${extra[@]}" -i --stats "$SOURCE/$r/" "$DEST/$r/" >"$rsync_out" 2>&1; then
    copied=$((copied+1))
    read -r n m d < <(awk '/^>f\+\+\+\+\+\+\+\+\+/{n++} /^>f/ && !/^>f\+\+\+\+\+\+\+\+\+/{m++} /^\*deleting/ && !/\/$/{d++} END{print n+0,m+0,d+0}' "$rsync_out")
    bytes="$(sed -nE 's/^Total transferred file size: ([0-9,.]+) bytes.*/\1/p' "$rsync_out" | tr -d ',.')"; bytes="${bytes:-0}"
    d_new=$((d_new+n)); d_mod=$((d_mod+m)); d_del=$((d_del+d)); d_bytes=$((d_bytes+bytes))
    if [ $((n+m+d)) -eq 0 ]; then
      log "Deployed: $r  ·  no changes"
    else
      log "Deployed: $r  ·  $n new  ·  $m modified  ·  $d deleted  ·  transferred $(human_size $bytes)"
      list_changes "$rsync_out"
    fi
  else
    log "ERROR copiando: $r"; tail -n 5 "$rsync_out" | tee -a "$LOG"; errors=$((errors+1))
  fi
  rm -f "$rsync_out"
done
for r in "${SEL_REPOS[@]}"; do
  [ -d "$DEST/$r" ] && $SUDO find "$DEST/$r" -type d -empty ! -name datos ! -name data -delete 2>/dev/null
done
log "Repos deployed: $copied"
log "Deployment summary -> new: $d_new | modified: $d_mod | deleted: $d_del | transferred $(human_size $d_bytes)"

# Remove from the deployment the repos that are no longer selected
for d in "$DEST"/*/; do
  n="$(basename "$d")"
  [ -d "$SOURCE/$n/.git" ] || [ -f "$SOURCE/$n/.git" ] || continue
  present=0; for r in "${SEL_REPOS[@]}"; do [ "$r" = "$n" ] && present=1; done
  if [ "$present" -eq 0 ]; then $SUDO rm -rf "$DEST/$n"; log "Removed from the deployment (not selected): $n"; fi
done

# apps.json catalog: read by the entry page (index.html) to list the apps.
# For each HTML file it collects title, description, size, last commit date and the
# nearest README (project and summary).
tmp_json="$(mktemp)"
python3 -I - "$SOURCE" "$DEST" "$tmp_json" >/dev/null <<'PYEOF'
import sys, os, re, json, subprocess, html, datetime

src_root, dest_root, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
SKIP = {'.git', 'node_modules', '.github'}

def read_text(p, n=65536):
    with open(p, 'rb') as f:
        return f.read(n).decode('utf-8', 'replace')

def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', s))).strip()

def html_meta(txt):
    t = re.search(r'<title[^>]*>(.*?)</title>', txt, re.I | re.S)
    d = (re.search(r'<meta[^>]+name=["\']description["\'][^>]*content=["\'](.*?)["\']', txt, re.I | re.S)
         or re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]*name=["\']description["\']', txt, re.I | re.S))
    return (clean(t.group(1)) if t else ''), (clean(d.group(1)) if d else '')

def md_plain(s):
    s = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', s)
    s = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', s)
    s = re.sub(r'[*_`]+', '', s)
    return re.sub(r'\s+', ' ', s).strip()

def shorten(s, n=200):
    if len(s) <= n:
        return s
    return s[:n].rsplit(' ', 1)[0].rstrip(',;:.') + '…'

def readme(path):
    title, paragraph, buf = '', '', []
    in_code = False
    for line in read_text(path, 20000).splitlines():
        l = line.strip()
        if l.startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not title and l.startswith('# '):
            title = md_plain(l[2:]); continue
        if not l:
            if buf:
                break
            continue
        if l[0] in '#|>-*<![`' or re.match(r'^\d+\.', l):
            if buf:
                break
            continue
        buf.append(l)
    paragraph = shorten(md_plain(' '.join(buf)))
    return title, paragraph

readme_cache = {}
def nearest_readme(repo_dir, rel_dir):
    d = rel_dir
    while d and d != '.':
        p = os.path.join(repo_dir, d, 'README.md')
        if os.path.isfile(p):
            if p not in readme_cache:
                readme_cache[p] = readme(p)
            return readme_cache[p]
        d = os.path.dirname(d)
    return '', ''

def git_date(repo_dir, rel):
    try:
        out = subprocess.run(['git', '-C', repo_dir, 'log', '-1', '--format=%cs', '--', rel],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return ''

apps = []
for repo in sorted(os.listdir(src_root)):
    repo_src = os.path.join(src_root, repo)
    repo_dest = os.path.join(dest_root, repo)
    if not (os.path.exists(os.path.join(repo_src, '.git')) and os.path.isdir(repo_dest)):
        continue
    for root_dir, dirs, filenames in os.walk(repo_dest):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for f in sorted(filenames):
            if not f.lower().endswith(('.html', '.htm')):
                continue
            full = os.path.join(root_dir, f)
            rel = os.path.relpath(full, repo_dest).replace(os.sep, '/')
            title, desc = html_meta(read_text(full))
            project_name, summary_text = nearest_readme(repo_src, os.path.dirname(rel))
            date_str = git_date(repo_src, rel)
            if not date_str:
                date_str = datetime.date.fromtimestamp(os.path.getmtime(full)).isoformat()
            apps.append({'repo': repo, 'path': rel, 'title': title, 'description': desc,
                         'project': project_name, 'summary': summary_text,
                         'size': os.path.getsize(full), 'updated': date_str})

with open(out_path, 'w', encoding='utf-8') as fh:
    json.dump({'generated': datetime.datetime.now().strftime('%d/%m/%Y %H:%M'), 'apps': apps},
              fh, ensure_ascii=False, indent=1)
print(len(apps))
PYEOF
$SUDO install -m 644 "$tmp_json" "$DEST/apps.json"
rm -f "$tmp_json"
log "Catalog generated: $DEST/apps.json ($(jq '.apps|length' "$DEST/apps.json") apps)"

# Entry page: index.html template next to this script (visual portal)
TEMPLATE="$(dirname "$SCRIPT_ABS")/index.html"
if [ "$INDEX" -eq 1 ] && [ -f "$TEMPLATE" ]; then
  $SUDO install -m 644 "$TEMPLATE" "$DEST/index.html"
  log "Portal installed: $DEST/index.html"
elif [ "$INDEX" -eq 1 ]; then
  log "WARNING: template $TEMPLATE not found; a simple index is generated"
  tmp="$(mktemp)"
  {
    echo '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    echo '<meta name="viewport" content="width=device-width,initial-scale=1">'
    echo "<title>$GH_USER applications</title>"
    echo '<style>body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222}'
    echo 'h1{font-size:1.5rem}h2{margin-top:1.6rem;font-size:1.1rem;border-bottom:1px solid #ddd}'
    echo 'ul{line-height:1.7}a{color:#0b5ed7;text-decoration:none}a:hover{text-decoration:underline}'
    echo 'small{color:#777}</style></head><body>'
    echo '<h1>HTML applications</h1>'
    echo "<small>Updated: $(date '+%Y-%m-%d %H:%M')</small>"
    for r in "${SEL_REPOS[@]}"; do
      [ -d "$DEST/$r" ] || continue
      mapfile -t files < <(cd "$DEST/$r" && find . -type f \( -iname '*.html' -o -iname '*.htm' \) \
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
  $SUDO install -m 644 "$tmp" "$DEST/index.html"
  rm -f "$tmp"
  log "Index generated: $DEST/index.html"
fi

# Permissions only on what the script manages (not on foreign content in DEST)
for item in "$DEST/index.html" "$DEST/apps.json"; do
  $SUDO test -f "$item" && $SUDO chown "$WEB_USER:$WEB_USER" "$item"
done
for r in "${SEL_REPOS[@]}"; do
  [ -d "$DEST/$r" ] || continue
  $SUDO chown -R "$WEB_USER:$WEB_USER" "$DEST/$r"
  $SUDO find "$DEST/$r" -type d -exec chmod 755 {} +
  $SUDO find "$DEST/$r" -type f -exec chmod 644 {} +
done
$SUDO touch "$MARKER"

# The folder where the collector writes the JSON must remain its own
COLLECTOR_DIR="/opt/telemet-collector"
fix_collector_dir() {
  local cfg="$COLLECTOR_DIR/config.ini" path
  id telemet >/dev/null 2>&1 || return 0
  $SUDO test -f "$cfg" || return 0
  path="$($SUDO sed -nE 's/^[[:space:]]*json_path[[:space:]]*=[[:space:]]*([^[:space:]]+).*/\1/p' "$cfg" | head -1)"
  [ -n "$path" ] || return 0
  case "$path" in "$DEST"/*) ;; *) return 0 ;; esac
  # If the folder does not exist (config.ini with the default path, e.g.), there is nothing to adjust
  $SUDO test -d "$(dirname "$path")" || { log "WARNING: the collector JSON folder does not exist: $(dirname "$path") (ignored; check json_path in $cfg)"; return 0; }
  $SUDO chown -R telemet:telemet "$(dirname "$path")" || log "WARNING: could not set the owner of $(dirname "$path")"
  return 0
}
fix_collector_dir
log "Permissions applied ($WEB_USER)"

# -----------------------------------------------------------------------------
step "4/6 Telemetry collector"
HEADERS_CONF=0

ini_set() {   # ini_set key value file  (the value travels in the environment, not on the command line)
  local k="$1" v="$2" f="$3" tmp act
  tmp="$(mktemp)"
  # If the key is already active, that line is replaced; only if it is not, the first
  # commented line is used (so the template's examples are left alone)
  act=0; $SUDO grep -qE "^[[:space:]]*$k[[:space:]]*=" "$f" && act=1
  $SUDO cat "$f" | K="$k" V="$v" ACT="$act" awk '
    BEGIN { k = ENVIRON["K"]; v = ENVIRON["V"]; pre = (ENVIRON["ACT"] == "1") ? "^[ \t]*" : "^[;# \t]*"; done = 0 }
    { if (!done && match($0, pre k "[ \t]*=")) { print k " = " v; done = 1 } else print }' > "$tmp"
  $SUDO install -m 600 "$tmp" "$f"
  rm -f "$tmp"
}

install_collector() {
  local src src_dir json_dir unit tmp station key resp pending=0 bak
  src="$(find "$SOURCE" -type f -path '*/telemetcollector/telemet_collector.py' 2>/dev/null | head -1)"
  if [ -z "$src" ]; then
    log "WARNING: telemetcollector not found in the cloned repos (is apps/telemetria selected?)"
    return 0
  fi
  src_dir="$(dirname "$src")"
  if [ -f "/etc/systemd/system/telemet-colector.service" ]; then
    log "WARNING: the service telemet-colector.service (the Spanish collector) is also installed; if it reads the same station, keep only one"
  fi

  # Where the JSON is published: --json-dir, or the one in its current config.ini, or the README's
  local cfg_path="" json_new=1
  if $SUDO test -f "$COLLECTOR_DIR/config.ini"; then
    cfg_path="$($SUDO sed -nE 's/^[[:space:]]*json_path[[:space:]]*=[[:space:]]*([^[:space:]]+).*/\1/p' "$COLLECTOR_DIR/config.ini" | head -1)"
  fi
  if [ -n "$JSON_DIR_CLI" ]; then json_dir="$JSON_DIR_CLI"
  elif [ -n "$cfg_path" ] && [ "$cfg_path" != "/path/history.json" ]; then json_dir="$(dirname "$cfg_path")"; json_new=0
  else json_dir="$DEST/telemethistory/data"; fi

  id telemet >/dev/null 2>&1 || {
    $SUDO useradd --system --home-dir "$COLLECTOR_DIR" --shell /usr/sbin/nologin telemet
    log "Service user 'telemet' created"
  }
  $SUDO mkdir -p "$COLLECTOR_DIR/data"
  if $SUDO test -f "$COLLECTOR_DIR/telemet_collector.py" && ! $SUDO cmp -s "$src_dir/telemet_collector.py" "$COLLECTOR_DIR/telemet_collector.py"; then
    bak="$COLLECTOR_DIR/telemet_collector.py.bak-$(date +%Y%m%d-%H%M%S)"
    $SUDO cp -a "$COLLECTOR_DIR/telemet_collector.py" "$bak"; log "Previous program saved in $bak"
  fi
  $SUDO install -m 644 "$src_dir/telemet_collector.py" "$COLLECTOR_DIR/telemet_collector.py"
  $SUDO install -m 644 "$src_dir/config.example.ini" "$COLLECTOR_DIR/config.example.ini"
  if ! $SUDO test -f "$COLLECTOR_DIR/config.ini"; then
    $SUDO install -m 600 "$src_dir/config.example.ini" "$COLLECTOR_DIR/config.ini"
    log "Created $COLLECTOR_DIR/config.ini from the template"
  fi
  $SUDO install -d -o telemet -g telemet -m 755 "$json_dir"
  if [ "$json_new" -eq 1 ]; then ini_set json_path "$json_dir/history.json" "$COLLECTOR_DIR/config.ini"; fi
  log "The collector publishes the JSON in $json_dir/history.json"

  # Credentials (only if they are still the template placeholders)
  if $SUDO grep -qE '^[[:space:]]*(station_id|api_key)[[:space:]]*=[[:space:]]*(YOUR_STATION_ID|YOUR_API_KEY)' "$COLLECTOR_DIR/config.ini"; then
    station="${TELEMET_STATION_ID:-}"; key="${TELEMET_API_KEY:-}"
    if [ -z "$station$key" ] && [ -t 0 ]; then
      read -r -p "Weather Underground Station ID (Enter = configure later): " station </dev/tty || station=""
      if [ -n "$station" ]; then read -r -s -p "API Key (not shown): " key </dev/tty || key=""; echo; fi
    fi
    if [ -n "$station" ] && [ -n "$key" ]; then
      ini_set station_id "$station" "$COLLECTOR_DIR/config.ini"
      ini_set api_key "$key" "$COLLECTOR_DIR/config.ini"
      log "Credentials saved in $COLLECTOR_DIR/config.ini (permissions 600)"
    fi
  fi
  $SUDO grep -qE '^[[:space:]]*(station_id|api_key)[[:space:]]*=[[:space:]]*(YOUR_STATION_ID|YOUR_API_KEY)' "$COLLECTOR_DIR/config.ini" && pending=1

  $SUDO chown -R telemet:telemet "$COLLECTOR_DIR"
  $SUDO chmod 600 "$COLLECTOR_DIR/config.ini"
  $SUDO chown -R telemet:telemet "$json_dir"

  # systemd service: if it already exists it is left as is (it may have its own settings)
  if $SUDO test -f /etc/systemd/system/telemet-collector.service; then
    log "Service already installed: /etc/systemd/system/telemet-collector.service is kept"
  else
  # systemd service: the repo's one, with the JSON folder adapted
  tmp="$(mktemp)"
  if [ -f "$src_dir/telemet-collector.service" ]; then
    sed "s|/var/www/htdocs/rafa/telemethistory/data|$json_dir|g" "$src_dir/telemet-collector.service" > "$tmp"
  else
    cat > "$tmp" <<UNIT
[Unit]
Description=TeleMet Collector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=telemet
Group=telemet
WorkingDirectory=$COLLECTOR_DIR
ExecStart=/usr/bin/python3 $COLLECTOR_DIR/telemet_collector.py -c $COLLECTOR_DIR/config.ini
Restart=always
RestartSec=10
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$COLLECTOR_DIR/data $json_dir

[Install]
WantedBy=multi-user.target
UNIT
  fi
  grep -qF "$json_dir" "$tmp" || sed -i "/^ReadWritePaths=/a ReadWritePaths=$json_dir" "$tmp"
  $SUDO install -m 644 "$tmp" /etc/systemd/system/telemet-collector.service
  rm -f "$tmp"
  log "Service installed: /etc/systemd/system/telemet-collector.service (JSON in $json_dir/history.json)"
  fi

  # Apache: make the browser not cache the JSON
  $SUDO a2enmod headers >/dev/null 2>&1 || true
  $SUDO tee /etc/apache2/conf-available/telemet-history.conf >/dev/null <<EOF
<Directory "$json_dir">
    <FilesMatch "\.json\$">
        Header set Cache-Control "no-store"
    </FilesMatch>
</Directory>
EOF
  $SUDO a2enconf telemet-history >/dev/null
  HEADERS_CONF=1

  if [ "$pending" -eq 1 ]; then
    log "WARNING: station_id and api_key are missing. To finish:"
    log "   sudo nano $COLLECTOR_DIR/config.ini"
    log "   sudo -u telemet python3 $COLLECTOR_DIR/telemet_collector.py -c $COLLECTOR_DIR/config.ini --test"
    log "   sudo systemctl enable --now telemet-collector"
  fi
  if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    $SUDO systemctl daemon-reload
    if [ "$pending" -eq 0 ]; then
      $SUDO systemctl enable telemet-collector >/dev/null 2>&1
      $SUDO systemctl restart telemet-collector
      sleep 2
      log "Service telemet-collector: $($SUDO systemctl is-active telemet-collector || true)"
    fi
  else
    log "WARNING: systemd is not active on this system; the service is installed but not started"
  fi
}

if [ "$COLLECTOR" -eq 1 ]; then
  install_collector
else
  log "Not requested (use --collector to install it)"
fi

# -----------------------------------------------------------------------------
step "5/6 Apache"
NEW_CONFS=()
if grep -rqE "<Directory[[:space:]]+\"?$DEST/?\"?[[:space:]]*>" /etc/apache2/ 2>/dev/null; then
  log "Apache: a <Directory $DEST> block already exists in /etc/apache2 (left untouched)"
else
  log "WARNING: no <Directory $DEST> block in /etc/apache2; if you get a 403, add 'Require all granted' for that folder"
fi
[ "$HEADERS_CONF" -eq 1 ] && NEW_CONFS+=(telemet-history)

if [ "$ROOT_ENTRY" -eq 1 ]; then
  $SUDO a2enmod alias >/dev/null 2>&1 || true
  $SUDO tee /etc/apache2/conf-available/rafa-entry.conf >/dev/null <<EOF
# Server entry: the root redirects to $ENTRY
RedirectMatch ^/\$ $ENTRY
EOF
  $SUDO a2enconf rafa-entry >/dev/null
  NEW_CONFS+=(rafa-entry)
  log "Redirect from / to $ENTRY enabled (conf rafa-entry)"
else
  log "Server front page not changed (use --root-entry to make / redirect to $ENTRY)"
fi

if [ "${#NEW_CONFS[@]}" -gt 0 ]; then
  if $SUDO apache2ctl configtest >>"$LOG" 2>&1; then
    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
      $SUDO systemctl reload apache2
    else
      $SUDO apache2ctl graceful || $SUDO apache2ctl start
    fi
    log "Apache reloaded (new configuration: ${NEW_CONFS[*]})"
  else
    log "ERROR in the Apache configuration: disabling what was added (${NEW_CONFS[*]})"
    for c in "${NEW_CONFS[@]}"; do $SUDO a2disconf "$c" >/dev/null 2>&1 || true; done
    log "Check: sudo apache2ctl configtest"
    exit 1
  fi
else
  log "No configuration changes: Apache does not need a reload"
fi

# -----------------------------------------------------------------------------
step "6/6 Check"
check() {   # check PATH -> HTTP code (resolves the host to this very server)
  local path="$1" code
  code="$(curl -s -o /dev/null -w '%{http_code}' --resolve "$WEB_HOST:443:127.0.0.1" "$URL_BASE$path" 2>/dev/null || true)"
  if [ -z "$code" ] || [ "$code" = "000" ]; then
    code="$(curl -sk -o /dev/null -w '%{http_code}' --resolve "$WEB_HOST:443:127.0.0.1" "$URL_BASE$path" 2>/dev/null || true)"
    if [ -n "$code" ] && [ "$code" != "000" ]; then code="$code (certificate not verified)"; fi
  fi
  if [ -z "$code" ] || [ "$code" = "000" ]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $WEB_HOST" "http://localhost$path" 2>/dev/null || true) (via http://localhost)"
  fi
  echo "$code"
}
log "$URL_BASE$ENTRY : $(check "$ENTRY")"
log "$URL_BASE${ENTRY}apps.json : $(check "${ENTRY}apps.json")"
if [ "$ROOT_ENTRY" -eq 1 ]; then log "$URL_BASE/ : $(check /)"; fi
if [ "$COLLECTOR" -eq 1 ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  log "telemet-collector : $(systemctl is-active telemet-collector 2>/dev/null || true)"
fi

if [ -n "$CRON_EXPR" ]; then
  cron_line="$CRON_EXPR $SCRIPT_ABS -u $GH_USER -o $SOURCE -d $DEST --docroot $DOCROOT --url $URL_BASE"
  [ "$MODE" != "web" ] && cron_line="$cron_line --mode $MODE"
  [ "$INDEX" -eq 0 ]  && cron_line="$cron_line --no-index"
  [ "$COLLECTOR" -eq 1 ] && cron_line="$cron_line --collector"
  [ "$ROOT_ENTRY" -eq 1 ] && cron_line="$cron_line --root-entry"
  [ -n "$JSON_DIR_CLI" ] && cron_line="$cron_line --json-dir $JSON_DIR_CLI"
  cron_line="$cron_line >/dev/null 2>&1"
  ( crontab -l 2>/dev/null | grep -vF "$SCRIPT_ABS" ; echo "$cron_line" ) | crontab -
  log "Cron scheduled: $CRON_EXPR (uses the selection saved in $SEL_FILE)"
fi

echo | tee -a "$LOG"
log "DONE. Portal: $URL_BASE$ENTRY  |  Errors: $errors  |  Duration: ${SECONDS}s${BACKUP_DIR:+  |  Backup: $BACKUP_DIR}"
[ "$errors" -eq 0 ]

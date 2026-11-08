#!/usr/bin/env bash
# =============================================================================
# install-all.sh  ·  Telemetry apps + telemet-collector (Debian 13)
#
# Reduced version of install-all: it only works with the telemetry apps
# (repo apps, folder telemetria/), which includes both collectors
# (telemetcolector in Spanish and telemetcollector in English).
#
#   1. Installs dependencies (apache2, git, curl, jq, rsync, python3)
#   2. Clones or updates ONLY apps/telemetria (partial clone)
#   3. Deploys to Apache only what is served over the web (HTML, CSS, JS,
#      images…), generates apps.json and installs the index.html portal
#   4. (Your choice) Installs telemet-collector (the English version) as a
#      systemd service. The Spanish version, telemet-colector, is installed
#      by instalar-todo.sh
#   5. Sets the server entry point to  http://<IP>/rafa/
#   6. Checks the result (and optionally schedules the task in cron)
#
# Full help:  ./install-all.sh -h
# It is idempotent: running it again updates everything.
# =============================================================================
set -euo pipefail

GH_USER="RafaUMH2110"
REPO="apps"
FOLDER="telemetria"
SOURCE="$HOME/RafaUMH2110-telemetria"
DEST=""
DOCROOT="/var/www/html"
FORCE=0
WEB_USER="www-data"
MODE="web"
INDEX=1
CRON_EXPR=""
COLLECTOR=""        # empty = ask (if there is a terminal) · 1 = install · 0 = do not install

usage() {
cat <<'EOF'
Usage: ./install-all.sh [options]

Clones only the telemetry apps (RafaUMH2110/apps, folder telemetria/, which
includes telemetcolector and telemetcollector), publishes them on Apache and,
if you choose, installs telemet-collector (the English collector) as a systemd
service.

Source and destination
  -u USER          GitHub account                       (def.: RafaUMH2110)
  -o SOURCE        Where the repo is cloned             (def.: ~/RafaUMH2110-telemetria)
  -d DEST          Apache directory for the apps        (def.: <docroot>/rafa)
  --docroot DIR    Apache DocumentRoot                  (def.: /var/www/html)
  --force          Do not ask for confirmation if DEST already has foreign content

What is published to Apache
  --mode web          (def.) Web files only: html, css, js, json, images,
                      fonts, audio/video, pdf. Excludes .py, .ini, .service, .md,
                      .env, keys and config*.json
  --mode html         Only *.html / *.htm      (alias: --html-only)
  --mode all          Whole content (except .git, .github and secrets)
  --no-index          Do not install the index.html portal (apps.json is always generated)

Collector (telemet-collector, English version)
  --collector         Install it as a systemd service (/opt/telemet-collector).
                      Credentials: variables TELEMET_STATION_ID and TELEMET_API_KEY,
                      or they are asked for in the terminal. Without them the service
                      is left ready but not started.
  --no-collector      Do not install it
  (neither of the two: it asks if there is a terminal; otherwise it is not
   installed. The Spanish version, telemet-colector, is installed by instalar-todo.sh)

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
    --force) FORCE=1; shift ;;
    --mode) MODE="$2"; shift 2 ;;
    --html-only) MODE="html"; shift ;;
    --no-index) INDEX=0; shift ;;
    --cron) CRON_EXPR="$2"; shift 2 ;;
    --collector) COLLECTOR=1; shift ;;
    --no-collector) COLLECTOR=0; shift ;;
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

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null || { echo "Run as root or install sudo." >&2; exit 1; }
  SUDO="sudo"
fi

SCRIPT_ABS="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# Install the collector? If not specified, ask (only with a terminal)
if [ -z "$COLLECTOR" ]; then
  if [ -t 0 ]; then
    read -r -p "Install telemet-collector (the English collector) as a systemd service? [y/N] " _resp </dev/tty || _resp=""
    if [[ "$_resp" =~ ^[yY] ]]; then COLLECTOR=1; else COLLECTOR=0; fi
  else
    COLLECTOR=0
  fi
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
step "2/6 Cloning the telemetry apps ($GH_USER/$REPO · folder $FOLDER)"
created=0; updated=0; errors=0; unchanged=0
g_commits=0; g_add=0; g_mod=0; g_del=0; g_ins=0; g_rem=0; g_bytes=0

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

SEL_REPOS=("$REPO")
sync_repo "$REPO" "$FOLDER"
for _c in telemetcolector telemetcollector; do
  if [ -d "$SOURCE/$REPO/$FOLDER/$_c" ]; then log "Collector available: $FOLDER/$_c"; else log "WARNING: $FOLDER/$_c not found in the cloned repo"; fi
done
log "Repos -> new: $created | updated: $updated (with changes: $((updated-unchanged)), unchanged: $unchanged) | errors: $errors"
log "Git summary -> commits: $g_commits | files: +$g_add ~$g_mod -$g_del | lines: +$g_ins/-$g_rem | download ≈ $(human_size $g_bytes)"

# -----------------------------------------------------------------------------
step "3/6 Deploy to Apache ($DEST) · mode $MODE"
MARKER="$DEST/.install-all"
FIRST_RUN=0; BACKUP_DIR=""
if $SUDO test -d "$DEST" && ! $SUDO test -f "$MARKER" && ! $SUDO test -f "$DEST/.install_all" && [ -n "$($SUDO ls -A "$DEST" 2>/dev/null)" ]; then
  FIRST_RUN=1
  echo
  echo "WARNING: $DEST already has content that was not created by this script:"
  { $SUDO ls -A "$DEST" | head -25 | sed 's/^/    /'; } || true
  echo "  The deployment will replace index.html and apps.json, and mirror $REPO/$FOLDER"
  echo "  (inside $REPO/$FOLDER/ it deletes whatever is not in the repository; the rest of $DEST is left alone)."
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
# 'datos/' and 'data/' are protected: the telemetry collector writes there (historial.json / history.json)
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
  [ -d "$SOURCE/$r/$FOLDER" ] || { log "ERROR: $r/$FOLDER does not exist in the clone in $SOURCE"; errors=$((errors+1)); continue; }
  $SUDO mkdir -p "$DEST/$r/$FOLDER"
  extra=()
  [ -n "$BACKUP_DIR" ] && extra=(--backup --backup-dir="$BACKUP_DIR/$r/$FOLDER")
  rsync_out="$(mktemp)"
  if $SUDO env LC_ALL=C rsync "${RSYNC_OPTS[@]}" "${extra[@]}" -i --stats "$SOURCE/$r/$FOLDER/" "$DEST/$r/$FOLDER/" >"$rsync_out" 2>&1; then
    copied=$((copied+1))
    read -r n m d < <(awk '/^>f\+\+\+\+\+\+\+\+\+/{n++} /^>f/ && !/^>f\+\+\+\+\+\+\+\+\+/{m++} /^\*deleting/ && !/\/$/{d++} END{print n+0,m+0,d+0}' "$rsync_out")
    bytes="$(sed -nE 's/^Total transferred file size: ([0-9,.]+) bytes.*/\1/p' "$rsync_out" | tr -d ',.')"; bytes="${bytes:-0}"
    d_new=$((d_new+n)); d_mod=$((d_mod+m)); d_del=$((d_del+d)); d_bytes=$((d_bytes+bytes))
    if [ $((n+m+d)) -eq 0 ]; then
      log "Deployed: $r/$FOLDER  ·  no changes"
    else
      log "Deployed: $r/$FOLDER  ·  $n new  ·  $m modified  ·  $d deleted  ·  transferred $(human_size $bytes)"
      list_changes "$rsync_out"
    fi
  else
    log "ERROR copying: $r"; tail -n 5 "$rsync_out" | tee -a "$LOG"; errors=$((errors+1))
  fi
  rm -f "$rsync_out"
done
for r in "${SEL_REPOS[@]}"; do
  [ -d "$DEST/$r/$FOLDER" ] && $SUDO find "$DEST/$r/$FOLDER" -type d -empty ! -name datos ! -name data -delete 2>/dev/null
done
log "Repos deployed: $copied"
log "Deployment summary -> new: $d_new | modified: $d_mod | deleted: $d_del | transferred $(human_size $d_bytes)"

# apps.json catalog: read by the entry page (index.html) to list the apps.
# For each HTML file it collects title, description, size, last commit date and the
# nearest README (project and summary).
tmp_json="$(mktemp)"
python3 -I - "$SOURCE" "$DEST" "$tmp_json" "$HOME" "$GH_USER" >/dev/null <<'PYEOF'
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

# Folders that may hold clones: this script's one and the user's sibling ones
# (e.g. ~/RafaUMH2110 if the full install-all is also used). This way the entry page
# lists ALL the cloned and deployed apps, not only those of this run.
home, user = sys.argv[4], sys.argv[5]
origins = [src_root]
for base in (os.path.dirname(os.path.abspath(src_root)), home):
    try:
        for n in sorted(os.listdir(base)):
            p = os.path.join(base, n)
            if (n == user or n.startswith(user + '-')) and os.path.isdir(p) and p not in origins:
                origins.append(p)
    except OSError:
        pass

apps = []
for repo in sorted(os.listdir(dest_root)):
    repo_dest = os.path.join(dest_root, repo)
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
            # clone that contains this file (this run's one may be partial)
            clone = next((c for c in clones if os.path.exists(os.path.join(c, rel))), None)
            title, desc = html_meta(read_text(full))
            project_name, summary_text = nearest_readme(clone, os.path.dirname(rel)) if clone else ('', '')
            date_str = git_date(clone, rel) if clone else ''
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
  for _f in favicon.svg favicon.ico apple-touch-icon.png; do
    if [ -f "$(dirname "$TEMPLATE")/$_f" ]; then $SUDO install -m 644 "$(dirname "$TEMPLATE")/$_f" "$DEST/$_f"; fi
  done
  log "Portal installed: $DEST/index.html"
elif [ "$INDEX" -eq 1 ]; then
  log "WARNING: template $TEMPLATE not found; a simple index is generated"
  tmp="$(mktemp)"
  mapfile -t _repos < <(find "$DEST" -mindepth 1 -maxdepth 1 -type d ! -name '.*' -printf '%f\n' | sort)
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
    for r in "${_repos[@]}"; do
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
for item in "$DEST/index.html" "$DEST/apps.json" "$DEST/favicon.svg" "$DEST/favicon.ico" "$DEST/apple-touch-icon.png"; do
  $SUDO test -f "$item" && $SUDO chown "$WEB_USER:$WEB_USER" "$item"
done
for r in "${SEL_REPOS[@]}"; do
  [ -d "$DEST/$r/$FOLDER" ] || continue
  $SUDO chown "$WEB_USER:$WEB_USER" "$DEST/$r"
  $SUDO chown -R "$WEB_USER:$WEB_USER" "$DEST/$r/$FOLDER"
  $SUDO find "$DEST/$r/$FOLDER" -type d -exec chmod 755 {} +
  $SUDO find "$DEST/$r/$FOLDER" -type f -exec chmod 644 {} +
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
step "4/6 TeleMet Collector (telemet-collector)"
HEADERS_CONF=0

ini_set() {   # ini_set key value file  (the value travels in the environment, not on the command line)
  local k="$1" v="$2" f="$3" tmp act
  tmp="$(mktemp)"
  # Only the FIRST active line of that key is replaced (or, if there is none, the first commented one):
  # this way the template examples are not uncommented and the key is not duplicated.
  # (a leading UTF-8 BOM, which breaks configparser, is also removed)
  act=0; $SUDO grep -qE "^[[:space:]]*$k[[:space:]]*=" "$f" && act=1
  $SUDO cat "$f" | sed '1s/^\xEF\xBB\xBF//' | K="$k" V="$v" ACT="$act" awk '
    BEGIN { k = ENVIRON["K"]; v = ENVIRON["V"]; pre = (ENVIRON["ACT"] == "1") ? "^[ \t]*" : "^[;# \t]*"; done = 0 }
    { if (!done && match($0, pre k "[ \t]*=")) { print k " = " v; done = 1 } else print }' > "$tmp"
  $SUDO install -m 600 "$tmp" "$f"
  rm -f "$tmp"
}

install_collector() {
  local src_dir app json_dir tmp station key pending=0
  src_dir="$SOURCE/$REPO/$FOLDER/telemetcollector"
  if [ ! -f "$src_dir/telemet_collector.py" ]; then
    log "WARNING: $src_dir/telemet_collector.py not found (was apps/$FOLDER cloned correctly?)"
    return 0
  fi
  if [ -f "/etc/systemd/system/telemet-colector.service" ]; then
    log "WARNING: the service telemet-colector.service (the other collector version) is also installed; if it reads the same station, keep only one"
  fi

  # Where the JSON is published: next to the deployed TeleMet History app
  app="$(find "$DEST" -type f -path '*/telemet/history/index.html' 2>/dev/null | head -1)"
  if [ -n "$app" ]; then json_dir="$(dirname "$app")/data"; else json_dir="$DEST/$REPO/$FOLDER/telemet/history/data"; fi

  id telemet >/dev/null 2>&1 || {
    $SUDO useradd --system --home-dir "$COLLECTOR_DIR" --shell /usr/sbin/nologin telemet
    log "Service user 'telemet' created"
  }
  $SUDO mkdir -p "$COLLECTOR_DIR/data"
  $SUDO install -m 644 "$src_dir/telemet_collector.py" "$COLLECTOR_DIR/telemet_collector.py"
  $SUDO install -m 644 "$src_dir/config.example.ini" "$COLLECTOR_DIR/config.example.ini"
  if ! $SUDO test -f "$COLLECTOR_DIR/config.ini"; then
    $SUDO install -m 600 "$src_dir/config.example.ini" "$COLLECTOR_DIR/config.ini"
    log "Created $COLLECTOR_DIR/config.ini from the template"
  fi
  $SUDO install -d -o telemet -g telemet -m 755 "$json_dir"
  ini_set json_path "$json_dir/history.json" "$COLLECTOR_DIR/config.ini"

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

  # systemd service: the one in the repo, with the JSON folder adapted
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

  # Apache: keep the browser from caching the JSON
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
  log "Collector: not installed (use --collector to install it)"
fi

# -----------------------------------------------------------------------------
step "5/6 Set the entry point to $ENTRY"
TS="$(date +%Y%m%d-%H%M%S)"
ENTRY_BACKUP="/var/backups/apache-entry-$TS"
$SUDO mkdir -p "$ENTRY_BACKUP"
changes=()

# 5a) Disable Redirect/Rewrite rules to /moda/ and DocumentRoot pointing to .../moda
mapfile -t CANDIDATES < <($SUDO grep -rliE "^[[:space:]]*(Redirect|RedirectMatch|RedirectPermanent|RewriteRule|DocumentRoot).*moda" \
    /etc/apache2/sites-available /etc/apache2/conf-available /etc/apache2/apache2.conf \
    "$DOCROOT/.htaccess" 2>/dev/null || true)
for f in "${CANDIDATES[@]}"; do
  [ -n "$f" ] || continue
  $SUDO cp -a --parents "$f" "$ENTRY_BACKUP"
  $SUDO sed -i --follow-symlinks -E \
    -e "s|^([[:space:]]*)(Redirect[A-Za-z]*[[:space:]].*[Mm][Oo][Dd][Aa].*)$|\1# [disabled $TS] \2|" \
    -e "s|^([[:space:]]*)(RewriteRule[[:space:]].*[Mm][Oo][Dd][Aa].*)$|\1# [disabled $TS] \2|" \
    -e "s|^([[:space:]]*)DocumentRoot[[:space:]]+\"?[^[:space:]\"]*[Mm][Oo][Dd][Aa]/?\"?[[:space:]]*$|\1DocumentRoot $DOCROOT|" \
    "$f"
  changes+=("$f")
  log "Rules pointing to /moda/ disabled in: $f"
done

# 5b) A root index.html that points to /moda/ -> replace it with a redirect
if [ -f "$DOCROOT/index.html" ] && $SUDO grep -qiE "moda" "$DOCROOT/index.html"; then
  $SUDO cp -a --parents "$DOCROOT/index.html" "$ENTRY_BACKUP"
  changes+=("$DOCROOT/index.html")
  log "Replaced $DOCROOT/index.html (it pointed to /moda/)"
  printf '%s\n' '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">' \
    "<meta http-equiv=\"refresh\" content=\"0; url=$ENTRY\"><title>Redirecting…</title></head>" \
    "<body><a href=\"$ENTRY\">Go to $ENTRY</a></body></html>" \
    | $SUDO tee "$DOCROOT/index.html" >/dev/null
fi

# 5c) Entry rule: the root redirects to /rafa/ (relative: works with localhost, IP or name)
$SUDO a2enmod alias >/dev/null 2>&1 || true
$SUDO tee /etc/apache2/conf-available/rafa-entry.conf >/dev/null <<EOF
# Default entry of the server: the root redirects to $ENTRY
RedirectMatch ^/\$ $ENTRY
EOF
$SUDO a2enconf rafa-entry >/dev/null

if $SUDO apache2ctl configtest >>"$LOG" 2>&1; then
  if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    $SUDO systemctl reload apache2
  else
    $SUDO apache2ctl graceful || $SUDO apache2ctl start
  fi
  log "Apache reloaded with the entry $ENTRY"
else
  log "ERROR in the Apache configuration: restoring backup"
  $SUDO a2disconf rafa-entry >/dev/null 2>&1 || true
  [ "$HEADERS_CONF" -eq 1 ] && $SUDO a2disconf telemet-history >/dev/null 2>&1 || true
  for f in "${changes[@]}"; do $SUDO cp -a "$ENTRY_BACKUP$f" "$f"; done
  log "Restored from $ENTRY_BACKUP. Check: sudo apache2ctl configtest"
  exit 1
fi

# 5d) Warnings: mentions of /moda/ that could not be disabled automatically
LEFTOVERS=$($SUDO grep -rniE "(Redirect|RewriteRule|DocumentRoot|DirectoryIndex|Alias).*moda" /etc/apache2 2>/dev/null | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' || true)
if [ -n "$LEFTOVERS" ]; then
  log "WARNING: references to 'moda' remain in the configuration; review them:"
  echo "$LEFTOVERS" | tee -a "$LOG"
fi

# -----------------------------------------------------------------------------
step "6/6 Check"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; IP="${IP:-localhost}"
root_code=$(curl -s -o /dev/null -w '%{http_code} -> %{redirect_url}' "http://localhost/" || echo "no response")
rafa_code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost$ENTRY" || echo "no response")
log "http://localhost/        : $root_code"
log "http://localhost$ENTRY : $rafa_code"
if [ "$COLLECTOR" -eq 1 ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  log "telemet-collector         : $(systemctl is-active telemet-collector 2>/dev/null || true)"
fi

if [ -n "$CRON_EXPR" ]; then
  cron_line="$CRON_EXPR $SCRIPT_ABS -u $GH_USER -o $SOURCE -d $DEST"
  [ "$MODE" != "web" ] && cron_line="$cron_line --mode $MODE"
  [ "$INDEX" -eq 0 ]  && cron_line="$cron_line --no-index"
  if [ "$COLLECTOR" -eq 1 ]; then cron_line="$cron_line --collector"; else cron_line="$cron_line --no-collector"; fi
  cron_line="$cron_line >/dev/null 2>&1"
  ( crontab -l 2>/dev/null | grep -vF "$SCRIPT_ABS" ; echo "$cron_line" ) | crontab -
  log "Cron scheduled: $CRON_EXPR"
fi

echo | tee -a "$LOG"
log "DONE. Entry: http://$IP$ENTRY  |  Errors: $errors  |  Duration: ${SECONDS}s  |  Backup: $ENTRY_BACKUP"
[ "$errors" -eq 0 ]

#!/usr/bin/env bash
# Deploys to the Apache document directory the content of the already cloned
# RafaUMH2110 repos, keeping the directory structure.
#
# Result:   <DEST>/<repo>/<original repo structure>
#           <DEST>/index.html   (index with links to all the HTML apps)
#
# Usage: ./deploy_apache.sh [-o SOURCE] [-d DEST] [--html-only] [--no-index] [-n]
#   -o SOURCE       Directory with the cloned repos     (def.: ~/RafaUMH2110)
#   -d DEST         Apache directory                    (def.: /var/www/html/rafa)
#   --html-only     Copy only *.html/*.htm (by default the whole repo content is copied)
#   --no-index      Do not generate the root index.html
#   -n              Dry run (changes nothing)
set -euo pipefail

SOURCE="$HOME/RafaUMH2110"
DEST="/var/www/html/rafa"
HTML_ONLY=0
INDEX=1
DRY_RUN=0
WEB_USER="www-data"

while [ $# -gt 0 ]; do
  case "$1" in
    -o) SOURCE="$2"; shift 2 ;;
    -d) DEST="$2"; shift 2 ;;
    --html-only) HTML_ONLY=1; shift ;;
    --no-index) INDEX=0; shift ;;
    -n) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# --- Checks -----------------------------------------------------------------
command -v rsync >/dev/null || { echo "Missing rsync. Install it with: sudo apt install -y rsync" >&2; exit 1; }
[ -d "$SOURCE" ] || { echo "Source does not exist: $SOURCE (have you cloned the repos yet?)" >&2; exit 1; }
case "$DEST" in
  ""|"/"|"/var"|"/var/www"|"/var/www/") echo "Dangerous destination: '$DEST'" >&2; exit 1 ;;
esac

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null || { echo "Run as root or install sudo." >&2; exit 1; }
  SUDO="sudo"
fi

SOURCE="$(cd "$SOURCE" && pwd)"
$SUDO mkdir -p "$DEST"
LOG="$SOURCE/deploy.log"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

RSYNC_OPTS=(-a --delete --exclude='.git' --exclude='.github' --exclude='.gitignore')
[ "$DRY_RUN" -eq 1 ] && RSYNC_OPTS+=(--dry-run -v)
if [ "$HTML_ONLY" -eq 1 ]; then
  RSYNC_OPTS+=(--prune-empty-dirs --include='*/' --include='*.html' --include='*.htm' --exclude='*')
fi

log "Deployment: $SOURCE -> $DEST (html_only=$HTML_ONLY, dry_run=$DRY_RUN)"

# --- Copy each repository ---------------------------------------------------
total=0; failures=0
for dir in "$SOURCE"/*/; do
  repo="$(basename "$dir")"
  [ -d "$dir/.git" ] || [ -f "$dir/.git" ] || continue   # git repos only
  if $SUDO rsync "${RSYNC_OPTS[@]}" "$dir" "$DEST/$repo/"; then
    log "Copied: $repo"; total=$((total+1))
  else
    log "ERROR copying: $repo"; failures=$((failures+1))
  fi
done

# --- Index ------------------------------------------------------------------
if [ "$INDEX" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
  tmp="$(mktemp)"
  {
    echo '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    echo '<meta name="viewport" content="width=device-width,initial-scale=1">'
    echo '<title>RafaUMH2110 applications</title>'
    echo '<style>body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222}'
    echo 'h1{font-size:1.5rem}h2{margin-top:1.6rem;font-size:1.1rem;border-bottom:1px solid #ddd}'
    echo 'ul{line-height:1.7}a{color:#0b5ed7;text-decoration:none}a:hover{text-decoration:underline}'
    echo 'small{color:#777}</style></head><body>'
    echo '<h1>HTML applications</h1>'
    echo "<small>Updated: $(date '+%Y-%m-%d %H:%M')</small>"
    for dir in "$SOURCE"/*/; do
      repo="$(basename "$dir")"
      [ -d "$DEST/$repo" ] || continue
      mapfile -t files < <(cd "$DEST/$repo" && find . -type f \( -iname '*.html' -o -iname '*.htm' \) \
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
  $SUDO install -m 644 "$tmp" "$DEST/index.html"
  rm -f "$tmp"
  log "Index generated: $DEST/index.html"
fi

# --- Permissions ------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  $SUDO chown -R "$WEB_USER:$WEB_USER" "$DEST"
  $SUDO find "$DEST" -type d -exec chmod 755 {} +
  $SUDO find "$DEST" -type f -exec chmod 644 {} +
  log "Permissions applied ($WEB_USER)"
fi

log "Done. Repos copied: $total | Errors: $failures"
[ "$failures" -eq 0 ]

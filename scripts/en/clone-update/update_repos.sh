#!/usr/bin/env bash
# Updates (git pull) the public repos of RafaUMH2110, clones the new ones
# and copies all .html files to the Apache document directory.
#
# Usage: ./update_repos.sh [repos_directory] [apache_directory]
#   repos_directory   default: $HOME/RafaUMH2110
#   apache_directory  default: /var/www/html/rafa
set -euo pipefail

GH_USER="RafaUMH2110"
REPOS_DIR="${1:-$HOME/$GH_USER}"
APACHE_DIR="${2:-/var/www/html/rafa}"
LOG="$REPOS_DIR/update.log"

for cmd in git curl jq rsync; do
  command -v "$cmd" >/dev/null || { echo "Missing '$cmd'. Install it with: sudo apt install -y git curl jq rsync" >&2; exit 1; }
done

mkdir -p "$REPOS_DIR"
cd "$REPOS_DIR"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "Starting synchronization of $GH_USER in $REPOS_DIR"
created=0; updated=0; errors=0
page=1
repo_list=()

while :; do
  response=$(curl -sf "https://api.github.com/users/$GH_USER/repos?type=public&per_page=100&page=$page") \
    || { log "ERROR: GitHub API query failed (request limit?)"; exit 1; }
  repos=$(echo "$response" | jq -r '.[].name')
  [ -z "$repos" ] && break

  for r in $repos; do
    repo_list+=("$r")
    if [ -d "$r/.git" ]; then
      if git -C "$r" pull --ff-only --quiet; then
        log "Updated: $r"; updated=$((updated+1))
      else
        log "ERROR updating: $r"; errors=$((errors+1))
      fi
    else
      if git clone --quiet "https://github.com/$GH_USER/$r.git"; then
        log "Cloned (new): $r"; created=$((created+1))
      else
        log "ERROR cloning: $r"; errors=$((errors+1))
      fi
    fi
  done
  page=$((page+1))
done

# --- Copy the HTML apps to the Apache document directory ---
# Keeps the <repo>/<subfolders>/file.html structure and excludes .git.
if [ ! -d "$APACHE_DIR" ] || [ ! -w "$APACHE_DIR" ]; then
  log "ERROR: '$APACHE_DIR' does not exist or is not writable (see the guide, section 'Apache')"
  errors=$((errors+1))
else
  for r in "${repo_list[@]}"; do
    [ -d "$r" ] || continue
    if rsync -a --prune-empty-dirs --chmod=D755,F644 \
         --include='*/' --include='*.html' --exclude='.git/' --exclude='*' \
         "$r/" "$APACHE_DIR/$r/"; then
      n=$(find "$APACHE_DIR/$r" -type f -name '*.html' | wc -l)
      log "Copied to Apache: $r ($n html)"
    else
      log "ERROR copying to Apache: $r"; errors=$((errors+1))
    fi
  done
fi

log "Done. New: $created | Updated: $updated | Errors: $errors"

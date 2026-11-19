#!/usr/bin/env bash
# =============================================================================
# clone-code.sh  ·  Clones or updates the COMPLETE repo RafaUMH2110/code
#
# Brings ALL the directories of the repo, including the new ones
# (telemetria/, telemetria/home/, telemetria/telemet-enchufes-*/, generador-apps/…),
# without partial cloning. If you already had a partial clone (sparse-checkout),
# it completes it. When done it reports what changed and checks that the
# required directories exist.
#
#   1. Clones (or updates with fetch + fast-forward) the whole repo
#   2. Reports: commits, new/modified/deleted files, lines, approximate
#      download and NEW DIRECTORIES
#   3. Checks that the required directories exist (default: those in the
#      REQUIRE_DEFAULT list, including telemetria/home)
#   4. Summarizes the content per first-level directory
#   5. (Optional) schedules the periodic update in cron
#
# Full help:  ./clone-code.sh -h
# It is idempotent: it can be run again to update.
# =============================================================================
set -euo pipefail

GH_USER="RafaUMH2110"
REPO="code"
SOURCE="$HOME/RafaUMH2110"
BRANCH=""
FORCE=0
TREE=0
CHECK=1
CRON_EXPR=""
REQUIRE_DEFAULT="telemetria/home,telemetria/telemet-enchufes-local,telemetria/telemet-enchufes-nube,telemetria/telemet-enchufes-vscode,generador-apps,linux,macos,windows,scripts"
REQUIRE="$REQUIRE_DEFAULT"

usage() {
cat <<'EOF'
Usage: ./clone-code.sh [options]

Clones (or updates) the complete repo RafaUMH2110/code, with all its
directories, and shows what has changed.

Source
  -u USER          GitHub account                    (def.: RafaUMH2110)
  -r REPO          Repository                        (def.: code)
  -o SOURCE        Folder that will hold the clone   (def.: ~/RafaUMH2110)
                   The repo ends up in SOURCE/REPO, e.g. ~/RafaUMH2110/code
  -b BRANCH        Branch to follow                  (def.: the repo's default branch)

Check
  --require LIST   Directories that must exist after cloning, comma-separated
                   (def.: telemetria/home, telemetria/telemet-enchufes-local,
                   telemetria/telemet-enchufes-nube, telemetria/telemet-enchufes-vscode,
                   generador-apps, linux, macos, windows, scripts)
  --no-check       Do not check directories (disables --require)
  --tree           Also show the second-level subdirectories

Update
  --force          If the clone has local changes or cannot fast-forward,
                   keep a copy (.patch and backup branch) and make it equal to the remote

Other
  --cron "EXPR"    Schedule the update in cron, e.g. --cron "0 3 * * *"
  -h, --help       This help

Exit codes: 0 = OK · 1 = error or a required directory is missing
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -u) GH_USER="$2"; shift 2 ;;
    -r) REPO="$2"; shift 2 ;;
    -o) SOURCE="${2%/}"; shift 2 ;;
    -b) BRANCH="$2"; shift 2 ;;
    --require) REQUIRE="$2"; shift 2 ;;
    --no-check) CHECK=0; shift ;;
    --tree) TREE=1; shift ;;
    --force) FORCE=1; shift ;;
    --cron) CRON_EXPR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1  (use -h for help)" >&2; exit 1 ;;
  esac
done

command -v git >/dev/null 2>&1 || { echo "Missing git (sudo apt install -y git)" >&2; exit 1; }

DEST="$SOURCE/$REPO"
URL="https://github.com/$GH_USER/$REPO.git"
SCRIPT_ABS="$(readlink -f "$0")"
mkdir -p "$SOURCE"
LOG="$SOURCE/clone-code.log"
SECONDS=0
errors=0

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# human_size BYTES -> "812 B" / "34.5 KB" / "1.2 MB"
human_size() { awk -v b="${1:-0}" 'BEGIN{ if(b<1024) printf "%d B",b; else if(b<1048576) printf "%.1f KB",b/1024; else printf "%.1f MB",b/1048576 }'; }

# dirs_of COMMIT -> directories (up to 3 levels) that contain files in that commit
dirs_of() {
  git -C "$DEST" ls-tree -r --name-only "$1" \
    | awk -F/ 'NF>1{ d=$1; print d; for(i=2;i<NF&&i<=3;i++){ d=d"/"$i; print d } }' | sort -u
}

# count_files DIR -> number of files (excluding .git)
count_files() { find "$1" -path "$1/.git" -prune -o -type f -print 2>/dev/null | wc -l | tr -d ' '; }

# -----------------------------------------------------------------------------
log "=== 1/4 Cloning $GH_USER/$REPO into $DEST ==="
if [ -z "$BRANCH" ]; then
  BRANCH="$(git ls-remote --symref "$URL" HEAD 2>/dev/null | awk '/^ref:/{sub("refs/heads/","",$2); print $2; exit}' || true)"
fi
[ -n "$BRANCH" ] || { log "ERROR: could not query $URL (no network, or the repo is not public?)"; exit 1; }
log "Branch: $BRANCH"

if [ -d "$DEST/.git" ]; then
  # --- existing clone: complete it if partial, warn about local changes, advance
  if [ "$(git -C "$DEST" config --get core.sparseCheckout 2>/dev/null || true)" = "true" ]; then
    before="$(count_files "$DEST")"
    git -C "$DEST" sparse-checkout disable >/dev/null 2>&1 || true
    after="$(count_files "$DEST")"
    log "Partial clone detected: sparse-checkout disabled and completed  ·  files: $before -> $after (+$((after-before)))"
  fi
  current_url="$(git -C "$DEST" remote get-url origin 2>/dev/null || true)"
  [ "$current_url" = "$URL" ] || log "WARNING: remote origin is '$current_url' (expected $URL)"

  TS="$(date +%Y%m%d-%H%M%S)"
  dirty="$(git -C "$DEST" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$dirty" -gt 0 ]; then
    if [ "$FORCE" -eq 1 ]; then
      mkdir -p "$SOURCE/clone-code-backups"
      git -C "$DEST" diff HEAD > "$SOURCE/clone-code-backups/$REPO-$TS.patch" || true
      log "Local changes ($dirty files) saved in $SOURCE/clone-code-backups/$REPO-$TS.patch"
      git -C "$DEST" reset --hard --quiet HEAD
    else
      log "WARNING: the clone has $dirty files with local changes (if it cannot be updated, use --force)"
    fi
  fi

  old="$(git -C "$DEST" rev-parse HEAD)"
  kb0="$(du -sk "$DEST/.git" 2>/dev/null | cut -f1)"
  if ! git -C "$DEST" fetch --quiet --prune origin "$BRANCH"; then
    log "ERROR: failed to query $URL"; exit 1
  fi
  new="$(git -C "$DEST" rev-parse FETCH_HEAD)"

  if [ "$old" = "$new" ]; then
    log "No changes: $REPO is already at the latest version ($(git -C "$DEST" rev-parse --short HEAD))"
  else
    if [ "$(git -C "$DEST" rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
      git -C "$DEST" checkout --quiet "$BRANCH" 2>/dev/null || log "WARNING: could not switch to branch $BRANCH"
    fi
    if ! git -C "$DEST" merge --ff-only --quiet FETCH_HEAD 2>/dev/null; then
      if [ "$FORCE" -eq 1 ]; then
        git -C "$DEST" branch "backup-before-force-$TS" "$old" >/dev/null 2>&1 || true
        git -C "$DEST" reset --hard --quiet FETCH_HEAD
        log "WARNING: could not fast-forward; made equal to the remote. Previous version in branch backup-before-force-$TS"
      else
        log "ERROR: cannot fast-forward. Review the clone or use --force"; exit 1
      fi
    fi
    n_commits="$(git -C "$DEST" rev-list --count "$old..$new" 2>/dev/null || echo 0)"
    read -r a m d < <(git -C "$DEST" diff --name-status "$old" "$new" \
      | awk '{c=substr($1,1,1)} c=="A"{a++} c=="D"{d++} c!="A"&&c!="D"{m++} END{print a+0,m+0,d+0}')
    read -r ins del < <(git -C "$DEST" diff --numstat "$old" "$new" \
      | awk '$1~/^[0-9]+$/{i+=$1} $2~/^[0-9]+$/{x+=$2} END{print i+0,x+0}')
    kb1="$(du -sk "$DEST/.git" 2>/dev/null | cut -f1)"
    dl=$(( (${kb1:-0} - ${kb0:-0}) * 1024 )); if [ "$dl" -lt 0 ]; then dl=0; fi
    log "Updated: $REPO  ·  +$n_commits commits  ·  files: $((a+m+d)) ($a new, $m modified, $d deleted)  ·  lines +$ins/-$del  ·  download ≈ $(human_size $dl)"
    git -C "$DEST" diff --name-status "$old" "$new" \
      | awk -v max=8 '{c=substr($1,1,1); s=(c=="A")?"+":(c=="D")?"-":"~"; if(++n<=max) print s " " $NF} END{if(n>max) print "… (+" n-max ")"}' \
      | while IFS= read -r l; do log "      $l"; done

    # new directories between the two versions
    new_dirs="$(comm -13 <(dirs_of "$old") <(dirs_of "$new") || true)"
    if [ -n "$new_dirs" ]; then
      log "New directories: $(echo "$new_dirs" | wc -l | tr -d ' ')"
      echo "$new_dirs" | awk -v max=15 'NR<=max{print "      + " $0} END{if(NR>max) print "      … (+" NR-max ")"}' | tee -a "$LOG"
    else
      log "New directories: none"
    fi
  fi
else
  # --- new clone: complete, no filters or sparse
  if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
    log "ERROR: $DEST exists and is not a git repository; move it or use another -o"; exit 1
  fi
  if git clone --quiet --branch "$BRANCH" "$URL" "$DEST"; then
    nf="$(count_files "$DEST")"
    dl=$(( $(du -sk "$DEST/.git" | cut -f1) * 1024 ))
    nd="$(dirs_of HEAD | wc -l | tr -d ' ')"
    log "Cloned (new): $REPO  ·  files: $nf  ·  directories: $nd  ·  download ≈ $(human_size $dl)"
    log "First- and second-level directories:"
    dirs_of HEAD | awk -F/ 'NF<=2{print "      + " $0}' | tee -a "$LOG"
  else
    log "ERROR cloning $URL"; exit 1
  fi
fi
log "Version: $(git -C "$DEST" log -1 --format='%h  %ad  %s' --date=short)"

# -----------------------------------------------------------------------------
log "=== 2/4 Directory check ==="
if [ "$CHECK" -eq 1 ]; then
  IFS=',' read -r -a required <<< "$REQUIRE"
  missing=0
  for p in "${required[@]}"; do
    p="${p//[[:space:]]/}"; p="${p%/}"; [ -n "$p" ] || continue
    if [ -d "$DEST/$p" ] && [ -n "$(find "$DEST/$p" -type f -print -quit 2>/dev/null)" ]; then
      log "  OK       $p  ($(count_files "$DEST/$p") files)"
    else
      log "  MISSING  $p"; missing=$((missing+1))
    fi
  done
  if [ "$missing" -gt 0 ]; then errors=$((errors+missing)); log "ERROR: $missing required directories are missing"; fi
else
  log "Check disabled (--no-check)"
fi

# -----------------------------------------------------------------------------
log "=== 3/4 Content per directory ==="
printf '%-26s %9s %10s\n' "directory" "files" "size" | tee -a "$LOG"
total_f=0
for d in "$DEST"/*/; do
  n="$(basename "$d")"
  f="$(count_files "$d")"; kb="$(du -sk "$d" | cut -f1)"; total_f=$((total_f+f))
  printf '%-26s %9s %10s\n' "$n/" "$f" "$(human_size $((kb*1024)))" | tee -a "$LOG"
  if [ "$TREE" -eq 1 ]; then
    for s in "$d"*/; do
      [ -d "$s" ] || continue
      printf '  %-24s %9s %10s\n' "$(basename "$s")/" "$(count_files "$s")" "$(human_size $(( $(du -sk "$s" | cut -f1) * 1024 )))" | tee -a "$LOG"
    done
  fi
done
log "Total: $total_f files (plus those in the repo root)"

# -----------------------------------------------------------------------------
log "=== 4/4 Scheduling ==="
if [ -n "$CRON_EXPR" ]; then
  cron_line="$CRON_EXPR $SCRIPT_ABS -u $GH_USER -r $REPO -o $SOURCE"
  [ -n "${BRANCH:-}" ] && cron_line="$cron_line -b $BRANCH"
  [ "$CHECK" -eq 0 ] && cron_line="$cron_line --no-check"
  [ "$REQUIRE" != "$REQUIRE_DEFAULT" ] && [ "$CHECK" -eq 1 ] && cron_line="$cron_line --require '$REQUIRE'"
  [ "$FORCE" -eq 1 ] && cron_line="$cron_line --force"
  cron_line="$cron_line >/dev/null 2>&1"
  ( crontab -l 2>/dev/null | grep -vF "$SCRIPT_ABS" ; echo "$cron_line" ) | crontab -
  log "Cron scheduled: $CRON_EXPR"
else
  log "Not scheduled (use --cron \"0 3 * * *\" to update every day)"
fi

echo | tee -a "$LOG"
log "DONE. Repo: $DEST  |  Errors: $errors  |  Duration: ${SECONDS}s"
[ "$errors" -eq 0 ]

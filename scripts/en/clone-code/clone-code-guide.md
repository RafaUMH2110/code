# clone-code.sh — clone the complete `code` repo

**Author:** Rafa · Department of Systems Engineering and Automation · Miguel Hernández University of Elche · r.puerto@umh.es
*Generated with AI · Reviewed by the author*

Clones (or updates) the **complete** repository `RafaUMH2110/code` with **all** its directories, including the new ones (`telemetria/meteo/`, `telemetria/home/`, `telemetria/home/telehome-servicio*/`, `generador-apps/`…). It does not use partial cloning: if you already had a partial clone (sparse-checkout), it completes it.

Spanish original: [`../../clonar-code/`](../../clonar-code/instrucciones-clonar-code.md).

## Quick start

```bash
chmod +x clone-code.sh
./clone-code.sh                       # clones into ~/RafaUMH2110/code (or updates)
./clone-code.sh -o /srv/repos         # another container folder
./clone-code.sh --tree                # adds the second level to the summary
./clone-code.sh --cron "0 3 * * *"    # and schedules it daily at 03:00
```

## What it does (4 steps)

1. **Cloning.** If `SOURCE/code` does not exist, it runs a full `git clone`. If it exists: it disables sparse-checkout if enabled, warns about local changes, runs `fetch` and advances with `merge --ff-only`. It reports commits, new/modified/deleted files, lines, approximate download and **new directories**.
2. **Check.** Verifies that the required directories exist (and contain files). Default: `telemetria/meteo/telemeteo-consulta`, `telemetria/meteo/telemeteo-monitor`, `telemetria/meteo/telemeteo-puente`, `telemetria/home/telehome-servicio`, `telemetria/home/telehome-pruebas`, `generador-apps`, `linux`, `macos`, `windows`, `scripts`.
3. **Content.** Table of files and size per first-level directory (`--tree`: second level too).
4. **Scheduling.** With `--cron` it replaces this script's cron line with the new one.

## Options

| Option | Meaning | Default |
|---|---|---|
| `-u USER` | GitHub account | `RafaUMH2110` |
| `-r REPO` | Repository | `code` |
| `-o SOURCE` | Folder that holds the clone (ends up in `SOURCE/REPO`) | `~/RafaUMH2110` |
| `-b BRANCH` | Branch to follow | repo default branch |
| `--require LIST` | Required directories, comma-separated | the 9 listed above |
| `--no-check` | Skip the directory check | — |
| `--tree` | Also show second-level subdirectories | — |
| `--force` | On local changes or when it cannot fast-forward: keep a copy and match the remote | — |
| `--cron "EXPR"` | Schedule the update in cron | — |
| `-h`, `--help` | Help | — |

## `--force`: what is kept

- Uncommitted local changes → `SOURCE/clone-code-backups/<repo>-<date>.patch`.
- Local commits not on the remote → branch `backup-before-force-<date>`.

Without `--force`, if it cannot advance the script exits with an error and changes nothing.

## Exit codes

`0` OK · `1` error (no network, clone cannot be updated, a required directory is missing, unknown option). The log is kept in `SOURCE/clone-code.log`.

## Notes

- **`telemetria/`** is organised as `meteo/` (`telemeteo-consulta`, `-monitor`, `-puente`) and `home/` (`telehome-servicio` and `telehome-pruebas`). If you had an earlier version cloned, the update moves the directories and the script lists them as new.
- The **web mode** of `install-all.sh` publishes the apps, not the whole `code` repo: this script is for having the source code on the server, not for deploying it to Apache.
- A saved `install-all` (sparse) selection does not affect this clone: they live in different folders unless you use the same `-o`; in that case `clone-code.sh` will complete the partial clone.
- To add a new directory to the check: `--require "…,new-dir"` (or edit `REQUIRE_DEFAULT` in the script).

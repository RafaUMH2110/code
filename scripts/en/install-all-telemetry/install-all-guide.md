# install-all.sh (telemetry only)

**Author:** Rafa · Department of Systems Engineering and Automation · Miguel Hernández University of Elche · r.puerto@umh.es
*AI-generated · Reviewed by the author*

Reduced version of `install-all` for Debian 13: it works **only** with the telemetry apps and lets you choose whether the collector is installed.

## What it does

1. Installs dependencies (`apache2`, `git`, `curl`, `jq`, `rsync`, `python3`).
2. Clones or updates **only** the `telemetria/` folder of the `RafaUMH2110/apps` repo (partial clone: `--filter=blob:none` + `sparse-checkout`). That folder contains both collectors: `telemetcolector` (Spanish) and `telemetcollector` (English).
3. Deploys to Apache the web files **of `telemetria/` only** (`<dest>/apps/telemetria/`), generates `apps.json` and installs the `index.html` portal with its favicon (they must sit next to the script).
4. **Your choice**: installs `telemet-collector` (the English version) as a systemd service. The Spanish one, `telemet-colector`, is installed by `instalar-todo.sh` (folder `instalar-todo-telemetria/`).
5. Sets the server entry point to `http://<IP>/rafa/`.
6. Checks the result and, if requested, schedules the task in cron.

It is idempotent: run it again to update.

## Usage

```bash
chmod +x install-all.sh
./install-all.sh -h
./install-all.sh --collector       # apps + telemet-collector
./install-all.sh --no-collector    # apps only
./install-all.sh                   # asks if there is a terminal; otherwise skips the collector
```

Collector credentials: the `TELEMET_STATION_ID` and `TELEMET_API_KEY` variables, or typed at the prompt. Without them the service is prepared but not started.

## Options

| Option | Effect |
|---|---|
| `-u USER` | GitHub account (default `RafaUMH2110`) |
| `-o SOURCE` | Where to clone (default `~/RafaUMH2110-telemetria`) |
| `-d DEST` | Apache directory for the apps (default `<docroot>/rafa`) |
| `--docroot DIR` | Apache DocumentRoot (default `/var/www/html`) |
| `--force` | Do not ask for confirmation if the destination has foreign content |
| `--mode web\|html\|all` | What gets published (default `web`); `--html-only` is an alias for `--mode html` |
| `--no-index` | Do not install the `index.html` portal |
| `--collector` / `--no-collector` | Install or skip `telemet-collector` |
| `--cron "EXPR"` | Schedule the task in cron, e.g. `"0 3 * * *"` |

## Entry page

- The portal lists **all the cloned and deployed apps**, not only the telemetry ones: if the same destination holds apps from other repos or from other folders of `apps/` (for example, those left by the full `install-all.sh`), they keep showing.
- To do so, when generating `apps.json` the script walks **the whole destination** and looks for the clones in the source folder (`-o`) and in the user's sibling folders (`~/RafaUMH2110`, `~/RafaUMH2110-telemetria`…): that is where each app's README, summary and date come from.
- The mirror (`rsync --delete`) is done **only on `apps/telemetria/`**: anything else in the destination is neither deleted nor touched.
- `favicon.svg`, `favicon.ico` and `apple-touch-icon.png` are copied next to the portal (browser tab icon, bookmarks and iOS).

## Notes

- The script's own files use hyphens (`install-all.sh`, marker `.install-all`); the collector's program files keep the repo names (`telemet_collector.py`, `config.ini`).
- The history (`data/`) is not deleted when updating.
- The collector writes `history.json` inside the `telemet/history/data/` app folder, and an Apache config without cache is added for that file.

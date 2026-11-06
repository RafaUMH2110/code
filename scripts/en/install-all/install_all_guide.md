# How to use `install_all.sh`

Deployment of the applications of the GitHub account **RafaUMH2110** on a local **Debian 13** server (`192.168.0.129`) with Apache, an entry portal and an optional telemetry collector.

Author: Rafael Puerto · Department of Systems Engineering and Automation · UMH · r.puerto@umh.es
_Generated with AI · Reviewed by the author_ · Last modified: 2026-11-04 02:40

---

## Contents

1. [What it does](#1-what-it-does)
2. [Files and requirements](#2-files-and-requirements)
3. [Quick start](#3-quick-start)
4. [Options reference](#4-options-reference)
5. [Choosing what to clone](#5-choosing-what-to-clone)
6. [What is published to Apache (modes)](#6-what-is-published-to-apache-modes)
7. [The entry portal](#7-the-entry-portal)
8. [Telemetry collector](#8-telemetry-collector)
9. [Server entry point (`/rafa/`)](#9-server-entry-point-rafa)
10. [Automatic updates with cron](#10-automatic-updates-with-cron)
11. [Where everything ends up](#11-where-everything-ends-up)
12. [Checks](#12-checks)
13. [Troubleshooting](#13-troubleshooting)
14. [Reverting and uninstalling](#14-reverting-and-uninstalling)
15. [Security](#15-security)

---

## 1. What it does

The script is **idempotent**: it can be run as many times as you like and leaves the server in the same final state. Each run goes through six steps:

| Step | Action |
|---|---|
| 1/6 | Installs whatever is missing: `apache2`, `git`, `curl`, `jq`, `rsync`, `python3`. |
| 2/6 | Decides which repos to clone (all, a list or a menu) and **clones or updates** them (`git pull --ff-only`). It can clone only some folders of a repo. |
| 3/6 | **Deploys to Apache** only the web files, generates the `apps.json` catalog and installs the `index.html` portal. |
| 4/6 | _(Optional, `--collector`)_ Installs the telemetry collector as a systemd service. |
| 5/6 | Sets the server entry point: `http://<IP>/` redirects to `http://<IP>/rafa/`. |
| 6/6 | Checks with `curl` that the entry answers and, if requested, schedules cron. |

Only the **public** repos of the account are cloned; no token is needed.

## 2. Files and requirements

**Two files in the same folder** are needed:

| File | Purpose |
|---|---|
| `install_all.sh` | The script. |
| `index.html` | Template of the portal published at `/rafa/`. If missing, the script generates a simple index as a fallback. |

Server requirements:

- Debian 13 with Internet access (HTTPS to `github.com` and `api.github.com`).
- A user with `sudo` (or run as root). The script uses `sudo` only to write to Apache, `/opt`, `/etc` and `/var`.
- The packages of step 1 are installed automatically.

## 3. Quick start

```bash
# 1. Copy to the server (from your computer)
scp install_all.sh index.html user@192.168.0.129:~/

# 2. On the server
chmod +x install_all.sh
./install_all.sh
```

This clones all public repos, deploys them to `/var/www/html/rafa/` and leaves the entry at `http://192.168.0.129/rafa/`.

Common combinations:

```bash
./install_all.sh -i                            # choose what to clone with a menu
./install_all.sh -i --collector                # choose, and also install the collector
./install_all.sh --repos "apps/telemetria"     # telemetry only
./install_all.sh --collector --cron "0 3 * * *"    # update every day at 3:00
./install_all.sh --list                        # see what exists and what is selected
```

## 4. Options reference

### Source and destination

| Option | Default | Description |
|---|---|---|
| `-u USER` | `RafaUMH2110` | GitHub account. |
| `-o SOURCE` | `~/RafaUMH2110` | Folder where the repos are cloned. |
| `-d DEST` | `<docroot>/rafa` | Apache folder where they are published. It must be inside the DocumentRoot; the web path of the entry is deduced from it. |
| `--docroot DIR` | `/var/www/html` | DocumentRoot of your Apache. Use it if it serves another folder, e.g. `--docroot /var/www/htdocs` (the destination becomes `/var/www/htdocs/rafa`). |
| `--force` | — | Do not ask for confirmation when `DEST` already has content not created by the script (see [section 6](#6-what-is-published-to-apache-modes)). |

### What to clone

| Option | Description |
|---|---|
| `-i`, `--interactive` | Menu to choose repos and, inside each one, folders. Saves the selection. |
| `--repos LIST` | Comma-separated list; each item is `repo` or `repo/folder`. Saves the selection. |
| `--exclude LIST` | All public repos **except** the ones listed. Saves the selection. |
| `--all` | Deletes the saved selection: clones everything again. |
| `--list` | Shows repos, folders and the current selection (`[x]` = will be cloned) and exits. Changes nothing. |

### What is published

| Option | Description |
|---|---|
| `--mode web` | (Default) Web files only. See [section 6](#6-what-is-published-to-apache-modes). |
| `--mode html` | Only `*.html` and `*.htm` (alias: `--html-only`). |
| `--mode all` | The whole repo content, except `.git`, `.github` and secrets. |
| `--no-index` | Do not install the `index.html` portal. The `apps.json` catalog is always generated. |

### Telemetry and automation

| Option | Description |
|---|---|
| `--collector` | Installs the telemetry collector as a service. See [section 8](#8-telemetry-collector). |
| `--cron "EXPR"` | Schedules periodic execution, e.g. `--cron "0 3 * * *"`. |
| `-h`, `--help` | Shows the help. |

## 5. Choosing what to clone

### 5.1 Interactive menu (`-i`)

It shows the list of repos with their language and size:

```
Public repositories of RafaUMH2110:
   1) apps               HTML, 1446 KB
   2) apps-pro           HTML, 110 KB
   3) Artifacts          HTML, 817 KB
   4) code               Python, 309 KB
   5) IAC                HTML, 256 KB
Choose (numbers or ranges like 1-3 separated by spaces; Enter = all; n = none):
```

- Type numbers separated by spaces (`1 4`), ranges (`1-3`) or a mix (`1 3-5`).
- **Enter** chooses all; **n** chooses none.
- For each chosen repo that has folders, it asks `all content (A) or choose folders (c)? [A/c]`. With `c` a second menu appears with the first-level folders (in `apps`: `moda`, `telemetria`, `consultar`…; in `code`: `linux`, `macos`, `windows`).
- It needs a terminal (it does not work in cron or with redirected input).

### 5.2 From the command line

```bash
# Only these folders and repos
./install_all.sh --repos "apps/telemetria,apps/moda,code/linux,code/telemetria"

# Everything except some repos
./install_all.sh --exclude "apps-pro,Artifacts"

# Back to everything
./install_all.sh --all
```

Repo names are case-insensitive. A name that does not exist in the account is ignored with a warning.

### 5.3 Saved selection

Every time you use `-i`, `--repos` or `--exclude`, the selection is saved in `~/RafaUMH2110/.selection` (or `<SOURCE>/.selection`) and **reused** in later runs, including cron ones. It is a text file, one entry per line:

```
apps/telemetria
apps/moda
code
-Artifacts
```

Rules:

- If there are positive lines (`repo` or `repo/folder`), **only** those are cloned.
- A `-repo` line excludes that repo. If there are only `-` lines, everything is cloned except those.
- If a repo appears whole and also with folders, the whole repo wins.
- A new selection **replaces** the previous one (it is not added).
- You can edit the file by hand.

### 5.4 What happens when you change the selection

- **Partial folders** (`repo/folder`): git _sparse checkout_ is used; only those folders are downloaded and deployed. The files at the root of the repo (for example `README.md`) are downloaded as well.
- **From partial to complete**: the script disables sparse checkout and the repo is completed on the next update.
- **Repos you stop selecting**: they are **removed from the deployment** in Apache (`/var/www/html/rafa/<repo>`) and disappear from the portal. Their cloned copy stays in `~/RafaUMH2110/` and is not deleted.
- **`--list`** changes nothing: use it to see the state before deciding.

> **GitHub API limit:** unauthenticated it is 60 requests per hour per IP. A normal run uses one; `-i` and `--list` also use one per repo (about 7 in total with the current account).

## 6. What is published to Apache (modes)

By default the script **does not copy the whole repo to Apache**, only what a browser needs.

### `web` mode (default)

These extensions are copied:

`html htm css js mjs json webmanifest svg png jpg jpeg gif webp avif ico bmp woff woff2 ttf otf eot mp3 mp4 webm ogg wav pdf xml csv`

Always excluded:

| Excluded | Reason |
|---|---|
| `*.py`, `*.ini`, `*.service`, `*.md`, `*.sh`, etc. | Not web content (includes the collector code). |
| Hidden folders and files (`.vscode`, `.env`, `.git`, `.github`…) | Internal configuration. |
| `*.key`, `*.pem`, `*secret*`, `*credential*`, `config.ini` | Possible secrets. |
| `package*.json`, `tsconfig*.json`, `*config*.json` | Development configuration files. |
| `node_modules/` | Dependencies. |

Folders that end up empty are not published.

### `html` mode

Only `*.html` and `*.htm`. It is the cleanest, but it **does not copy images or icons** (for example, the `apple-touch-icon.png` of the telemetry apps).

### `all` mode

Copies the whole repo except `.git`, `.github`, `.gitignore`, `.env*`, keys and `config.ini`. Use it if an app needs files that `web` mode excludes.

### If `DEST` already has your content

If the destination folder **already exists and has files not created by this script** (for example, a web root you were already using), the first time the script:

1. Lists what is there and **asks for confirmation** (`Continue? [y/N]`). Without a terminal, as in cron, it **stops** unless you use `--force`.
2. Saves in `/var/backups/install-all-<date>/` a copy of whatever it replaces or deletes: the previous `index.html` and `apps.json` and any file that a repo mirror replaces or removes.
3. Marks the folder with the hidden file `.install_all`; from then on it does not ask again.

Only `index.html`, `apps.json` and the folders named after a selected repo are touched. Any other folder or file in `DEST` (for example, `GenImOd/` or `empty/`) is left as it is. If you already had a folder with the same name as a repo (for example, `apps/`), its content is replaced by the repo's: review the list before accepting.

### Notes

- The deployment is a **mirror**: what you delete or change in the repo is reflected in Apache, and any file you add by hand inside `/var/www/html/rafa/<repo>/` is deleted on the next run.
- There is one exception: folders named **`datos/`** are protected, because the telemetry collector writes there.
- The final permissions are owner `www-data`, 755 on folders and 644 on files, only on what the script manages.

## 7. The entry portal

`index.html` is a static page that reads the `apps.json` catalog and shows one card per application.

- **Categories:** in the `apps` repo, the first folder is the category (`moda`, `telemetria`, `consultar`…) and each one forms a section. The other repos form one section each.
- **Cards:** they show the HTML title, its description (`<meta description>` or, if there is none, the summary of the nearest README), the project, the operating system (in `code`: Linux/macOS/Windows), the size and the date of the last commit. Versions such as `pro`, `lite`, etc. are shown as a badge next to the app name.
- **Search and filters:** the search box (shortcut `/`) and the category buttons filter instantly.
- **Theme:** light or dark depending on the system.
- **Catalog:** `apps.json` is regenerated on every run of the script. If you open `index.html` directly from disk (`file://`) or without `apps.json` next to it, the message "The catalog could not be loaded" appears.

To change the design, edit `index.html` next to the script and run it again. To change only the page without touching the repos:

```bash
sudo install -m 644 index.html /var/www/html/rafa/index.html
```

The descriptions of the known apps (GenImOd, GenOutFit, GenPatMod…) are in the `INFO` dictionary inside `index.html`, and the category names in the `CAT` dictionary.

## 8. Telemetry collector

The `apps` repo contains in `telemetria/telemetcolector/` a Python program that reads your weather station (Weather Underground) every 5 minutes, keeps the last 12 hours in SQLite and exports a `historial.json` used by the **TeleMet Historial** app. **It is not a web page**: it is a service that has to be running on the server. It only uses the Python standard library.

### 8.1 Installation

```bash
# With the credentials prompt (asks for Station ID and API Key)
./install_all.sh --repos "apps/telemetria" --collector

# Without being asked (environment variables)
read -rp "Station ID: " TELEMET_STATION_ID
read -rsp "API Key: " TELEMET_API_KEY; echo
export TELEMET_STATION_ID TELEMET_API_KEY
./install_all.sh --repos "apps/telemetria" --collector
```

Requirement: the `apps` repo with the `telemetria` folder must be in the selection (otherwise the script warns that it cannot find `telemetcolector`).

> Typing the key on the command line (`TELEMET_API_KEY=xxx ./install_all.sh …`) leaves it in the shell history. The format above, or letting the script ask for it, is preferable.

### 8.2 What the script does with `--collector`

| Item | Location |
|---|---|
| Service user (no shell) | `telemet` |
| Program and configuration | `/opt/telemet-colector/` (`telemet_colector.py`, `config.ini`, `config.example.ini`) |
| Database | `/opt/telemet-colector/datos/telemet.sqlite` |
| systemd service | `/etc/systemd/system/telemet-colector.service` |
| Published JSON | next to the Historial app: `/var/www/html/rafa/apps/telemetria/telemet/historial/datos/historial.json` |
| Anti-cache header for the JSON | `/etc/apache2/conf-available/telemet-historial.conf` |

- The service is generated from the repo's `.service`, with the JSON folder adapted to this server.
- `config.ini` is created from the template **only if it does not exist**: running the script again does not overwrite your credentials. The `telemet_colector.py` program is always updated.
- `config.ini` ends up with `600` permissions and owned by `telemet`.
- The `datos/` folder where the JSON is written keeps the `telemet` owner even if it is deployed again.
- The JSON can be seen at `http://192.168.0.129/rafa/apps/telemetria/telemet/historial/datos/historial.json`.

### 8.3 With and without credentials

- **With credentials** (environment variables or answers to the prompt): they are written to `config.ini`, the service is enabled at boot and (re)started.
- **Without credentials**: the service is installed but **not started**, and the script shows what to do:

```bash
sudo nano /opt/telemet-colector/config.ini        # edit station_id and api_key
sudo -u telemet python3 /opt/telemet-colector/telemet_colector.py \
     -c /opt/telemet-colector/config.ini --probar # one test reading, nothing saved
sudo systemctl enable --now telemet-colector
```

### 8.4 Managing the service

```bash
systemctl status telemet-colector                 # status
journalctl -u telemet-colector -f                 # live log
sudo systemctl restart telemet-colector           # after editing config.ini

# Program utilities
sudo -u telemet python3 /opt/telemet-colector/telemet_colector.py -c /opt/telemet-colector/config.ini --estado
sudo -u telemet python3 /opt/telemet-colector/telemet_colector.py -c /opt/telemet-colector/config.ini --una-vez
```

Useful `config.ini` parameters: `intervalo_s` (default 300; with 288 calls per day, lowering it uses more of your API Key quota), `duracion_horas` (12) and `modo` (`deslizante` or `reinicio`).

> The collector's own command-line flags (`--probar`, `--estado`, `--una-vez`) and `config.ini` keys are those of the `telemetcolector` program in the repo, so they keep their original names.

### 8.5 Things to keep in mind

- The TeleMet Historial app only uses the JSON if its **Station ID** matches the collector's (case-insensitive).
- If there is no JSON yet, the app works the same, without the server history.
- The app warns if the last server reading is more than 15 minutes old.
- If the Historial app is not deployed, the JSON is published in `/var/www/html/rafa/telemethistorial/datos/`.
- On a system without active systemd (containers) the service is installed but does not start.

## 9. Server entry point (`/rafa/`)

In step 5 the script leaves `http://192.168.0.129/` redirecting to `http://192.168.0.129/rafa/`:

1. It creates `/etc/apache2/conf-available/rafa-entry.conf` with `RedirectMatch ^/$ /rafa/` and enables it. The redirect is relative, so it works the same with `localhost`, the IP or a host name.
2. **It disables any old configuration that led to `/moda/`**: it comments out the `Redirect`, `RedirectMatch`, `RewriteRule` lines that mention `moda` and the `DocumentRoot` lines ending in `moda`, both in `/etc/apache2` and in `/var/www/html/.htaccess`. If the root `index.html` pointed to `moda`, it replaces it with a redirect.
3. Before touching anything it makes a **backup** in `/var/backups/apache-entry-<date>/`.
4. It checks the configuration with `apache2ctl configtest`. If it fails, it **restores the backup** and undoes the changes.
5. If references to `moda` remain that it could not disable (an `Alias`, a `<Directory>`…), it lists them as a warning at the end.

If you change the destination (`-d /var/www/html/apps`), the entry becomes `/apps/`.

## 10. Automatic updates with cron

```bash
./install_all.sh --cron "0 3 * * *"                   # daily, at 3:00
./install_all.sh --collector --cron "30 2 * * 1"      # weekly, Mondays at 2:30
```

- The script adds a line to your `crontab` and replaces the previous one of the same script (no duplicates).
- Cron uses the **saved selection** and repeats the options `-o`, `-d`, `--mode`, `--no-index` and `--collector`.
- Cron has no terminal: credentials are not asked for (those in `config.ini` are kept) and `-i` cannot be used.
- To review or remove it: `crontab -l` and `crontab -e`.
- To see what happened: `tail -n 40 ~/RafaUMH2110/install_all.log`.

> `crontab` must be that of the same user who runs the script; the steps that need privileges use `sudo`, which in cron requires `NOPASSWD` or running as root (`sudo crontab -e`).

## 11. Where everything ends up

```
~/RafaUMH2110/                        ← SOURCE (clones)
├── apps/  code/ …       ← one directory per selected repo
├── .selection                        ← saved selection
└── install_all.log                   ← log of all the runs

/var/www/html/                        ← Apache DocumentRoot
└── rafa/                             ← DEST
    ├── index.html                    ← portal
    ├── apps.json                     ← catalog read by the portal
    ├── apps/moda/…  apps/telemetria/…  ← one folder per repo, original structure
    └── apps/telemetria/telemet/historial/datos/historial.json   ← written by the collector

/opt/telemet-colector/                ← collector (if --collector was used)
/etc/systemd/system/telemet-colector.service
/etc/apache2/conf-available/rafa-entry.conf
/etc/apache2/conf-available/telemet-historial.conf
/var/backups/apache-entry-<date>/     ← backup made before touching Apache
```

Resulting URLs (with IP `192.168.0.129`):

| URL | Content |
|---|---|
| `http://192.168.0.129/` | Redirects to `/rafa/`. |
| `http://192.168.0.129/rafa/` | Portal. |
| `http://192.168.0.129/rafa/<repo>/<path>/index.html` | Each app, e.g. `…/rafa/apps/moda/genimod/pro/index.html`. |

## 12. Checks

```bash
# Entry and portal
curl -sI http://192.168.0.129/      | head -3     # 302 with Location: /rafa/
curl -sI http://192.168.0.129/rafa/ | head -1     # 200

# Catalog: number of apps and categories
jq '.apps | length' /var/www/html/rafa/apps.json
jq -r '.apps[].path' /var/www/html/rafa/apps.json | cut -d/ -f1 | sort | uniq -c

# Selection and state
./install_all.sh --list
cat ~/RafaUMH2110/.selection

# Apache
sudo apache2ctl configtest
systemctl status apache2

# Collector
systemctl status telemet-colector
curl -s http://192.168.0.129/rafa/apps/telemetria/telemet/historial/datos/historial.json | head -c 300
```

When it finishes, the script prints a final line with the entry, the number of errors and the backup path:

```
DONE. Entry: http://192.168.0.129/rafa/  |  Errors: 0  |  Backup: /var/backups/apache-entry-…
```

The exit code is `0` if there were no errors.

## 13. Troubleshooting

| Symptom | Likely cause | Solution |
|---|---|---|
| `ERROR: … has foreign content and there is no terminal to confirm` | `DEST` already had content and the script ran without a terminal (cron, pipe). | Review it and run once by hand (or with `--force`). |
| `WARNING: the collector JSON folder does not exist` | `ruta_json` in `/opt/telemet-colector/config.ini` points to a folder that does not exist (e.g. the default path). | It is only a warning. Fix `ruta_json` in `config.ini`, or run with `--collector` so it adjusts to the deployed Historial app. |
| `The destination must be inside /var/www/html` | Your Apache serves another folder. | Use `--docroot` (e.g. `--docroot /var/www/htdocs`). |
| `ERROR: GitHub API query failed` | 60 requests/hour limit or no network. | Wait an hour; check `curl -I https://api.github.com`. |
| `ERROR updating: <repo>` | Local changes or rewritten history on the remote (`pull --ff-only` fails). | `git -C ~/RafaUMH2110/<repo> status`; if there is nothing to keep: `git -C … fetch && git -C … reset --hard origin/main`. |
| `WARNING: '<x>' is not a public repo…` | Misspelled name or private repo. | Check with `--list`. |
| `ERROR configuring folders of <repo>` | The folder does not exist in the repo. | Check the name with `--list` or `-i`. |
| The portal shows "The catalog could not be loaded" | `apps.json` is missing or the HTML was opened from disk. | Run the script and open `http://IP/rafa/`. |
| An app does not show or lacks images/files | `web` or `html` mode excludes that file type. | Use `--mode all`. |
| `ERROR in the Apache configuration: restoring backup` | `configtest` failed after the changes. | It restores itself; see the details in `install_all.log` and run `sudo apache2ctl configtest`. |
| `/` does not redirect to `/rafa/` | Another earlier rule (`.htaccess`, `DirectoryIndex`, another VirtualHost). | Review the final warnings; `sudo grep -rni "moda" /etc/apache2 /var/www/html/.htaccess`. |
| Warning "references to 'moda' remain" | An `Alias` or `<Directory>` that the script does not touch. | Edit that line by hand. |
| `telemet-colector` does not start | Missing credentials or the JSON folder is not writable. | `journalctl -u telemet-colector -e`; check `config.ini` and that `datos/` belongs to `telemet`. |
| `HTTP 401` in the collector log | Wrong or expired API Key. | Fix it in `config.ini` and `sudo systemctl restart telemet-colector`. |
| The Historial app says the history is from another station | The app's Station ID does not match the collector's. | Make them equal. |
| The JSON gives 404 | The Historial app is not deployed at the expected path. | Check `ruta_json` in `/opt/telemet-colector/config.ini` and that it points next to the app. |
| `Permission denied` when running | Missing `sudo` or execute permission. | `chmod +x install_all.sh`; use a user with `sudo`. |
| Cron does nothing | Relative path, `sudo` with password or another user's `crontab`. | Use absolute paths, `NOPASSWD` or `sudo crontab -e`; check `install_all.log`. |

## 14. Reverting and uninstalling

**Remove the entry redirect**

```bash
sudo a2disconf rafa-entry && sudo systemctl reload apache2
# Restore previous files: copy from /var/backups/apache-entry-<date>/
```

**Remove the portal and the published apps** (the clones are kept)

```bash
sudo rm -rf /var/www/html/rafa
```

**Remove the collector**

```bash
sudo systemctl disable --now telemet-colector
sudo rm /etc/systemd/system/telemet-colector.service && sudo systemctl daemon-reload
sudo a2disconf telemet-historial && sudo systemctl reload apache2
sudo rm -rf /opt/telemet-colector          # also deletes the SQLite database and config.ini
sudo userdel telemet
```

**Remove the cron job**: `crontab -e` and delete the `install_all.sh` line.

**Delete the clones**: `rm -rf ~/RafaUMH2110`.

## 15. Security

- `web` mode does not publish `.py`, `.ini`, `.env`, keys or `config*.json` files, so that code and configuration cannot be downloaded from Apache.
- The collector's `config.ini` contains the API Key: it ends up with `600` permissions, owned by `telemet`, and **must not be uploaded to GitHub** (the repo already ignores it). The key does not appear in the exported JSON.
- The collector service runs with a user without a shell, with `ProtectSystem=strict` and write access only to its data folder and the JSON folder.
- The script only clones **public** repos and does not use GitHub tokens.
- Credentials are passed to the configuration file through the environment, not the command line, so they do not show up in `ps`.
- Check that the server is not exposed to the Internet if that is not intended: the redirect and the apps are served over HTTP without authentication.

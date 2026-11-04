# Deployment on https://isa.umh.es with `install_all_isa.sh`

**Author:** Rafa · Department of Systems Engineering and Automation · Miguel Hernández University of Elche · r.puerto@umh.es
**Date:** 2026-11-04
*Generated with AI · Reviewed by the author*

---

## 1. What it is

A variant of the `install_all.sh` installer for the production server **https://isa.umh.es** (Debian 13), whose Apache DocumentRoot is `/var/www/htdocs`. The content is published in `/var/www/htdocs/rafa` and the portal ends up at **https://isa.umh.es/rafa/**.

The core difference: the server already has its own configuration (`<Directory /var/www/htdocs/rafa>`, `Alias "/moda"`, `.htaccess` in `rafa/` and `rafa/moda/`). This variant **does not modify it**.

## 2. Differences from the local version

| Aspect | Local version | isa.umh.es version |
|---|---|---|
| Default DocumentRoot | `/var/www/html` | `/var/www/htdocs` |
| URL | Server IP | `https://isa.umh.es` (`--url`) |
| Rules pointing to `/moda` | Disables them (with a backup) | **Does not touch them** |
| Server front page (`/`) | Redirects to `/rafa/` | **Unchanged**; only with `--root-entry` |
| `apache2.conf` / `Directory` block | — | Only checks it exists and warns if missing |
| Collector already installed | Rewrites path and service | **Keeps** `config.ini`, the JSON path and the systemd unit |
| Apache reload | Always | Only if it adds new configuration (with `configtest` and rollback) |
| Final check | `http://localhost` | `https://isa.umh.es` resolved to the server itself, falling back to `http://localhost` |

## 3. Requirements

- Debian 13 with Apache already running for isa.umh.es.
- A user with `sudo`.
- In the same folder as the script: `index.html` (the portal).
- Access to `api.github.com` and `github.com` (public repos of `RafaUMH2110`).

The script installs `git`, `curl`, `jq`, `rsync` and `python3` itself if they are missing.

## 4. Usage

```bash
chmod +x install_all_isa.sh

# Choose what to clone and deploy
./install_all_isa.sh --repos "apps/telemetria,apps/moda,code/linux"

# Interactive menu
./install_all_isa.sh -i

# Everything + telemetry collector
./install_all_isa.sh --all --collector

# See the available repos and folders
./install_all_isa.sh --list
```

### Options specific to this variant

| Option | Effect |
|---|---|
| `--url URL` | Public URL (def.: `https://isa.umh.es`) |
| `--docroot DIR` | DocumentRoot (def.: `/var/www/htdocs`) |
| `--root-entry` | Also, `/` redirects to `/rafa/` (changes the front page) |
| `--json-dir DIR` | Folder where the collector publishes `historial.json` |

The remaining options (`-u`, `-o`, `-d`, `--mode`, `--repos`, `--exclude`, `--all`, `--list`, `--no-index`, `--collector`, `--cron`, `--force`) work as in the local version; see `install_all_guide.md`.

## 5. First run on isa.umh.es

`/var/www/htdocs/rafa` already has content (`.htaccess`, `moda/`, `telemethistorial/`…), so the script:

1. Lists what is there and **asks for confirmation** (`--force` skips it).
2. Makes a copy in `/var/backups/install-all-<date>/` of whatever it replaces or deletes.
3. Replaces `rafa/index.html` and `rafa/apps.json`.
4. Mirrors each selected repo **only inside `rafa/<repo>/`**.

Not modified: `rafa/.htaccess`, `rafa/moda/`, `rafa/telemethistorial/datos/` or `/var/www/htdocs/index.html`.

> **Warning:** if a repo has the same name as a folder of yours (for example, a repo called `moda`), its mirror would delete whatever is not in the repository. Review the warning list before confirming.

## 6. Telemetry collector (`--collector`)

- **If** `/opt/telemet-colector/config.ini` **already exists**: `station_id`, `api_key` and `ruta_json` are kept.
- **If the program differs:** `telemet_colector.py.bak-<date>` is saved and the program is updated.
- **If** `/etc/systemd/system/telemet-colector.service` **already exists**: it is left as is.
- **If it is a new installation:** it creates the `telemet` user, the systemd unit and the JSON folder (`rafa/telemethistorial/datos` unless `--json-dir` is given). Credentials are taken from `TELEMET_STATION_ID` and `TELEMET_API_KEY`, or asked on the terminal.
- It adds `conf-available/telemet-historial.conf` (`Cache-Control: no-store` header for the JSON).

## 7. Periodic updates

```bash
./install_all_isa.sh --cron "0 3 * * *" --collector
```

The cron entry includes `--docroot` and `--url`, and reuses the selection saved in `<SOURCE>/.selection`.

## 8. Verification

```bash
curl -I https://isa.umh.es/rafa/
curl -I https://isa.umh.es/rafa/apps.json
curl -I https://isa.umh.es/moda/          # must remain as before
sudo apache2ctl configtest
sudo systemctl status telemet-colector
```

The log of each run is in `<SOURCE>/install_all.log`.

## 9. Common problems

| Symptom | Cause and solution |
|---|---|
| 403 on `/rafa/` | `Require all granted` is missing for `/var/www/htdocs/rafa`. The script warns if it does not find the `Directory` block. |
| 404 on `/rafa/` | Apache does not serve `/var/www/htdocs`. Check `DocumentRoot` with `apache2ctl -S`. |
| `moda` stopped working | It should not happen. Restore what applies from `/var/backups/install-all-<date>/`. |
| Check reports "via http://localhost" | Port 443 or the certificate do not answer from the server itself; it does not imply a failure from outside. |
| Collector not starting | `station_id` and `api_key` are missing: edit `/opt/telemet-colector/config.ini` and run `sudo systemctl enable --now telemet-colector`. |
| Error in `configtest` | The script disables what it added (`a2disconf`) and stops. Check `sudo apache2ctl configtest`. |

## 10. Restoring

```bash
ls /var/backups/install-all-*/
sudo cp -a /var/backups/install-all-<date>/index.html /var/www/htdocs/rafa/index.html
```

To remove the configuration added by the script:

```bash
sudo a2disconf telemet-historial rafa-entry
sudo systemctl reload apache2
```

---
*Last modified: 2026-11-04 02:42*

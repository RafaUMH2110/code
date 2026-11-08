# scripts (English)

**Author:** Rafa · Department of Systems Engineering and Automation · Miguel Hernández University of Elche · r.puerto@umh.es
*Generated with AI · Reviewed by the author*

English versions of the scripts in the parent folder (Spanish originals): names, options, parameters, variables, messages and guides are all in English.

Scripts to clone the public repos of `RafaUMH2110`, deploy their web apps to Apache and, optionally, install the telemetry collector.

## Contents

| Folder | File | Spanish original | Purpose |
|---|---|---|---|
| `clone-update/` | `update-repos.sh` | `actualizar-repos.sh` | Clones or updates the public repos (first version) |
| | `deploy-apache.sh` | `desplegar-apache.sh` | Copies the HTML apps to the Apache directory (first version) |
| | `clone-update-repos.md` | `clonar-actualizar-repos.md` | Guide for the two above |
| `install-all/` | `install-all.sh` | `instalar-todo.sh` | All-in-one for the local server (repo selection, deployment, collector, `/rafa/` entry) |
| | `install-all-isa.sh` | `instalar-todo-isa.sh` | Variant for https://isa.umh.es (DocumentRoot `/var/www/htdocs`; leaves the existing configuration alone) |
| | `index.html`, `favicon.svg`, `favicon.ico`, `apple-touch-icon.png` | same | Entry portal and its favicon; must be next to the scripts |
| | `install-all-guide.md` | `instrucciones-instalar-todo.md` | Guide for `install-all.sh` |
| | `install-all-isa-guide.md` | `instrucciones-instalar-todo-isa.md` | Guide for `install-all-isa.sh` |
| | `apache-docroot.md` | `apache-docroot-htdocs.md` | Why `/rafa/` gives 404 if Apache serves another DocumentRoot |
| `install-all-telemetry/` | `install-all.sh` | `instalar-todo-telemetria/instalar-todo.sh` | Reduced version: clones **only** `apps/telemetria` (partial clone), deploys it to Apache and lets you choose to install `telemet-collector` (`--collector` / `--no-collector`). Its Spanish counterpart installs `telemet-colector` |
| | `index.html`, `favicon.svg`, `favicon.ico`, `apple-touch-icon.png` | same | Entry portal (lists **all** the cloned apps, not only the telemetry ones) and its favicon; must sit next to the script |
| | `install-all-guide.md` | `instrucciones-instalar-todo.md` | Guide for `install-all.sh` |
| `../telemet-collector-info/` | `telemet-collector-info.py` | `telemet-collector-info.py` | Shows all the TeleMet Collector parameters (bilingual output, `--lang en`). Standalone, read-only |
| | `telemet-collector-info-ssh.py` | `telemet-collector-info-ssh.py` | Runs on your computer (CLI or VS Code): connects by SSH (password or RSA key) and shows the report of one or several servers. `--check-key` / `--install-key` / `--generate-key` validate or install `authorized_keys` login. Manual in Spanish: `MANUAL.md` |

`install-all*.sh` supersede the scripts in `clone-update/`.

## Option names (Spanish → English)

| Spanish | English |
|---|---|
| `--forzar` | `--force` |
| `--interactivo` | `--interactive` |
| `--excluir` | `--exclude` |
| `--todos` | `--all` |
| `--listar` | `--list` |
| `--modo web\|html\|todo` | `--mode web\|html\|all` |
| `--solo-html` | `--html-only` |
| `--sin-indice` | `--no-index` |
| `--colector` | `--collector` |
| `--entrada-raiz` | `--root-entry` |
| `-u USUARIO` / `-o ORIGEN` / `-d DESTINO` | `-u USER` / `-o SOURCE` / `-d DEST` |

Files created by the scripts are renamed too: `.selection`, `.install-all`, `install-all.log`, `/var/backups/install-all-<date>/`, `rafa-entry.conf`. The English scripts install the English collector (`telemetcollector`, service `telemet-collector`, `/opt/telemet-collector`, `json_path`, `data/`); its program files keep the repo names (`telemet_collector.py`). The Spanish scripts install `telemet-colector`. Other names that belong to the repos (`apps/moda`, `apps/telemetria`…) are unchanged.

## Quick start

```bash
cd install-all
chmod +x install-all.sh install-all-isa.sh
./install-all.sh -h        # local server
./install-all-isa.sh -h    # isa.umh.es
```

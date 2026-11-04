# scripts (English)

**Author:** Rafa · Department of Systems Engineering and Automation · Miguel Hernández University of Elche · r.puerto@umh.es
*Generated with AI · Reviewed by the author*

English versions of the scripts in the parent folder (Spanish originals): names, options, parameters, variables, messages and guides are all in English.

Scripts to clone the public repos of `RafaUMH2110`, deploy their web apps to Apache and, optionally, install the telemetry collector.

## Contents

| Folder | File | Spanish original | Purpose |
|---|---|---|---|
| `clone-update/` | `update_repos.sh` | `actualizar_repos.sh` | Clones or updates the public repos (first version) |
| | `deploy_apache.sh` | `desplegar_apache.sh` | Copies the HTML apps to the Apache directory (first version) |
| | `clone_update_repos.md` | `clonar_actualizar_repos.md` | Guide for the two above |
| `install-all/` | `install_all.sh` | `instalar_todo.sh` | All-in-one for the local server (repo selection, deployment, collector, `/rafa/` entry) |
| | `install_all_isa.sh` | `instalar_todo_isa.sh` | Variant for https://isa.umh.es (DocumentRoot `/var/www/htdocs`; leaves the existing configuration alone) |
| | `index.html` | `index.html` | Entry portal; must be next to the scripts |
| | `install_all_guide.md` | `instrucciones_instalar_todo.md` | Guide for `install_all.sh` |
| | `install_all_isa_guide.md` | `instrucciones_instalar_todo_isa.md` | Guide for `install_all_isa.sh` |
| | `apache_docroot.md` | `apache_docroot_htdocs.md` | Why `/rafa/` gives 404 if Apache serves another DocumentRoot |

`install_all*.sh` supersede the scripts in `clone-update/`.

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

Files created by the scripts are renamed too: `.selection`, `.install_all`, `install_all.log`, `/var/backups/install-all-<date>/`, `rafa-entry.conf`. Names that belong to the repos themselves (`telemetcolector`, `telemethistorial`, `datos/`, `ruta_json`, `apps/moda`, `apps/telemetria`…) are unchanged.

## Quick start

```bash
cd install-all
chmod +x install_all.sh install_all_isa.sh
./install_all.sh -h        # local server
./install_all_isa.sh -h    # isa.umh.es
```

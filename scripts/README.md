# scripts

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Scripts para clonar los repos públicos de `RafaUMH2110`, desplegar sus apps web en Apache y, opcionalmente, instalar el colector de telemetría.

## Contenido

| Carpeta | Fichero | Para qué sirve |
|---|---|---|
| `clonar-actualizar/` | `actualizar-repos.sh` | Clona o actualiza los repos públicos (primera versión) |
| | `desplegar-apache.sh` | Copia las apps HTML al directorio de Apache (primera versión) |
| | `clonar-actualizar-repos.md` | Guía de las dos anteriores |
| `instalar-todo/` | `instalar-todo.sh` | Todo en uno para el servidor local (selección de repos, despliegue, colector, entrada `/rafa/`) |
| | `instalar-todo-isa.sh` | Variante para https://isa.umh.es (DocumentRoot `/var/www/htdocs`; no toca la configuración existente) |
| | `index.html`, `favicon.svg`, `favicon.ico`, `apple-touch-icon.png` | Portal de entrada y su favicon; deben estar junto a los scripts |
| | `instrucciones-instalar-todo.md` | Guía de `instalar-todo.sh` |
| | `instrucciones-instalar-todo-isa.md` | Guía de `instalar-todo-isa.sh` |
| | `apache-docroot-htdocs.md` | Por qué `/rafa/` da 404 si Apache sirve otro DocumentRoot |
| | `anteriores/instalar-todo-anterior.sh` | Versión previa de `instalar-todo.sh`, solo como histórico |
| `instalar-todo-telemetria/` | `instalar-todo.sh` | Versión reducida: clona **solo** `apps/telemetria` (clonado parcial), lo despliega en Apache y permite elegir instalar `telemet-colector` (`--colector` / `--sin-colector`). Su pareja inglesa instala `telemet-collector` |
| | `index.html`, `favicon.svg`, `favicon.ico`, `apple-touch-icon.png` | Portal de entrada (lista **todas** las apps clonadas, no solo las de telemetría) y su favicon; deben estar junto al script |
| | `instrucciones-instalar-todo.md` | Guía de `instalar-todo.sh` |
| `telemet-colector/` | `telemet_colector.py` | TeleMet Colector: lee de forma continua la estación meteorológica y guarda un histórico (24 h por defecto; `duracion_horas`, `--horas` o `TELEMET_HORAS`) en SQLite y como JSON para las apps TeleMet. Admite varias estaciones, cada una con su API Key (`[estacion:ID]`). |
| | `MANUAL.md`, `README.md` | Manual detallado (instalación, configuración y funcionamiento) y guía rápida |
| | `config.example.ini`, `telemet-colector.service` | Plantilla de configuración y servicio systemd |
| `telemet-collector-info/` | `telemet-collector-info.py` | `telemet-collector-info.py` (en el servidor): muestra todos los parámetros de TeleMet Collector (estaciones, API Key enmascarada, rutas, estado de BD y JSON, servicio systemd y diagnóstico). Independiente y de solo lectura |
| | `telemet-collector-info-ssh.py` | Versión para ejecutar en tu ordenador (CLI o VS Code): se conecta por SSH (contraseña o clave RSA) y muestra el informe de uno o varios servidores sin instalar nada en ellos |
| | `MANUAL.md`, `README.md`, `vscode-ejemplo/` | Manual detallado, resumen y ejemplos de `launch.json` / `tasks.json` |
| `mover-repo/` | `instrucciones-mover-repo.md` | Guía para mover un repo de GitHub a una subcarpeta de otro conservando el historial |

Los scripts `instalar-todo*.sh` sustituyen a los de `clonar-actualizar/`.

## Uso rápido

```bash
cd instalar-todo
chmod +x instalar-todo.sh instalar-todo-isa.sh
./instalar-todo.sh -h        # servidor local
./instalar-todo-isa.sh -h    # isa.umh.es
```

## English version

See [`en/`](en/README.md) for the English versions of all the scripts and guides.

# code — normas para trabajar en este repositorio

Ejemplos de código y apps de escritorio en Python (macOS, Windows, Linux), más herramientas de apoyo. Idioma de trabajo: español. Estructura y reglas completas en el [README](README.md).

## Antes de tocar nada
- Trabaja en una rama (`feat/…`, `fix/…`, `docs/…`) y abre un PR; no hagas force-push a `main`.
- **No renombres ni muevas** `macos/`, `windows/`, `linux/` ni las carpetas de `scripts/`: los instaladores (`scripts/instalar-todo*`), los manuales y los repos de `RafaUMH2110` enlazan a esas rutas.
- **El colector TeleMet no está aquí.** Su única fuente es el repo `apps` (`telemetria/telemetcolector` y `telemetcollector`). No lo copies a este repo.
- Nombres de directorio en minúsculas y con guiones; los módulos Python conservan `_`.
- Una app que cambia según el sistema va en `macos/`, `windows/` y `linux/`; si es idéntica en los tres, una sola vez en la raíz (`generador-apps/`). Cada app es autocontenida: no se comparten ficheros entre apps.

## Al editar
- Las claves de API no van en el código: variables de entorno o `.env` local (ya excluido por `.gitignore`; solo se versiona `.env.example`).
- Los `.vscode/` de cada app **sí** se versionan.
- Si cambias una app, actualiza su manual y la tabla de apps del README.
- Antes de subir un cambio grande: `python3 scripts/mantenimiento-repos/auditar-repos.py` (ver su [README](scripts/mantenimiento-repos/README.md)).

## Commits
- Mensajes en español. Termina los commits de Claude Code con las líneas de atribución que indique la sesión (`Co-Authored-By` y `Claude-Session`).
- No commitees `__pycache__`, claves, `config.ini` ni bases de datos.

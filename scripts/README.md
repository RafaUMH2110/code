# scripts

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Scripts para clonar los repos públicos de `RafaUMH2110`, desplegar sus apps web en Apache y, opcionalmente, instalar el colector de telemetría.

## Contenido

| Carpeta | Fichero | Para qué sirve |
|---|---|---|
| `instalar-todo/` | `instalar-todo.sh` | Todo en uno para el servidor local (selección de repos, despliegue, colector, entrada `/rafa/`) |
| | `instalar-todo-isa.sh` | Variante para https://isa.umh.es (DocumentRoot `/var/www/htdocs`; no toca la configuración existente) |
| | `index.html`, `favicon.svg`, `favicon.ico`, `apple-touch-icon.png` | Portal de entrada y su favicon; deben estar junto a los scripts |
| | `instrucciones-instalar-todo.md` | Guía de `instalar-todo.sh` |
| | `instrucciones-instalar-todo-isa.md` | Guía de `instalar-todo-isa.sh` |
| | `apache-docroot-htdocs.md` | Por qué `/rafa/` da 404 si Apache sirve otro DocumentRoot |
| `instalar-todo-telemetria/` | `instalar-todo.sh` | Versión reducida: clona **solo** `apps/telemetria` (clonado parcial), lo despliega en Apache y permite elegir instalar `telemet-colector` (`--colector` / `--sin-colector`). Su pareja inglesa instala `telemet-collector` |
| | `index.html`, `favicon.svg`, `favicon.ico`, `apple-touch-icon.png` | Portal de entrada (lista **todas** las apps clonadas, no solo las de telemetría) y su favicon; deben estar junto al script |
| | `instrucciones-instalar-todo.md` | Guía de `instalar-todo.sh` |
| `telemet-colector/` | *(movido)* | TeleMet Colector ya **no está en este repositorio**: su única fuente es [`RafaUMH2110/apps`](https://github.com/RafaUMH2110/apps/tree/main/telemetria/telemetcolector) (`telemetria/telemetcolector/` en español, `telemetcollector/` en inglés), de donde lo instalan los scripts `instalar-todo*.sh`. |
| `telemet-collector-info/` | `telemet-collector-info.py` | `telemet-collector-info.py` (en el servidor): muestra todos los parámetros de TeleMet Collector (estaciones, API Key enmascarada, rutas, estado de BD y JSON, servicio systemd y diagnóstico). Independiente y de solo lectura |
| | `telemet-collector-info-ssh.py` | Versión para ejecutar en tu ordenador (CLI o VS Code): se conecta por SSH (contraseña o clave RSA) y muestra el informe de uno o varios servidores sin instalar nada en ellos. Con `--check-key` / `--install-key` / `--generate-key` valida o instala el acceso por `authorized_keys` |
| | `MANUAL.md`, `README.md`, `vscode-ejemplo/` | Manual detallado, resumen y ejemplos de `launch.json` / `tasks.json` |
| `mantenimiento-repos/` | `auditar-repos.sh` | Revisa los repos de `RafaUMH2110` (secretos, ramas sin integrar, ficheros grandes y duplicados, workflows, enlaces rotos) sin modificar nada. Ver su README y el artifact de mantenimiento |
| | `README.md` | Guía de uso y de la rutina de mantenimiento |
| `mover-repo/` | `instrucciones-mover-repo.md` | Guía para mover un repo de GitHub a una subcarpeta de otro conservando el historial |

Los scripts `instalar-todo*.sh` sustituyeron a los de la antigua carpeta `clonar-actualizar/`, que ya no existe (siguen en el historial de Git).

## Uso rápido

```bash
cd instalar-todo
chmod +x instalar-todo.sh instalar-todo-isa.sh
./instalar-todo.sh -h        # servidor local
./instalar-todo-isa.sh -h    # isa.umh.es
```

## English version

See [`en/`](en/README.md) for the English versions of all the scripts and guides.

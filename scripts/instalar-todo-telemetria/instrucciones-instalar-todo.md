# instalar-todo.sh (solo telemetría)

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Versión reducida de `instalar-todo` para Debian 13: trabaja **solo** con las apps de telemetría y deja elegir qué colector se instala.

## Qué hace

1. Instala dependencias (`apache2`, `git`, `curl`, `jq`, `rsync`, `python3`).
2. Clona o actualiza **solo** la carpeta `telemetria/` del repo `RafaUMH2110/apps` (clonado parcial: `--filter=blob:none` + `sparse-checkout`). Esa carpeta incluye los dos colectores: `telemetcolector` (español) y `telemetcollector` (inglés).
3. Despliega en Apache los ficheros web **solo de `telemetria/`** (`<destino>/apps/telemetria/`), genera `apps.json` e instala el portal `index.html` con su favicon (deben estar junto al script).
4. **A elegir**: instala `telemet-colector` (versión española) como servicio systemd. La versión inglesa, `telemet-collector`, la instala `install-all.sh` (carpeta `en/install-all-telemetry/`).
5. Fija la entrada del servidor en `http://<IP>/rafa/`.
6. Comprueba el resultado y, si se pide, programa la tarea en cron.

Es idempotente: se puede ejecutar de nuevo para actualizar.

## Uso

```bash
chmod +x instalar-todo.sh
./instalar-todo.sh -h
./instalar-todo.sh --colector          # apps + telemet-colector
./instalar-todo.sh --sin-colector      # solo las apps
./instalar-todo.sh                     # pregunta si hay terminal; si no, no instala el colector
```

Credenciales del colector: variables `TELEMET_STATION_ID` y `TELEMET_API_KEY`, o se piden por terminal. Sin ellas el servicio queda preparado pero sin arrancar.

## Opciones

| Opción | Efecto |
|---|---|
| `-u USUARIO` | Cuenta de GitHub (def. `RafaUMH2110`) |
| `-o ORIGEN` | Dónde se clona (def. `~/RafaUMH2110-telemetria`) |
| `-d DESTINO` | Directorio de Apache para las apps (def. `<docroot>/rafa`) |
| `--docroot DIR` | DocumentRoot de Apache (def. `/var/www/html`) |
| `--forzar` | No pedir confirmación si el destino tiene contenido ajeno |
| `--modo web\|html\|todo` | Qué se publica (def. `web`); `--solo-html` es alias de `--modo html` |
| `--sin-indice` | No instalar el portal `index.html` |
| `--colector` / `--sin-colector` | Instalar o no `telemet-colector` |
| `--cron "EXPR"` | Programa la tarea en cron, p. ej. `"0 3 * * *"` |

## Página de entrada

- El portal lista **todas las apps clonadas y desplegadas**, no solo las de telemetría: si en el mismo destino hay apps de otros repos o de otras carpetas de `apps/` (por ejemplo, las que dejó el `instalar-todo.sh` completo), siguen apareciendo.
- Para ello, al generar `apps.json` el script recorre **todo el destino** y busca los clones en la carpeta de origen (`-o`) y en las carpetas vecinas del mismo usuario (`~/RafaUMH2110`, `~/RafaUMH2110-telemetria`…): de ahí salen el README, el resumen y la fecha de cada app.
- El espejo (`rsync --delete`) se hace **solo sobre `apps/telemetria/`**: lo demás que haya en el destino no se borra ni se toca.
- Junto al portal se copian `favicon.svg`, `favicon.ico` y `apple-touch-icon.png` (icono de la pestaña del navegador, marcadores e iOS).

## Notas

- Los ficheros del propio script usan guiones (`instalar-todo.sh`, marca `.instalar-todo`); los ficheros del programa del colector conservan los nombres del repo (`telemet_colector.py`, `config.ini`).
- El histórico (`datos/`) no se borra al actualizar.
- El colector escribe `historial.json` dentro de la app `telemet/historial/datos/` y se añade una configuración de Apache sin caché para ese fichero.

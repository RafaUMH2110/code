# Instrucciones de uso de `instalar_todo.sh`

Despliegue de las aplicaciones de la cuenta GitHub **RafaUMH2110** en un servidor local **Debian 13** (`192.168.0.129`) con Apache, portal de entrada y colector de telemetría opcional.

Autor: Rafael Puerto · Departamento de Ingeniería de Sistemas y Automática · UMH · r.puerto@umh.es
_Generado con IA · Revisado por el autor_ · Última modificación: 06/11/2026 20:45

---

## Índice

1. [Qué hace](#1-qué-hace)
2. [Ficheros y requisitos](#2-ficheros-y-requisitos)
3. [Puesta en marcha rápida](#3-puesta-en-marcha-rápida)
4. [Referencia de opciones](#4-referencia-de-opciones)
5. [Elegir qué se clona](#5-elegir-qué-se-clona)
6. [Qué se publica en Apache (modos)](#6-qué-se-publica-en-apache-modos)
7. [El portal de entrada](#7-el-portal-de-entrada)
8. [Colector de telemetría](#8-colector-de-telemetría)
9. [Entrada del servidor (`/rafa/`)](#9-entrada-del-servidor-rafa)
10. [Actualización automática con cron](#10-actualización-automática-con-cron)
11. [Dónde queda cada cosa](#11-dónde-queda-cada-cosa)
12. [Comprobaciones](#12-comprobaciones)
13. [Solución de problemas](#13-solución-de-problemas)
14. [Revertir y desinstalar](#14-revertir-y-desinstalar)
15. [Seguridad](#15-seguridad)

---

## 1. Qué hace

El script es **idempotente**: se puede ejecutar tantas veces como se quiera y deja el servidor en el mismo estado final. Cada ejecución recorre seis pasos:

| Paso | Acción |
|---|---|
| 1/6 | Instala lo que falte: `apache2`, `git`, `curl`, `jq`, `rsync`, `python3`. |
| 2/6 | Decide qué repos clonar (todos, una lista o un menú) y los **clona o actualiza** (`git pull --ff-only`). Admite clonar solo algunas carpetas de un repo. |
| 3/6 | **Despliega en Apache** solo los ficheros web, genera el catálogo `apps.json` e instala el portal `index.html`. |
| 4/6 | _(Opcional, `--colector`)_ Instala el colector de telemetría como servicio systemd. |
| 5/6 | Fija la entrada del servidor: `http://<IP>/` redirige a `http://<IP>/rafa/`. |
| 6/6 | Comprueba con `curl` que la entrada responde y, si se pidió, programa cron. |

Solo se clonan los repos **públicos** de la cuenta; no hace falta token.

## 2. Ficheros y requisitos

Hacen falta **dos ficheros en la misma carpeta**:

| Fichero | Para qué sirve |
|---|---|
| `instalar_todo.sh` | El script. |
| `index.html` | Plantilla del portal que se publica en `/rafa/`. Si falta, el script genera un índice simple como alternativa. |

Requisitos del servidor:

- Debian 13 con acceso a Internet (HTTPS hacia `github.com` y `api.github.com`).
- Un usuario con `sudo` (o ejecutar como root). El script usa `sudo` solo para escribir en Apache, `/opt`, `/etc` y `/var`.
- Los paquetes del paso 1 se instalan solos.

## 3. Puesta en marcha rápida

```bash
# 1. Copiar al servidor (desde tu equipo)
scp instalar_todo.sh index.html usuario@192.168.0.129:~/

# 2. En el servidor
chmod +x instalar_todo.sh
./instalar_todo.sh
```

Con eso se clonan todos los repos públicos, se despliegan en `/var/www/html/rafa/` y la entrada queda en `http://192.168.0.129/rafa/`.

Combinaciones habituales:

```bash
./instalar_todo.sh -i                          # elegir con menú qué clonar
./instalar_todo.sh -i --colector               # elegir y, además, instalar el colector
./instalar_todo.sh --repos "apps/telemetria"   # solo la telemetría
./instalar_todo.sh --colector --cron "0 3 * * *"   # actualizar cada día a las 3:00
./instalar_todo.sh --listar                    # ver qué hay y qué está seleccionado
```

## 4. Referencia de opciones

### Origen y destino

| Opción | Valor por defecto | Descripción |
|---|---|---|
| `-u USUARIO` | `RafaUMH2110` | Cuenta de GitHub. |
| `-o ORIGEN` | `~/RafaUMH2110` | Carpeta donde se clonan los repos. |
| `-d DESTINO` | `<docroot>/rafa` | Carpeta de Apache donde se publican. Debe estar dentro del DocumentRoot; de ella se deduce la ruta web de la entrada. |
| `--docroot DIR` | `/var/www/html` | DocumentRoot de tu Apache. Úsalo si sirve otra carpeta, p. ej. `--docroot /var/www/htdocs` (el destino pasa a ser `/var/www/htdocs/rafa`). |
| `--forzar` | — | No pide confirmación cuando `DESTINO` ya tiene contenido que no creó el script (ver [sección 6](#6-qué-se-publica-en-apache-modos)). |

### Qué clonar

| Opción | Descripción |
|---|---|
| `-i`, `--interactivo` | Menú para elegir repos y, dentro de cada uno, carpetas. Guarda la selección. |
| `--repos LISTA` | Lista separada por comas; cada elemento es `repo` o `repo/carpeta`. Guarda la selección. |
| `--excluir LISTA` | Todos los repos públicos **menos** los indicados. Guarda la selección. |
| `--todos` | Borra la selección guardada: vuelve a clonar todo. |
| `--listar` | Muestra repos, carpetas y la selección actual (`[x]` = se clonará) y termina. No modifica nada. |

### Qué se publica

| Opción | Descripción |
|---|---|
| `--modo web` | (Por defecto) Solo ficheros web. Ver [sección 6](#6-qué-se-publica-en-apache-modos). |
| `--modo html` | Solo `*.html` y `*.htm` (alias antiguo: `--solo-html`). |
| `--modo todo` | Todo el contenido del repo, salvo `.git`, `.github` y secretos. |
| `--sin-indice` | No instala el portal `index.html`. El catálogo `apps.json` se genera siempre. |

### Telemetría y automatización

| Opción | Descripción |
|---|---|
| `--colector` | Instala el colector de telemetría como servicio. Ver [sección 8](#8-colector-de-telemetría). |
| `--cron "EXPR"` | Programa la ejecución periódica, p. ej. `--cron "0 3 * * *"`. |
| `-h`, `--help` | Muestra la ayuda. |

## 5. Elegir qué se clona

### 5.1 Menú interactivo (`-i`)

Muestra la lista de repos con su lenguaje y tamaño:

```
Repositorios públicos de RafaUMH2110:
   1) apps               HTML, 1446 KB
   2) apps-pro           HTML, 110 KB
   3) Artifacts          HTML, 817 KB
   4) code               Python, 309 KB
   5) IAC                HTML, 256 KB
Elige (números o rangos 1-3 separados por espacios; Enter = todos; n = ninguno):
```

- Escribe números separados por espacios (`1 4`), rangos (`1-3`) o una mezcla (`1 3-5`).
- **Enter** elige todos; **n** no elige ninguno.
- Para cada repo elegido que tenga carpetas, pregunta `¿todo el contenido (T) o elegir carpetas (c)? [T/c]`. Con `c` aparece un segundo menú con las carpetas de primer nivel (en `apps`: `moda`, `telemetria`, `consultar`…; en `code`: `linux`, `macos`, `windows`).
- Necesita una terminal (no funciona en cron ni con la entrada redirigida).

### 5.2 Por línea de comandos

```bash
# Solo estas carpetas y repos
./instalar_todo.sh --repos "apps/telemetria,apps/moda,code/linux,code/telemetria"

# Todo menos algunos repos
./instalar_todo.sh --excluir "apps-pro,Artifacts"

# Volver a todos
./instalar_todo.sh --todos
```

Los nombres de repo no distinguen mayúsculas de minúsculas. Un nombre que no exista en la cuenta se ignora con un aviso.

### 5.3 Selección guardada

Cada vez que usas `-i`, `--repos` o `--excluir`, la selección se guarda en `~/RafaUMH2110/.seleccion` (o `<ORIGEN>/.seleccion`) y **se reutiliza** en las siguientes ejecuciones, también las de cron. Es un fichero de texto, una entrada por línea:

```
apps/telemetria
apps/moda
code
-Artifacts
```

Reglas:

- Si hay líneas positivas (`repo` o `repo/carpeta`), **solo** se clonan esas.
- Una línea `-repo` excluye ese repo. Si solo hay líneas con `-`, se clonan todos menos esos.
- Si un repo aparece completo y también con carpetas, gana el repo completo.
- Una nueva selección **sustituye** a la anterior (no se suma).
- Puedes editar el fichero a mano.

### 5.4 Qué pasa al cambiar la selección

- **Carpetas parciales** (`repo/carpeta`): se usa _sparse checkout_ de git; solo se descargan y despliegan esas carpetas. Los ficheros de la raíz del repo (por ejemplo `README.md`) también se descargan.
- **De parcial a completo**: el script desactiva el sparse checkout y el repo se completa en la siguiente actualización.
- **Repos que dejas de seleccionar**: se **retiran del despliegue** en Apache (`/var/www/html/rafa/<repo>`) y desaparecen del portal. Su copia clonada se queda en `~/RafaUMH2110/` y no se borra.
- **`--listar`** no cambia nada: sirve para ver el estado antes de decidir.

> **Límite de la API de GitHub:** sin autenticar son 60 peticiones por hora y por IP. Una ejecución normal usa una; `-i` y `--listar` usan además una por repo (unas 7 en total con la cuenta actual).

## 6. Qué se publica en Apache (modos)

Por defecto el script **no copia a Apache todo el repo**, solo lo que un navegador necesita.

### Modo `web` (por defecto)

Se copian estas extensiones:

`html htm css js mjs json webmanifest svg png jpg jpeg gif webp avif ico bmp woff woff2 ttf otf eot mp3 mp4 webm ogg wav pdf xml csv`

Se excluyen siempre:

| Excluido | Motivo |
|---|---|
| `*.py`, `*.ini`, `*.service`, `*.md`, `*.sh`, etc. | No son contenido web (incluye el código del colector). |
| Carpetas y ficheros ocultos (`.vscode`, `.env`, `.git`, `.github`…) | Configuración interna. |
| `*.key`, `*.pem`, `*secret*`, `*credential*`, `config.ini` | Posibles secretos. |
| `package*.json`, `tsconfig*.json`, `*config*.json` | Ficheros de configuración de desarrollo. |
| `node_modules/` | Dependencias. |

Las carpetas que se quedan vacías no se publican.

### Modo `html`

Solo `*.html` y `*.htm`. Es el más limpio, pero **no copia imágenes ni iconos** (por ejemplo, los `apple-touch-icon.png` de las apps de telemetría).

### Modo `todo`

Copia todo el repo menos `.git`, `.github`, `.gitignore`, `.env*`, claves y `config.ini`. Úsalo si alguna app necesita ficheros que el modo `web` excluye.

### Si `DESTINO` ya tiene contenido tuyo

Si la carpeta de destino **ya existe y tiene ficheros que no creó este script** (por ejemplo, una raíz web que ya usabas), la primera vez el script:

1. Lista lo que hay y **pide confirmación** (`¿Continuar? [s/N]`). Sin terminal, como en cron, **se detiene** salvo que uses `--forzar`.
2. Guarda en `/var/backups/instalar-todo-<fecha>/` una copia de lo que sustituya o borre: el `index.html` y `apps.json` anteriores y cualquier fichero que el espejo de un repo reemplace o elimine.
3. Marca la carpeta con el fichero oculto `.instalar_todo`; desde entonces no vuelve a preguntar.

Solo se tocan `index.html`, `apps.json` y las carpetas con nombre de repo seleccionado. Cualquier otra carpeta o fichero de `DESTINO` (por ejemplo, `GenImOd/` o `vacio/`) se deja como está. Si ya tenías una carpeta con el mismo nombre que un repo (por ejemplo, `apps/`), su contenido se sustituye por el del repo: revisa la lista antes de aceptar.

### Notas

- El despliegue es un **espejo**: lo que borres o cambies en el repo se refleja en Apache, y cualquier fichero que añadas a mano dentro de `/var/www/html/rafa/<repo>/` se borra en la siguiente ejecución.
- Hay una excepción: las carpetas llamadas **`datos/`** están protegidas, porque ahí escribe el colector de telemetría.
- Los permisos finales son propietario `www-data`, 755 en carpetas y 644 en ficheros, solo sobre lo que gestiona el script.

## 7. El portal de entrada

`index.html` es una página estática que lee el catálogo `apps.json` y muestra una ficha por aplicación.

- **Categorías:** en el repo `apps`, la primera carpeta es la categoría (`moda`, `telemetria`, `consultar`…) y cada una forma una sección. Los demás repos forman una sección cada uno.
- **Fichas:** muestran el título del HTML, su descripción (`<meta description>` o, si no hay, el resumen del README más cercano), el proyecto, el sistema operativo (en `code`: Linux/macOS/Windows), el tamaño y la fecha del último commit. Las versiones `pro`, `lite`, etc. se muestran como una insignia junto al nombre de la app.
- **Búsqueda y filtros:** el cuadro de búsqueda (atajo `/`) y los botones de categoría filtran en el momento.
- **Tema:** claro u oscuro según el sistema.
- **Catálogo:** `apps.json` se regenera en cada ejecución del script. Si abres el `index.html` directamente desde el disco (`file://`) o sin `apps.json` al lado, aparece el aviso «No se pudo cargar el catálogo».

Para cambiar el diseño, edita `index.html` junto al script y vuelve a ejecutarlo. Para cambiar solo la página sin tocar los repos:

```bash
sudo install -m 644 index.html /var/www/html/rafa/index.html
```

Las descripciones de las apps conocidas (GenImOd, GenOutFit, GenPatMod…) están en el diccionario `INFO` dentro del `index.html`, y los nombres de categoría con tilde en el diccionario `CAT`.

## 8. Colector de telemetría

El repo `apps` contiene en `telemetria/telemetcolector/` un programa en Python que lee tu estación meteorológica (Weather Underground) cada 5 minutos, guarda las últimas 12 horas en SQLite y exporta un `historial.json` que usa la app **TeleMet Historial**. **No es una página web**: es un servicio que debe estar en marcha en el servidor. Solo usa la biblioteca estándar de Python.

### 8.1 Instalación

```bash
# Con menú de credenciales (te pide Station ID y API Key)
./instalar_todo.sh --repos "apps/telemetria" --colector

# Sin que las pida (variables de entorno)
read -rp "Station ID: " TELEMET_STATION_ID
read -rsp "API Key: " TELEMET_API_KEY; echo
export TELEMET_STATION_ID TELEMET_API_KEY
./instalar_todo.sh --repos "apps/telemetria" --colector
```

Requisito: el repo `apps` con la carpeta `telemetria` debe estar en la selección (si no, el script avisa de que no encuentra `telemetcolector`).

> Escribir la clave en la línea de comandos (`TELEMET_API_KEY=xxx ./instalar_todo.sh …`) la deja en el historial del shell. Es preferible el formato anterior o dejar que el script la pida.

### 8.2 Qué hace el script con `--colector`

| Elemento | Ubicación |
|---|---|
| Usuario de servicio (sin shell) | `telemet` |
| Programa y configuración | `/opt/telemet-colector/` (`telemet_colector.py`, `config.ini`, `config.example.ini`) |
| Base de datos | `/opt/telemet-colector/datos/telemet.sqlite` |
| Servicio systemd | `/etc/systemd/system/telemet-colector.service` |
| JSON publicado | junto a la app Historial: `/var/www/html/rafa/apps/telemetria/telemet/historial/datos/historial.json` |
| Cabecera anti-caché del JSON | `/etc/apache2/conf-available/telemet-historial.conf` |

- El servicio se genera a partir del `.service` del repo, con la carpeta del JSON adaptada a este servidor.
- `config.ini` se crea desde la plantilla **solo si no existe**: al volver a ejecutar el script no se pisan tus credenciales. Siempre se actualiza el programa `telemet_colector.py`.
- `config.ini` queda con permisos `600` y propiedad de `telemet`.
- La carpeta `datos/` donde se escribe el JSON conserva el propietario `telemet`, aunque se vuelva a desplegar.
- El JSON se puede ver en `http://192.168.0.129/rafa/apps/telemetria/telemet/historial/datos/historial.json`.

### 8.3 Con y sin credenciales

- **Con credenciales** (variables de entorno o respuestas al menú): se escriben en `config.ini`, se activa el servicio al arranque y se (re)inicia.
- **Sin credenciales**: el servicio queda instalado pero **sin arrancar**, y el script muestra qué hacer:

```bash
sudo nano /opt/telemet-colector/config.ini        # editar station_id y api_key
sudo -u telemet python3 /opt/telemet-colector/telemet_colector.py \
     -c /opt/telemet-colector/config.ini --probar # una lectura de prueba, sin guardar
sudo systemctl enable --now telemet-colector
```

### 8.4 Manejo del servicio

```bash
systemctl status telemet-colector                 # estado
journalctl -u telemet-colector -f                 # log en vivo
sudo systemctl restart telemet-colector           # tras editar config.ini

# Utilidades del programa
sudo -u telemet python3 /opt/telemet-colector/telemet_colector.py -c /opt/telemet-colector/config.ini --estado
sudo -u telemet python3 /opt/telemet-colector/telemet_colector.py -c /opt/telemet-colector/config.ini --una-vez
```

Parámetros útiles de `config.ini`: `intervalo_s` (por defecto 300; con 288 llamadas diarias, bajarlo consume más cuota de tu API Key), `duracion_horas` (12) y `modo` (`deslizante` o `reinicio`).

### 8.5 Detalles a tener en cuenta

- La app TeleMet Historial solo usa el JSON si su **Station ID** coincide con el del colector (sin distinguir mayúsculas).
- Si todavía no hay JSON, la app funciona igual, sin el histórico del servidor.
- La app avisa si la última lectura del servidor tiene más de 15 minutos.
- Si la app Historial no está desplegada, el JSON se publica en `/var/www/html/rafa/telemethistorial/datos/`.
- En un sistema sin systemd activo (contenedores) el servicio se instala pero no arranca.

## 9. Entrada del servidor (`/rafa/`)

En el paso 5 el script deja `http://192.168.0.129/` redirigiendo a `http://192.168.0.129/rafa/`:

1. Crea `/etc/apache2/conf-available/entrada-rafa.conf` con `RedirectMatch ^/$ /rafa/` y lo activa. La redirección es relativa, así que sirve igual con `localhost`, la IP o un nombre de equipo.
2. **Anula cualquier configuración antigua que llevara a `/moda/`**: comenta las líneas `Redirect`, `RedirectMatch`, `RewriteRule` que mencionen `moda` y los `DocumentRoot` que terminen en `moda`, tanto en `/etc/apache2` como en `/var/www/html/.htaccess`. Si el `index.html` de la raíz apuntaba a `moda`, lo sustituye por una redirección.
3. Antes de tocar nada hace una **copia de seguridad** en `/var/backups/entrada-apache-<fecha>/`.
4. Comprueba la configuración con `apache2ctl configtest`. Si falla, **restaura la copia** y deshace los cambios.
5. Si después quedan referencias a `moda` que no pudo anular (un `Alias`, un `<Directory>`…), las lista como aviso al final.

Si cambias el destino (`-d /var/www/html/apps`), la entrada pasa a ser `/apps/`.

## 10. Actualización automática con cron

```bash
./instalar_todo.sh --cron "0 3 * * *"                 # diaria, a las 3:00
./instalar_todo.sh --colector --cron "30 2 * * 1"     # semanal, lunes a las 2:30
```

- El script añade una línea a tu `crontab` y sustituye la anterior del mismo script (no se duplican).
- Cron usa la **selección guardada** y repite las opciones `-o`, `-d`, `--modo`, `--sin-indice` y `--colector`.
- En cron no hay terminal: no se piden credenciales (se conservan las del `config.ini`) y no puede usarse `-i`.
- Para revisarlo o quitarlo: `crontab -l` y `crontab -e`.
- Para ver qué pasó: `tail -n 40 ~/RafaUMH2110/instalar_todo.log`.

> `crontab` debe ser el del mismo usuario que ejecuta el script; los pasos que necesitan privilegios usan `sudo`, que en cron requiere `NOPASSWD` o ejecutar como root (`sudo crontab -e`).

## 11. Dónde queda cada cosa

```
~/RafaUMH2110/                        ← ORIGEN (clones)
├── apps/  code/ …       ← un directorio por repo seleccionado
├── .seleccion                        ← selección guardada
└── instalar_todo.log                 ← registro de todas las ejecuciones

/var/www/html/                        ← DocumentRoot de Apache
└── rafa/                             ← DESTINO
    ├── index.html                    ← portal
    ├── apps.json                     ← catálogo que lee el portal
    ├── apps/moda/…  apps/telemetria/…  ← una carpeta por repo, estructura original
    └── apps/telemetria/telemet/historial/datos/historial.json   ← lo escribe el colector

/opt/telemet-colector/                ← colector (si se usó --colector)
/etc/systemd/system/telemet-colector.service
/etc/apache2/conf-available/entrada-rafa.conf
/etc/apache2/conf-available/telemet-historial.conf
/var/backups/entrada-apache-<fecha>/  ← copia de seguridad previa a tocar Apache
```

URLs resultantes (con la IP `192.168.0.129`):

| URL | Contenido |
|---|---|
| `http://192.168.0.129/` | Redirige a `/rafa/`. |
| `http://192.168.0.129/rafa/` | Portal. |
| `http://192.168.0.129/rafa/<repo>/<ruta>/index.html` | Cada app, p. ej. `…/rafa/apps/moda/genimod/pro/index.html`. |

## 12. Comprobaciones

```bash
# Entrada y portal
curl -sI http://192.168.0.129/      | head -3     # 302 con Location: /rafa/
curl -sI http://192.168.0.129/rafa/ | head -1     # 200

# Catálogo: número de apps y categorías
jq '.apps | length' /var/www/html/rafa/apps.json
jq -r '.apps[].path' /var/www/html/rafa/apps.json | cut -d/ -f1 | sort | uniq -c

# Selección y estado
./instalar_todo.sh --listar
cat ~/RafaUMH2110/.seleccion

# Apache
sudo apache2ctl configtest
systemctl status apache2

# Colector
systemctl status telemet-colector
curl -s http://192.168.0.129/rafa/apps/telemetria/telemet/historial/datos/historial.json | head -c 300
```

### Información de cada actualización

En cada ejecución el log (pantalla y `instalar_todo.log`) detalla qué ha cambiado:

```
Actualizado: apps  [carpetas: telemetria]  ·  +4 commits  ·  ficheros: 1 (0 nuevos, 1 modificados, 0 borrados)  ·  líneas +33/-12  ·  descarga ≈ 4.0 KB
      ~ telemetria/telemet/multi/index.html
Sin cambios: code  [carpetas: linux]
Resumen git -> commits: 4 | ficheros: +0 ~1 -0 | líneas: +33/-12 | descarga ≈ 4.0 KB
Desplegado: apps  ·  0 nuevos  ·  1 modificados  ·  0 borrados  ·  transferido 191.4 KB
Resumen despliegue -> nuevos: 0 | modificados: 1 | borrados: 0 | transferido 191.4 KB
```

- **Paso 2 (git), por repo:** commits nuevos, ficheros añadidos/modificados/borrados (solo de las carpetas seleccionadas si el clon es parcial), líneas añadidas y borradas, y la descarga aproximada (crecimiento de `.git`). Un repo nuevo muestra el número de ficheros y la descarga. Si no hay nada nuevo: `Sin cambios`.
- **Paso 3 (Apache), por repo:** ficheros nuevos, modificados y borrados en el despliegue y los bytes transferidos. Debajo se listan los primeros 6 ficheros (`+` nuevo, `~` modificado, `-` borrado) y `… (+N)` si hay más.
- **Resúmenes:** una línea al final de cada paso con los totales, y la línea final con la duración total.
- Los ficheros «modificados» del despliegue incluyen los que solo cambian de fecha o permisos.

Al terminar, el script imprime una línea final con la entrada, el número de errores y la ruta de la copia de seguridad:

```
FIN. Entrada: http://192.168.0.129/rafa/  |  Errores: 0  |  Duración: 12s  |  Copia de seguridad: /var/backups/entrada-apache-…
```

El código de salida es `0` si no hubo errores.

## 13. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ERROR: … tiene contenido ajeno y no hay terminal para confirmar` | `DESTINO` ya tenía contenido y el script se ejecutó sin terminal (cron, tubería). | Revisarlo y ejecutar una vez a mano (o con `--forzar`). |
| `AVISO: la carpeta del JSON del colector no existe` | `/opt/telemet-colector/config.ini` apunta en `ruta_json` a una carpeta que no existe (p. ej. la ruta por defecto). | Es solo un aviso. Corrige `ruta_json` en `config.ini`, o ejecuta con `--colector` para que se ajuste a la app Historial desplegada. |
| `El destino debe estar dentro de /var/www/html` | Tu Apache sirve otra carpeta. | Usar `--docroot` (p. ej. `--docroot /var/www/htdocs`). |
| `ERROR: fallo al consultar la API de GitHub` | Límite de 60 peticiones/hora o sin red. | Esperar una hora; comprobar `curl -I https://api.github.com`. |
| `ERROR actualizando: <repo>` | Cambios locales o historia reescrita en el remoto (`pull --ff-only` falla). | `git -C ~/RafaUMH2110/<repo> status`; si no hay nada que conservar: `git -C … fetch && git -C … reset --hard origin/main`. |
| `AVISO: '<x>' no es un repo público…` | Nombre mal escrito o repo privado. | Revisar con `--listar`. |
| `ERROR configurando carpetas de <repo>` | La carpeta no existe en el repo. | Comprobar el nombre con `--listar` o `-i`. |
| El portal muestra «No se pudo cargar el catálogo» | Falta `apps.json` o se abrió el HTML desde el disco. | Ejecutar el script y abrir `http://IP/rafa/`. |
| Una app no se ve o le faltan imágenes/ficheros | El modo `web` o `html` excluye ese tipo de fichero. | Usar `--modo todo`. |
| `ERROR en la configuración de Apache: restaurando…` | Fallo de `configtest` tras los cambios. | Se restaura solo; mira el detalle en `instalar_todo.log` y ejecuta `sudo apache2ctl configtest`. |
| `/` no redirige a `/rafa/` | Otra regla anterior (`.htaccess`, `DirectoryIndex`, otro VirtualHost). | Revisar los avisos finales; `sudo grep -rni "moda" /etc/apache2 /var/www/html/.htaccess`. |
| Aviso «quedan referencias a 'moda'» | Un `Alias` o `<Directory>` que el script no toca. | Editar a mano esa línea. |
| `telemet-colector` no arranca | Faltan credenciales o la carpeta del JSON no es escribible. | `journalctl -u telemet-colector -e`; revisar `config.ini` y que `datos/` sea de `telemet`. |
| `HTTP 401` en el log del colector | API Key incorrecta o caducada. | Corregirla en `config.ini` y `sudo systemctl restart telemet-colector`. |
| La app Historial dice que el histórico es de otra estación | El Station ID de la app no coincide con el del colector. | Igualarlos. |
| El JSON da 404 | La app Historial no está desplegada en la ruta esperada. | Comprobar la ruta `ruta_json` en `/opt/telemet-colector/config.ini` y que apunte junto a la app. |
| `Permission denied` al ejecutar | Falta `sudo` o permisos de ejecución. | `chmod +x instalar_todo.sh`; usar un usuario con `sudo`. |
| Cron no hace nada | Ruta relativa, `sudo` con contraseña o `crontab` de otro usuario. | Usar rutas absolutas, `NOPASSWD` o `sudo crontab -e`; revisar `instalar_todo.log`. |

## 14. Revertir y desinstalar

**Quitar la redirección de la entrada**

```bash
sudo a2disconf entrada-rafa && sudo systemctl reload apache2
# Restaurar ficheros previos: copiar desde /var/backups/entrada-apache-<fecha>/
```

**Quitar el portal y las apps publicadas** (los clones se conservan)

```bash
sudo rm -rf /var/www/html/rafa
```

**Quitar el colector**

```bash
sudo systemctl disable --now telemet-colector
sudo rm /etc/systemd/system/telemet-colector.service && sudo systemctl daemon-reload
sudo a2disconf telemet-historial && sudo systemctl reload apache2
sudo rm -rf /opt/telemet-colector          # borra también la base SQLite y config.ini
sudo userdel telemet
```

**Quitar la tarea de cron**: `crontab -e` y eliminar la línea de `instalar_todo.sh`.

**Borrar los clones**: `rm -rf ~/RafaUMH2110`.

## 15. Seguridad

- El modo `web` no publica `.py`, `.ini`, `.env`, claves ni ficheros `config*.json`, para que el código y la configuración no puedan descargarse desde Apache.
- `config.ini` del colector contiene la API Key: queda con permisos `600`, propiedad de `telemet`, y **no debe subirse a GitHub** (el repo ya lo ignora). La clave no aparece en el JSON exportado.
- El servicio del colector corre con un usuario sin shell, con `ProtectSystem=strict` y escritura solo en su carpeta de datos y en la del JSON.
- El script solo clona repos **públicos** y no usa tokens de GitHub.
- Las credenciales se pasan al fichero de configuración por entorno, no por la línea de comandos, para que no aparezcan en `ps`.
- Revisa que el servidor no esté expuesto a Internet si no es lo previsto: la redirección y las apps se sirven por HTTP sin autenticación.

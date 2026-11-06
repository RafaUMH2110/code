# Despliegue en https://isa.umh.es con `instalar_todo_isa.sh`

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
**Fecha:** 04/11/2026
*Generado con IA · Revisado por el autor*

---

## 1. Qué es

Variante del instalador `instalar_todo.sh` para el servidor de producción **https://isa.umh.es** (Debian 13), cuyo DocumentRoot de Apache es `/var/www/htdocs`. El contenido se publica en `/var/www/htdocs/rafa` y el portal queda en **https://isa.umh.es/rafa/**.

Diferencia de fondo: el servidor ya tiene configuración propia (`<Directory /var/www/htdocs/rafa>`, `Alias "/moda"`, `.htaccess` en `rafa/` y `rafa/moda/`). Esta variante **no la modifica**.

## 2. Diferencias respecto a la versión local

| Aspecto | Versión local | Versión isa.umh.es |
|---|---|---|
| DocumentRoot por defecto | `/var/www/html` | `/var/www/htdocs` |
| URL | IP del servidor | `https://isa.umh.es` (`--url`) |
| Reglas hacia `/moda` | Las anula (con copia) | **No las toca** |
| Portada del servidor (`/`) | Redirige a `/rafa/` | **Sin cambios**; solo con `--entrada-raiz` |
| `apache2.conf` / bloque `Directory` | — | Solo comprueba que existe y avisa si falta |
| Colector ya instalado | Reescribe ruta y servicio | **Conserva** `config.ini`, ruta del JSON y unidad systemd |
| Recarga de Apache | Siempre | Solo si añade configuración nueva (con `configtest` y reversión) |
| Comprobación final | `http://localhost` | `https://isa.umh.es` resuelto al propio servidor, con alternativa por `http://localhost` |

## 3. Requisitos

- Debian 13 con Apache ya funcionando para isa.umh.es.
- Usuario con `sudo`.
- En la misma carpeta que el script: `index.html` (el portal).
- Acceso a `api.github.com` y `github.com` (repos públicos de `RafaUMH2110`).

El script instala por sí mismo `git`, `curl`, `jq`, `rsync` y `python3` si faltan.

## 4. Uso

```bash
chmod +x instalar_todo_isa.sh

# Elegir qué clonar y desplegar
./instalar_todo_isa.sh --repos "apps/telemetria,apps/moda,code/linux"

# Menú interactivo
./instalar_todo_isa.sh -i

# Todo + colector de telemetría
./instalar_todo_isa.sh --todos --colector

# Ver repos y carpetas disponibles
./instalar_todo_isa.sh --listar
```

### Opciones propias de esta variante

| Opción | Efecto |
|---|---|
| `--url URL` | URL pública (def.: `https://isa.umh.es`) |
| `--docroot DIR` | DocumentRoot (def.: `/var/www/htdocs`) |
| `--entrada-raiz` | Además, `/` redirige a `/rafa/` (cambia la portada) |
| `--json-dir DIR` | Carpeta donde el colector publica `historial.json` |

El resto de opciones (`-u`, `-o`, `-d`, `--modo`, `--repos`, `--excluir`, `--todos`, `--listar`, `--sin-indice`, `--colector`, `--cron`, `--forzar`) funcionan igual que en la versión local; ver `instrucciones_instalar_todo.md`.

## 5. Primera ejecución en isa.umh.es

`/var/www/htdocs/rafa` ya tiene contenido (`.htaccess`, `moda/`, `telemethistorial/`…), así que el script:

1. Lista lo que hay y **pide confirmación** (`--forzar` la omite).
2. Crea una copia en `/var/backups/instalar-todo-<fecha>/` de lo que sustituya o borre.
3. Reemplaza `rafa/index.html` y `rafa/apps.json`.
4. Hace un espejo de cada repo seleccionado **solo dentro de `rafa/<repo>/`**.

No se modifican: `rafa/.htaccess`, `rafa/moda/`, `rafa/telemethistorial/datos/` ni `/var/www/htdocs/index.html`.

> **Atención:** si un repo se llama igual que una carpeta tuya (por ejemplo, un repo `moda`), su espejo borraría lo que no esté en el repositorio. Revisa la lista del aviso antes de confirmar.

## 6. Colector de telemetría (`--colector`)

- **Si ya existe** `/opt/telemet-colector/config.ini`: se conservan `station_id`, `api_key` y `ruta_json`.
- **Si el programa difiere:** se guarda `telemet_colector.py.bak-<fecha>` y se actualiza.
- **Si ya existe** `/etc/systemd/system/telemet-colector.service`: se respeta tal cual.
- **Si es instalación nueva:** crea el usuario `telemet`, la unidad systemd y la carpeta del JSON (`rafa/telemethistorial/datos` salvo `--json-dir`). Las credenciales se toman de `TELEMET_STATION_ID` y `TELEMET_API_KEY`, o se piden por terminal.
- Añade `conf-available/telemet-historial.conf` (cabecera `Cache-Control: no-store` para el JSON).

## 7. Actualización periódica

```bash
./instalar_todo_isa.sh --cron "0 3 * * *" --colector
```

La entrada de cron incluye `--docroot` y `--url`, y reutiliza la selección guardada en `<ORIGEN>/.seleccion`.

## 8. Verificación

```bash
curl -I https://isa.umh.es/rafa/
curl -I https://isa.umh.es/rafa/apps.json
curl -I https://isa.umh.es/moda/          # debe seguir igual que antes
sudo apache2ctl configtest
sudo systemctl status telemet-colector
```

El log de cada ejecución queda en `<ORIGEN>/instalar_todo.log`. Incluye, por repo y en total, commits, ficheros nuevos/modificados/borrados, líneas, descarga y bytes transferidos a Apache (ver «Información de cada actualización» en `instrucciones_instalar_todo.md`).

## 9. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| 403 en `/rafa/` | Falta `Require all granted` para `/var/www/htdocs/rafa`. El script avisa si no encuentra el bloque `Directory`. |
| 404 en `/rafa/` | Apache no sirve `/var/www/htdocs`. Comprueba `DocumentRoot` con `apache2ctl -S`. |
| `moda` dejó de funcionar | No debería ocurrir. Restaura lo que corresponda desde `/var/backups/instalar-todo-<fecha>/`. |
| Comprobación "por http://localhost" | El puerto 443 o el certificado no responden desde el propio servidor; no implica fallo en el exterior. |
| Colector sin arrancar | Faltan `station_id` y `api_key`: edita `/opt/telemet-colector/config.ini` y ejecuta `sudo systemctl enable --now telemet-colector`. |
| Error en `configtest` | El script desactiva lo que añadió (`a2disconf`) y se detiene. Revisa `sudo apache2ctl configtest`. |

## 10. Restaurar

```bash
ls /var/backups/instalar-todo-*/
sudo cp -a /var/backups/instalar-todo-<fecha>/index.html /var/www/htdocs/rafa/index.html
```

Para retirar la configuración que añadió el script:

```bash
sudo a2disconf telemet-historial entrada-rafa
sudo systemctl reload apache2
```

---
*Última modificación: 04/11/2026 02:25*

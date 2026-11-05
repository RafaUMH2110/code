# TeleMet Colector — Manual completo

Manual de instalación, uso, configuración y funcionamiento interno de **TeleMet Colector**, el programa en Python que mantiene en el servidor Linux un histórico de las últimas 24 horas (configurable) de la estación meteorológica y lo pone a disposición de la app **TeleMet Historial**.

- **Código:** `RafaUMH2110/apps` → `telemetria/telemetcolector/`
- **App asociada:** `telemetria/telemet/historial/index.html` (TeleMet Historial)
- **Versión del programa:** 1.0 · **Formato del JSON:** 1

---

## Índice

1. [Para qué sirve](#1-para-qué-sirve)
2. [Arquitectura y flujo de datos](#2-arquitectura-y-flujo-de-datos)
3. [Requisitos](#3-requisitos)
4. [Contenido del paquete](#4-contenido-del-paquete)
5. [Instalación paso a paso](#5-instalación-paso-a-paso)
6. [Primera puesta en marcha y pruebas](#6-primera-puesta-en-marcha-y-pruebas)
7. [Ejecución como servicio (systemd)](#7-ejecución-como-servicio-systemd)
8. [Instalar y conectar la app TeleMet Historial](#8-instalar-y-conectar-la-app-telemet-historial)
9. [Referencia de configuración (`config.ini`)](#9-referencia-de-configuración-configini)
10. [Referencia de línea de órdenes](#10-referencia-de-línea-de-órdenes)
11. [Cómo funciona por dentro](#11-cómo-funciona-por-dentro)
12. [Formato de los datos](#12-formato-de-los-datos)
13. [Cómo funciona la parte de la app](#13-cómo-funciona-la-parte-de-la-app)
14. [Operación diaria: logs, estado, copias, actualización](#14-operación-diaria-logs-estado-copias-actualización)
15. [Seguridad](#15-seguridad)
16. [Resolución de problemas](#16-resolución-de-problemas)
17. [Preguntas frecuentes](#17-preguntas-frecuentes)
18. [Desinstalación](#18-desinstalación)
19. [Apéndice: ejemplos](#19-apéndice-ejemplos)

---

## 1. Para qué sirve

TeleMet Historial dibuja gráficas de evolución de las últimas 12 o 24 horas (y de 7 días) a partir de las lecturas que **el propio navegador** ha ido guardando mientras la app estaba abierta. Si la app se cierra, el navegador se suspende (pestaña en segundo plano, iPad bloqueado…) o se abre desde un dispositivo nuevo, esas gráficas tienen huecos.

TeleMet Colector resuelve eso con un proceso que **no se detiene nunca** en el servidor:

1. Consulta la estación cada cierto tiempo (por defecto, **cada 5 minutos**).
2. Guarda cada lectura en una base de datos SQLite.
3. Conserva solo las **últimas 24 horas** (modo `deslizante`, por defecto; el número de horas es configurable con `duracion_horas`, `--horas` o `TELEMET_HORAS`) o, si se prefiere, **borra todo al cumplirse esas horas** y empieza de nuevo (modo `reinicio`).
4. Tras cada lectura publica el histórico en un fichero `historial.json` que sirve Apache.
5. La app, al abrirse, lee ese JSON y **añade a su base local las lecturas que le faltan**, de forma que las gráficas de 12 y de 24 horas no pierden información.

Todo es configurable desde un único fichero `config.ini`.

---

## 2. Arquitectura y flujo de datos

```
┌──────────────┐      HTTPS      ┌───────────────────────────┐
│  Estación    │ ──────────────► │ API Weather Underground / │
│  Vevor       │                 │ Earth Network (PWS)       │
└──────────────┘                 └─────────────┬─────────────┘
                                               │ GET .../observations/current
                                               ▼
                              ┌────────────────────────────────┐
                              │  telemet_colector.py (systemd) │
                              │   · lectura cada intervalo_s   │
                              │   · reintentos con backoff     │
                              │   · regla de duracion_horas    │
                              └───────┬─────────────────┬──────┘
                                      │                 │
                       INSERT OR IGNORE                 │ escritura atómica
                                      ▼                 ▼
                       ┌────────────────────┐   ┌──────────────────────────────┐
                       │ SQLite             │   │ historial.json               │
                       │ datos/telemet.sqlite│   │ (carpeta que sirve Apache)   │
                       └────────────────────┘   └──────────────┬───────────────┘
                                                               │ HTTP(S), mismo origen
                                                               ▼
                                              ┌────────────────────────────────┐
                                              │ Navegador: TeleMet Historial   │
                                              │  · IndexedDB (histórico local) │
                                              │  · fusión aditiva con el JSON  │
                                              │  · gráficas 12 h / 24 h / 7 d  │
                                              └────────────────────────────────┘
```

Puntos clave del diseño:

- **El colector y la app son independientes.** El colector no sabe nada de los navegadores; solo escribe un fichero. La app funciona igual sin colector (solo con lo que registra el navegador).
- **Sin puerto nuevo ni proxy.** Apache sirve el JSON como un fichero estático más. No hay que abrir puertos ni configurar CORS si la app y el JSON están en el mismo sitio.
- **Sin dependencias.** Solo biblioteca estándar de Python (`urllib`, `sqlite3`, `json`, `configparser`, `logging`…).
- **La API Key nunca sale del servidor.** El JSON contiene datos meteorológicos y el Station ID, pero no la clave.

---

## 3. Requisitos

| Requisito | Detalle |
|---|---|
| Sistema | Linux con systemd (probado el diseño para Debian/Ubuntu con Apache; vale cualquier distribución). |
| Python | 3.8 o superior. No requiere `pip`. Comprueba con `python3 --version`. |
| Red | Salida HTTPS (443) hacia `api.weather.com`. |
| Credenciales | **Station ID** y **API Key** de tu estación en Weather Underground / Earth Network. |
| Servidor web | Apache (u otro) sirviendo la carpeta donde estará la app. En el servidor de ejemplo: `/var/www/htdocs/rafa/`. |
| Permisos | Acceso `sudo` para crear el usuario de servicio, las carpetas y la unidad systemd. |

---

## 4. Contenido del paquete

```
telemetria/telemetcolector/
├── telemet_colector.py          ← el programa
├── config.example.ini           ← plantilla de configuración comentada
├── telemet-colector.service     ← unidad systemd
├── README.md                    ← guía rápida
├── MANUAL.md                    ← este manual
└── .gitignore                   ← evita subir config.ini, datos/ y logs a GitHub
```

Además, la app que consume los datos:

```
telemetria/telemet/historial/
├── index.html                   ← TeleMet Historial (ya incluye la lectura del JSON)
└── apple-touch-icon.png
```

---

## 5. Instalación paso a paso

Los comandos suponen un servidor Debian/Ubuntu. Sustituye las rutas si usas otras.

### 5.1. Obtener los ficheros

Desde GitHub (en tu equipo o en el servidor):

```bash
git clone https://github.com/RafaUMH2110/apps.git
cd apps/telemetria/telemetcolector
```

o copia al servidor la carpeta `telemet-colector/` del `.zip` descargado (por ejemplo con `scp -r`).

### 5.2. Crear el usuario de servicio y la carpeta del programa

Un usuario sin shell ni contraseña, dedicado solo a esto:

```bash
sudo useradd --system --home /opt/telemet-colector --shell /usr/sbin/nologin telemet
sudo mkdir -p /opt/telemet-colector/datos
sudo cp telemet_colector.py config.example.ini /opt/telemet-colector/
sudo cp config.example.ini /opt/telemet-colector/config.ini
sudo chown -R telemet:telemet /opt/telemet-colector
sudo chmod 600 /opt/telemet-colector/config.ini
```

> **Importante:** la carpeta `/opt/telemet-colector/datos` debe existir **antes** de arrancar el servicio. La unidad systemd la declara en `ReadWritePaths` y, si no existe, systemd no puede montar el entorno protegido y el servicio falla al iniciarse (error `status=226/NAMESPACE`).

### 5.3. Crear la carpeta donde se publica el JSON

Debe estar dentro de la carpeta que sirve Apache, junto a la app, y ser escribible por el usuario `telemet`:

```bash
sudo install -d -o telemet -g telemet -m 755 /var/www/htdocs/rafa/telemethistorial/datos
```

Apache solo necesita **leer**; el fichero se publica con permisos `644` automáticamente.

### 5.4. Editar la configuración

```bash
sudo -u telemet nano /opt/telemet-colector/config.ini
```

Como mínimo, rellena:

```ini
[estacion]
station_id = TU_STATION_ID
api_key    = TU_API_KEY
```

Y revisa `ruta_json` en la sección `[salida]` (debe apuntar a la carpeta del paso 5.3). El resto de parámetros tiene valores por defecto razonables; todos están explicados en la [sección 9](#9-referencia-de-configuración-configini).

> Alternativa para no dejar secretos en el `.ini`: usa variables de entorno `TELEMET_STATION_ID` y `TELEMET_API_KEY` (ver [sección 15](#15-seguridad)).

---

## 6. Primera puesta en marcha y pruebas

Haz estas pruebas **antes** de instalar el servicio, siempre como el usuario `telemet` para detectar problemas de permisos:

```bash
cd /opt/telemet-colector
```

### 6.1. Probar la conexión con la estación (no guarda nada)

```bash
sudo -u telemet python3 telemet_colector.py --probar
```

Salida esperada: la fecha de la observación y los valores en JSON, por ejemplo:

```
Observación de 2026-11-03 21:19:12
{
  "temp_c": 18.4,
  "heat_index_c": 18.4,
  "dewpoint_c": 11.2,
  "humidity_pct": 62,
  "pressure_hpa": 1015.3,
  "wind_kmh": 7.2,
  "gust_kmh": 12.9,
  "wind_dir_deg": 204,
  "rainrate_mmh": 0.0,
  "rain_total_mm": 0.0,
  "solarradiation_wm2": 143.7,
  "uv_index": 1.0,
  "quality_code": 1
}
```

Si da `ERROR: HTTP 401…` la clave es incorrecta; si da `HTTP 404…`, el Station ID no existe (ver [sección 16](#16-resolución-de-problemas)).

### 6.2. Hacer una lectura real y publicar el JSON

```bash
sudo -u telemet python3 telemet_colector.py --una-vez
ls -l /var/www/htdocs/rafa/telemethistorial/datos/
sudo -u telemet python3 telemet_colector.py --estado
```

Debes ver `historial.json` con permisos `-rw-r--r--` y, en `--estado`, una lectura guardada.

### 6.3. Comprobar que Apache lo sirve

Desde cualquier equipo:

```bash
curl -s https://TU-SERVIDOR/RUTA/telemethistorial/datos/historial.json | head -c 400
```

(o ábrelo en el navegador). Si da 404, la ruta publicada no coincide con la de `ruta_json` (ver [sección 8](#8-instalar-y-conectar-la-app-telemet-historial)).

### 6.4. Ejecución en primer plano (opcional)

```bash
sudo -u telemet python3 telemet_colector.py
```

Verás una línea de log por lectura. Se detiene con `Ctrl+C` (cierra la base de datos limpiamente).

---

## 7. Ejecución como servicio (systemd)

### 7.1. Instalación

```bash
sudo cp /home/<tu-usuario>/apps/telemetria/telemetcolector/telemet-colector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telemet-colector
```

### 7.2. Contenido de la unidad y qué hace cada línea

```ini
[Unit]
Description=TeleMet Colector (histórico de la estación meteorológica)
# Arranca cuando ya hay red
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=telemet
Group=telemet
WorkingDirectory=/opt/telemet-colector
ExecStart=/usr/bin/python3 /opt/telemet-colector/telemet_colector.py -c /opt/telemet-colector/config.ini
# Si el proceso muere, se relanza a los 10 s
Restart=always
RestartSec=10

# Endurecimiento: sistema de ficheros en solo lectura, sin acceso a /home, /tmp propio...
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
# ...salvo estas dos carpetas, que deben existir antes de arrancar
ReadWritePaths=/opt/telemet-colector/datos /var/www/htdocs/rafa/telemethistorial/datos

[Install]
# Arranca con el servidor
WantedBy=multi-user.target
```

> En los ficheros `.service` los comentarios deben ir en su propia línea (empezando por `#`); systemd no admite comentarios al final de una línea de ajuste.

> Si cambias el usuario, las rutas del programa o la ruta del JSON, ajusta `User`, `Group`, `WorkingDirectory`, `ExecStart` y `ReadWritePaths`. Si usas `fichero` de log en `[log]`, añade también su carpeta a `ReadWritePaths`.

### 7.3. Órdenes habituales

| Acción | Orden |
|---|---|
| Ver estado | `systemctl status telemet-colector` |
| Ver el log en vivo | `journalctl -u telemet-colector -f` |
| Ver el log de hoy | `journalctl -u telemet-colector --since today` |
| Reiniciar tras cambiar `config.ini` | `sudo systemctl restart telemet-colector` |
| Parar | `sudo systemctl stop telemet-colector` |
| Que no arranque con el servidor | `sudo systemctl disable telemet-colector` |

El programa responde a `SIGTERM` (el que envía `systemctl stop`) y a `SIGINT`: termina la espera en curso, cierra la base de datos y sale con código 0.

### 7.4. Alternativa sin servicio: cron

Si prefieres no usar systemd, puedes programar una lectura puntual con `--una-vez`:

```cron
*/5 * * * * telemet /usr/bin/python3 /opt/telemet-colector/telemet_colector.py -c /opt/telemet-colector/config.ini --una-vez >> /var/log/telemet-colector.log 2>&1
```

Funciona igual (la regla de `duracion_horas` se aplica en cada ejecución), pero pierdes los reintentos con backoff y el ritmo fijo del bucle. Se recomienda systemd.

### 7.5. Variante: secretos fuera del `config.ini`

```bash
sudo install -m 600 -o root -g root /dev/null /etc/telemet-colector.env
echo 'TELEMET_API_KEY=TU_API_KEY'       | sudo tee -a /etc/telemet-colector.env
echo 'TELEMET_STATION_ID=TU_STATION_ID' | sudo tee -a /etc/telemet-colector.env
```

y en la unidad, dentro de `[Service]`:

```ini
EnvironmentFile=/etc/telemet-colector.env
```

Las variables de entorno **tienen prioridad** sobre los valores de `config.ini`.

---

## 8. Instalar y conectar la app TeleMet Historial

### 8.1. Copiar la app

Copia `index.html` y `apple-touch-icon.png` a la carpeta de la app en el servidor:

```bash
sudo mkdir -p /var/www/htdocs/rafa/telemethistorial
sudo cp telemetria/telemet/historial/{index.html,apple-touch-icon.png} /var/www/htdocs/rafa/telemethistorial/
```

### 8.2. Cómo se enlazan app y JSON

La app busca el histórico en una ruta **relativa a su propia página**:

```js
const SERVIDOR_HISTORIAL_URL = 'datos/historial.json';
```

Por tanto, si la app está en `…/telemethistorial/index.html`, el JSON debe estar en `…/telemethistorial/datos/historial.json`. Eso es exactamente lo que escribe el colector con la configuración por defecto:

```
ruta_json = /var/www/htdocs/rafa/telemethistorial/datos/historial.json
```

| Si… | Haz… |
|---|---|
| Publicas la app en **otra carpeta** | Cambia `ruta_json` en `config.ini` para que acabe en `<carpeta-de-la-app>/datos/historial.json`, y actualiza `ReadWritePaths` en la unidad. |
| Quieres el JSON en **otro sitio** (otra carpeta o dominio) | Cambia la constante `SERVIDOR_HISTORIAL_URL` en el HTML. Si es otro origen, el servidor debe enviar cabeceras CORS (ver 8.4). |

### 8.3. Evitar que se cachee el JSON (opcional)

La app ya añade un parámetro `?t=<marca de tiempo>` en cada petición, así que no suele hacer falta. Si quieres reforzarlo en Apache (requiere `mod_headers`):

```apache
<Directory /var/www/htdocs/rafa/telemethistorial/datos>
    <FilesMatch "\.json$">
        Header set Cache-Control "no-store"
    </FilesMatch>
</Directory>
```

Activar la compresión del JSON (`mod_deflate`, tipo `application/json`) reduce el tamaño transferido, aunque con 144 lecturas apenas importa (~45 KB).

### 8.4. Casos especiales

- **App y JSON en el mismo servidor y origen (lo normal):** no hay que hacer nada más.
- **App en HTTPS:** el JSON debe servirse también por HTTPS (lo hace automáticamente si es una ruta relativa).
- **JSON en otro origen:** añade en Apache `Header set Access-Control-Allow-Origin "https://origen-de-la-app"` para ese fichero.
- **Abrir `index.html` directamente desde el disco (`file://`):** el navegador bloquea la lectura del JSON; la app lo ignora y funciona solo con su base local.
- **SELinux (RHEL/Rocky/Alma):** si Apache no puede leer el JSON, etiqueta la carpeta, p. ej. `sudo chcon -R -t httpd_sys_content_t /var/www/.../datos`.

### 8.5. Verificar que la app lo usa

Abre la app, introduce (o deja guardado) el Station ID y despliega el panel **«Evolución de las últimas 12 horas»** (o 24, según el selector 12 h / 24 h del panel). Debajo de la nota verás una de estas líneas (ver [sección 13.4](#134-mensajes-que-muestra-la-app)).

---

## 9. Referencia de configuración (`config.ini`)

Formato estándar INI. Las rutas relativas se resuelven **respecto a la carpeta del `config.ini`** (no respecto al directorio desde el que se lanza el programa). Los comentarios empiezan por `#`. Si falta un parámetro, se usa el valor por defecto de la tabla.

### 9.1. `[estacion]`

| Parámetro | Defecto | Descripción |
|---|---|---|
| `station_id` | *(vacío)* | Identificador de la estación (p. ej. `IELCHE12`). Obligatorio. Si cambia respecto al que usó la base de datos, **se borran los datos antiguos** (ver 11.7). |
| `api_key` | *(vacío)* | Clave de la API de Weather Underground / Earth Network. Obligatoria. |

Ambos pueden venir de las variables de entorno `TELEMET_STATION_ID` y `TELEMET_API_KEY`, que prevalecen sobre el `.ini`. De forma análoga, `TELEMET_HORAS` sustituye a `duracion_horas`.

### 9.2. `[lectura]`

| Parámetro | Defecto | Mín. | Descripción |
|---|---|---|---|
| `url_base` | `https://api.weather.com/v2/pws/observations/current` | — | Endpoint de la observación actual. Solo habría que tocarlo si la API cambia (o para pruebas con un servidor simulado). |
| `intervalo_s` | `300` | 5 | Segundos entre lecturas. |
| `timeout_s` | `15` | 1 | Tiempo máximo de espera de cada petición HTTP. |
| `backoff_base_s` | `2` | 0,5 | Espera inicial tras un fallo temporal. Las siguientes se duplican: base, 2·base, 4·base… |
| `backoff_max_s` | `300` | `backoff_base_s` | Tope de espera tras fallos. También es el intervalo de reintento tras errores de clave/estación (401/403/404). |

**Elegir `intervalo_s`.** Cada lectura es una llamada a la API:

| `intervalo_s` | Llamadas/día | Lecturas en 24 h | Tamaño aprox. del JSON |
|---|---|---|---|
| 60 | 1.440 | 1.440 | ~460 KB |
| 120 | 720 | 720 | ~230 KB |
| **300 (defecto)** | **288** | **288** | **~90 KB** |
| 600 | 144 | 144 | ~45 KB |

El tamaño es proporcional a las horas guardadas (con 12 h sería la mitad; con 48 h, el doble).

Los visitantes de la app que usen la misma API Key consumen llamadas adicionales (la app sondea por su cuenta cada 60 s por defecto mientras está en marcha). Comprueba el límite diario de tu clave antes de bajar mucho el intervalo.

### 9.3. `[ciclo]`

| Parámetro | Defecto | Descripción |
|---|---|---|
| `duracion_horas` | `24` | Horas de histórico que se conservan. Admite decimales (p. ej. `0.5`). Debe ser > 0. 24 h bastan para las gráficas de 12 h y de 24 h de la app. Se puede sustituir sin tocar el `.ini` con la opción `--horas H` o la variable de entorno `TELEMET_HORAS` (prioridad: `--horas` > `TELEMET_HORAS` > `.ini`). |
| `modo` | `deslizante` | Qué ocurre al cumplirse `duracion_horas`. Ver abajo. |

**`modo = deslizante` (por defecto).** En cada vuelta se borran las lecturas con más de `duracion_horas`. El servidor siempre dispone de las últimas `duracion_horas` horas completas. Es el modo recomendado: nunca hay un momento con el histórico vacío.

**`modo = reinicio`.** Se cuenta desde el instante de inicio del ciclo; cuando `ahora − inicio ≥ duracion_horas` se **borra todo** y se abre un ciclo nuevo. Justo después el histórico del servidor está vacío y se va llenando; un navegador sin datos propios vería entonces la gráfica casi vacía hasta que pase tiempo. El instante de inicio se guarda en la base de datos, de modo que reiniciar el servicio o el servidor **no** reinicia el ciclo.

### 9.4. `[almacen]`

| Parámetro | Defecto | Descripción |
|---|---|---|
| `ruta_bd` | `./datos/telemet.sqlite` | Fichero SQLite. La carpeta se crea si no existe (si el usuario tiene permiso). Se crean también `*.sqlite-wal` y `*.sqlite-shm` (modo WAL). |

### 9.5. `[salida]`

| Parámetro | Defecto | Descripción |
|---|---|---|
| `ruta_json` | `/var/www/htdocs/rafa/telemethistorial/datos/historial.json` | Dónde se publica el histórico. La **carpeta** debe ser escribible por el usuario del servicio (la escritura atómica crea un fichero temporal en ella). |
| `decimales` | `2` | Decimales de los valores numéricos exportados. La base de datos guarda el valor completo; el redondeo solo afecta al JSON. |

### 9.6. `[log]`

| Parámetro | Defecto | Descripción |
|---|---|---|
| `nivel` | `INFO` | `DEBUG`, `INFO`, `WARNING` o `ERROR`. |
| `fichero` | *(vacío)* | Si se indica, además de la salida estándar se escribe en ese fichero con rotación (1 MB × 3 copias). Vacío = solo salida estándar, que con systemd va a `journalctl`. |

### 9.7. Validaciones al arrancar

El programa termina con un mensaje claro si: el `-c` apunta a un fichero inexistente; `duracion_horas` ≤ 0; `modo` no es `reinicio` ni `deslizante`; o faltan `station_id`/`api_key` (en `.ini` y entorno). Los valores numéricos por debajo del mínimo se corrigen al mínimo.

### 9.8. Aplicar cambios

El `config.ini` se lee solo al arrancar: tras editarlo, `sudo systemctl restart telemet-colector`.

---

## 10. Referencia de línea de órdenes

```
python3 telemet_colector.py [-c RUTA_CONFIG] [--horas H] [--una-vez | --probar | --estado]
```

| Opción | Efecto | Escribe en BD / JSON |
|---|---|---|
| *(ninguna)* | Servicio continuo: bucle infinito hasta `SIGINT`/`SIGTERM`. | Sí |
| `-c`, `--config RUTA` | Fichero de configuración. Si se omite, usa `config.ini` junto al script **si existe**; si no, solo valores por defecto y entorno. | — |
| `--horas H` | Horas de histórico a conservar (admite decimales). Sustituye a `duracion_horas` del `.ini` y a `TELEMET_HORAS`. | — |
| `--una-vez` | Una lectura; la guarda, exporta el JSON y sale. | Sí |
| `--probar` | Una lectura; la imprime y sale. Código de salida 1 si falla. | **No** |
| `--estado` | Resumen de la BD: ruta, estación, nº de lecturas con primer/último instante, inicio del ciclo. No necesita credenciales. | No |

`--una-vez`, `--probar` y `--estado` son mutuamente excluyentes.

Ejemplo de `--estado`:

```
BD:            /opt/telemet-colector/datos/telemet.sqlite
Estación:      IELCHE12
Lecturas:      141  (de 2026-11-03 09:34:12 a 2026-11-03 21:19:12)
Ciclo desde:   2026-11-03 08:50:03
```

---

## 11. Cómo funciona por dentro

### 11.1. El bucle principal

```
arranque
  └─ cargar config, abrir SQLite, recuperar inicio de ciclo
  └─ exportar JSON inicial (para que la app encuentre el fichero ya)
  └─ repetir hasta SIGINT/SIGTERM:
        1. aplicar la regla de duracion_horas
        2. consultar la API
        3. guardar la lectura (si es nueva)
        4. exportar el JSON (si algo cambió)
        5. esperar (intervalo_s menos lo que haya tardado la vuelta, mínimo 1 s)
```

La espera es a **ritmo fijo**: se descuenta el tiempo de la petición, de modo que con `intervalo_s = 300` las lecturas no se van desplazando poco a poco.

### 11.2. La petición a la API

Se hace un `GET` al endpoint con estos parámetros (la clave viaja como parámetro de URL, igual que en la app):

```
stationId=<id>&format=json&numericPrecision=decimal&units=m&apiKey=<clave>
```

`units=m` pide unidades métricas (°C, km/h, hPa, mm). Se envía la cabecera `User-Agent: telemet-colector/1.0`. Si la respuesta no trae cuerpo (HTTP 204) o la lista `observations` está vacía, se registra «La API no ha devuelto observaciones nuevas» y se espera el intervalo normal.

### 11.3. Extracción de valores

La función `extraer_valores()` es un **portado fiel** de `extraerValores()` de la app (mismos campos, mismos *fallbacks* entre nombres de campo y mismas fórmulas), para que un dato guardado en el servidor sea idéntico al que habría guardado el navegador. Ver la [sección 12.3](#123-campos-de-v-lecturas) para el mapeo.

La **sensación térmica** (`heat_index_c`) se calcula localmente, sin más llamadas a la API:

| Temperatura | Método |
|---|---|
| ≥ 26,7 °C (≈ 80 °F) | Índice de calor NWS (Rothfusz) con la humedad; nunca por debajo de la temperatura real. |
| ≤ 10 °C | Sensación de frío por viento (Environment Canada) si el viento > 4,8 km/h; nunca por encima de la temperatura real. |
| entre ambos | La propia temperatura. |

Se ha comprobado contra la implementación JavaScript de la app con 880 combinaciones de temperatura, humedad y viento: **0 discrepancias**.

### 11.4. Gestión de errores

| Situación | Reacción |
|---|---|
| Fallo de red, timeout, HTTP 5xx/429/otros, JSON inválido | **Temporal.** Aviso en el log y reintento con backoff exponencial: `backoff_base_s · 2^(n−1)` hasta `backoff_max_s`. Al primer éxito el contador vuelve a 0. |
| HTTP 401 o 403 (clave inválida o sin permiso) | **Fatal pero no mortal.** Error en el log y reintento cada `backoff_max_s`. El servicio no se cae por si fuera un fallo pasajero. |
| HTTP 404 (estación o endpoint inexistente) | Igual que el anterior. |
| Observación con el mismo instante (`epoch`) ya guardado | No se guarda dos veces y no se reescribe el JSON. |
| Excepción inesperada en el código | Se registra con traceback y el bucle continúa tras un backoff; el servicio no muere. |
| No se puede escribir el JSON | Error en el log (con la ruta y la pista de permisos) y se sigue leyendo y guardando. |

### 11.5. La regla de `duracion_horas`

Se ejecuta **al principio de cada vuelta**, antes de pedir la lectura.

- **Deslizante:** `DELETE … WHERE epoch_ms < ahora − duracion`. Si borró algo, el JSON se reexporta.
- **Reinicio:** si `ahora − ciclo_inicio ≥ duracion`, `DELETE` de todas las lecturas + `VACUUM`, nuevo `ciclo_inicio` = ahora (guardado en la tabla `meta`) y reexportación. Mensaje en el log: «Ciclo de 24 h cumplido: borradas N lecturas y comienza un ciclo nuevo.»

### 11.6. Cuándo se escribe el JSON

- Una vez al arrancar (aunque no haya lecturas aún, con `lecturas: []`).
- Tras cada lectura **nueva** guardada.
- Tras cualquier cambio en la regla del ciclo (borrado de lecturas).
- Tras un error de red **solo** si el ciclo acababa de cambiar el contenido.

Si la estación deja de publicar datos, el JSON deja de cambiar; la app lo detecta (ver 13.4).

### 11.7. Cambio de estación

Al arrancar se compara el `station_id` guardado en la tabla `meta` con el de la configuración. Si difieren, se borran todas las lecturas y se reinicia el ciclo, de forma que nunca se mezclen datos de dos estaciones.

### 11.8. Escritura atómica del JSON

1. Se crea un fichero temporal oculto (`.historial-XXXX.tmp`) **en la misma carpeta** de destino.
2. Se escribe el contenido completo y se le da permiso `0644`.
3. Se renombra sobre `historial.json` con `os.replace()` (operación atómica en el mismo sistema de ficheros).

Así Apache nunca sirve un JSON a medio escribir. Por eso el usuario del servicio necesita permiso de escritura en la **carpeta**, no solo en el fichero. Si algo falla, el temporal se borra.

### 11.9. La base de datos

SQLite en modo WAL (más robusto ante cortes de energía):

```sql
CREATE TABLE lecturas (
  epoch_ms INTEGER PRIMARY KEY,   -- instante de la observación, ms desde 1970 (UTC)
  vals     TEXT NOT NULL          -- JSON con los valores (ver sección 12.3)
);
CREATE TABLE meta (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL                 -- station_id, ciclo_inicio_ms
);
```

`epoch_ms` es clave primaria, y se inserta con `INSERT OR IGNORE`: repetir una observación no duplica nada. Para inspeccionarla a mano:

```bash
sudo -u telemet sqlite3 /opt/telemet-colector/datos/telemet.sqlite \
  "SELECT datetime(epoch_ms/1000,'unixepoch','localtime'), json_extract(vals,'$.temp_c') FROM lecturas ORDER BY epoch_ms DESC LIMIT 10;"
```

(requiere el paquete `sqlite3`; el programa no lo necesita).

### 11.10. Cierre ordenado

`SIGTERM`/`SIGINT` activan una bandera; la espera del bucle se interrumpe, se cierra la base de datos y se imprime «Detenido.». Si la señal llega durante una petición HTTP, se espera a que termine (como máximo `timeout_s`).

---

## 12. Formato de los datos

### 12.1. Fichero `historial.json`

```json
{
  "formato": 1,
  "stationId": "IELCHE12",
  "generadoMs": 1793737178059,
  "modo": "deslizante",
  "duracionMs": 43200000,
  "cicloInicioMs": 1793737168054,
  "cicloFinMs": null,
  "intervaloS": 300.0,
  "lecturas": [
    {
      "t": 1793737178000,
      "v": {
        "temp_c": 18.4,
        "heat_index_c": 18.4,
        "dewpoint_c": 11.2,
        "humidity_pct": 62,
        "pressure_hpa": 1015.3,
        "wind_kmh": 7.2,
        "gust_kmh": 12.9,
        "wind_dir_deg": 204,
        "rainrate_mmh": 0.0,
        "rain_total_mm": 0.0,
        "solarradiation_wm2": 143.7,
        "uv_index": 1.0,
        "quality_code": 1
      }
    }
  ]
}
```

### 12.2. Cabecera

| Campo | Significado |
|---|---|
| `formato` | Versión del formato (actualmente `1`). La app **rechaza** ficheros con otro valor. |
| `stationId` | Estación a la que pertenecen los datos. La app solo los usa si coincide (sin distinguir mayúsculas) con el Station ID escrito en ella. |
| `generadoMs` | Instante de la exportación (ms UTC). |
| `modo` | `deslizante` o `reinicio`. |
| `duracionMs` | Duración del ciclo en milisegundos (24 h = 86 400 000). |
| `cicloInicioMs` | Inicio del ciclo guardado en la BD. En modo deslizante es solo informativo. |
| `cicloFinMs` | Fin previsto del ciclo (solo en modo `reinicio`; `null` en deslizante). |
| `intervaloS` | Intervalo de lectura configurado; la app lo usa para ajustar el aviso de «colector parado». |
| `lecturas` | Lista ordenada por `t` ascendente. |

### 12.3. Campos de `v` (lecturas)

Cada valor puede ser `null` si la estación no lo informó.

| Campo | Unidad | Origen en la respuesta de la API |
|---|---|---|
| `temp_c` | °C | `metric.temp` (o `metric.tempAvg`) |
| `heat_index_c` | °C | **Calculado** (ver 11.3) |
| `dewpoint_c` | °C | `dewpoint`, `metric.dewpt`, `metric.dewptAvg` o `metric.dewpoint` |
| `humidity_pct` | % | `humidity` (o `humidityAvg`) |
| `pressure_hpa` | hPa | `metric.pressure` (o media de `pressureMax`/`pressureMin`) |
| `wind_kmh` | km/h | `metric.windSpeed` (o `windspeedAvg`) |
| `gust_kmh` | km/h | `metric.windGust` (o `windgustAvg`) |
| `wind_dir_deg` | ° (0–360) | `winddir` / `windDir` / `winddirAvg` |
| `rainrate_mmh` | mm/h | `metric.precipRate` |
| `rain_total_mm` | mm | `metric.precipTotal` |
| `solarradiation_wm2` | W/m² | `solarRadiation` / `solarradiation` / `solarRadiationHigh` |
| `uv_index` | — | `uv` (o `uvHigh`) |
| `quality_code` | — | `qcStatus` / `qualityControlFlag`, o `"N/A"`. El valor `1` significa «verificada» |

### 12.4. Zonas horarias

Todos los instantes son **epoch en milisegundos (UTC)**. La zona horaria solo interviene al mostrarlos: el log del colector usa la hora local del servidor; la app usa la del navegador.

---

## 13. Cómo funciona la parte de la app

Todo está en `telemetria/telemet/historial/index.html`, en el bloque «HISTÓRICO DEL SERVIDOR (TeleMet Colector)».

### 13.1. Constantes ajustables (en el propio HTML)

| Constante | Valor | Descripción |
|---|---|---|
| `SERVIDOR_HISTORIAL_URL` | `'datos/historial.json'` | Ruta del JSON, relativa a la página. |
| `SERVIDOR_TIMEOUT_MS` | `15000` | Tiempo máximo de la descarga. |
| `SERVIDOR_SYNC_CADA_MIN` | `10` | Cada cuántos minutos se vuelve a consultar con la app abierta. |
| `SERVIDOR_MERGE_TOLERANCIA_MS` | `30000` | Una lectura del servidor a menos de 30 s de una local se considera la misma. |
| `SERVIDOR_AVISO_PARADO_MIN` | `15` | Minutos sin lecturas nuevas tras los que se avisa (mínimo; se amplía a 3 intervalos del colector si este es mayor). |

### 13.2. Cuándo sincroniza

1. **Al abrir la app**, sin esperar a pulsar «Iniciar» (usa el Station ID guardado en el navegador).
2. **Al pulsar «Iniciar»**, antes de la recuperación de huecos con la API de Weather Underground, que así solo consultará los días que sigan incompletos y gasta menos llamadas.
3. **Cada 10 minutos** mientras la pestaña esté visible.
4. **Al volver a la pestaña** (evento `visibilitychange`), por ejemplo al desbloquear el iPad.

Si ya hay una sincronización en curso, las demás se omiten.

### 13.3. Cómo se fusionan los datos (siempre de forma aditiva)

1. Descarga el JSON (con `?t=<ahora>` para esquivar cachés).
2. Valida: `formato === 1`, `lecturas` es una lista, el `stationId` coincide.
3. Lee de IndexedDB las lecturas locales de ese rango temporal (±30 s).
4. Para cada lectura del servidor, busca (búsqueda binaria) si hay una local a menos de 30 s. Si la hay, la descarta; si no, la marca como nueva.
5. Inserta todas las nuevas en **una sola transacción**.
6. Si añadió algo y el panel de evolución está abierto, lo repinta.

Garantías:

- **Nunca borra ni modifica** nada de lo que ya tenía el navegador.
- Las lecturas del servidor **no se comparan entre sí**, solo con lo que ya había en local; así las lecturas muy próximas del servidor no se descartan unas a otras.
- Si no se puede ni leer la base local (modo privado, bloqueo de IndexedDB…) no se inserta nada, para no arriesgar duplicados.
- Los datos del servidor entran en la **misma base** que usan las gráficas de 7 días y el resumen diario, así que también los completan (el navegador purga a los 9 días).

### 13.4. Mensajes que muestra la app

En el panel «Evolución de las últimas 12 horas» (o 24):

| Situación | Mensaje |
|---|---|
| Se añadieron lecturas | «Histórico del servidor: ha aportado N lecturas que faltaban en este navegador (última lectura del servidor: HH:MM).» |
| Ya estaba todo | «Histórico del servidor: consultado, no faltaba ninguna lectura (última lectura del servidor: HH:MM).» |
| El colector aún no ha guardado nada | «Histórico del servidor: el recolector aún no tiene lecturas guardadas.» |
| Última lectura demasiado vieja | Se añade: «Atención: hace más de N minutos que el servidor no registra nada; el recolector podría estar parado.» |
| Otra estación | «El histórico del servidor es de otra estación (X)… no se ha usado.» |
| Formato inválido o error al guardar | «No se ha podido usar el histórico del servidor…» |
| El fichero no existe / no hay red | **No se muestra nada** y la app funciona como siempre (caso de GitHub Pages). |

### 13.5. Qué NO hace

- No usa el servidor en lugar del navegador: el navegador sigue registrando sus propias lecturas cada `pollInterval` (60 s por defecto).
- No ofrece más horas de las guardadas: el JSON solo contiene la ventana del servidor (`duracion_horas`, 24 h por defecto). Con una ventana de 24 h en la app, la primera mitad depende de lo que el navegador haya guardado si `duracion_horas` es menor de 24.
- No soporta varias estaciones en el mismo JSON (ver FAQ).

---

## 14. Operación diaria: logs, estado, copias, actualización

### 14.1. Interpretar el log

```
2026-11-03 21:19:12 INFO TeleMet Colector 1.0 · estación ITEST1 · cada 300 s · ciclo 24 h (deslizante)
2026-11-03 21:19:12 INFO BD: /opt/telemet-colector/datos/telemet.sqlite · JSON: /var/www/.../historial.json
2026-11-03 21:19:12 INFO 21:19:12  T=18.4 °C  HR=62 %  viento=7.2 km/h  guardada
2026-11-03 21:24:12 INFO 21:24:12  T=18.3 °C  HR=62 %  viento=6.8 km/h  guardada
2026-11-03 21:29:12 WARNING Lectura fallida (HTTP 500); reintento n.º 1 en 2 s.
2026-11-03 21:29:15 INFO 21:24:12  T=18.3 °C  HR=62 %  viento=6.8 km/h  (observación repetida, no se guarda)
```

La hora que aparece al principio de la línea de datos es la de la **observación** de la estación (no la del servidor): si coincide con la anterior, la estación no ha publicado nada nuevo.

### 14.2. Comprobaciones rápidas de salud

```bash
systemctl is-active telemet-colector                 # active
sudo -u telemet python3 /opt/telemet-colector/telemet_colector.py -c /opt/telemet-colector/config.ini --estado
ls -l --time-style=full-iso /var/www/htdocs/rafa/telemethistorial/datos/historial.json   # fecha reciente
```

### 14.3. Copias de seguridad

No son necesarias: son datos de unas horas, reconstruibles y efímeros. Solo conviene guardar `config.ini` (por la clave) en un sitio seguro.

### 14.4. Actualizar el programa

```bash
cd ~/apps && git pull
sudo cp telemetria/telemetcolector/telemet_colector.py /opt/telemet-colector/
sudo chown telemet:telemet /opt/telemet-colector/telemet_colector.py
sudo systemctl restart telemet-colector
journalctl -u telemet-colector -n 20
```

Si en la actualización se añaden parámetros nuevos, compara `config.example.ini` con tu `config.ini`: los parámetros que falten toman su valor por defecto. Tu `config.ini` no se sobrescribe.

### 14.5. Actualizar la app

```bash
sudo cp ~/apps/telemetria/telemet/historial/index.html /var/www/htdocs/rafa/telemethistorial/
```

Los navegadores cargarán la versión nueva al recargar (a veces hay que forzar con `Ctrl+Shift+R`).

### 14.6. Cambiar de modo o de intervalo

Edita `config.ini` y reinicia el servicio. Al pasar de `reinicio` a `deslizante` no se pierde nada; al pasar de `deslizante` a `reinicio`, el ciclo cuenta desde el `ciclo_inicio` guardado en la BD (el de la primera vez que se creó), por lo que podría reiniciarse enseguida. Si quieres un ciclo nuevo desde ahora, para el servicio y borra `datos/telemet.sqlite*` antes de arrancar.

---

## 15. Seguridad

- **API Key:** está en `config.ini` con permisos `600` y propietario `telemet`. No lo subas a GitHub (el `.gitignore` ya lo excluye). Alternativa: variables de entorno con `EnvironmentFile` (sección 7.5).
- **Exposición:** el JSON publicado no contiene la clave, pero sí datos meteorológicos y el Station ID, accesibles a quien conozca la URL. Si no quieres que sean públicos, protege la carpeta `datos/` con autenticación de Apache (ten en cuenta que la app tendría que enviarla).
- **Mínimos privilegios:** el servicio corre como usuario sin shell, con `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome` y `PrivateTmp`; solo puede escribir en `datos/` y en la carpeta del JSON.
- **Clave en la URL de la API:** es el diseño de la API de Weather Underground; la conexión es HTTPS, pero la clave aparecería en logs de un proxy intermedio si lo hubiera.
- **Red:** el programa solo hace conexiones salientes; no abre ningún puerto.

---

## 16. Resolución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El servicio no arranca; `status=226/NAMESPACE` | No existe una carpeta de `ReadWritePaths` (`/opt/telemet-colector/datos` o la del JSON). | Créalas (secciones 5.2 y 5.3) y `systemctl restart`. |
| `ERROR: HTTP 401` / log «HTTP 401: API Key inválida» | Clave mal copiada, caducada o sin permiso para ese Station ID. | Revisa `api_key` en `config.ini` (sin espacios ni comillas). Se reintenta sola cada `backoff_max_s`. |
| `HTTP 404: Station ID no encontrado` | Station ID erróneo (o con minúsculas/espacios). | Corrige `station_id`. |
| «Lectura fallida (fallo de red…)» repetido | El servidor no sale a Internet, DNS o firewall. | `curl -I https://api.weather.com`; revisa proxy/cortafuegos. |
| «La API no ha devuelto observaciones nuevas» | La estación está desconectada o sin datos recientes. | Comprueba la estación y su conexión a Wi-Fi/Weather Underground. |
| «No se pudo escribir …historial.json» | La carpeta no existe o el usuario `telemet` no puede escribir en ella (o falta en `ReadWritePaths`). | `ls -ld` de la carpeta; `chown telemet:telemet`; revisa la unidad. |
| `curl` al JSON da 404 | La ruta de Apache no coincide con `ruta_json`. | Comprueba `DocumentRoot`/alias y la ruta real del fichero. |
| `curl` al JSON da 403 | Apache no puede leer la carpeta (permisos de directorio o SELinux). | `chmod 755` en las carpetas intermedias; `chcon` si usas SELinux. |
| La app no muestra ninguna línea «Histórico del servidor» | No encuentra/lee el JSON (404, `file://`, otro origen sin CORS) o no hay Station ID. | Abre la URL del JSON en el navegador; mira la consola (F12 → Red). |
| La app dice «otra estación (X)» | El Station ID de la app y el del colector no coinciden. | Escribe en la app el mismo Station ID que en `config.ini`. |
| La app avisa «el recolector podría estar parado» | Última lectura del servidor muy antigua. | `systemctl status`, `journalctl`; comprueba la estación y la red. |
| Gráficas con tramos rotos en la línea | Hueco > 90 min sin lecturas (la app corta la línea a partir de ahí). | Mira el log del colector en ese intervalo. |
| El histórico del servidor se vacía de golpe al cumplirse `duracion_horas` | Estás en `modo = reinicio`. | Cambia a `modo = deslizante` y reinicia el servicio. |
| `PermissionError` al abrir la BD | La carpeta `datos/` no pertenece a `telemet`. | `sudo chown -R telemet:telemet /opt/telemet-colector`. |
| Fechas del log desfasadas | Zona horaria del servidor distinta de la esperada. | `timedatectl`; los datos (epoch UTC) son correctos igualmente. |

Para depurar en detalle: pon `nivel = DEBUG`, reinicia y mira `journalctl -u telemet-colector -f`.

---

## 17. Preguntas frecuentes

**¿Qué pasa si el servidor se reinicia o se corta la luz?**
El servicio arranca con el sistema (`enable`) y reabre la base SQLite. En modo deslizante, al volver continúa donde lo dejó (las lecturas de las últimas `duracion_horas` se conservan; habrá un hueco por el tiempo caído). En modo reinicio, el ciclo continúa con su inicio original.

**¿Puedo guardar más (o menos) de 24 horas?**
Sí: cambia `duracion_horas` en el `.ini` (p. ej. `48`), o usa `--horas 48` / `TELEMET_HORAS=48` sin tocar el fichero. Las gráficas de 12 h y de 24 h de la app solo necesitan 24 h; con más horas, el servidor entrega datos extra que quedan en la base local del navegador y alimentan las gráficas de 7 días. El tamaño del JSON crece proporcionalmente. Con menos de 24 h, la gráfica de 24 h dependerá en su parte antigua de lo que haya guardado el navegador.

**¿Puedo usar un intervalo menor de 5 s?**
No: el mínimo es 5 s, y la API no actualiza tan rápido; además consumiría la cuota diaria.

**¿Y si dos lecturas llegan con el mismo instante?**
Solo se guarda la primera (clave primaria `epoch_ms`).

**¿Se pueden monitorizar varias estaciones?**
Cada instancia del colector atiende una estación. Para varias, crea otra carpeta con su propio `config.ini`, otra `ruta_bd`, otra `ruta_json` y otra unidad systemd (`telemet-colector-2.service`). La app, sin embargo, lee un único `datos/historial.json` relativo a su página, por lo que cada estación necesitaría su propia copia de la app en otra carpeta (o cambiar `SERVIDOR_HISTORIAL_URL`).

**¿Por qué no un servidor HTTP propio en Python?**
Un fichero estático servido por Apache es más simple y robusto: no hay otro proceso expuesto, ni puerto, ni problemas de contenido mixto HTTP/HTTPS, y escala sin esfuerzo.

**¿Funciona con la copia de la app en GitHub Pages?**
La app funciona, pero sin servidor: al no existir `datos/historial.json` en Pages, la lectura se ignora sin errores. Para usar el histórico del servidor, la app debe alojarse en el mismo servidor.

**¿El colector necesita que haya alguien con la app abierta?**
No. Funciona 24 h al día; la app solo lee lo que ya está guardado.

**¿Gasta mucha CPU, memoria o disco?**
No: unos pocos milisegundos de CPU cada 5 minutos, pocos MB de memoria y decenas de KB de disco.

**¿Cómo lo pruebo sin estación real?**
Con `url_base` apuntando a un servidor simulado que devuelva el mismo formato de la API, y duraciones/intervalos cortos (`intervalo_s = 5`, `duracion_horas = 0.004`) para ver el borrado en segundos.

---

## 18. Desinstalación

```bash
sudo systemctl disable --now telemet-colector
sudo rm /etc/systemd/system/telemet-colector.service
sudo systemctl daemon-reload
sudo rm -rf /opt/telemet-colector
sudo rm -f /var/www/htdocs/rafa/telemethistorial/datos/historial.json
sudo userdel telemet
```

La app seguirá funcionando sin el JSON.

---

## 19. Apéndice: ejemplos

### 19.1. `config.ini` por defecto (5 min, deslizante, 24 h)

```ini
[estacion]
station_id = TU_STATION_ID
api_key    = TU_API_KEY

[lectura]
url_base       = https://api.weather.com/v2/pws/observations/current
intervalo_s    = 300
timeout_s      = 15
backoff_base_s = 2
backoff_max_s  = 300

[ciclo]
duracion_horas = 24
modo = deslizante

[almacen]
ruta_bd = ./datos/telemet.sqlite

[salida]
ruta_json = /var/www/htdocs/rafa/telemethistorial/datos/historial.json
decimales = 2

[log]
nivel   = INFO
fichero =
```

### 19.2. Resolución alta (1 lectura por minuto)

```ini
[lectura]
intervalo_s = 60
```

(1.440 llamadas al día; ~460 KB de JSON).

### 19.3. Borrado completo cada 12 h (comportamiento «reinicio»)

```ini
[ciclo]
duracion_horas = 12
modo = reinicio
```

### 19.4. Guardar 48 h

```ini
[ciclo]
duracion_horas = 48
modo = deslizante
```

O sin tocar el fichero: `python3 telemet_colector.py --horas 48` (o `TELEMET_HORAS=48`).

### 19.5. Instalación completa en un bloque (para copiar y pegar)

```bash
# Desde la carpeta apps/telemetria/telemetcolector del repositorio clonado
sudo useradd --system --home /opt/telemet-colector --shell /usr/sbin/nologin telemet
sudo mkdir -p /opt/telemet-colector/datos
sudo cp telemet_colector.py /opt/telemet-colector/
sudo cp config.example.ini /opt/telemet-colector/config.ini
sudo chown -R telemet:telemet /opt/telemet-colector
sudo chmod 600 /opt/telemet-colector/config.ini
sudo install -d -o telemet -g telemet -m 755 /var/www/htdocs/rafa/telemethistorial/datos

sudo -u telemet nano /opt/telemet-colector/config.ini        # station_id y api_key
sudo -u telemet python3 /opt/telemet-colector/telemet_colector.py -c /opt/telemet-colector/config.ini --probar
sudo -u telemet python3 /opt/telemet-colector/telemet_colector.py -c /opt/telemet-colector/config.ini --una-vez

sudo cp telemet-colector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telemet-colector
journalctl -u telemet-colector -f
```

---

*Autor: Rafael Puerto (r.puerto@umh.es) · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche.*

# TeleHome Enchufes

> TeleHome Enchufes (0.5.1): macOS y Linux, modo local y modo nube de Tuya, contraseña opcional. Sustituye a la antigua versión «local» (0.1.0, solo macOS y red local), que ya está incluida aquí: el modo local funciona igual y el modo nube es opcional. Para probar los enchufes antes de instalar nada: [`telehome-enchufes-vscode`](../telehome-enchufes-vscode/).

Telemetría y control de enchufes Wi-Fi con medidor de consumo **Energeeks EG-EW008MC**
(el pack de 3 se vende como EG-EW009MC: son los mismos enchufes), hasta **7 enchufes**, en **macOS** o **Linux**.
Cada enchufe se lee en **modo local** (misma red) o en **modo nube** (API de Tuya, desde cualquier sitio).

- Lectura periódica de **potencia, tensión y corriente** y estado (encendido/apagado), con histórico en SQLite.
- **Encender/apagar** cada enchufe desde la interfaz.
- Energía (kWh) de hoy y por intervalo, disponibilidad, gráficas de 1 h a 30 días y exportación a CSV.
- **Modo local**: habla con los enchufes por la LAN (protocolo local de Tuya vía [TinyTuya](https://github.com/jasonacox/tinytuya)).
- **Modo nube**: lee y conmuta a través de la API de Tuya IoT, sin estar en la red de los enchufes (p. ej. en una VM de Azure).
- Interfaz web (un solo HTML, sin librerías externas) servida en `127.0.0.1`, con contraseña opcional: un contador arriba con la
  potencia total, su reparto por enchufe y la energía de hoy en cifras de contador; una lista de enchufes con barra de carga,
  minigráfica e interruptor (la gráfica empieza en la primera lectura si hay menos histórico que el intervalo); gráfica de potencia,
  tensión o corriente (1 h a 30 días) con valores al pasar el ratón o el dedo; tabla resumen con totales; ajustes por
  pestañas (Enchufes, Nube de Tuya, Buscar e importar, Opciones); modo oscuro automático.

## Cómo funciona

El EG-EW008MC es un dispositivo Tuya (Wi-Fi 2,4 GHz, compatible con las apps Energeeks 3.0, Tuya Smart y Smart Life).
Un navegador no puede hablar TCP/UDP con él, así que la app es un pequeño servicio Python + una interfaz HTML:

```
navegador ──HTTP──▶ telehome_enchufes (Python) ──TCP 6668──────────▶ enchufes (modo local, misma LAN)
                         │                  └──HTTPS (API Tuya)──▶ nube de Tuya ◀── enchufes (modo nube)
                         └── SQLite (telemetría)
```

## Instalación en macOS

Necesitas Python 3.9 o superior (`xcode-select --install` o `brew install python`).

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/RafaUMH2110/code.git
cd code && git sparse-checkout set telemetria/home/telehome-enchufes
cd telemetria/home/telehome-enchufes
./macos/instalar-macos.sh             # crea .venv e instala dependencias
./macos/instalar-macos.sh --launchd   # opcional: arranca al iniciar sesión
```

Arranque: doble clic en `macos/iniciar-telehome-enchufes.command` (abre el navegador en <http://127.0.0.1:8765/>)
o `.venv/bin/python -m telehome_enchufes`.

> En macOS reciente, la primera vez aparece un aviso para que Python acceda a la **Red local**. Debes permitirlo;
> si usas el LaunchAgent, ejecuta antes la app una vez desde el Terminal para ver ese aviso.

Prueba sin hardware: `.venv/bin/python -m telehome_enchufes serve --simulate 4` (datos simulados, carpeta de datos aparte).

## Instalación en Linux (p. ej. una VM de Azure)

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/RafaUMH2110/code.git
cd code && git sparse-checkout set telemetria/home/telehome-enchufes
cd telemetria/home/telehome-enchufes
sudo ./linux/instalar-linux.sh          # servicio systemd «telehome-enchufes», código en /opt, datos en /var/lib
```

El instalador crea un usuario de servicio, el entorno virtual, la unidad systemd (con `ProtectSystem=strict`) y la
orden `telehome-enchufes`, que actúa sobre los datos del servicio. Los cambios hechos con esa orden se aplican al
momento, sin reiniciar. Opciones: `--puerto N`, `--host DIR`, `--allow-host NOMBRE` (proxy inverso), `--allow-origin ORIGEN` (web externa), `--quitar`.

Acceso desde tu ordenador sin abrir puertos en Azure: `ssh -L 8765:127.0.0.1:8765 usuario@tu-vm` y abre
<http://127.0.0.1:8765/>. Si prefieres publicarla con Apache (HTTPS), la interfaz funciona en una subruta:

```apache
ProxyPass        /enchufes/ http://127.0.0.1:8765/
ProxyPassReverse /enchufes/ http://127.0.0.1:8765/
```

En ese caso instala con `--allow-host tu-dominio` y pon contraseña (`sudo telehome-enchufes password`).

## Modo nube (API de Tuya)

Sirve cuando el programa no está en la misma red que los enchufes. Requisitos:

1. Los enchufes deben estar en **Smart Life** o **Tuya Smart**. Con la app de marca **Energeeks 3.0** el enlace con la
   plataforma de Tuya normalmente **no funciona** (son cuentas de otro sistema); en ese caso hay que restablecer cada
   enchufe con su botón y emparejarlo en Smart Life (la ficha de Energeeks lo admite).
2. Cuenta en [iot.tuya.com](https://iot.tuya.com) → *Cloud → Create Cloud Project* (tipo **Smart Home**, centro de
   datos **Central Europe** para España). Suscribe *IoT Core* y *Authorization* (plan de prueba gratuito) y
   **autoriza tu proyecto** a usarlos: *Cloud Services → IoT Core → View Details → Authorized Projects → Add
   Authorization* (o, en el proyecto, *Service API → Go to Authorize*); la columna *Authorized Projects* debe mostrar
   tu proyecto.
3. En el proyecto: *Devices → Link Tuya App Account → Add App Account* y escanea el QR desde la pestaña «Yo» de
   Smart Life. Deben aparecer tus enchufes.
   **Para poder encender y apagar**, en esa misma lista pulsa *Change* en la columna *Device Permission* de cada
   enchufe y elige **Controllable**: con *Read* (lo que suele salir por defecto) solo se puede leer y Tuya responde
   «No permissions. This project is not authorized to call this API» al conmutar.
4. Copia el **Access ID** y el **Access Secret** (pestaña *Overview*) en *Ajustes → Nube de Tuya*, pulsa
   *Ver dispositivos de la nube* y añádelos; o por línea de órdenes:
   `telehome-enchufes cloud-setup --region eu --access-id …` y `telehome-enchufes cloud-import`.

Notas:

- El plan gratuito de IoT Core **caduca al mes**: se renueva en la consola de Tuya (*Extend trial period*). Si
  caduca, los enchufes en modo nube aparecen «sin conexión» con el error de la API hasta renovarlo.
- El cupo de llamadas del plan gratuito es limitado. La app lee **todos** los enchufes de la nube con 1-2 llamadas por
  ciclo (caché compartida) y por defecto cada **300 s** (mínimo 60). *Ajustes → Opciones* muestra la estimación mensual y, desde la 0.5.1, las llamadas reales
  que ha hecho el servicio cada día (hoy, ayer, mes, últimos 30 días y gráfico). Se guardan en la base de datos
  (`telemetria.sqlite3`, tabla `api_calls`) y salen en `api/state` → `cloud` (`today`, `yesterday`, `month`, `last30`, `by_day`).
  Tuya no indica cuántos créditos cuesta cada llamada: compara el recuento con los créditos restantes de iot.tuya.com.
- Códigos de datos por defecto: `switch_1`, `cur_power` (÷10 → W), `cur_voltage` (÷10 → V), `cur_current` (mA).
  Se ajustan por enchufe en *Avanzado*; `telehome-enchufes probe <enchufe>` muestra lo que devuelve la nube.
- Los **dispositivos virtuales** de la consola de Tuya (Device ID que empieza por `vdevo`) sirven solo para pruebas: se
  leen, pero no dan potencia, tensión ni corriente y la nube rechaza las órdenes (error 28841105). La app lo indica
  en el aviso; lo normal es no añadirlos o quitarlos.
- Al importar desde la nube también se guarda la *Local Key*, así que el enchufe puede pasarse a modo local más tarde.
- La lectura en modo nube se ha comprobado con una cuenta real de Tuya (proyecto *Smart Home*, Central Europe). Para
  leer y para conmutar el programa prueba varias formas de llamar a la API (tres para cada cosa) y se queda con la que
  el proyecto tenga autorizada. Si Tuya rechaza la orden, el mensaje incluye el código de error y, en los errores de
  permisos (28841105, 28841106, 1106), qué cambiar en iot.tuya.com.

## Dar de alta los enchufes (modo local)

Cada enchufe necesita: **Device ID**, **Local Key**, IP (o `Auto`) y versión del protocolo (normalmente 3.3 o 3.4).

1. Empareja el enchufe con la app **Smart Life / Tuya Smart** (o Energeeks 3.0).
2. Obtén la Local Key una vez con el asistente de TinyTuya (requiere una cuenta gratuita de desarrollador en
   iot.tuya.com con tu app vinculada): `.venv/bin/python -m tinytuya wizard`. Genera `devices.json` con todos tus
   dispositivos. La clave cambia si borras el enchufe de la app o lo restableces.
3. Impórtalos: botón **Ajustes → Importar devices.json**, o `python -m telehome_enchufes import devices.json`.
   También puedes añadirlos a mano y buscar IP/Device ID con **Buscar en la red** (`python -m telehome_enchufes scan`).

Con IP `Auto` la app localiza el enchufe por su Device ID y se adapta si el router le cambia la IP.
Aun así, lo ideal es reservar una IP fija para cada enchufe en el router.

### Mapa de datos (DPS)

Valores por defecto de un enchufe Tuya con medidor: interruptor `1`, corriente `18` (mA), potencia `19` (÷10 → W),
tensión `20` (÷10 → V). **No he podido verificarlos con un EG-EW008MC real**; si las lecturas salen mal, mira los DPS
crudos con `python -m telehome_enchufes probe <nombre>` y ajústalos en *Ajustes → Avanzado* de ese enchufe.

## Límites y buenas prácticas

- **Máximo 7 enchufes** en total, sumando ambos modos (límite aplicado en la configuración, la API y la interfaz).
- Los dispositivos Tuya suelen admitir **una sola conexión TCP**: cierra la app del móvil mientras uses TeleHome Enchufes.
- Intervalo de lectura local: 10 s por defecto, **mínimo 5 s** (los medidores no toleran sondeos más rápidos).
  En la nube: 300 s por defecto, mínimo 60 s.
- Si un enchufe se cae, se reintenta con espera creciente (hasta 60 s) y se registra como «sin conexión».
- Histórico: 30 días por defecto (configurable); al eliminar un enchufe se borra también su histórico.

## Datos y seguridad

- Datos en `~/Library/Application Support/telehome-enchufes/` (macOS), `~/.telehome-enchufes/` (Linux) o
  `/var/lib/telehome-enchufes/` (servicio Linux): `config.json` con permisos 600 y `telemetria.sqlite3`.
  Las *Local Keys*, el *Access Secret* de Tuya y la contraseña (PBKDF2) **nunca** salen por la API ni se suben al
  repositorio (`.gitignore`).
- La interfaz escucha en `127.0.0.1`, rechaza `Host` ajenos (DNS rebinding) y exige la cabecera `X-TeleHome` y un
  `Origin` propio en las operaciones de escritura (CSRF).
- Contraseña opcional (HTTP Basic, cualquier usuario): `telehome-enchufes password`. Por HTTP sin cifrar solo tiene
  sentido tras un túnel SSH o un proxy con HTTPS. No uses `--host 0.0.0.0` sin contraseña.

## API (JSON)

`GET /api/state` · `POST /api/devices/<id>/command {"action":"switch","value":true}` ·
`GET /api/history?dev=all&range=3600` · `GET /api/summary?range=86400` ·
`GET /api/export.csv?dev=<id>&range=86400` · `POST|PUT|DELETE /api/devices` ·
`POST /api/devices/import` · `PUT /api/options` · `POST /api/discover` · `PUT /api/cloud` ·
`POST /api/cloud/test` · `POST /api/cloud/devices` · `POST /api/cloud/import {"dev_ids":[…]}`

### Protocolo genérico de TeleHome (0.5.0)

La app genérica [TeleHome](https://rafaumh2110.github.io/apps/telemetria/home/telehome/) sirve para
varios tipos de dispositivo, no solo enchufes, y este servicio ya habla su protocolo. Nada de lo
anterior desaparece: las apps TeleHome Enchufes (web, iPhone, iPad) siguen funcionando igual.

- `GET /api/health` y `GET /api/state` añaden `"api": "telehome"` y `"types": ["enchufe"]`.
  `app` sigue siendo `TeleHome Enchufes`, así que las apps anteriores lo reconocen; la app genérica
  ve `api` y le habla directamente, sin su adaptador de compatibilidad. En `types` están los tipos que
  este servicio sabe leer: la app deshabilita en el alta los que no estén.
- Cada dispositivo lleva `type` (de momento solo `enchufe`) y `room` (estancia, opcional, hasta 24
  caracteres; la app agrupa por ella).
- Cada lectura añade el modelo común `state` y `values`, junto a los campos de siempre:

  ```json
  { "ts": 1763645000, "online": true, "error": null,
    "on": true, "power_w": 517.7, "voltage_v": 227.9, "current_a": 2.271,
    "state":  { "on": true },
    "values": { "p": 517.7, "v": 227.9, "i": 2.271 } }
  ```

  Y el acumulado del día va también en `accum` (`{"energy_today_kwh": 6.23}`).
- `POST /api/devices/<id>/command` con `{"action": "switch", "value": true|false}` es la orden
  genérica; un enchufe solo admite `switch`, y cualquier otra (`level`, `position`, `setpoint`) se
  rechaza con 400. `POST /api/plugs/<id>/power {"on":…}` se mantiene como alias.
- `GET /api/summary` devuelve los mismos datos en `devices` (nombre genérico) y en `plugs`
  (compatibilidad), y cada fila añade el bloque `m` con una entrada por magnitud
  (`{"p":{"avg","min","max"},"v":{…},"i":{…}}`) y `on_ratio`.
- En `history`, `export.csv` y `summary`, `dev=` es el nombre genérico y `plug=` sigue valiendo.
- `POST /api/cloud/import` acepta `type` y lo valida contra `types`.

Para añadir un tipo nuevo (sensor, luz, persiana): añádelo a `DEVICE_TYPES` en `config.py` con sus
campos, enséñale a `devices.py` a leer sus DPS o códigos, devuelve sus magnitudes en
`reading.values` y declara sus órdenes en `Monitor.ACTIONS`. En la app, una entrada en su catálogo
`TYPES` con las mismas claves de magnitud.

## Órdenes

`serve` (por defecto) · `scan` · `probe <enchufe>` · `import <devices.json> [--nube]` · `list` · `cloud-setup` ·
`cloud-list` · `cloud-import [ids…]` · `password [--quitar]` — ver `python -m telehome_enchufes --help`.

## Desarrollo

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```

Estructura: `telehome_enchufes/` (config, devices, cloud, store, monitor, server, cli, `static/index.html`), `macos/`
(instalador y lanzador), `linux/` (instalador con systemd), `tests/`. Convenciones: scripts y guías con guiones; los `.py` del programa conservan `_`.

---
Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es  
Generado con IA · Revisado por el autor

## Usar la API desde una web externa (`--allow-origin`)

Por defecto el servicio solo admite peticiones del mismo origen. Para que la app TeleHome publicada en otra web
(p. ej. GitHub Pages) use este servicio, autoriza su origen: `telehome_enchufes serve --allow-origin https://usuario.github.io`
(repetible; en Linux, `sudo ./linux/instalar-linux.sh --allow-origin https://usuario.github.io`). El servicio responde
al *preflight* CORS solo a esos orígenes; `Host`, `X-TeleHome` y la contraseña se siguen exigiendo. Autorizar un origen
es confiar en esa web: usa contraseña.

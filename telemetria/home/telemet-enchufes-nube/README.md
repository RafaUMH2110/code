# TeleMet Enchufes · versión nube

> **Versión «nube»** de TeleMet Enchufes (0.2.0): macOS y Linux, modo local y modo nube de Tuya, contraseña opcional. Incluye todo lo de [`telemet-enchufes-local`](../telemet-enchufes-local/) (la versión anterior, solo macOS y red local). Para probar los enchufes antes de instalar nada: [`telemet-enchufes-vscode`](../telemet-enchufes-vscode/). Cada versión es autocontenida y usa la misma carpeta de datos, así que no las instales a la vez.

Telemetría y control de enchufes Wi-Fi con medidor de consumo **Energeeks EG-EW008MC**
(el pack de 3 se vende como EG-EW009MC: son los mismos enchufes), hasta **7 enchufes**, en **macOS** o **Linux**.
Cada enchufe se lee en **modo local** (misma red) o en **modo nube** (API de Tuya, desde cualquier sitio).

- Lectura periódica de **potencia, tensión y corriente** y estado (encendido/apagado), con histórico en SQLite.
- **Encender/apagar** cada enchufe desde la interfaz.
- Energía (kWh) de hoy y por intervalo, disponibilidad, gráficas de 1 h a 30 días y exportación a CSV.
- **Modo local**: habla con los enchufes por la LAN (protocolo local de Tuya vía [TinyTuya](https://github.com/jasonacox/tinytuya)).
- **Modo nube**: lee y conmuta a través de la API de Tuya IoT, sin estar en la red de los enchufes (p. ej. en una VM de Azure).
- Interfaz web (un solo HTML, sin librerías externas) servida en `127.0.0.1`, con contraseña opcional.

## Cómo funciona

El EG-EW008MC es un dispositivo Tuya (Wi-Fi 2,4 GHz, compatible con las apps Energeeks 3.0, Tuya Smart y Smart Life).
Un navegador no puede hablar TCP/UDP con él, así que la app es un pequeño servicio Python + una interfaz HTML:

```
navegador ──HTTP──▶ telemet_enchufes (Python) ──TCP 6668──────────▶ enchufes (modo local, misma LAN)
                         │                  └──HTTPS (API Tuya)──▶ nube de Tuya ◀── enchufes (modo nube)
                         └── SQLite (telemetría)
```

## Instalación en macOS

Necesitas Python 3.9 o superior (`xcode-select --install` o `brew install python`).

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/RafaUMH2110/code.git
cd code && git sparse-checkout set telemetria/home/telemet-enchufes-nube
cd telemetria/home/telemet-enchufes-nube
./macos/instalar-macos.sh             # crea .venv e instala dependencias
./macos/instalar-macos.sh --launchd   # opcional: arranca al iniciar sesión
```

Arranque: doble clic en `macos/iniciar-telemet-enchufes.command` (abre el navegador en <http://127.0.0.1:8765/>)
o `.venv/bin/python -m telemet_enchufes`.

> En macOS reciente, la primera vez aparece un aviso para que Python acceda a la **Red local**. Debes permitirlo;
> si usas el LaunchAgent, ejecuta antes la app una vez desde el Terminal para ver ese aviso.

Prueba sin hardware: `.venv/bin/python -m telemet_enchufes serve --simulate 4` (datos simulados, carpeta de datos aparte).

## Instalación en Linux (p. ej. una VM de Azure)

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/RafaUMH2110/code.git
cd code && git sparse-checkout set telemetria/home/telemet-enchufes-nube
cd telemetria/home/telemet-enchufes-nube
sudo ./linux/instalar-linux.sh          # servicio systemd «telemet-enchufes», código en /opt, datos en /var/lib
```

El instalador crea un usuario de servicio, el entorno virtual, la unidad systemd (con `ProtectSystem=strict`) y la
orden `telemet-enchufes`, que actúa sobre los datos del servicio. Los cambios hechos con esa orden se aplican al
momento, sin reiniciar. Opciones: `--puerto N`, `--host DIR`, `--allow-host NOMBRE` (proxy inverso), `--apache NOMBRE` (ver más abajo), `--quitar`.

Acceso desde tu ordenador sin abrir puertos en Azure: `ssh -L 8765:127.0.0.1:8765 usuario@tu-vm` y abre
<http://127.0.0.1:8765/>.

### Publicar en Apache, como el resto de apps

La interfaz es un HTML estático (`telemet_enchufes/static/index.html`), así que se despliega con
[`instalar-todo`](../../../scripts/README.md) igual que las demás apps; Apache solo tiene que enrutar su API
(`api/…`) al servicio local. Son dos pasos:

1. **Interfaz**: añade la carpeta `code/telemetria/home/telemet-enchufes-nube` a la selección de
   `instalar-todo-isa.sh` (menú `-i`, o `--repos` con tu lista actual más esa carpeta; `--listar` la muestra).
   Cuidado: `--repos` **sustituye** la selección guardada. Queda en
   `/var/www/htdocs/rafa/code/telemetria/home/telemet-enchufes-nube/telemet_enchufes/static/` y el portal la lista.
2. **API**: en la máquina donde corre el servicio (Apache y servicio, en la misma máquina):

   ```bash
   sudo telemet-enchufes password                      # obligatoria: la API enciende y apaga enchufes
   sudo ./linux/instalar-linux.sh --apache isa.umh.es  # --docroot y --ruta-web si difieren de los valores por defecto
   ```

   El instalador activa los módulos `proxy` y `proxy_http`, escribe `/etc/apache2/conf-available/telemet-enchufes.conf`
   (`ProxyPass` de `…/api/` a `127.0.0.1:8765` y un alias corto), comprueba la configuración y recarga Apache.
   **Si no hay contraseña, deja la configuración preparada pero sin activar**: ponla y vuelve a ejecutar el instalador.
   El nombre del servidor se añade a `--allow-host`.

Direcciones resultantes: `https://isa.umh.es/rafa/enchufes/` (corta) y la ruta larga del despliegue. La contraseña la
pide el propio servicio (HTTP Basic) al primer acceso a la API. `--quitar` elimina también la configuración de Apache.

## Modo nube (API de Tuya)

Sirve cuando el programa no está en la misma red que los enchufes. Requisitos:

1. Los enchufes deben estar en **Smart Life** o **Tuya Smart**. Con la app de marca **Energeeks 3.0** el enlace con la
   plataforma de Tuya normalmente **no funciona** (son cuentas de otro sistema); en ese caso hay que restablecer cada
   enchufe con su botón y emparejarlo en Smart Life (la ficha de Energeeks lo admite).
2. Cuenta en [iot.tuya.com](https://iot.tuya.com) → *Cloud → Create Cloud Project* (tipo **Smart Home**, centro de
   datos **Central Europe** para España). Suscribe *IoT Core* y *Authorization* (plan de prueba gratuito).
3. En el proyecto: *Devices → Link Tuya App Account → Add App Account* y escanea el QR desde la pestaña «Yo» de
   Smart Life. Deben aparecer tus enchufes.
4. Copia el **Access ID** y el **Access Secret** (pestaña *Overview*) en *Ajustes → Nube de Tuya*, pulsa
   *Ver dispositivos de la nube* y añádelos; o por línea de órdenes:
   `telemet-enchufes cloud-setup --region eu --access-id …` y `telemet-enchufes cloud-import`.

Notas:

- El plan gratuito de IoT Core **caduca al mes**: se renueva en la consola de Tuya (*Extend trial period*). Si
  caduca, los enchufes en modo nube aparecen «sin conexión» con el error de la API hasta renovarlo.
- El cupo de llamadas del plan gratuito es limitado. La app lee **todos** los enchufes de la nube con 1-2 llamadas por
  ciclo (caché compartida) y por defecto cada **300 s** (mínimo 60). *Ajustes → Opciones* muestra la estimación mensual.
- Códigos de datos por defecto: `switch_1`, `cur_power` (÷10 → W), `cur_voltage` (÷10 → V), `cur_current` (mA).
  Se ajustan por enchufe en *Avanzado*; `telemet-enchufes probe <enchufe>` muestra lo que devuelve la nube.
- Al importar desde la nube también se guarda la *Local Key*, así que el enchufe puede pasarse a modo local más tarde.
- **El modo nube está probado con un cliente simulado, no contra una cuenta real de Tuya.** El programa prueba tres
  formas de consulta de la API y se queda con la que funcione; si algo falla, el error de Tuya se ve en la tarjeta.

## Dar de alta los enchufes (modo local)

Cada enchufe necesita: **Device ID**, **Local Key**, IP (o `Auto`) y versión del protocolo (normalmente 3.3 o 3.4).

1. Empareja el enchufe con la app **Smart Life / Tuya Smart** (o Energeeks 3.0).
2. Obtén la Local Key una vez con el asistente de TinyTuya (requiere una cuenta gratuita de desarrollador en
   iot.tuya.com con tu app vinculada): `.venv/bin/python -m tinytuya wizard`. Genera `devices.json` con todos tus
   dispositivos. La clave cambia si borras el enchufe de la app o lo restableces.
3. Impórtalos: botón **Ajustes → Importar devices.json**, o `python -m telemet_enchufes import devices.json`.
   También puedes añadirlos a mano y buscar IP/Device ID con **Buscar en la red** (`python -m telemet_enchufes scan`).

Con IP `Auto` la app localiza el enchufe por su Device ID y se adapta si el router le cambia la IP.
Aun así, lo ideal es reservar una IP fija para cada enchufe en el router.

### Mapa de datos (DPS)

Valores por defecto de un enchufe Tuya con medidor: interruptor `1`, corriente `18` (mA), potencia `19` (÷10 → W),
tensión `20` (÷10 → V). **No he podido verificarlos con un EG-EW008MC real**; si las lecturas salen mal, mira los DPS
crudos con `python -m telemet_enchufes probe <nombre>` y ajústalos en *Ajustes → Avanzado* de ese enchufe.

## Límites y buenas prácticas

- **Máximo 7 enchufes** en total, sumando ambos modos (límite aplicado en la configuración, la API y la interfaz).
- Los dispositivos Tuya suelen admitir **una sola conexión TCP**: cierra la app del móvil mientras uses TeleMet Enchufes.
- Intervalo de lectura local: 10 s por defecto, **mínimo 5 s** (los medidores no toleran sondeos más rápidos).
  En la nube: 300 s por defecto, mínimo 60 s.
- Si un enchufe se cae, se reintenta con espera creciente (hasta 60 s) y se registra como «sin conexión».
- Histórico: 30 días por defecto (configurable); al eliminar un enchufe se borra también su histórico.

## Datos y seguridad

- Datos en `~/Library/Application Support/telemet-enchufes/` (macOS), `~/.telemet-enchufes/` (Linux) o
  `/var/lib/telemet-enchufes/` (servicio Linux): `config.json` con permisos 600 y `telemetria.sqlite3`.
  Las *Local Keys*, el *Access Secret* de Tuya y la contraseña (PBKDF2) **nunca** salen por la API ni se suben al
  repositorio (`.gitignore`).
- La interfaz escucha en `127.0.0.1`, rechaza `Host` ajenos (DNS rebinding) y exige la cabecera `X-TeleMet` y un
  `Origin` propio en las operaciones de escritura (CSRF).
- Contraseña opcional (HTTP Basic, cualquier usuario): `telemet-enchufes password`. Por HTTP sin cifrar solo tiene
  sentido tras un túnel SSH o un proxy con HTTPS. No uses `--host 0.0.0.0` sin contraseña.

## API (JSON)

`GET /api/state` · `POST /api/plugs/<id>/power {"on":true}` · `GET /api/history?plug=all&range=3600` ·
`GET /api/summary?range=86400` · `GET /api/export.csv?plug=<id>&range=86400` · `POST|PUT|DELETE /api/devices` ·
`POST /api/devices/import` · `PUT /api/options` · `POST /api/discover` · `PUT /api/cloud` ·
`POST /api/cloud/test` · `POST /api/cloud/devices` · `POST /api/cloud/import {"dev_ids":[…]}`

## Órdenes

`serve` (por defecto) · `scan` · `probe <enchufe>` · `import <devices.json> [--nube]` · `list` · `cloud-setup` ·
`cloud-list` · `cloud-import [ids…]` · `password [--quitar]` — ver `python -m telemet_enchufes --help`.

## Desarrollo

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```

Estructura: `telemet_enchufes/` (config, devices, cloud, store, monitor, server, cli, `static/index.html`), `macos/`
(instalador y lanzador), `linux/` (instalador con systemd), `tests/`. Convenciones: scripts y guías con guiones; los `.py` del programa conservan `_`.

---
Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es  
Generado con IA · Revisado por el autor

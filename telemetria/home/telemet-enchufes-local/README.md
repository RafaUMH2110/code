# TeleMet Enchufes · versión local

> **Versión «local»** de TeleMet Enchufes (0.1.0): solo macOS y solo red local. Hermanas: [`telemet-enchufes-nube`](../telemet-enchufes-nube/) (añade modo nube, Linux y contraseña; es la que sirve para una VM de Azure) y [`telemet-enchufes-vscode`](../telemet-enchufes-vscode/) (pruebas preliminares por línea de órdenes). Cada versión es autocontenida y usa la misma carpeta de datos, así que no las instales a la vez.

Telemetría y control **en red local** de enchufes Wi-Fi con medidor de consumo **Energeeks EG-EW008MC**
(el pack de 3 se vende como EG-EW009MC: son los mismos enchufes), para **macOS**, hasta **7 enchufes**.

- Lectura periódica de **potencia, tensión y corriente** y estado (encendido/apagado), con histórico en SQLite.
- **Encender/apagar** cada enchufe desde la interfaz.
- Energía (kWh) de hoy y por intervalo, disponibilidad, gráficas de 1 h a 30 días y exportación a CSV.
- Todo **local**: habla con los enchufes por la LAN (protocolo local de Tuya vía [TinyTuya](https://github.com/jasonacox/tinytuya)); no usa la nube salvo una vez, para obtener la *Local Key*.
- Interfaz web (un solo HTML, sin librerías externas) servida solo en `127.0.0.1`.

## Cómo funciona

El EG-EW008MC es un dispositivo Tuya (Wi-Fi 2,4 GHz, compatible con las apps Energeeks 3.0, Tuya Smart y Smart Life).
Un navegador no puede hablar TCP/UDP con él, así que la app es un pequeño servicio Python + una interfaz HTML:

```
navegador ──HTTP──▶ telemet_enchufes (Python, en tu Mac) ──TCP 6668──▶ enchufes Tuya (LAN)
                         └── SQLite (telemetría)
```

## Instalación en macOS

Necesitas Python 3.9 o superior (`xcode-select --install` o `brew install python`).

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/RafaUMH2110/code.git
cd code && git sparse-checkout set telemetria/home/telemet-enchufes-local
cd telemetria/home/telemet-enchufes-local
./macos/instalar-macos.sh             # crea .venv e instala dependencias
./macos/instalar-macos.sh --launchd   # opcional: arranca al iniciar sesión
```

Arranque: doble clic en `macos/iniciar-telemet-enchufes.command` (abre el navegador en <http://127.0.0.1:8765/>)
o `.venv/bin/python -m telemet_enchufes`.

> En macOS reciente, la primera vez aparece un aviso para que Python acceda a la **Red local**. Debes permitirlo;
> si usas el LaunchAgent, ejecuta antes la app una vez desde el Terminal para ver ese aviso.

Prueba sin hardware: `.venv/bin/python -m telemet_enchufes serve --simulate 4` (datos simulados, carpeta de datos aparte).

## Dar de alta los enchufes

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

- **Máximo 7 enchufes** (límite aplicado en la configuración, la API y la interfaz).
- Los dispositivos Tuya suelen admitir **una sola conexión TCP**: cierra la app del móvil mientras uses TeleMet Enchufes.
- Intervalo de lectura: 10 s por defecto, **mínimo 5 s** (los medidores de energía no toleran sondeos más rápidos).
- Si un enchufe se cae, se reintenta con espera creciente (hasta 60 s) y se registra como «sin conexión».
- Histórico: 30 días por defecto (configurable); al eliminar un enchufe se borra también su histórico.

## Datos y seguridad

- Datos en `~/Library/Application Support/telemet-enchufes/` (`config.json` con permisos 600, `telemetria.sqlite3`).
  Las *Local Keys* **nunca** salen por la API ni se suben al repositorio (`.gitignore`).
- La interfaz solo escucha en `127.0.0.1`, rechaza `Host` ajenos (DNS rebinding) y exige la cabecera `X-TeleMet`
  en las operaciones de escritura (CSRF). Con `--host 0.0.0.0` queda abierta a la red **sin contraseña**: no lo hagas
  en redes que no controles.

## API (JSON)

`GET /api/state` · `POST /api/plugs/<id>/power {"on":true}` · `GET /api/history?plug=all&range=3600` ·
`GET /api/summary?range=86400` · `GET /api/export.csv?plug=<id>&range=86400` · `POST|PUT|DELETE /api/devices` ·
`POST /api/devices/import` · `PUT /api/options` · `POST /api/discover`

## Órdenes

`serve` (por defecto) · `scan` · `probe <enchufe>` · `import <devices.json>` · `list` — ver `python -m telemet_enchufes --help`.

## Desarrollo

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```

Estructura: `telemet_enchufes/` (config, devices, store, monitor, server, cli, `static/index.html`), `macos/` (instalador y
lanzador), `tests/`. Convenciones: scripts y guías con guiones; los `.py` del programa conservan `_`.

---
Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es  
Generado con IA · Revisado por el autor

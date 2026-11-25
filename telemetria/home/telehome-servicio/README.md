# TeleHome

> TeleHome (0.10.0): enchufes y luces (bombillas y tiras LED regulables, blancos y color), macOS y Linux, modo local y modo nube de Tuya, contraseña opcional. Sustituye a la antigua versión «local» (0.1.0, solo macOS y red local), que ya está incluida aquí: el modo local funciona igual y el modo nube es opcional. Para probar los enchufes antes de instalar nada: [`telehome-pruebas`](../telehome-pruebas/).

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
navegador ──HTTP──▶ telehome (Python) ──TCP 6668──────────▶ enchufes (modo local, misma LAN)
                         │                  └──HTTPS (API Tuya)──▶ nube de Tuya ◀── enchufes (modo nube)
                         └── SQLite (telemetría)
```

## Instalación en macOS

Necesitas Python 3.9 o superior (`xcode-select --install` o `brew install python`).

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/RafaUMH2110/code.git
cd code && git sparse-checkout set telemetria/home/telehome-servicio
cd telemetria/home/telehome-servicio
./macos/instalar-macos.sh             # crea .venv e instala dependencias
./macos/instalar-macos.sh --launchd   # opcional: arranca al iniciar sesión
```

Arranque: doble clic en `macos/iniciar-telehome.command` (abre el navegador en <http://127.0.0.1:8765/>)
o `.venv/bin/python -m telehome`.

> En macOS reciente, la primera vez aparece un aviso para que Python acceda a la **Red local**. Debes permitirlo;
> si usas el LaunchAgent, ejecuta antes la app una vez desde el Terminal para ver ese aviso.

Prueba sin hardware: `.venv/bin/python -m telehome serve --simulate 4` (datos simulados, carpeta de datos aparte).

## Instalación en Linux (p. ej. una VM de Azure)

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/RafaUMH2110/code.git
cd code && git sparse-checkout set telemetria/home/telehome-servicio
cd telemetria/home/telehome-servicio
sudo ./linux/instalar-linux.sh          # servicio systemd «telehome», código en /opt/telehome, datos en /var/lib/telehome
```

El instalador crea un usuario de servicio, el entorno virtual, la unidad systemd (con `ProtectSystem=strict`) y la
orden `telehome`, que actúa sobre los datos del servicio. Los cambios hechos con esa orden se aplican al
momento, sin reiniciar. Opciones: `--puerto N`, `--host DIR`, `--allow-host NOMBRE` (proxy inverso), `--allow-origin ORIGEN` (web externa), `--quitar`.

Desde la 0.5.4, cuando hay varios enchufes, la gráfica dibuja una mini-gráfica por enchufe, cada una con su propia escala vertical y
todas con el mismo eje de tiempo, de modo que un enchufe de 1.800 W ya no aplasta a los de 4 W. El selector «Escala» (Por enchufe / Común)
permite volver a una sola gráfica con una escala compartida; la elección se guarda en el navegador y el cursor y el cuadro de valores
siguen mostrando todos los enchufes a la vez.

Desde la 0.5.3 la gráfica recuerda el intervalo elegido (1 h … 30 días; se guarda en el navegador), dibuja las líneas aunque las
lecturas por nube estén separadas 1-5 min (antes solo se veía el último punto en 1 h y 6 h) y la «Energía hoy» ya no se pone casi a
cero al reiniciar el servicio con lecturas por nube.

Desde la 0.5.2 el servicio se llama **`telehome`** (antes `telehome-enchufes`). Si ya lo tenías instalado, vuelve a ejecutar
el instalador: retira la unidad y la orden antiguas, mueve `/var/lib/telehome-enchufes` a `/var/lib/telehome`, renombra el
usuario de servicio y recrea el entorno virtual, sin perder configuración, credenciales ni histórico. En macOS el
LaunchAgent pasa a `es.umh.telehome` (registro `~/Library/Logs/telehome.log`).

Acceso desde tu ordenador sin abrir puertos en Azure: `ssh -L 8765:127.0.0.1:8765 usuario@tu-vm` y abre
<http://127.0.0.1:8765/>. Si prefieres publicarla con Apache (HTTPS), la interfaz funciona en una subruta:

```apache
ProxyPass        /enchufes/ http://127.0.0.1:8765/
ProxyPassReverse /enchufes/ http://127.0.0.1:8765/
```

En ese caso instala con `--allow-host tu-dominio` y pon contraseña (`sudo telehome password`).

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
   `telehome cloud-setup --region eu --access-id …` y `telehome cloud-import`.

Notas:

- El plan gratuito de IoT Core **caduca al mes**: se renueva en la consola de Tuya (*Extend trial period*). Si
  caduca, los enchufes en modo nube aparecen «sin conexión» con el error de la API hasta renovarlo.
- El cupo de llamadas del plan gratuito es limitado. La app lee **todos** los enchufes de la nube con 1-2 llamadas por
  ciclo (caché compartida) y por defecto cada **300 s** (mínimo 60). *Ajustes → Opciones* muestra la estimación mensual y, desde la 0.5.1, las llamadas reales
  que ha hecho el servicio cada día (hoy, ayer, mes, últimos 30 días y gráfico). Se guardan en la base de datos
  (`telemetria.sqlite3`, tabla `api_calls`) y salen en `api/state` → `cloud` (`today`, `yesterday`, `month`, `last30`, `by_day`).
  El uso oficial de la cuenta está en iot.tuya.com → *Cloud → Usage* (*API Statistics*): compara ambos recuentos. Los
  créditos que se ven en la portada de la consola son de **Cobuilder** (IA para paneles, manuales, etc.) y no se gastan
  con estas llamadas. Según la ficha de Tuya, el plan de prueba de IoT Core permite unas 26 000 llamadas al mes (sin acumular).
- Códigos de datos por defecto: `switch_1`, `cur_power` (÷10 → W), `cur_voltage` (÷10 → V), `cur_current` (mA).
  Se ajustan por enchufe en *Avanzado*; `telehome probe <enchufe>` muestra lo que devuelve la nube.
- Los **dispositivos virtuales** de la consola de Tuya (Device ID que empieza por `vdevo`) sirven solo para pruebas: se
  leen, pero no dan potencia, tensión ni corriente y la nube rechaza las órdenes (error 28841105). La app lo indica
  en el aviso; lo normal es no añadirlos o quitarlos.
- Al importar desde la nube también se guarda la *Local Key*, así que el enchufe puede pasarse a modo local más tarde.
- La lectura en modo nube se ha comprobado con una cuenta real de Tuya (proyecto *Smart Home*, Central Europe). Para
  leer y para conmutar el programa prueba varias formas de llamar a la API (tres para cada cosa) y se queda con la que
  el proyecto tenga autorizada. Si Tuya rechaza la orden, el mensaje incluye el código de error y, en los errores de
  permisos (28841105, 28841106, 1106), qué cambiar en iot.tuya.com.
- **Actualizar ahora** (0.9.4): el servicio lee la nube cada `cloud_poll_interval` (300 s por defecto), así que un
  cambio hecho con otra app (la de Tuya, por ejemplo) no aparece hasta el siguiente ciclo. El botón **Actualizar** de
  *Dispositivos* llama a `POST /api/refresh`, que descarta la caché de la nube y lee **todos** los dispositivos a la vez
  (una sola llamada a Tuya para todos los de la nube; los locales se leen en paralelo). Lo puede pulsar cualquiera que
  pueda ver el estado (no hace falta ser usuario ni administrador, porque solo lee). Se admite como mucho una vez cada
  5 s: si se repite antes, responde `{"refrescado": false, "espera": n}` sin llamar a Tuya, de modo que no gasta cuota
  por pulsar de más. Cada actualización cuenta como una llamada más en el recuento de la cuota de Tuya. Los servicios
  anteriores a la 0.9.4 no tienen esta ruta: la app lo detecta (404) y solo vuelve a pedir el estado.
- **Mensajes de error** (0.9.2): los fallos de red ya no se enseñan tal como los suelta la librería
  (`HTTPSConnectionPool… NameResolutionError…`). Se traducen a una frase que explica qué pasó y qué mirar
  (sin DNS, sin salida por el puerto 443, proxy, certificado, tiempo agotado, conexión cortada), nombrando el
  servidor de Tuya al que no se llegó. El texto técnico sigue estando: en la interfaz, plegado bajo
  «Detalle técnico», y entero en el registro del servicio (`journalctl -u telehome`). Lo mismo se aplica a los
  enchufes en **modo local** y al inicio de sesión fallido, que ahora dice si lo que hay que revisar son las
  credenciales o el centro de datos.

## Dar de alta los enchufes (modo local)

Cada enchufe necesita: **Device ID**, **Local Key**, IP (o `Auto`) y versión del protocolo (normalmente 3.3 o 3.4).

1. Empareja el enchufe con la app **Smart Life / Tuya Smart** (o Energeeks 3.0).
2. Obtén la Local Key una vez con el asistente de TinyTuya (requiere una cuenta gratuita de desarrollador en
   iot.tuya.com con tu app vinculada): `.venv/bin/python -m tinytuya wizard`. Genera `devices.json` con todos tus
   dispositivos. La clave cambia si borras el enchufe de la app o lo restableces.
3. Impórtalos: botón **Ajustes → Importar devices.json**, o `python -m telehome import devices.json`.
   También puedes añadirlos a mano y buscar IP/Device ID con **Buscar en la red** (`python -m telehome scan`).

Con IP `Auto` la app localiza el enchufe por su Device ID y se adapta si el router le cambia la IP.
Aun así, lo ideal es reservar una IP fija para cada enchufe en el router.

### Mapa de datos (DPS)

Valores por defecto de un enchufe Tuya con medidor: interruptor `1`, corriente `18` (mA), potencia `19` (÷10 → W),
tensión `20` (÷10 → V). **No he podido verificarlos con un EG-EW008MC real**; si las lecturas salen mal, mira los DPS
crudos con `python -m telehome probe <nombre>` y ajústalos en *Ajustes → Avanzado* de ese enchufe.

## Luces (bombillas y tiras LED, 0.10.0)

Además de enchufes, TeleHome maneja **luces** Tuya (tipo `luz`): encendido, brillo, blanco cálido/frío, color y
modo. Se dan de alta igual que un enchufe (modo nube o local) y las apps (web genérica, iPhone, iPad) les muestran un
panel propio: interruptor, brillo, deslizador cálido↔frío, tono e intensidad del color, colores y blancos rápidos.

**Unidades.** Las apps y la API hablan siempre en las mismas unidades, sea cual sea la escala de la bombilla:
`level` 0-100 (0 apaga), `temp` 0-100 (0 cálido, 100 frío), `color` como `"#rrggbb"` (o `{"h":0-360,"s":0-100,"v":0-100}`),
`mode` `"white"` o `"colour"`. El servicio convierte a los códigos de Tuya: `switch_led`, `work_mode`,
`bright_value_v2` (10-1000), `temp_value_v2` (0-1000) y `colour_data_v2` (`{"h","s","v"}`, s y v en 0-1000); en modo
local, los DPS 20-24. Las bombillas con códigos antiguos (`bright_value`, `temp_value`, `colour_data`, escala 0-255) se
detectan solas y no hay que tocar nada. El brillo mínimo es 1 %: para apagar se usa `switch`.

**Órdenes** (`POST /api/devices/<id>/command {"action":…,"value":…}`):

| acción | valor | efecto |
|---|---|---|
| `switch` | `true` / `false` | enciende o apaga |
| `level` | 0-100 | brillo (0 = apagar); en modo color es el brillo del color |
| `temp` | 0-100 | pasa a modo blanco con ese tono (0 cálido, 100 frío) |
| `color` | `"#rrggbb"` o `{h,s,v}` | pasa a modo color |
| `mode` | `white` / `colour` | cambia de modo sin tocar el resto |

`level`, `temp` y `color` encienden la luz si estaba apagada; `mode` no. En la nube, todos los códigos de una orden
van en **una sola** llamada a Tuya. La respuesta incluye el estado completo de la luz.

**Lectura.** `reading.state` lleva `on`, `br`, `temp`, `mode`, `color {h,s,v}` y `hex`; `reading.values` solo `br`
(0 si está apagada). Cada dispositivo añade `caps` (`mode`, `level`, `temp`, `color`) con lo que **esa** bombilla sabe
hacer, deducido de los códigos que devuelve: una bombilla solo blanca no muestra el selector de color. El brillo se
guarda en el histórico (`br`), en el resumen (`m.br`) y en el CSV (`brillo_pct`).

**Programaciones.** Admiten `switch`, `level`, `temp`, `color` y `mode` para luces (p. ej. «a las 21:00, blanco cálido al
30 %»: dos programaciones, `temp` 10 y `level` 30), y la condición puede usar la métrica `br`.

**Importar.** Al importar desde la nube el tipo sale de la categoría de Tuya (`dj`, `dd`, `xdd`, `fwd`, `dc`, `tgq` → luz;
el resto → enchufe); un `type` explícito manda sobre la categoría. **Si ya tenías una bombilla dada de alta como
«enchufe»** (las versiones anteriores a la 0.10.0 lo hacían), el servicio se da cuenta de que responde como luz, la
convierte a `luz` por sí solo (cambia sus códigos, conserva nombre, estancia, Device ID y clave) y sigue. También se puede
cambiar a mano: *Editar* → tipo. El tope de 7 dispositivos cuenta enchufes y luces juntos.

**Límites.** El modo local de las luces solo está probado con simulaciones de la bombilla (las bombillas del autor
funcionan por la nube); si algún DPS no coincide, se ajustan en *Avanzado* igual que los del enchufe
(`dp_switch`, `dp_mode`, `dp_level`, `dp_temp`, `dp_color`). Los colores de las escenas y de la música de Tuya no se
manejan: TeleHome puede poner esos modos (0.11.0) pero no editarlos.

## TeleHome Pro: escenas, grupos, transiciones y temporizadores (0.11.0 y 0.12.0)

La versión 0.11.0 añade, sin tocar lo anterior, lo que usa la app **TeleHome Pro** (`telemetria/home/telehome-pro`
del repo `apps`). Las apps anteriores siguen funcionando igual; las nuevas se activan según `features`
(`["luces","escenas","grupos","transiciones","temporizadores","parametros-luz"]`, más
`"escena-puntual"`, `"escena-transicion"` y `"temporizador-persistente"` desde la 0.12.0) en `GET /api/health` y
`GET /api/state`.

- **Escenas** (máx. 24). Una escena es una lista de `items` `{device, on, mode, level, temp, color}`; aplicarla manda a
  cada dispositivo su orden **en paralelo** (en la nube, una sola llamada a Tuya por dispositivo). Si uno falla, los
  demás se aplican y la respuesta dice cuál (`resultados`).
  `POST /api/scenes` · `PUT|DELETE /api/scenes/<id>` · `POST /api/scenes/<id>/apply`. Aplicar es de usuario de
  confianza; crear, editar y borrar, de administrador.
  Desde la 0.12.0, aplicar admite `{"fade": segundos}`: el color o el blanco se ponen ya y el brillo llega poco a
  poco (desde donde esté la luz, o desde el 1 % si estaba apagada). Y `POST /api/scenes/apply {"items":[…],"fade"?}`
  aplica una **escena puntual** que no se guarda: es lo que usan el «Deshacer» y las acciones rápidas de la app.
- **Grupos** (máx. 8). Una lista de dispositivos que se manejan juntos: `POST /api/groups/<id>/command
  {"action","value","fade"?}`. Los miembros que no admiten la orden (un enchufe no tiene brillo) se saltan; solo si
  ninguno la admite es un error. `POST /api/groups` · `PUT|DELETE /api/groups/<id>`.
- **Transiciones.** `level`, `temp` y `color` aceptan `"fade": segundos` (0-3600): la luz va poco a poco al nuevo valor.
  Se hace por pasos: como mínimo **4 s entre pasos por la nube** y **1,5 s en local**, y nunca más de 20 pasos. Cada paso es
  una orden y, por la nube, **una llamada a Tuya**: una transición de un minuto cuesta unas 15 llamadas, no 60. Una
  orden manual sobre esa luz cancela la transición. `GET /api/state` lista las que están en curso en `fades`.
- **Temporizadores.** `POST /api/devices/<id>/timer {"minutes":1-1440,"action":"off"|"on","fade"?}` apaga o enciende
  **cualquier dispositivo** (también un enchufe; ahí la transición se ignora) dentro de N minutos: uno por
  dispositivo, poner otro sustituye al anterior, y `DELETE` lo cancela. Los pendientes salen en `timers`.
  Desde la 0.12.0 **se guardan en el fichero de configuración**, así que un reinicio no los pierde: al arrancar, los
  que vencieron mientras el servicio estaba parado se ejecutan si fue hace menos de 15 minutos y se descartan si
  fue hace más. Para algo a una hora fija siguen estando las programaciones.
- **Programaciones.** Admiten la acción `scene` (`value` = id de la escena, sin dispositivo), el destino `grupo:<id>` y
  el campo `fade`, que desde la 0.12.0 vale también para una escena. Con escenas y grupos no hay condiciones.
- **Parámetros de la bombilla** (`PUT /api/devices/<id>`, administrador): `level_min` y `level_max` (1-100; TeleHome
  recorta el brillo antes de mandarlo, p. ej. un máximo del 60 % convierte «100» en 60), y `kelvin_min` y `kelvin_max`
  (solo para que las apps muestren «2 700 K» en vez de un porcentaje; no se mandan a la bombilla). Los códigos y escalas
  de Tuya (`code_*`, `dp_*`, `scale_*`) siguen siendo ajustables como antes.
- **Modos de Tuya.** `mode` admite también `scene` y `music` (la bombilla pone la escena o el modo música que tenga
  guardados en la app de Tuya; TeleHome no cambia esos colores). No están verificados con bombillas reales.
- **Datos crudos.** `GET /api/devices/<id>/raw` (administrador) pregunta a la bombilla qué códigos (nube) o DPS (local)
  devuelve, para ajustar los parámetros avanzados. Por la nube cuesta una llamada a Tuya.
- **Ligereza.** Todo lo que ocurre «con el tiempo» (transiciones y temporizadores) vive en **un solo hilo** que duerme
  mientras no haya nada pendiente. Sin uso, no gasta CPU ni hace llamadas.
- **Límites a la vista.** `GET /api/health` y `GET /api/state` traen `limits` (`max_fade`, `max_timer`, `max_scenes`,
  `max_groups`, `max_schedules`, `max_devices`, `fade_max_steps`, `fade_step_cloud`, `fade_step_local`): así la app
  avisa de lo que va a costar una transición en vez de llevar los topes a mano.
- La exportación e importación de la configuración incluyen escenas y grupos; al borrar un dispositivo se quita de
  las escenas y los grupos (y desaparecen los que se quedan vacíos).

## Estancias (0.13.0)

La estancia de un dispositivo (`room`) deja de ser un texto suelto y pasa a ser una **lista con nombre y orden** que
se maneja desde la app (*Ajustes → Estancias*, en TeleHome Pro). Las apps la usan para agrupar («Por estancia») y para
ofrecer un desplegable al dar de alta o editar un dispositivo, en vez de tener que escribirla bien cada vez.

- Hasta 24 estancias. `GET /api/state` las trae en `rooms` (`[{"id","name","devices"}]`, con cuántos dispositivos
  tiene cada una) y en el orden en que deben enseñarse.
- `POST /api/rooms {"name":"Salón"}` crea · `PUT /api/rooms/<id> {"name":"…"}` renombra · `DELETE /api/rooms/<id>`
  borra · `PUT /api/rooms {"ids":[…]}` ordena. Todo de administrador.
- **Renombrar cambia también la estancia de sus dispositivos**, y la respuesta dice a cuántos ha afectado. El `id` no
  cambia al renombrar. **Borrar** deja a sus dispositivos sin estancia; no borra ningún dispositivo.
- No se admiten dos estancias con el mismo nombre (sin distinguir mayúsculas) y el nombre son como mucho 24
  caracteres.
- **No hay que migrar nada**: al arrancar, el servicio da de alta las estancias que ya usaran los dispositivos, y lo
  mismo cuando se escribe una nueva al guardar un dispositivo o al importar una configuración. Un dispositivo sigue
  guardando el **nombre** de su estancia, así que las apps anteriores siguen funcionando igual.
- La exportación y la importación de la configuración incluyen las estancias.

## Límites y buenas prácticas

- **Máximo 7 enchufes** en total, sumando ambos modos (límite aplicado en la configuración, la API y la interfaz).
- Los dispositivos Tuya suelen admitir **una sola conexión TCP**: cierra la app del móvil mientras uses TeleHome.
- Intervalo de lectura local: 10 s por defecto, **mínimo 5 s** (los medidores no toleran sondeos más rápidos).
  En la nube: 300 s por defecto, mínimo 60 s.
- Si un enchufe se cae, se reintenta con espera creciente (hasta 60 s) y se registra como «sin conexión».
- Histórico: 30 días por defecto (configurable); al eliminar un enchufe se borra también su histórico.

## Datos y seguridad

- Datos en `~/Library/Application Support/telehome/` (macOS), `~/.telehome/` (Linux) o
  `/var/lib/telehome/` (servicio Linux; si solo existe la carpeta con el nombre antiguo `telehome-enchufes`, se sigue usando): `config.json` con permisos 600 y `telemetria.sqlite3`.
  Las *Local Keys*, el *Access Secret* de Tuya y la contraseña (PBKDF2) **nunca** salen por la API ni se suben al
  repositorio (`.gitignore`).
- La interfaz escucha en `127.0.0.1`, rechaza `Host` ajenos (DNS rebinding) y exige la cabecera `X-TeleHome` y un
  `Origin` propio en las operaciones de escritura (CSRF).
- **Compartir la configuración** (0.6.0): `telehome export-config -o config.json` (o «Ajustes → Compartir → Exportar
  configuración») guarda los enchufes con su Local Key, el Access ID y el Access Secret de tuya.com y los ajustes
  (intervalos, retención, región) y, si se indica, la ruta por la que se llega al servicio (`--ruta /rafa/telehome/`; la interfaz y la app TeleHome la añaden solas), **sin la contraseña del servicio**. Otra persona lo carga con
  `telehome import-config config.json` (o «Compartir → Importar») y no tiene que configurar nada: por defecto reemplaza sus enchufes
  (los que ya existían conservan id e histórico); con `--anadir` solo añade los que falten. Su contraseña del servicio no se toca.
  El fichero lleva credenciales y claves: compártelo solo con quien debas (se crea con permisos 600).
- **Programaciones** (0.9.0): encienden, apagan o regulan un dispositivo **a una hora fija, al amanecer o al
  anochecer** (con desplazamiento en minutos), los días de la semana que elijas (la casilla «Todos los días» y los
  atajos «Lunes a viernes» y «Fin de semana» los marcan de golpe, desde 0.9.3); **sin ningún día marcado se
  ejecutan una sola vez** y quedan desactivadas. Las evalúa el servicio cada 20 s,
  así que funcionan sin tener ninguna app abierta. Dos refinamientos: una **condición** sobre una magnitud
  («solo si la potencia lleva 10 min por debajo de 5 W», para apagar la lavadora al acabar) y
  **«no me pises»** (`skip_if_manual`), que se salta la orden si has manejado el aparato a mano desde la vez
  anterior. Tras una parada del servicio solo se recupera lo de la última hora, para no disparar de golpe todo lo
  que tocaba de madrugada. El amanecer y el anochecer se calculan con el algoritmo del NOAA sin dependencias, a
  partir del lugar que se guarda en las opciones (`lat`/`lon`, Elche por omisión). Se gestionan en
  «Ajustes → Programaciones» y con `telehome schedules`. Máximo 32.
- **Usuario de confianza** (0.8.0): `telehome user-password` pone una tercera contraseña. Quien entre con ella puede
  **encender, apagar y regular** los enchufes, pero no cambiar la configuración ni ninguna contraseña, y `api/state`
  le oculta lo mismo que a quien solo mira. Los tres niveles son: sin contraseña **solo lectura**, con la de usuario
  **manda órdenes**, y con la de administrador **todo**. `POST /api/login` acepta cualquiera de las dos y devuelve el
  nivel; `api/state` lo trae en `sesion.nivel`. Quitarla: `telehome user-password --quitar`.
- **Modo Administrador** (0.7.0): `telehome admin-password` pone una contraseña *distinta* de la del servicio. Con ella puesta,
  quien abra la interfaz solo ve las lecturas de los dispositivos: no puede encender ni apagar nada, ni cambiar la configuración,
  y `api/state` oculta Device ID, IP, versión, mapas de datos (DPS), credenciales de Tuya y el recuento de llamadas. Para
  administrar se pulsa «Administrador» en la cabecera y se escribe la contraseña: el servicio devuelve un token
  (cabecera `X-TeleHome-Admin`) que dura 12 h y vive solo en la pestaña. El servicio rechaza con 403 toda petición que no sea
  `GET` sin ese token, así que no basta con ocultar botones. Sin contraseña de administrador el servicio funciona como antes.
  No se exporta ni se importa con la configuración. Quitarla: `telehome admin-password --quitar`.
- Contraseña opcional (HTTP Basic, cualquier usuario): `telehome password`. Desde 0.7.1 también se cambia o se quita
  en «Ajustes → Opciones → Contraseña del servicio», estando en modo Administrador. **La actual no se puede mostrar**:
  se guarda con PBKDF2 y no hay forma de recuperarla; solo se puede sustituir por otra. Por HTTP sin cifrar solo tiene
  sentido tras un túnel SSH o un proxy con HTTPS. No uses `--host 0.0.0.0` sin contraseña.
  Desde 0.9.1 el servicio solo envía el reto `WWW-Authenticate` (el diálogo nativo del navegador) a las *navegaciones*
  (`Sec-Fetch-Dest: document`, `iframe`…); a las peticiones `fetch` de las apps responde 401 sin reto, de modo que el
  navegador no abre su ventana por sorpresa. La interfaz del propio servicio, si recibe un 401, recarga la página una vez
  para que el navegador pida la contraseña. Los navegadores que no envían `Sec-Fetch-Dest` (Safari anterior a 16.4)
  conservan el comportamiento anterior.

## API (JSON)

`GET /api/state` · `POST /api/refresh` (lectura inmediata de todos los dispositivos, 0.9.4) · `POST /api/devices/<id>/command {"action":"switch","value":true}` (las luces admiten además `level`, `temp`, `color` y `mode`, 0.10.0, y `fade`, 0.11.0) ·
`POST|PUT|DELETE /api/scenes` · `POST /api/scenes/<id>/apply` · `POST /api/scenes/apply` (escena puntual, 0.12.0) ·
`POST /api/rooms` · `PUT|DELETE /api/rooms/<id>` · `PUT /api/rooms {"ids":[…]}` (estancias, 0.13.0) · `POST|PUT|DELETE /api/groups` · `POST /api/groups/<id>/command` · `POST|DELETE /api/devices/<id>/timer` · `GET /api/devices/<id>/raw` (0.11.0, ver [Pro](#telehome-pro-escenas-grupos-transiciones-y-temporizadores-0110)) ·
`GET /api/history?dev=all&range=3600` · `GET /api/summary?range=86400` ·
`GET /api/export.csv?dev=<id>&range=86400` · `POST|PUT|DELETE /api/devices` ·
`POST /api/devices/import` · `PUT /api/options` · `POST /api/discover` · `PUT /api/cloud` ·
`POST /api/cloud/test` · `POST /api/cloud/devices` · `POST /api/cloud/import {"dev_ids":[…]}` ·
`POST /api/config/export {"ruta":"/rafa/telehome/"}` (descarga la configuración completa; por POST para exigir `X-TeleHome`; `ruta` es opcional) ·
`POST /api/config/import {"config":{…},"modo":"reemplazar"|"añadir"}` ·
`POST /api/login {"password":"…"}` (devuelve `nivel`) · `POST /api/logout` ·
`POST /api/admin/login` y `POST /api/admin/logout` (compatibilidad) ·
`PUT /api/admin/password {"password":"…"|"quitar":true}` · `PUT /api/user-password {"password":"…"|"quitar":true}` ·
`PUT /api/password {"password":"…"|"quitar":true}` (contraseña del servicio; solo administradores) ·
`GET /api/sun` · `POST /api/schedules` · `PUT|DELETE /api/schedules/<id>` · `POST /api/schedules/<id>/run` ·
`PUT /api/place {"lat":…,"lon":…}`

### Protocolo genérico de TeleHome (0.5.0)

La app genérica [TeleHome](https://rafaumh2110.github.io/apps/telemetria/home/telehome/) sirve para
varios tipos de dispositivo, no solo enchufes, y este servicio ya habla su protocolo. Nada de lo
anterior desaparece: las apps TeleHome (web, iPhone, iPad) siguen funcionando igual.

- `GET /api/health` y `GET /api/state` añaden `"api": "telehome"` y `"types": ["enchufe", "luz"]`.
  `app` es `TeleHome` (hasta la 0.9.0 era `TeleHome Enchufes`); las apps reconocen el servicio por `api` y le
  hablan directamente: su adaptador de compatibilidad solo se usa con servicios anteriores a la 0.5.0. En `types` están los tipos que
  este servicio sabe leer: la app deshabilita en el alta los que no estén.
- Cada dispositivo lleva `type` (`enchufe` o `luz`) y `room` (estancia, opcional, hasta 24
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
  rechaza con 400. Una luz admite `switch`, `level`, `temp`, `color` y `mode` (ver [Luces](#luces-bombillas-y-tiras-led-0100)). `POST /api/plugs/<id>/power {"on":…}` se mantiene como alias.
- `GET /api/summary` devuelve los mismos datos en `devices` (nombre genérico) y en `plugs`
  (compatibilidad), y cada fila añade el bloque `m` con una entrada por magnitud
  (`{"p":{"avg","min","max"},"v":{…},"i":{…}}`) y `on_ratio`.
- En `history`, `export.csv` y `summary`, `dev=` es el nombre genérico y `plug=` sigue valiendo.
- `POST /api/cloud/import` acepta `type` y lo valida contra `types`.

Para añadir un tipo nuevo (sensor, persiana; la luz ya está): añádelo a `DEVICE_TYPES` en `config.py` con sus
campos, enséñale a `devices.py` a leer sus DPS o códigos, devuelve sus magnitudes en
`reading.values` y declara sus órdenes en `Monitor.ACTIONS`. En la app, una entrada en su catálogo
`TYPES` con las mismas claves de magnitud.

## Órdenes

`serve` (por defecto) · `scan` · `probe <enchufe>` · `import <devices.json> [--nube]` · `list` · `cloud-setup` ·
`cloud-list` · `cloud-import [ids…]` · `password [--quitar]` · `admin-password [--quitar]` · `user-password [--quitar]` · `schedules [--activar ID|--desactivar ID|--borrar ID]` · `export-config [-o fichero] [--ruta /ruta/]` · `import-config <fichero> [--anadir]` — ver `python -m telehome --help`.

## Desarrollo

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```

Estructura: `telehome/` (config, devices, cloud, luces, pro, store, monitor, scheduler, server, cli, `static/index.html`), `macos/`
(instalador y lanzador), `linux/` (instalador con systemd), `tests/`. Convenciones: scripts y guías con guiones; los `.py` del programa conservan `_`.

---
Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es  
Generado con IA · Revisado por el autor

## Usar la API desde una web externa (`--allow-origin`)

Por defecto el servicio solo admite peticiones del mismo origen. Para que la app TeleHome publicada en otra web
(p. ej. GitHub Pages) use este servicio, autoriza su origen: `telehome serve --allow-origin https://usuario.github.io`
(repetible; en Linux, `sudo ./linux/instalar-linux.sh --allow-origin https://usuario.github.io`). El servicio responde
al *preflight* CORS solo a esos orígenes; `Host`, `X-TeleHome` y la contraseña se siguen exigiendo. Autorizar un origen
es confiar en esa web: usa contraseña.

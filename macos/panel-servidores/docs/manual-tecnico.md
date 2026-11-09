# Panel de Servidores · Manual técnico

*Versión 1.0 · Autor: Rafa (Dpto. de Ingeniería de Sistemas y Automática, UMH) · Generado con IA · Revisado por el autor*

Este documento explica **cómo está hecha** la aplicación y **por qué**: arquitectura, flujos, protocolos internos, decisiones de seguridad, pruebas, empaquetado y cómo extenderla. El manual de uso está en `manual-usuario.md`.

---

## 1. Visión general

| | |
|---|---|
| Lenguaje / toolkit | Python ≥ 3.10 · **PySide6** (Qt 6) |
| Plataforma objetivo | macOS (el núcleo funciona también en Linux, y es lo que se usa en las pruebas) |
| SSH | El `ssh`, `ssh-keygen` y `ssh-add` del sistema (OpenSSH). **No** se usa ninguna biblioteca SSH de Python |
| Dependencias | `PySide6` (obligatoria) · `keyring` (Llavero, opcional) · `certifi` (TLS en Python de python.org, opcional) |
| Tamaño | ≈ 6 300 líneas de aplicación (≈ 2 900 núcleo sin Qt, ≈ 3 200 interfaz) y ≈ 1 100 de pruebas |

### Principios de diseño

1. **Núcleo sin interfaz.** Todo lo que *hace cosas* vive en `nucleo/` y no importa Qt. Se prueba con `pytest`, se puede usar desde un script y la interfaz se puede rehacer sin tocarlo.
2. **No reimplementar los scripts.** El instalador y el informe se **envían al servidor y se ejecutan allí**. Así el comportamiento es exactamente el del script del repositorio y una corrección se hereda sin recompilar.
3. **OpenSSH como motor.** Se hereda gratis `~/.ssh/config`, `ProxyJump`, `ssh-agent`, claves con frase, FIDO2, `known_hosts`… y la conducta de seguridad más auditada que existe.
4. **Ningún secreto en la línea de comandos ni en disco.** Viajan por la entrada estándar del canal cifrado, por el *askpass* interno o por el entorno del proceso.
5. **Todo comando es visible.** Cada `ssh` que se lanza se anota (sin secretos) en el panel *Actividad*.

---

## 2. Estructura del proyecto

```
panel-servidores/
├── lanzador.py                  Punto de entrada para PyInstaller / ejecución directa
├── pyproject.toml · requirements*.txt
├── scripts/                     ejecutar.sh · construir-app.sh · sincronizar-recursos.sh · crear-icono.py
├── .vscode/                     launch · tasks · settings · extensions
├── docs/                        manual-usuario.md · manual-tecnico.md
├── tests/                       conftest.py · test_unitarias.py · test_ssh_integracion.py · test_ui.py · test_listar_real.py
└── src/panel_servidores/
    ├── __init__.py              Versión, nombre, autor
    ├── __main__.py · app.py     Arranque (QApplication, contexto, ventana)
    ├── rutas.py                 Dónde están los datos, los recursos y los ejecutables
    ├── recursos/                Scripts del repo incluidos + portal (index.html, favicons)
    ├── nucleo/                  ← lógica sin Qt
    └── ui/                      ← interfaz Qt
```

### 2.1 `nucleo/` (sin Qt)

| Módulo | Responsabilidad |
|---|---|
| `modelos.py` | Dataclasses: `Perfil`, `Ajustes`, `Resultado`, `FuenteSecreto`; protocolo `Interaccion`; constantes de códigos de salida |
| `almacen.py` | Persistencia atómica de perfiles/ajustes (JSON, permisos 600); importar/exportar |
| `secretos.py` | `Llavero` (keyring) y `ResolutorSecretos`: de dónde sale cada secreto y cuál se recuerda |
| `askpass.py` / `askpass_cliente.py` | Servidor (en la app) y cliente (lo ejecuta `ssh`) del puente de preguntas |
| `ssh.py` | `Conexion`: construye y ejecuta `ssh`, multiplexado, streaming, cancelación, sudo |
| `remoto.py` | Constructores **puros** de comandos para el servidor; envoltorio del instalador |
| `claves.py` | Claves locales, agente, generación; `authorized_keys` remoto; comprobación solo con clave |
| `colector.py` | Informe, auditoría de claves, resumen, servicio systemd |
| `instalador.py` | `OpcionesInstalador`, análisis del registro, `asegurar_sudo`, ejecución, cron |
| `github.py` | API pública de GitHub (repos y carpetas) y descarga de scripts |
| `recursos.py` | Resolución de los scripts incluidos / descargados / propios |
| `sshconfig.py` | Lectura de `~/.ssh/config` para importar servidores |
| `terminal.py` | Abrir Terminal/iTerm con AppleScript |
| `ansi.py` | ANSI → HTML |

### 2.2 `ui/` (Qt)

| Módulo | Responsabilidad |
|---|---|
| `hilos.py` | `Trabajo` (hilo de trabajo + cancelación) y `en_gui()` (vuelta segura al hilo de la interfaz) |
| `puente.py` | `PuenteInteraccion`: contesta a `pedir_secreto`/`confirmar` con diálogos |
| `contexto.py` | Estado compartido: perfiles, conexiones abiertas, askpass, señales |
| `widgets.py` · `estilo.py` | Consola ANSI, barra de tarea, tablas y árboles (`tabla`, `preparar_arbol`, `ajustar_columnas`), `VistaComando`, `botones_es`; `estilo`: temas claro/oscuro, roles de color, fuentes |
| `paginas/*.py` | Una pestaña por función, todas derivadas de `PaginaBase` |
| `dialogo_servidor.py` · `dialogo_ajustes.py` · `dialogo_flota.py` · `dialogo_acerca.py` | Ventanas modales (*Acerca de* usa los datos de `nucleo/acerca.py`) |
| `ventana_principal.py` | Lista, pestañas, dock de actividad, menús |

**Regla:** la interfaz solo llama a funciones de `nucleo/` dentro de un `Trabajo` y pinta el resultado.

#### Aspecto y temas (`ui/estilo.py`)

* **Un rol, no un color.** Las pestañas nunca escriben colores fijos: `estilo.poner_rol(widget, "ok" | "aviso" | "error" | "tenue" | "titulo" | "subtitulo" | "activo")`. La hoja de estilo de la aplicación (`estilo.hoja()`) asigna el color según el tema; si hace falta un color en HTML o `QColor`, `estilo.color(rol)` / `estilo.qcolor(rol)`.
* **Tema.** `estilo.es_oscuro()` mira la paleta real. `aplicar_tema("sistema" | "claro" | "oscuro")` usa `QStyleHints.setColorScheme` (Qt ≥ 6.8, de ahí `PySide6>=6.8`) y, al cambiar la paleta, vuelve a aplicar la hoja y emite `estilo.notificador.cambiado`. Quien guarde colores ya convertidos (consola ANSI, visor de informe, diagnóstico HTML, lista de servidores) se suscribe a esa señal y se repinta.
* **ANSI.** `nucleo/ansi.py` tiene dos paletas (`PALETAS`), una por tema, con contraste ≥ 4,5:1 sobre blanco y sobre gris oscuro.
* **Tablas y árboles.** Siempre se crean con `widgets.tabla(...)` / `preparar_arbol(...)`: cabeceras alineadas a la izquierda, sin resaltar, ancho de columna ≥ el de su cabecera (`sectionSizeHint`) y ≤ 460 px, texto largo abreviado por el centro con tooltip.
* **Letra de ancho fijo.** `fuente_mono()` sin argumentos = la del sistema, un punto menor que la de la interfaz; no se usan tamaños absolutos (en macOS y en Linux «11 pt» se ven distintos).
* **Textos en español.** `estilo.instalar_traduccion` carga `qtbase_es`; los diálogos propios llevan además `botones_es(...)` por si la app empaquetada no incluye la traducción.

---

## 3. Flujo de una orden SSH

```
Pestaña (hilo GUI) ─ correr(texto, funcion, al_terminar)
        │  crea Trabajo → hilo de trabajo
        ▼
funcion(trabajo) ──► nucleo.colector.generar_informe(con, …)
        ▼
Conexion.ejecutar_sudo / ejecutar
   1. _asegurar_maestro()         abre (una vez) la conexión principal ControlMaster
   2. opciones() + comando        arma: ssh <opciones> usuario@host '<comando remoto>'
   3. ejecutar_proceso()          Popen + hilos lector/escritor, timeout, cancelación
   4. Resultado(codigo, salida, error, duracion)
        ▼
en_gui(al_terminar)  ──► la pestaña pinta el resultado
```

### 3.1 Construcción de las opciones de ssh (`Conexion.opciones`)

Siempre: `-p` (si hay puerto), `ConnectTimeout=<perfil>`, `ServerAliveInterval=15`, `ForwardAgent=no`, `ForwardX11=no`, `-T`, y `-J` si hay salto. Después, las `opciones_ssh` del perfil (tal cual, con `shlex.split`) y, al final, las del multiplexado. Según el método y el modo:

| Método / modo | Opciones añadidas |
|---|---|
| auto | `LogLevel=ERROR`, `NumberOfPasswordPrompts=1` |
| clave | lo anterior + `-i <ruta>` + `IdentitiesOnly=yes` |
| password · interactiva | lo anterior + `PreferredAuthentications=keyboard-interactive,password` + `PubkeyAuthentication=no` |
| solo clave (`--check-key`) | `-v` (sin `LogLevel`: el primero que aparece gana y taparía a `-v`), `PreferredAuthentications=publickey`, `PasswordAuthentication=no`, `KbdInteractiveAuthentication=no`, `ControlPath=none` |
| huella nueva aceptada | `StrictHostKeyChecking=accept-new` (si no, el valor por defecto de ssh: preguntar) |
| desatendido | `BatchMode=yes` |

`NumberOfPasswordPrompts=1` hace que una contraseña incorrecta falle de inmediato en lugar de volver a preguntar tres veces.

### 3.2 Multiplexado (ControlMaster)

Con `perfil.multiplexar` la primera orden abre una conexión principal en segundo plano (`ControlMaster=yes`, `ControlPersist=900`, `-N -f`) con `ControlPath=/tmp/ps-ctl-xxxx/%C` (directorio 700). Las demás órdenes la reutilizan (`ControlMaster=no`): **una sola autenticación por sesión**.

Detalles que costó descubrir:

* `%C` es un hash de host+puerto+usuario+salto. `ssh -O check` y `ssh -O exit` deben recibir **las mismas opciones** que la conexión principal; si no, ssh busca otro socket y «no existe».
* El maestro se arranca con `stderr` a un fichero temporal, no a una *pipe*: `-f` deja un proceso hijo que mantiene la pipe abierta y `communicate()` no terminaría.
* `_asegurar_maestro` está protegido con un cerrojo; varias pestañas pueden pedir conexión a la vez y solo una abre el maestro.
* `ejecutar_sudo` **abre antes la conexión** y solo después lee la contraseña de sudo: si no, con «reutilizar la contraseña SSH» la contraseña aún no existe. (Fallo real detectado por las pruebas.)

### 3.3 `ejecutar_proceso`

`Popen` con `start_new_session=True` (así cancelar mata todo el grupo de procesos), un hilo que escribe la entrada estándar, hilos que leen stdout/stderr línea a línea y llaman a `on_salida`/`on_error` (streaming en vivo), y un bucle que vigila el **timeout** (código 124) y el `Cancelador` (código 130). Códigos especiales: 255 = fallo de ssh; 127 = comando no encontrado.

---

## 4. El puente *askpass*

OpenSSH, cuando necesita un dato interactivo y no hay terminal, ejecuta el programa de `SSH_ASKPASS` con la pregunta como argumento y lee la respuesta por su salida estándar. La aplicación aprovecha esto para **todas** las preguntas: contraseña, frase de la clave, código 2FA y *«¿confiar en esta huella? (yes/no)»*.

```
ssh ──(SSH_ASKPASS_REQUIRE=force)──► askpass.sh ──► python askpass_cliente.py "pregunta"
                                                         │  socket Unix privado /tmp/ps-XXXX/s (700)
                                                         ▼
                                       GestorAskpass (hilo de la app)  ──►  ResolutorSecretos.responder_askpass
                                                                                      │
                                                         diálogo Qt (PuenteInteraccion) o secreto ya conocido
```

* **Protocolo:** una línea JSON por sentido. Cliente→servidor: `{"token","prompt"}`. Servidor→cliente: `{"ok":true,"valor":"…"}` o `{"ok":false}`. Salida 0 con respuesta, 1 si se cancela (ssh lo trata como autenticación abortada).
* **Token por conexión:** cada `Conexion` (y cada operación local con `ssh-keygen`/`ssh-add`) registra su propio token y su propio *respondedor*; el socket sirve a todas. Un token desconocido recibe `ok:false`.
* **Clasificación de preguntas** (`responder_askpass`): *yes/no* de huella → `confirmar`; «passphrase» → frase; «password» → contraseña SSH (se recuerda); **cualquier otra** (códigos 2FA, PIN…) → se pregunta **siempre** y nunca se cachea.
* **Variables:** `SSH_ASKPASS`, `SSH_ASKPASS_REQUIRE=force` (OpenSSH ≥ 8.4), `DISPLAY` (para versiones antiguas que exigen que exista).
* **Modo empaquetado:** `askpass.sh` ejecuta `"<ejecutable de la app>" --askpass "$@"`; `lanzador.py`/`__main__.py` atienden `--askpass` **antes** de importar Qt.
* `askpass_cliente.py` usa **solo la biblioteca estándar** para arrancar en milisegundos.

### 4.1 Hilos y diálogos

Las preguntas llegan desde hilos no-GUI (el del askpass o el de trabajo). `PuenteInteraccion._preguntar_en_gui` publica un callable en el hilo principal (`en_gui`), muestra el diálogo y **bloquea al hilo que preguntó** con un `threading.Event`. Un cerrojo garantiza **un solo diálogo a la vez**.

---

## 5. Hilos en Qt (`ui/hilos.py`)

Qt solo permite tocar widgets desde el hilo principal. Las operaciones SSH se ejecutan en hilos de Python; para volver a la interfaz se usa `en_gui(f)`.

> **Trampa:** conectar una señal a una `lambda` ejecuta la lambda en el hilo del *emisor*. Por eso `en_gui` emite una señal de un `QObject` (`_Despachador`) que vive en el hilo principal y cuyo slot ejecuta `f`: una señal con slot de `QObject` sí se entrega en el hilo del receptor.

`Trabajo(funcion, titulo, al_terminar, al_error, al_linea, al_fin)`: `funcion(trabajo)` corre en un hilo; `trabajo.cancelador` se pasa al núcleo; `trabajo.linea()` envía salida en vivo. Las devoluciones de llamada siempre corren en el hilo de la interfaz y `al_fin` se ejecuta **después** de `al_terminar` (se vuelve a habilitar la interfaz cuando el resultado ya está pintado).

`PaginaBase.correr()` añade: una tarea a la vez por pestaña, botones deshabilitados mientras corre, barra de progreso con **Cancelar** y una entrada en el panel Actividad.

---

## 6. Comandos remotos (`nucleo/remoto.py`)

Todo lo que se ejecuta en el servidor se construye con funciones **puras** (no ejecutan nada, por eso se prueban con `sh -c` en local). Tres reglas:

1. **Todo lo externo va citado** con `shlex.quote`.
2. **El script va en un único argumento de `sh -c`** y los datos variables se pasan como parámetros posicionales (`$1`, `$2`…): no hay doble interpretación. `sh_c(script, *params)`.
3. **Los secretos nunca van en el comando.**

### 6.1 sudo sin terminal

`prefijo_sudo()` deja en `$@` el prefijo `sudo -S -p ""` si no eres root (con `set --` porque una variable perdería el argumento vacío). La contraseña llega por la entrada estándar (`-S`) en la primera línea. `como_root(orden)` = `sh -c '<prefijo> "$@" <orden>'`.

`Conexion.ejecutar_sudo`: abre la conexión, lee la contraseña (`contrasena_sudo()`), la antepone a la entrada y, si sudo la rechaza (`RE_SUDO_FALLO`) y hay usuario delante, la pide y **reintenta una vez**.

### 6.2 Informe en memoria

`comando_informe` envía el script **comprimido con zlib y en base64** dentro del propio argumento de `python3 -c`, que lo descomprime y ejecuta con `exec`, fijando `__file__` a una ruta ficticia dentro del directorio del colector (el informe busca `config.ini` junto a su propio fichero). No se escribe nada en disco.

### 6.3 Envoltorio del instalador (`_SCRIPT_ENVOLTORIO`)

El instalador necesita ficheros (el script y el portal) y variables (sudo, credenciales del colector). Todo viaja por **una sola entrada estándar**:

```
N\n                           ← número de variables
NOMBRE=base64(valor)\n  × N   ← variables (admiten cualquier carácter)
<tar.gz>                      ← instalar-todo*.sh + index.html + favicons
```

El programa remoto: lee las variables y las exporta; extrae el tar.gz en un directorio **persistente** (`~/panel-servidores/instalar-todo`, porque el cron guarda la ruta del script); crea un directorio temporal (`mktemp -d`, borrado con `trap`) con un **`sudo` de sustitución** y un *askpass* que lee `PANEL_SUDO_PW`:

```sh
# $T/bin/sudo      →  exec /usr/bin/sudo -A "$@"
# $T/askpass       →  printf '%s\n' "$PANEL_SUDO_PW"
export SUDO_ASKPASS="$T/askpass" PATH="$T/bin:$PATH"
bash "$DEST/$SCRIPT" "$@" </dev/null
```

Así el instalador (que llama a `sudo` decenas de veces) funciona **sin terminal y sin contraseña en ningún comando ni fichero**. Códigos 70–76 = fallos del envoltorio (entrada truncada, variable inválida, `mkdir`, `tar`, `mktemp`, `cd`). Si el script dice «tiene contenido ajeno y no hay terminal», `AnalizadorLog.necesita_forzar` lo detecta y la interfaz ofrece repetir con `--forzar`.

`asegurar_sudo` valida **antes** de empezar (`sudo -S true`, hasta 3 intentos) para no descubrir una contraseña errónea a mitad de una instalación de 10 minutos.

### 6.4 `authorized_keys`

`comando_instalar_clave`: `umask 077`, crea `~/.ssh` (700) y el fichero (600), no duplica la clave (comprueba el cuerpo base64), añade salto de línea si faltaba, `restorecon` si existe. `comando_revocar_clave`: copia con marca de tiempo y `grep -vF`.

### 6.5 Desinstalar un servicio

`comando_desinstalar_servicio` solo borra directorios que empiecen por `/opt/?*` (el `case` descarta cualquier otra ruta y lo dice). Hay una prueba que lo verifica con un directorio ajeno.

---

## 7. Claves SSH (`nucleo/claves.py`)

* `listar_claves_locales`: `ssh-keygen -lf` (tipo, bits, huella) y `ssh-keygen -y -P "" -f clave` para saber si tiene frase (si falla sin pedir nada, está protegida).
* `generar_clave`: **nunca sobrescribe**; si hay frase, `ssh-keygen` la pide por el askpass (dos veces) y la aplicación responde, de modo que la frase **no aparece en `-N`** (visible con `ps`).
* `agregar_al_agente`: `ssh-add --apple-use-keychain` en macOS, con reintento sin la opción si el `ssh-add` no la conoce (Homebrew).
* `comprobar_acceso_clave` (`--check-key`): abre una conexión **solo con clave** y `-v`, y analiza la salida: qué claves se ofrecieron (`Offering public key`), cuál aceptó el servidor (`Server accepts key`) y el motivo del fallo: `no_keys`, `not_authorized`, `connection`, `timeout`, `other`. Mejora sobre el script: si la clave tiene frase, el askpass la pide (el script exigía tenerla cargada en el agente).

---

## 8. Datos y recursos

### 8.1 Almacén (`almacen.py`)

`~/Library/Application Support/Panel de Servidores/` (o `PANEL_SERVIDORES_HOME`):

* `perfiles.json` — `{"version":1,"perfiles":[…]}`; los secretos **no** están; solo su *fuente* (`preguntar|llavero|entorno` y nombre de variable).
* `ajustes.json` — preferencias (incluido el token de GitHub si se configura).
* `scripts/` — scripts descargados de GitHub.

Escritura **atómica** (fichero temporal + `os.replace`, `chmod 600`). Si un JSON está corrupto se renombra a `.bak` y se arranca vacío. `Perfil.desde_dict` ignora claves desconocidas (compatibilidad hacia delante) y rellena las que faltan con sus valores por defecto (hacia atrás).

### 8.2 Llavero (`secretos.py`)

`keyring` con servicio `Panel de Servidores` y cuenta `"<id perfil>:<password|frase|sudo>"`. Si `keyring` no está instalado, `disponible` es `False` y la casilla «Guardar en el Llavero» no aparece.

### 8.3 Recursos (`recursos.py`)

Un fichero se busca en este orden: **carpeta propia** (Preferencias) → **descargados** (`scripts/` en datos) → **incluidos** (`src/panel_servidores/recursos`; en PyInstaller, `_MEIPASS`). `inventario()` da nombre, origen y huella SHA-256 abreviada, que se muestra en Preferencias para saber qué versión del script se está enviando.

> **Ojo:** `scripts/sincronizar-recursos.sh` copia lo que haya en la **rama activa** del repositorio `code` y sobrescribe los incluidos. Cambia a la rama deseada antes de ejecutarlo.

---

## 9. Seguridad

| Amenaza | Medida |
|---|---|
| Contraseña visible con `ps` | Nunca en argumentos: entrada estándar o askpass |
| Contraseña en disco | No se guarda; Llavero solo a petición |
| **Inyección de opciones en ssh** (`-oProxyCommand=…` como «servidor») | `RE_DESTINO` rechaza destinos que empiecen por `-` o con espacios/control; el destino es siempre el último argumento de ssh |
| Inyección de comandos remotos | `shlex.quote` + parámetros posicionales; nombres de servicio validados con regex; acciones de `systemctl` en lista blanca |
| Borrado destructivo | La desinstalación solo borra bajo `/opt/`; copias previas en `/var/backups`; `--forzar` nunca se recuerda |
| Huella de servidor falsa | `StrictHostKeyChecking=ask` por defecto; la huella **cambiada** se rechaza siempre; «aceptar nuevas» es opt-in por servidor |
| Otros usuarios locales leyendo el socket del askpass | Directorio 700 + token aleatorio por conexión |
| Secretos en el registro de actividad | `_anotar` solo registra opciones y destino, no entradas ni entorno |
| Sobrescribir claves | `generar_clave` se niega si existe la clave |

Limitaciones conocidas: los secretos están en memoria de Python mientras dura la sesión (no se pueden «borrar» de forma garantizada); la firma «ad-hoc» del `.app` no pasa la notarización de Apple.

---

## 10. Pruebas

```bash
./scripts/ejecutar.sh --pruebas        # o:  python -m pytest -q
```

| Fichero | Qué cubre | Requisitos |
|---|---|---|
| `test_unitarias.py` | Destinos, comandos remotos (ejecutados con `sh` local), opciones del instalador, validaciones, analizador de log, cron, ANSI, almacén, secretos, askpass (ida y vuelta), GitHub (servidor HTTP falso), `ssh_config`, terminal | Nada |
| `test_ssh_integracion.py` | **sshd real** con usuario de prueba: contraseña con `"` `$` y espacios, 2FA/askpass, multiplexado, huella, sudo (reutilizar/reintentar/nunca), streaming, cancelación, timeout, claves (con y sin frase), auditoría, informe JSON/texto, resumen, servicio | root + OpenSSH servidor/cliente (si no, se **saltan solas**) |
| `test_ui.py` | La ventana completa sin pantalla (`QT_QPA_PLATFORM=offscreen`) contra el sshd: conectar, resumen, informe con sudo, instalador con script simulado, claves, aplicaciones, flota, diálogo de servidor. Un «autopiloto» contesta a los diálogos | Lo anterior + PySide6 |
| `test_visual.py` | Renderiza cada pestaña, sub-pestaña y diálogo en **claro y oscuro** y con dos tamaños de ventana, y falla si algún texto o cabecera de tabla queda cortado o desalineado; comprueba el contraste de todos los colores. Con `PSV_CAPTURAS=/carpeta` guarda además las imágenes PNG para revisarlas | Lo anterior + PySide6 |
| `test_listar_real.py` | El `instalar-todo.sh` **real** (`--listar`) subido y ejecutado por el envoltorio | Lo anterior |

El `sshd` de pruebas (`conftest.py`) se arranca en un puerto libre con el usuario `psv-test`, contraseña `Pa55 w0rd"$x` y `sudo` con contraseña (`/etc/sudoers.d/psv-test`). Solo se ejecuta si eres root; en tu Mac esas pruebas se saltan y corren las unitarias.

**Lo que NO se ha podido verificar en el entorno de desarrollo:** ejecución real en macOS (Llavero, `--apple-use-keychain`, AppleScript de Terminal/iTerm), `construir-app.sh` (PyInstaller, `iconutil`, `codesign`) y servidores con 2FA reales. El código está escrito para ello y la lógica común está probada, pero conviene una primera ejecución manual en el Mac.

---

## 11. Empaquetado (PyInstaller)

`scripts/construir-app.sh`: crea `.venv-build`, genera el icono (`crear-icono.py` dibuja con Qt; `iconutil` crea el `.icns`), ejecuta PyInstaller con `--windowed`, `--osx-bundle-identifier es.umh.panel-servidores`, incluye `recursos/` e `icono.png` como datos, y firma ad-hoc con `codesign`.

Puntos delicados:

* **`--askpass` en modo congelado:** `GestorAskpass._escribir_script` detecta `sys.frozen` y genera `exec "<app>" --askpass "$@"`. `lanzador.py` lo atiende antes de importar Qt.
* **PATH de una app lanzada desde Finder** es mínimo: `rutas.buscar_ejecutable` prueba `/usr/bin`, `/opt/homebrew/bin`, `/usr/local/bin`… si `which` falla.
* **Recursos congelados:** `rutas.dir_recursos` usa `sys._MEIPASS`.
* `--hidden-import keyring.backends.macOS` garantiza el backend del Llavero.
* Distribuir a otros equipos requiere **Developer ID + notarización** (no incluidas).

---

## 12. Cómo extender

### Añadir una pestaña

1. Crea `ui/paginas/mi_pagina.py` con una clase que herede de `PaginaBase` (`titulo = "…"`), construya su interfaz sobre `self.raiz` y sobrescriba `perfil_cambiado()`.
2. Cada acción: `self.correr("texto", lambda t: funcion_del_nucleo(con, …, t.cancelador), al_terminar, deshabilitar=[boton])`.
3. Regístrala en `VentanaPrincipal._construir_paginas`.

### Añadir una opción del instalador

1. Campo en `OpcionesInstalador` (dataclass) y su traducción en `a_argumentos()`; validación en `validar()`.
2. Widget en `PaginaInstalador._construir_config` y lectura/escritura en `opciones()` / `poner_opciones()`.
3. Una prueba en `test_unitarias.py` (argumentos + validación).

### Añadir una operación remota

1. Función pura en `remoto.py` que devuelva el comando (citado, parámetros posicionales, sin secretos) y una prueba que lo ejecute con `sh` local.
2. Función en el módulo de dominio (`colector.py`, `claves.py`…) que llame a `conexion.ejecutar` / `ejecutar_sudo` y devuelva un dato estructurado.

### Uso desatendido (equivalente de `--batch`)

`Conexion(perfil, ajustes, askpass, desatendido=True)` (o `InteraccionNula`) nunca pregunta nada: si falta una contraseña, falla con un mensaje en lugar de abrir un diálogo. La interfaz actual no lo expone, pero el núcleo permite hacer scripts o tareas programadas con él.

---

## 13. Equivalencia de códigos de salida

Se conservan los del script SSH original, en `modelos.py` (`COD_*`): 0 correcto · 1 el informe encontró errores · 2 conectó pero no pudo leer `config.ini` · 3 problema local · 4 fallo de conexión/autenticación/sudo/python/tiempo · 5 el servidor no acepta solo clave. A nivel de proceso: 255 ssh, 124 tiempo agotado, 130 cancelado, 127 comando no encontrado.

## 14. Decisiones y alternativas descartadas

* **Qt (PySide6) frente a Toga/Tk:** Qt da tablas, árboles, consolas con formato, diálogos modales con hilos y apariencia nativa en macOS; Toga y Tk se descartaron por requisito.
* **`ssh` del sistema frente a Paramiko/AsyncSSH:** se pierde control fino del protocolo pero se gana compatibilidad completa con `~/.ssh/config`, agente, FIDO2, saltos y la política de seguridad de OpenSSH.
* **Enviar los scripts frente a reescribirlos en Python:** evita divergencias entre la app y los scripts del repo; el coste es depender de `bash`, `jq`, `git`, `rsync` en el servidor (como ya hacía el script).
* **Askpass frente a `pexpect`:** más robusto (no se parsea texto de un pseudo-terminal) y compatible con 2FA y huellas.

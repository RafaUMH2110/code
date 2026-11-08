# Panel de Servidores · Manual de usuario

*Versión 1.0 · Autor: Rafa (Dpto. de Ingeniería de Sistemas y Automática, UMH) · Generado con IA · Revisado por el autor*

---

## 1. ¿Qué es?

**Panel de Servidores** es una aplicación de escritorio para macOS que sustituye, con ventanas y botones, a los tres scripts del repositorio `code`:

| Script | Dónde está en la aplicación |
|---|---|
| `instalar-todo.sh` / `instalar-todo-isa.sh` | Pestaña **Instalador** |
| `telemet-collector-info.py` | Pestañas **Informe** y **Servicio** |
| `telemet-collector-info-ssh.py` | La conexión SSH de todo el programa + pestaña **Claves SSH** |

No reimplementa los scripts: **envía al servidor los propios scripts y los ejecuta allí**. Lo que cambia es todo lo de alrededor: formularios con validación, un selector visual de repositorios, contraseñas en diálogos (nunca en la línea de comandos), progreso por pasos, varios servidores guardados, etc.

Todo se hace por **SSH** con el `ssh` que ya trae macOS. Admite todas las formas de autenticación del script original: claves, `ssh-agent`, claves con frase de paso, contraseña, segundo factor (2FA), saltos por bastión y alias de `~/.ssh/config`.

---

## 2. Instalación y arranque

### 2.1 Requisitos

* macOS 12 o superior (Intel o Apple Silicon).
* Python 3.10 o superior (`python3 --version`). El de Homebrew o el de python.org valen.
* `ssh`, `ssh-keygen` y `ssh-add` (vienen con macOS).

### 2.2 Desde VS Code (modo desarrollo)

1. Abre la carpeta `panel-servidores` en VS Code (*Archivo → Abrir carpeta…*).
2. Terminal integrada: `./scripts/ejecutar.sh`. La primera vez crea el entorno virtual `.venv` e instala las dependencias; las siguientes veces arranca directamente.
3. O bien: *Ejecutar y depurar* (⇧⌘D) → **Panel de Servidores** → ▶. La variante «datos de prueba aislados» guarda los perfiles en `.datos-prueba/` para no tocar los reales.
4. Las pruebas: tarea «Pruebas» (⇧⌘B → *Pruebas*) o `./scripts/ejecutar.sh --pruebas`.

### 2.3 Crear la aplicación `.app`

```bash
./scripts/construir-app.sh          # crea dist/Panel de Servidores.app
./scripts/construir-app.sh --dmg    # además crea un .dmg
```

Arrástrala a *Aplicaciones*. La primera vez: **clic derecho → Abrir** (la firma es «ad-hoc», suficiente para uso propio). Si macOS la bloquea:
`xattr -dr com.apple.quarantine "/Applications/Panel de Servidores.app"`.

---

## 3. Primeros pasos

1. Pulsa **+** (abajo a la izquierda) o *Archivo → Nuevo servidor…* (⌘N).
2. En **General**: nombre y **destino**, por ejemplo `rafa@192.168.0.129` o `rafa@isa.umh.es:22`. También vale un alias de `~/.ssh/config` (o impórtalos todos con *Archivo → Importar de ~/.ssh/config…*).
3. En **Autenticación** deja *Automática* si ya entras por clave; si entras con contraseña elige *Contraseña*.
4. Pulsa **Probar conexión**. Si es la primera vez que conectas, aparecerá la huella del servidor para que la confirmes. Si hace falta, te pedirá la contraseña en una ventana.
5. **Guardar**. Ya puedes usar las pestañas.

> La contraseña se pide **una sola vez por sesión**: la aplicación mantiene una conexión abierta y reutiliza la autenticación en todas las pestañas.

---

## 4. La ventana principal

* **Izquierda:** lista de servidores. `●` verde = conexión abierta; `○` = sin conexión. Doble clic = editar.
* **Centro:** pestañas *Resumen · Informe · Servicio · Instalador · Claves SSH · Aplicaciones* (⌘1…⌘6).
* **Abajo:** panel **Actividad**, con cada comando `ssh` que lanza la aplicación (sin contraseñas). Sirve para aprender, para depurar y para copiar un comando y repetirlo a mano. *Guardar registro…* lo exporta.
* **Barra de cada pestaña:** estado de la operación, barra de progreso y botón **Cancelar**. Una pestaña ejecuta una operación a la vez; las demás siguen disponibles.

Menús: **Archivo** (nuevo, importar/exportar, preferencias), **Servidor** (editar, duplicar, eliminar, desconectar), **Herramientas** (informe de varios servidores), **Ver** (panel Actividad, **Apariencia**, ir a una pestaña), **Ayuda**.

**Apariencia clara u oscura.** *Ver ▸ Apariencia* (o *Preferencias ▸ General*) permite elegir **Según el sistema** (por defecto: sigue el modo claro/oscuro de macOS y cambia solo cuando tú lo cambias), **Claro** u **Oscuro**. La elección se recuerda. Los colores de estado (verde correcto, ámbar aviso, rojo error), los informes con color y el registro de actividad se ajustan solos para leerse bien en ambos modos.

---

## 5. El servidor (perfil)

### 5.1 General

| Campo | Significado | Equivale a (script SSH) |
|---|---|---|
| Nombre | Texto para la lista | — |
| Destino | `[usuario@]host[:puerto]` o alias | argumento `TARGET` |
| Usuario / Puerto | Si no van en el destino | `-u` / `-p` |
| Tipo de servidor | *Local* (`instalar-todo.sh`, `/var/www/html`) o *isa* (`instalar-todo-isa.sh`, `/var/www/htdocs`) | — |
| URL pública | Para copiar enlaces de aplicaciones | — |
| Notas | Libre | — |

### 5.2 Autenticación

| Método | Qué hace | Equivale a |
|---|---|---|
| **Automática** | `ssh` prueba tus claves, el agente y, si hace falta, pide la contraseña | (por defecto) |
| **Clave concreta** | Solo la clave indicada (`IdentitiesOnly`); si tiene frase, se pide en un diálogo | `-i` |
| **Contraseña** | Solo contraseña; desactiva las claves | `--ask-password` / `--password-env` |
| **Interactiva** | Contraseña **+ código 2FA/OTP**; cada pregunta del servidor sale en un diálogo | keyboard-interactive |

**De dónde sale cada secreto** (contraseña SSH, frase de la clave, contraseña de sudo):

* **Preguntar:** diálogo; se recuerda solo mientras dure la sesión.
* **Llavero de macOS:** el diálogo ofrece *«Guardar en el Llavero»*; las siguientes veces no pregunta. *(Necesita el paquete `keyring`, incluido en `requirements.txt`.)*
* **Variable de entorno:** lee el valor de una variable del proceso (equivale a `--password-env`). Útil para automatizar; ten en cuenta que la app, lanzada desde el Finder, no hereda variables de tu terminal.

Los códigos 2FA **se preguntan siempre** (caducan): nunca se recuerdan ni se guardan.

### 5.3 sudo

| Opción | Significado | Equivale a |
|---|---|---|
| Automático | Usa `sudo` si no eres root; reutiliza la contraseña SSH | (por defecto) |
| Nunca usar sudo | No se intenta sudo | `--no-sudo` |
| Contraseña propia | Contraseña de sudo distinta de la SSH | `--ask-sudo-password` / `--sudo-password-env` |
| *Reutilizar la contraseña SSH* | Casilla | inverso de `--no-reuse-password` |

Si sudo rechaza la contraseña, se te pide la correcta y se reintenta **una vez** (como en el script).

### 5.4 Conexión

| Campo | Equivale a |
|---|---|
| Aceptar huella nueva automáticamente | `--accept-new-host-key` |
| Reutilizar una única conexión | (mejora: autenticarse una sola vez) |
| Salto (bastión) | `-J` / ProxyJump |
| Opciones de ssh (una por línea) | `--ssh-arg` |
| Espera de conexión / por operación | `--connect-timeout` / `--timeout` |
| Python en el servidor | `--remote-python` |

> *Aceptar huella nueva* acepta solo servidores **desconocidos**. Si la huella **cambia** respecto a la guardada, la conexión se rechaza siempre y se explica por qué (puede ser un ataque o una reinstalación).

### 5.5 Colector

Ruta de `config.ini` y nombre del servicio, con dos preajustes:

* **TeleMet Collector (inglés):** `/opt/telemet-collector`, servicio `telemet-collector` — el que entiende el informe.
* **TeleMet Colector (español):** `/opt/telemet-colector`, servicio `telemet-colector` — el que despliega `instalar-todo.sh`.

---

## 6. Pestañas

### 6.1 Resumen

Botones: **Conectar y actualizar** (muestra usuario, sistema, disco, Apache, cron, servicios del colector, estado de sudo), **Comprobar (--check)**, **Abrir en Terminal** (abre Terminal o iTerm con el mismo comando ssh), **Copiar comando ssh** y **Desconectar** (cierra la conexión y olvida las contraseñas de la sesión).

### 6.2 Informe

Ejecuta `telemet-collector-info.py` **en memoria** en el servidor (no copia nada en disco).

* **Opciones:** colector (preajuste), ruta `-c`, servicio `--service`, *No consultar el servicio* (`--no-service`), *Mostrar la clave API* (`--show-key`), *Auditar authorized_keys* (`--authorized-keys`) e idioma (`--lang`).
* **Resultado en tres vistas:** **Diagnóstico** (errores y avisos, los graves primero), **Informe** (el texto con colores del script) y **JSON** (los datos tal cual).
* **Exportar…** guarda `.txt`, `.json` o `.html`; **Copiar texto** lo lleva al portapapeles.
* Si el informe no se puede leer, el mensaje distingue «no se pudo conectar / sudo / python» de «conectó pero falta config.ini».

### 6.3 Servicio

Control del servicio systemd del colector: **Consultar estado** (activo, arranque, reinicios, PID, usuario), **Iniciar / Detener / Reiniciar / Recargar / Activar al arrancar / Desactivar**, **Leer registro** (`journalctl -u`, con filtro de texto) y **Desinstalar…**.

Desinstalar para y desactiva el servicio, elimina su unidad systemd y, si lo marcas, hace copia en `/var/backups` y borra el programa. **Solo borra carpetas bajo `/opt/`.** Siempre pide confirmación.

### 6.4 Instalador

Cuatro subpestañas.

**Configuración** — todas las opciones de `instalar-todo.sh` con validación y, abajo, el **comando equivalente** (copiable) que ejecutarías a mano:

| Campo | Opción del script |
|---|---|
| Usuario de GitHub | `-u` |
| Carpeta de repos | `-o` |
| Destino web | `-d` |
| DocumentRoot de Apache | `--docroot` |
| Modo *web / html / todo* | `--modo` |
| No generar el portal | `--sin-indice` |
| Sobrescribir contenido ajeno | `--forzar` |
| Instalar el colector (+ Station ID y API Key opcionales) | `--colector` (las credenciales viajan por entorno: `TELEMET_STATION_ID`, `TELEMET_API_KEY`) |
| Cron (preajustes o expresión de 5 campos) | `--cron` |
| Solo *isa*: URL, entrada en la raíz, carpeta JSON | `--url`, `--entrada-raiz`, `--json-dir` |

*Guardar como predeterminado* recuerda estas opciones **en ese servidor**. La clave API **nunca** se guarda y `--forzar` tampoco (hay que decidirlo cada vez).

**Repositorios** — qué clonar: *selección guardada en el servidor*, *todos*, *solo los marcados* o *todos menos los marcados*. **Cargar repos de GitHub** muestra un árbol (sin repos archivados); despliega un repo para marcar **carpetas concretas** (`repo/carpeta`). A la derecha: **Leer del servidor** (el fichero `.seleccion`) y **Listar con el script** (`--listar`).

**Ejecución** — los 6 pasos (Dependencias, Selección y clonado, Despliegue en Apache, Colector, Entrada del servidor, Comprobación) se marcan según avanza el script; debajo, el registro en vivo y un **resumen** (repos nuevos/actualizados, ficheros desplegados, URL, errores, duración).

**Mantenimiento** — registro del instalador del servidor, crontab (ver y **quitar las entradas de instalar-todo**) y copias de seguridad de `/var/backups`.

**Al pulsar «Instalar / actualizar»** se valida el formulario, se te muestra lo que va a ocurrir y se pide confirmación. La aplicación comprueba antes que **sudo funcionará** (y valida la contraseña) para no fallar a mitad. Si el destino ya contiene algo que no creó el instalador, te propone repetir con `--forzar` (con copia previa).

### 6.5 Claves SSH

* **Claves de este equipo:** tipo, bits, si tienen frase, huella SHA256 y fichero. **Generar nueva…** (Ed25519, RSA 4096 o ECDSA, con frase de paso; **nunca sobrescribe** una clave existente). **Cargar en ssh-agent** (en macOS usa el Llavero para recordar la frase). **Copiar pública**. **Usar en este servidor** (cambia el perfil a «clave concreta»).
* **En el servidor** (con la clave seleccionada, o la del perfil):
  * **Comprobar acceso solo con clave** (`--check-key`): intenta entrar con contraseñas desactivadas y te dice qué clave aceptó el servidor o por qué no (sin clave, no autorizada, conexión…). Si la clave tiene frase, la pide en un diálogo (mejora: no hace falta tenerla en el agente).
  * **Instalar clave** (`--install-key`): como `ssh-copy-id`, idempotente, y arregla permisos de `~/.ssh`.
  * **Revocar clave…:** la quita de `authorized_keys` haciendo copia antes.
  * **Auditar authorized_keys** (`--authorized-keys`): permisos, claves y ajustes de sshd.
  * **Olvidar huella del servidor…** (`ssh-keygen -R`): para cuando la huella cambió a propósito.

Receta típica para dejar de usar contraseña: *Generar nueva* → seleccionarla → *Instalar clave* → *Comprobar acceso solo con clave* → *Usar en este servidor*.

### 6.6 Aplicaciones

*Leer apps.json del servidor* muestra el catálogo del portal (título, repo, ruta, proyecto, descripción, tamaño, fecha) con filtro. **Copiar URL** da el enlace público (usa la *URL pública* del servidor).

---

## 7. Informe de varios servidores

*Herramientas → Informe de varios servidores…*: marca los servidores y pulsa **Generar informes**. Recorre uno tras otro (cada uno con sus credenciales) y muestra una tabla con estado, errores, avisos y duración. Al seleccionar una fila ves su informe completo; **Exportar CSV…** guarda la tabla.

---

## 8. Preferencias (⌘,)

* **General:** ruta de `ssh` (vacío = autodetectar), apariencia (sistema / claro / oscuro), idioma del informe, Terminal o iTerm, confirmaciones antes de acciones que modifican el servidor, mostrar clave API por defecto, tamaño de las consolas.
* **GitHub y scripts:** usuario y rama, token opcional (sube el límite de 60 peticiones/hora de la API), y la tabla de **scripts que se envían al servidor** con su origen y huella. Tres orígenes, por orden de prioridad: *carpeta propia* → *descargados de GitHub* (botón **Actualizar desde GitHub**) → *incluidos en la aplicación* (botón **Volver a los incluidos**).

---

## 9. Seguridad y privacidad

* Las contraseñas **no se guardan en ningún fichero** de la aplicación. Solo se recuerdan en memoria durante la sesión o, si tú lo pides, en el **Llavero de macOS**.
* Ninguna contraseña viaja en la línea de comandos (no se vería con `ps`): van por la entrada estándar de la conexión cifrada o por el *askpass* interno.
* `perfiles.json` y `ajustes.json` se guardan en `~/Library/Application Support/Panel de Servidores/` con permisos 600. El token de GitHub, si lo pones, se guarda ahí.
* **Exportar servidores** crea un JSON **sin secretos** (puede incluir rutas y nombres de usuario).
* El registro de Actividad nunca muestra contraseñas.
* Los destinos que empiezan por `-` o contienen espacios se rechazan (evita que un destino se interprete como opción de `ssh`).

---

## 10. Solución de problemas

| Síntoma | Qué hacer |
|---|---|
| «No se pudo conectar por SSH» | Revisa destino, puerto y usuario. El mensaje distingue DNS, puerto cerrado, credenciales rechazadas y permisos de la clave. Prueba *Abrir en Terminal* para ver el error de ssh en bruto. |
| «La huella del servidor no coincide» | Averigua por qué cambió. Si es legítimo: pestaña *Claves SSH → Olvidar huella del servidor*. |
| Pide la contraseña en cada pestaña | Comprueba que *Reutilizar una única conexión* está activada (Perfil → Conexión). |
| «sudo necesita contraseña» | Perfil → sudo: pon *Contraseña propia* o activa NOPASSWD en el servidor. |
| El informe dice «no se pudo leer config.ini» | La ruta es de otro colector: usa el preajuste correcto (inglés `/opt/telemet-collector`, español `/opt/telemet-colector`). |
| «Límite de peticiones de GitHub agotado» | Añade un token en Preferencias o espera una hora. |
| La clave se rechaza (*not authorized*) | *Instalar clave* la añade y corrige permisos; si persiste, mira `journalctl -u ssh` en el servidor. |
| No abre Terminal | Solo funciona en macOS; da permiso de *Automatización* a la app cuando macOS lo pida. |
| Un script no se comporta como en el repo | Preferencias → *GitHub y scripts*: mira cuál se está enviando (incluido, descargado o propio). |

---

## 11. Atajos

⌘N nuevo servidor · ⌘E editar · ⌘, preferencias · ⌘1…⌘6 pestañas · ⌘Q salir.

## 12. Equivalencias rápidas con la línea de comandos

| Antes (terminal) | Ahora |
|---|---|
| `telemet-collector-info-ssh.py rafa@srv` | Servidor → Informe → *Generar informe* |
| `… --show-key` / `--no-service` / `--authorized-keys` | Casillas de la pestaña Informe |
| `… --check` | Resumen → *Comprobar* |
| `… --check-key` / `--install-key` / `--generate-key` | Claves SSH → *Comprobar acceso solo con clave* / *Instalar clave* / *Generar nueva…* |
| `./instalar-todo.sh --colector --cron "0 3 * * *"` | Instalador → Configuración |
| `./instalar-todo.sh --listar` | Instalador → Repositorios → *Listar con el script* |
| Menú numerado de repos | Instalador → Repositorios (árbol) |
| `--batch` | No aplica: la aplicación es interactiva (el núcleo lo soporta, ver manual técnico) |

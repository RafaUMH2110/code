# Manual de `telemet-collector-info` (local y remoto por SSH)

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Este manual cubre dos scripts que muestran **todos los parámetros de TeleMet Collector**:

| Script | Dónde se ejecuta | Para qué |
|---|---|---|
| `telemet-collector-info.py` | **En el servidor** donde está instalado el colector | Informe local |
| `telemet-collector-info-ssh.py` | **En tu ordenador** (CLI o VS Code) | Se conecta por SSH al servidor (contraseña o clave RSA) y muestra el mismo informe sin instalar nada allí |

Ambos son de **solo lectura**: no modifican ningún fichero, no tocan el servicio y no consultan la API de Weather Underground. La única excepción es `--install-key` del script SSH (sección 5.4), que añade tu clave pública a `~/.ssh/authorized_keys` del servidor, y `--generate-key`, que crea una clave en tu ordenador; solo se ejecutan si las pides.

---

## 1. Contenido de la carpeta

```
telemet-collector-info/
├── telemet-collector-info.py        Informe (se ejecuta en el servidor; también es la "carga" que envía el script SSH)
├── telemet-collector-info-ssh.py    Cliente SSH (se ejecuta en tu ordenador)
├── MANUAL.md                        Este manual
├── README.md                        Resumen
└── vscode-ejemplo/
    ├── launch.json                  Configuraciones de depuración / ejecución para VS Code
    └── tasks.json                   Tareas de VS Code
```

> **Los dos `.py` deben estar en la misma carpeta**: el script SSH lee `telemet-collector-info.py` y lo envía al servidor.

## 2. Requisitos

| Dónde | Qué hace falta |
|---|---|
| Tu ordenador | Python 3.7 o superior y el comando `ssh` (cliente OpenSSH). Solo biblioteca estándar: no hay que instalar paquetes con `pip`. |
| Servidor | `python3` y, si no entras como `root`, un usuario que pueda usar `sudo` (el fichero `config.ini` es 600 y pertenece a `telemet`). |

Comprobar el cliente SSH:

- **Linux / macOS**: `ssh -V` (viene instalado).
- **Windows 10/11**: *Configuración → Aplicaciones → Características opcionales → Cliente OpenSSH*; después, `ssh -V` en PowerShell.

## 3. Cómo funciona (y por qué es seguro)

1. El script abre **una sola conexión SSH** con tu cliente `ssh` (así respeta tu `~/.ssh/config`, tus claves, `ssh-agent`, `known_hosts`, `ProxyJump`…).
2. Por esa conexión envía un único comando: el informe `telemet-collector-info.py` **comprimido y en base64**, que `python3` descomprime y ejecuta en memoria. **No se copia ningún fichero al servidor y no queda nada en disco.**
3. Si el usuario no es root, el informe se lanza con `sudo -S`; la contraseña de sudo viaja por la entrada estándar de la conexión cifrada, **nunca en la línea de comandos** (no aparece en `ps`).
4. La salida del informe vuelve por la misma conexión y se muestra en tu terminal.
5. La contraseña SSH, si usas `--ask-password` o `--password-env`, se entrega a `ssh` mediante un ayudante temporal (`SSH_ASKPASS`) que se borra al terminar. No se escribe en ningún fichero ni en la línea de comandos.

## 4. Uso rápido (CLI)

```bash
# Con clave RSA / ed25519 (la de siempre, o -i para indicar una)
python3 telemet-collector-info-ssh.py rafa@192.168.0.129
python3 telemet-collector-info-ssh.py rafa@192.168.0.129 -i ~/.ssh/id_rsa

# Con contraseña (la pide ssh en el terminal)
python3 telemet-collector-info-ssh.py rafa@192.168.0.129

# Con contraseña pedida por el propio script (oculta)
python3 telemet-collector-info-ssh.py rafa@192.168.0.129 --ask-password

# Otro puerto, alias de ~/.ssh/config, varios servidores
python3 telemet-collector-info-ssh.py rafa@servidor:2222
python3 telemet-collector-info-ssh.py isa
python3 telemet-collector-info-ssh.py rafa@srv1 rafa@srv2 --json

# Sin argumentos: te pregunta servidor y contraseña
python3 telemet-collector-info-ssh.py

# Solo comprobar la conexión (usuario, python, config.ini, sudo, servicios)
python3 telemet-collector-info-ssh.py rafa@192.168.0.129 --check
```

Opcionalmente, `chmod +x telemet-collector-info-ssh.py` permite ejecutarlo como `./telemet-collector-info-ssh.py …` en Linux y macOS.

## 5. Autenticación

### 5.1 Clave RSA / ed25519 con `authorized_keys` (recomendada)

El acceso por clave consiste en guardar tu **clave pública** en el fichero `~/.ssh/authorized_keys` del usuario del servidor. El script puede hacerlo todo por ti (ver también la sección 5.4):

```bash
# 1) Crear el par de claves (solo si no tienes ninguna): RSA 4096 en ~/.ssh/id_rsa
python3 telemet-collector-info-ssh.py --generate-key

# 2) Copiar la clave pública al servidor (pide la contraseña SSH una sola vez) y validar
python3 telemet-collector-info-ssh.py rafa@192.168.0.129 --install-key

# 3) Comprobar cuando quieras que el acceso por clave (sin contraseña) funciona
python3 telemet-collector-info-ssh.py rafa@192.168.0.129 --check-key

# 4) Uso normal
python3 telemet-collector-info-ssh.py rafa@192.168.0.129 -i ~/.ssh/id_rsa
```

Equivale a hacer a mano `ssh-keygen -t rsa -b 4096` y `ssh-copy-id -i ~/.ssh/id_rsa.pub rafa@192.168.0.129`.

- Si no indicas `-i`, `ssh` prueba las claves por defecto y las del `ssh-agent`.
- Si la clave tiene **frase de paso**, `ssh` la pide en el terminal; para no escribirla cada vez usa `ssh-agent` / `ssh-add ~/.ssh/id_rsa` (en macOS: `ssh-add --apple-use-keychain`). Con `--check-key` no se puede pedir la frase (se usa `BatchMode`), así que la clave debe estar cargada en el agente.
- En Windows, la clave está en `C:\Users\<tú>\.ssh\id_rsa` y el agente es el servicio *OpenSSH Authentication Agent*.
- La clave privada debe tener permisos estrictos (`chmod 600 ~/.ssh/id_rsa`); si no, `ssh` responde `UNPROTECTED PRIVATE KEY FILE`.

### 5.2 Contraseña

Hay cuatro formas, de más cómoda a más automática:

| Forma | Cómo | Cuándo usarla |
|---|---|---|
| Que la pida `ssh` | No pongas ninguna opción | Uso interactivo normal (terminal de VS Code incluido) |
| Que la pida el script | `--ask-password` | Quieres que la misma contraseña sirva también para `sudo` |
| Variable de entorno | `--password-env VAR` | Scripts, tareas: `export TELEMET_PW='…'` antes de ejecutar |
| Sin argumentos | Ejecutar el script sin destino | Te pregunta servidor y contraseña (Enter = usar clave) |

Notas importantes:

- La **primera vez** que te conectas a un servidor, `ssh` pregunta si confías en su huella (*fingerprint*). Con `--ask-password` o `--password-env` esa pregunta no se puede responder, así que conéctate antes una vez con `ssh rafa@servidor` o añade `--accept-new-host-key` (acepta la huella de servidores nuevos, pero **rechaza** si cambia la de uno ya conocido).
- Se permite **un único intento** de contraseña (`NumberOfPasswordPrompts=1`) para no bloquear la cuenta por fallos repetidos (fail2ban, etc.).
- Una variable de entorno es visible para tu usuario y para procesos con sus mismos permisos; no la dejes definida en ficheros compartidos.

### 5.3 Alias de `~/.ssh/config`

Como se usa tu `ssh`, vale cualquier alias. Ejemplo de `~/.ssh/config`:

```
Host isa
    HostName isa.umh.es
    User rafa
    IdentityFile ~/.ssh/id_rsa

Host servidor-lab
    HostName 192.168.0.129
    User rafa
    Port 22
    ProxyJump pasarela      # salto por otro servidor
```

```bash
python3 telemet-collector-info-ssh.py isa
python3 telemet-collector-info-ssh.py servidor-lab
```

Si necesitas un salto o una opción sin tocar `~/.ssh/config`: `--ssh-arg '-J pasarela'`, `--ssh-arg '-o KexAlgorithms=+diffie-hellman-group14-sha1'` (se puede repetir).

### 5.4 Validar el acceso por `authorized_keys` (`--check-key`, `--install-key`, `--generate-key`)

Estas opciones **no piden informe del colector**: solo trabajan con las claves SSH.

| Opción | Qué hace |
|---|---|
| `--generate-key` | Crea un par RSA 4096 en la ruta de `-i` (por defecto `~/.ssh/id_rsa`). **Nunca sobrescribe** una clave existente. Si hay terminal, `ssh-keygen` te deja poner frase de paso. No necesita servidor |
| `--install-key` | Añade tu clave pública a `~/.ssh/authorized_keys` del servidor (como `ssh-copy-id`). Usa la contraseña SSH (`--ask-password`, `--password-env VAR` o la que pide al ejecutar en un terminal). Es **idempotente** (no duplica), crea `~/.ssh` (700) y el fichero (600) si faltan y corrige sus permisos. Después valida el acceso por clave automáticamente |
| `--check-key` | Valida que se puede entrar **solo con clave** y muestra la auditoría de `authorized_keys` del servidor |
| `--pubkey FICHERO.pub` | Clave pública a instalar. Por defecto: `<clave de -i>.pub` (si solo existe la privada, se obtiene con `ssh-keygen -y`) o la primera de `~/.ssh/id_ed25519.pub`, `id_rsa.pub`, `id_ecdsa.pub` |

**Cómo valida el acceso por clave.** `--check-key` abre una conexión con `PreferredAuthentications=publickey`, `PasswordAuthentication=no`, `KbdInteractiveAuthentication=no` y `BatchMode=yes`: si entra, es que `authorized_keys` funciona de verdad (no es la contraseña quien te deja pasar). Usa `ssh -v` para decir **qué clave** se ofreció y aceptó (huella SHA256 y fichero, o `ssh-agent`). Si te conectas con `-i`, solo se ofrece esa clave (`IdentitiesOnly`).

Ejemplo de salida correcta:

```
== Acceso por clave SSH (authorized_keys) en rafa@192.168.0.129 ==
✔ Acceso por clave correcto: entras en isa-server como 'rafa' sin contraseña.
  Clave usada: SHA256:6bsaq0sx4NAW95LjMeGCuddzBOANzPSsJIIMnTOxaTM  /home/rafa/.ssh/id_rsa

Auditoría de authorized_keys en el servidor:
▌ Claves SSH autorizadas (authorized_keys)
  Usuario:              rafa
  Directorio personal:  /home/rafa · 750 · rafa:rafa
  Carpeta .ssh:         /home/rafa/.ssh · 700 · rafa:rafa
  Fichero de claves:    /home/rafa/.ssh/authorized_keys · 600 · rafa:rafa
  Claves autorizadas (1):
    #1 ssh-rsa 4096  SHA256:6bsaq0sx…  rafa@mi-portatil
▌ Diagnóstico
  ✔ OK Acceso por clave correcto: 1 clave(s) autorizada(s) y permisos válidos.
```

**Si falla**, el script distingue tres causas y te dice qué hacer:

| Mensaje | Causa | Solución |
|---|---|---|
| *ssh no tiene ninguna clave privada que ofrecer* | No hay clave en `~/.ssh`, ni en el agente, ni en `-i` | `--generate-key`, `-i RUTA` o `ssh-add` |
| *La clave se ha ofrecido pero el servidor no la ha aceptado* | La clave pública no está en `authorized_keys`, o sshd la ignora por permisos | `--install-key` (la añade y corrige permisos). Si ya está, ejecuta `--check-key --ask-password`: con la contraseña entra y **audita el servidor** para decirte el motivo |
| *No se pudo conectar por SSH* | Servidor, puerto, huella (`--accept-new-host-key`) | Ver sección 11 |

**Qué audita en el servidor** (por el usuario con el que entras; también disponible en local con `telemet-collector-info.py --keys-only`):

- Cada clave de `authorized_keys`: tipo, bits (RSA), huella SHA256 (la misma que muestra `ssh-keygen -lf`), comentario y opciones (`command="…"`, `from="…"`…).
- Permisos y propietario de la **carpeta personal, `~/.ssh` y el fichero**. Con `StrictModes yes` (por defecto) sshd **ignora** las claves si alguno es escribible por grupo u otros o es de otro usuario; el diagnóstico indica el `chmod` exacto.
- Claves débiles u obsoletas (DSA, RSA < 2048 bits), fichero vacío o inexistente.
- Ajustes de `/etc/ssh/sshd_config` (y sus `Include`): `PubkeyAuthentication`, `AuthorizedKeysFile`, `PasswordAuthentication`, `PermitRootLogin`, `StrictModes`. Si `PasswordAuthentication` sigue en `yes`, sugiere ponerlo en `no` **cuando ya hayas comprobado que la clave funciona** (hazlo con otra sesión abierta para no quedarte fuera).
- Solo ve las directivas globales de `sshd_config`; no evalúa bloques `Match` ni lo que dice `sshd -T`.

**Con `--json`** se obtiene un objeto con `key_login` (`ok`, `user`, `host`, `key`, `reason`…), `install` (si se instaló) y `audit` (la auditoría completa); con varios servidores, un objeto por destino.

**Informe completo + claves.** Añade `--authorized-keys` al informe normal para incluir la auditoría de claves del usuario de login en el mismo informe (y sus avisos en el diagnóstico).

> `--install-key` solo escribe en el fichero estándar `~/.ssh/authorized_keys`. Si `sshd` usa otro `AuthorizedKeysFile`, la auditoría lo avisa.

---

## 6. `sudo` en el servidor

`/opt/telemet-collector/config.ini` es 600 y de `telemet` (contiene la API Key), por eso el informe necesita `sudo` si no eres root. El script lo gestiona así:

| Situación | Qué ocurre |
|---|---|
| Entras como `root` | No se usa sudo |
| sudo con `NOPASSWD` | Funciona sin más |
| sudo con contraseña y entraste con **contraseña SSH** (`--ask-password`, `--password-env` o modo sin argumentos) | Se **reutiliza** esa contraseña para sudo (desactívalo con `--no-reuse-password`) |
| sudo con contraseña y entraste con clave | `--ask-sudo-password` (oculta) o `--sudo-password-env VAR`; si no la das y hay terminal, **te la pide al fallar** y reintenta una vez |
| No quieres sudo | `--no-sudo` (solo funciona si tu usuario puede leer `config.ini`) |

Alternativas en el servidor, según prefieras:

```bash
# A) sudo sin contraseña SOLO para este informe (sudo visudo -f /etc/sudoers.d/telemet-info)
rafa ALL=(root) NOPASSWD: /usr/bin/python3

# B) dejar que tu usuario lea config.ini, sin sudo (usar entonces --no-sudo)
sudo usermod -aG telemet rafa
sudo chmod 640 /opt/telemet-collector/config.ini
```

> La opción A autoriza `python3` completo como root sin contraseña: úsala solo si el servidor es de confianza. La B es más estricta, pero amplía quién puede leer la API Key.

## 7. Qué muestra el informe

Mismo contenido que `telemet-collector-info.py` (ver README): fichero de configuración, estaciones (con la **API Key enmascarada**), lectura, ciclo, salida y log, estado de la base de datos y del JSON de cada estación, servicio systemd y un diagnóstico con avisos y errores. Ejemplo abreviado:

```
Conectando con rafa@192.168.0.129 …
TeleMet Collector · parámetros   · Generado 2026-11-08 00:55:14

▌ Estaciones (1)
  Estación 1
    Station ID:    IELCHE12   [config.ini]
    API Key:       abcd…78 (16)   [config.ini] (usa --show-key para verla completa)
    Intervalo:     300 s  (288 llamadas/día)
    Base de datos: /opt/telemet-collector/data/telemet.sqlite
    JSON publicado:/var/www/html/rafa/apps/telemetria/telemet/history/data/history.json
…
▌ Diagnóstico
  ✔ OK Sin problemas detectados.
```

La API Key solo se muestra completa con `--show-key`. **No pegues esa salida en chats, correos ni incidencias.**

## 8. Referencia de opciones (`telemet-collector-info-ssh.py`)

| Opción | Efecto |
|---|---|
| `destino…` | Uno o varios: `[usuario@]host[:puerto]` o alias de `~/.ssh/config` |
| `-u, --user` / `-p, --port` | Usuario / puerto si no van en el destino |
| `-i, --identity CLAVE` | Clave privada (RSA, ed25519…) |
| `--ask-password` | Pide aquí la contraseña SSH (oculta) |
| `--password-env VAR` | Lee la contraseña SSH de la variable `VAR` |
| `--accept-new-host-key` | Acepta la huella de un servidor visto por primera vez |
| `--batch` | No pregunta nada (para scripts / cron); falla si falta autenticación |
| `--ssh-arg 'OPCIONES'` | Opciones extra para `ssh` (repetible), p. ej. `'-J pasarela'` |
| `--ssh-path RUTA` | Ruta del comando `ssh` |
| `--connect-timeout N` / `--timeout N` | Segundos para conectar (15) / máximos por servidor (90) |
| `--no-sudo` | No usar sudo en el servidor |
| `--ask-sudo-password` | Pide aquí la contraseña de sudo (oculta) |
| `--sudo-password-env VAR` | Lee la contraseña de sudo de `VAR` |
| `--no-reuse-password` | No reutilizar la contraseña SSH como contraseña de sudo |
| `-c, --config RUTA` | Ruta de `config.ini` **en el servidor** (def. `/opt/telemet-collector/config.ini`) |
| `--service NOMBRE` / `--no-service` | Nombre del servicio / no consultar systemd |
| `--show-key` | Muestra la API Key completa |
| `--json` | Salida JSON (con varios servidores, un objeto por servidor) |
| `--color` / `--no-color` | Forzar / quitar colores |
| `--lang es\|en` | Idioma (por defecto, según `$LANG`) |
| `--remote-python CMD` | Comando de Python en el servidor (def. `python3`) |
| `--check` | Solo comprueba conexión, python, `config.ini`, sudo y servicios |
| `--authorized-keys` | Añade al informe la auditoría de `authorized_keys` del usuario de login |
| `--check-key` | Valida el acceso solo con clave y audita `authorized_keys` en el servidor (sección 5.4) |
| `--install-key` | Instala tu clave pública en `authorized_keys` del servidor y la valida |
| `--pubkey FICHERO.pub` | Clave pública a instalar (por defecto la de `-i` o `~/.ssh/id_*.pub`) |
| `--generate-key` | Crea un par RSA 4096 si no existe (`-i RUTA`, por defecto `~/.ssh/id_rsa`) |

### Códigos de salida

| Código | Significado |
|---|---|
| 0 | Todo correcto |
| 1 | El informe se generó y el **diagnóstico encontró algún error** de configuración |
| 2 | Conectó, pero **no se pudo leer `config.ini`** (ruta incorrecta o falta sudo) |
| 3 | Problema local: no hay `ssh`, falta `telemet-collector-info.py` o el destino no es válido |
| 4 | Fallo de conexión SSH, de autenticación, de sudo, de `python3` o tiempo agotado |
| 5 | Con `--check-key` / `--install-key`: se conectó, pero el servidor **no acepta el acceso solo con clave** |

Con varios servidores devuelve el peor código.

## 9. Usarlo desde VS Code

VS Code no necesita nada especial: ejecuta el script en un terminal. **Lo importante es que sea un terminal real**, porque `ssh` y el script piden contraseñas ahí. Hay cuatro formas.

### 9.1 Terminal integrado (la más simple)

`Terminal → Nuevo terminal` (Ctrl+`) y ejecuta los mismos comandos de la sección 4. Para navegar a la carpeta: `cd scripts/telemet-collector-info`.

### 9.2 Botón "Run Python File" o F5

- Abre `telemet-collector-info-ssh.py` y pulsa **▶ Run Python File**. Sin argumentos, el script **te pregunta** el servidor y la contraseña en el terminal que abre VS Code.
- Para argumentos fijos usa `launch.json`: copia `vscode-ejemplo/launch.json` a `.vscode/launch.json` de tu espacio de trabajo, ajusta la ruta de `program` y los servidores, y lanza con **F5** eligiendo la configuración.
- Mantén `"console": "integratedTerminal"`: con la consola de depuración interna no se pueden escribir contraseñas.
- El tipo `debugpy` requiere la extensión *Python Debugger* (se instala con la extensión Python de Microsoft). En versiones antiguas de VS Code usa `"type": "python"`.

### 9.3 Tareas (Terminal → Ejecutar tarea)

Copia `vscode-ejemplo/tasks.json` a `.vscode/tasks.json`. Quedan cinco tareas: informe con contraseña, comprobar conexión, validar el acceso por `authorized_keys`, instalar tu clave pública en el servidor e informe JSON con clave RSA. Cada una te pide el servidor (`${input:destino}`) y se ejecuta en un panel dedicado. Puedes asignarles un atajo en *Keyboard Shortcuts (JSON)* con `workbench.action.tasks.runTask`.

### 9.4 Alternativa: Remote-SSH

Con la extensión **Remote - SSH** abres una ventana de VS Code *dentro* del servidor: ahí lo normal es ejecutar `telemet-collector-info.py` (la versión local, sin SSH) con `sudo python3 telemet-collector-info.py` en el terminal integrado. Usa el script `-ssh` cuando quieras lanzarlo desde tu ordenador sin abrir una sesión remota, consultar **varios servidores** a la vez o integrarlo en tareas.

### 9.5 Consejos

- Elige el intérprete correcto (*Python: Select Interpreter*); basta cualquier Python 3.7+.
- Si usas **alias de `~/.ssh/config`**, VS Code Remote-SSH y este script comparten la misma configuración.
- En Windows, `ssh` debe estar en el `PATH` del terminal de VS Code (PowerShell o Git Bash). Si usas `--ask-password`/`--password-env` en Windows, el ayudante `SSH_ASKPASS` depende de la versión de OpenSSH; si falla, usa clave RSA o deja que `ssh` pida la contraseña (sin esas opciones).
- Puedes guardar la salida: `python3 telemet-collector-info-ssh.py srv --no-color > informe.txt` o `--json > informe.json` (no incluyas `--show-key` si vas a compartirlo).

## 10. Automatización

```bash
# Comprobación periódica en cron (clave RSA, sin preguntas); sale con código ≠ 0 si hay errores
python3 telemet-collector-info-ssh.py rafa@srv -i ~/.ssh/id_rsa --batch --no-sudo --json > /tmp/colector.json
echo $?

# Solo los diagnósticos con jq
python3 telemet-collector-info-ssh.py rafa@srv -i ~/.ssh/id_rsa --batch --json | jq '.diagnostics'

# Contraseña por variable de entorno
export TELEMET_PW='…'
python3 telemet-collector-info-ssh.py rafa@srv --password-env TELEMET_PW --accept-new-host-key --json
```

Para cron, lo recomendable es una clave dedicada, sin contraseña de sudo (`NOPASSWD` o `--no-sudo` con permiso de lectura por grupo) y `--batch`.

## 11. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `No se encuentra el comando 'ssh'` | No hay cliente OpenSSH | Instálalo (sección 2) o usa `--ssh-path` |
| `No se encuentra telemet-collector-info.py junto a este script` | Faltan ficheros | Copia los dos `.py` a la misma carpeta |
| `No se pudo conectar por SSH … (código 255)` | Servidor, puerto, usuario o credenciales incorrectos | Prueba `ssh -v usuario@servidor`; revisa `-p`, `-i` y la contraseña |
| `Host key verification failed` | Servidor nuevo o su huella cambió | Si es nuevo: `--accept-new-host-key` o `ssh usuario@servidor` una vez. Si **cambió**, averigua por qué antes de borrar la línea de `~/.ssh/known_hosts` |
| `Permission denied (publickey,password)` | Contraseña o clave incorrecta | Revísalas; con `--batch` no se puede pedir contraseña |
| `--check-key` dice que la clave no se acepta aunque ya la instalé | Permisos de la carpeta personal, `~/.ssh` o `authorized_keys` (StrictModes), o `PubkeyAuthentication no` | `--check-key --ask-password` audita y muestra el `chmod` necesario; `--install-key` también repara `~/.ssh` y el fichero |
| `--install-key`: «No hay clave pública que instalar» | Sin `~/.ssh/id_*.pub` ni `-i`/`--pubkey` | `--generate-key` o `--pubkey FICHERO.pub` |
| `UNPROTECTED PRIVATE KEY FILE` | Permisos de la clave | `chmod 600 ~/.ssh/id_rsa` |
| `sudo necesita contraseña … no se ha podido autenticar` | sudo exige contraseña y no se dio o es otra | `--ask-sudo-password`, `--sudo-password-env`, NOPASSWD o `--no-sudo` (sección 6) |
| `No se puede leer /opt/telemet-collector/config.ini` (código 2) | Falta sudo o la ruta es otra | Quita `--no-sudo` o indica la ruta con `-c` |
| `El servidor no tiene python3` | Sin Python 3 en el servidor | Instálalo (`sudo apt install python3`) o usa `--remote-python /ruta/python3` |
| Se queda esperando | Pide una contraseña que no ves (VS Code sin terminal real) o el servidor no responde | Ejecuta en el terminal integrado; ajusta `--connect-timeout` / `--timeout` |
| Con `--ask-password` pide otra vez la contraseña o falla en la primera conexión | La pregunta de la huella no se puede responder | Añade `--accept-new-host-key` o conéctate antes una vez a mano |
| Aparecen avisos de BOM, permisos, `ReadWritePaths`… | Son diagnósticos del colector, no del script | Léelos: indican el problema y cómo arreglarlo |

## 12. Seguridad

- El script **no guarda** contraseñas ni claves; el ayudante temporal de `ssh` se crea con permisos 700 en un directorio temporal propio y se borra al terminar.
- Las contraseñas no se pasan nunca como argumentos de la línea de comandos.
- La API Key sale enmascarada; `--show-key` la muestra completa en pantalla.
- `--accept-new-host-key` solo evita la pregunta de la primera conexión; si la huella de un servidor conocido cambia, `ssh` sigue rechazando la conexión.
- Preferible **clave RSA/ed25519 con frase de paso + ssh-agent** antes que contraseña.
- `--install-key` es la **única** operación que escribe en el servidor: solo añade una línea a `~/.ssh/authorized_keys` del usuario con el que entras (y ajusta permisos de `~/.ssh` a 700 y del fichero a 600). Nunca borra ni modifica otras claves. El resto de opciones son de solo lectura.
- `--generate-key` nunca sobrescribe una clave privada existente. Si lo ejecutas sin terminal (cron, tareas) la crea **sin frase de paso**.
- Se instala la clave **pública**; la privada no sale de tu ordenador.

## 13. Limitaciones

- Solo lectura (salvo `--install-key` / `--generate-key`): no arregla nada; solo informa.
- Necesita `python3` en el servidor (cualquier 3.7+; Debian 13 trae 3.13).
- Probado con OpenSSH en Linux (clave RSA, contraseña con `--password-env` y por terminal, sudo con y sin contraseña, varios servidores, `--check`). En macOS es el mismo OpenSSH; en **Windows** no se ha probado y el ayudante de contraseñas (`--ask-password` / `--password-env`) puede comportarse distinto según la versión de OpenSSH.
- La validación de claves se ha probado con OpenSSH en Linux (clave RSA 4096, instalación idempotente, reparación de permisos, clave no autorizada, destino inexistente). `--install-key` asume un shell POSIX en el servidor.
- El informe lee el servicio por `systemctl`; en servidores sin systemd solo se muestra la unidad si existe el fichero.

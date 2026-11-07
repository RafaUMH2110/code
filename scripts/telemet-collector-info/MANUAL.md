# Manual de `telemet-collector-info` (local y remoto por SSH)

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Este manual cubre dos scripts que muestran **todos los parámetros de TeleMet Collector**:

| Script | Dónde se ejecuta | Para qué |
|---|---|---|
| `telemet-collector-info.py` | **En el servidor** donde está instalado el colector | Informe local |
| `telemet-collector-info-ssh.py` | **En tu ordenador** (CLI o VS Code) | Se conecta por SSH al servidor (contraseña o clave RSA) y muestra el mismo informe sin instalar nada allí |

Ambos son de **solo lectura**: no modifican ningún fichero, no tocan el servicio y no consultan la API de Weather Underground.

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

### 5.1 Clave RSA (recomendada)

Crear la clave (una vez, en tu ordenador) y copiarla al servidor:

```bash
ssh-keygen -t rsa -b 4096 -C "rafa@mi-portatil"      # o: ssh-keygen -t ed25519
ssh-copy-id -i ~/.ssh/id_rsa.pub rafa@192.168.0.129  # pide la contraseña esta única vez
```

Uso:

```bash
python3 telemet-collector-info-ssh.py rafa@192.168.0.129 -i ~/.ssh/id_rsa
```

- Si no indicas `-i`, `ssh` prueba las claves por defecto y las del `ssh-agent`.
- Si la clave tiene **frase de paso**, `ssh` la pide en el terminal; para no escribirla cada vez usa `ssh-agent` / `ssh-add ~/.ssh/id_rsa` (en macOS: `ssh-add --apple-use-keychain`).
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

### Códigos de salida

| Código | Significado |
|---|---|
| 0 | Todo correcto |
| 1 | El informe se generó y el **diagnóstico encontró algún error** de configuración |
| 2 | Conectó, pero **no se pudo leer `config.ini`** (ruta incorrecta o falta sudo) |
| 3 | Problema local: no hay `ssh`, falta `telemet-collector-info.py` o el destino no es válido |
| 4 | Fallo de conexión SSH, de autenticación, de sudo, de `python3` o tiempo agotado |

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

Copia `vscode-ejemplo/tasks.json` a `.vscode/tasks.json`. Quedan tres tareas: informe con contraseña, comprobar conexión e informe JSON con clave RSA. Cada una te pide el servidor (`${input:destino}`) y se ejecuta en un panel dedicado. Puedes asignarles un atajo en *Keyboard Shortcuts (JSON)* con `workbench.action.tasks.runTask`.

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

## 13. Limitaciones

- Solo lectura: no arregla nada; solo informa.
- Necesita `python3` en el servidor (cualquier 3.7+; Debian 13 trae 3.13).
- Probado con OpenSSH en Linux (clave RSA, contraseña con `--password-env` y por terminal, sudo con y sin contraseña, varios servidores, `--check`). En macOS es el mismo OpenSSH; en **Windows** no se ha probado y el ayudante de contraseñas (`--ask-password` / `--password-env`) puede comportarse distinto según la versión de OpenSSH.
- El informe lee el servicio por `systemctl`; en servidores sin systemd solo se muestra la unidad si existe el fichero.

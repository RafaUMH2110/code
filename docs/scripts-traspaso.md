# Traspaso: scripts de Rafa (repo `RafaUMH2110/code`, carpeta `scripts/`)

> Copia, tal cual, del documento del proyecto «Telemetría» (`claude/scripts-traspaso.md`). Es una foto del **2026-11-08**: algunas rutas, versiones y pendientes pueden haber cambiado desde entonces.

Actualizado: 2026-11-08 · Último commit: e28c596 · Idioma de trabajo: español (Rafa, UMH). Documento para continuar el trabajo desde otro proyecto/sesión.

## 1. Repos y rutas
| Qué | Dónde |
|---|---|
| Scripts | GitHub `RafaUMH2110/code`, carpeta `scripts/` (también existen `telemetria/`, `linux/`, `macos/`, `windows/` en la raíz) |
| Apps web | GitHub `RafaUMH2110/apps` (`apps/telemetria/...`, `apps/moda/...`) |
| Clones en el sandbox de Claude | `/home/claude/code`, `/home/claude/apps` (pueden no existir en una sesión nueva: volver a clonar) |
| Entregables | zips en `/home/claude/out/` |
| Servidores | Apache local (`/rafa/`) e `isa.umh.es` (DocumentRoot `/var/www/htdocs`, contenido en `/var/www/htdocs/rafa`) |

## 2. Convenciones (importantes)
- Nombres de scripts, guías, marcadores y logs con **guiones `-`**, nunca `_`. Excepción: los ficheros del programa Python (`telemet_colector.py`, `telemet_collector.py`) conservan `_`.
- Carpetas `linux/`, `macos/`, `windows/` **no** se han renombrado (riesgo: requirements.txt y paquetes Python); solo si Rafa lo pide.
- Versión española instala `telemet-colector` (apps/telemetria/telemetcolector, servicio `telemet-colector`, `/opt/telemet-colector`); la inglesa instala `telemet-collector` (telemetcollector, servicio `telemet-collector`, `/opt/telemet-collector`). Opciones EN: `--collector/--no-collector`; ES: `--colector/--sin-colector`.
- Zips: el nombre debe llevar **fecha y hora** (`nombre_YYYYMMDD_HHMM.zip`).
- Documentos con autor: «Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es» y leyenda «Generado con IA · Revisado por el autor».
- Commits desde Claude Code: terminar con `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` y `Claude-Session: <url de la sesión>`.
- Git: `__pycache__` está en `.gitignore`; no commitear `.pyc`.

## 3. Estructura de `scripts/`
```
scripts/
├── README.md                         índice (ES)
├── clonar-actualizar/                actualizar-repos.sh, desplegar-apache.sh (primera versión, sustituidos por instalar-todo)
├── instalar-todo/                    instalar-todo.sh, instalar-todo-isa.sh, index.html + favicon*, guías, anteriores/
├── instalar-todo-telemetria/         instalar-todo.sh (solo apps/telemetria), index.html + favicon*, guía
├── telemet-colector/                 colector ES (telemet_colector.py, MANUAL, README, config.example.ini, .service)
├── telemet-collector-info/           informe del colector local y por SSH (ver §5)
├── mover-repo/                       guía para mover un repo a subcarpeta de otro conservando historial
└── en/                               versión inglesa: clone-update/, install-all/, install-all-telemetry/, README
```

## 4. Instaladores (`instalar-todo*.sh` / `install-all*.sh`)
- Todo en uno para el servidor: selección de repos (`.selection`), clonado/actualización (sparse-checkout en la variante de telemetría), despliegue en Apache (rsync), entrada `/rafa/`, informe detallado de cada actualización, opcionalmente instala el colector como servicio systemd. Variante `-isa`: para https://isa.umh.es, no toca la configuración existente de Apache.
- Variante `instalar-todo-telemetria/instalar-todo.sh`: clona **solo** `apps/telemetria`, permite elegir el colector. El portal `index.html` lista **todas** las apps clonadas (catálogo `apps.json` generado con Python embebido) aunque se use la variante de telemetría; incluye favicon (`favicon.svg`, `favicon.ico`, `apple-touch-icon.png`) que debe estar junto al script.
- `ini_set` (edición de `config.ini`): consciente de secciones/comentarios (no descomenta ejemplos de la plantilla ni duplica `api_key`), usa awk con ENVIRON y **elimina el BOM UTF-8** inicial.
- Los colectores leen `config.ini` con `encoding="utf-8-sig"` (corrige el bucle de reinicios `MissingSectionHeaderError … '﻿# TeleMet Collector'`). Arreglo manual en un servidor ya afectado: `sudo sed -i '1s/^\xEF\xBB\xBF//' /opt/telemet-collector/config.ini`.
- Guías: `instrucciones-instalar-todo*.md` (ES) e `install-all-guide.md` (EN); `apache-docroot-htdocs.md` explica el 404 de `/rafa/` cuando Apache sirve otro DocumentRoot.

## 5. `telemet-collector-info/` (último trabajo)
Dos scripts independientes (solo biblioteca estándar de Python 3.7+), con manual `MANUAL.md` (13 secciones), `README.md` y `vscode-ejemplo/{launch,tasks}.json`.

**`telemet-collector-info.py`** (en el servidor, solo lectura): muestra config.ini (ruta, propietario, permisos, BOM), estaciones (station_id, API Key enmascarada, origen de cada dato), lectura/ciclo/salida/log, BD SQLite y JSON de cada estación, servicio systemd y diagnóstico. Opciones: `-c`, `--service`, `--show-key`, `--use-shell-env`, `--no-service`, `--json`, `--no-color/--color`, `--lang es|en`, **`--authorized-keys [USER]`** (añade auditoría de claves al informe) y **`--keys-only [USER]`** (solo auditoría de claves, sin config.ini ni sudo). Salida bilingüe (diccionario `T`). Códigos: 0 ok, 1 hay errores de diagnóstico, 2 config ilegible.
- Auditoría de `authorized_keys` (`audit_authorized_keys`): claves (tipo, bits RSA, huella SHA256 calculada, comentario, opciones), permisos/propietario de home, `~/.ssh` y fichero según StrictModes (con el `chmod` exacto), claves débiles (DSA, RSA<2048), `sshd_config` (+Include; solo directivas globales, sin bloques Match): PubkeyAuthentication, AuthorizedKeysFile, PasswordAuthentication, PermitRootLogin, StrictModes.

**`telemet-collector-info-ssh.py`** (en el ordenador de Rafa; Linux/macOS/Windows con cliente OpenSSH): usa el `ssh` del sistema, envía el script de informe comprimido (zlib+base64) como argumento de `python3 -c` (no deja nada en el servidor), `sudo -S -p ""` opcional con truco `set --`/`"$@"`. Autenticación por clave (`-i`, agente, `~/.ssh/config`) o contraseña (`--ask-password`, `--password-env VAR`) mediante ayudante temporal `SSH_ASKPASS` (rechaza preguntas yes/no de huella; usar `--accept-new-host-key`); un único intento de contraseña. Opciones: `--ask-sudo-password`, `--sudo-password-env`, `--no-sudo`, `--no-reuse-password`, `-c`, `--service`, `--no-service`, `--show-key`, `--json` (varios servidores → objeto por servidor), `--lang`, `--remote-python`, `--check` (diagnóstico de conexión), `--ssh-arg`, `--batch`, `--connect-timeout`, `--timeout`.
- **Acceso por `authorized_keys`** (nuevo): `--generate-key` (RSA 4096 en `-i` o `~/.ssh/id_rsa`; nunca sobrescribe), `--install-key` (+`--pubkey FICHERO.pub`; añade la clave a `~/.ssh/authorized_keys` de forma idempotente, crea/repara permisos 700/600, luego valida), `--check-key` (login solo-clave con `PreferredAuthentications=publickey`, `PasswordAuthentication=no`, `KbdInteractiveAuthentication=no`, `BatchMode=yes`, `-v` para saber qué clave se ofreció/aceptó; si falla distingue: sin clave local / clave no aceptada / conexión; con contraseña disponible audita el servidor para diagnosticar). Detalle: caso `-v` no admite `-o LogLevel` previo (por eso en el modo clave no se fija LogLevel). Si no hay `-i`, se detecta la privada que corresponde a la pública usada.
- **Códigos de salida del cliente**: 0 ok · 1 el informe/auditoría encontró errores · 2 config.ini ilegible · 3 problema local (sin ssh, falta payload, destino no válido, sin clave pública) · 4 fallo SSH/sudo/python/timeout · 5 el servidor no acepta el acceso solo con clave.
- Los dos `.py` deben estar en la misma carpeta.

## 6. Cómo se probó (trucos del sandbox)
- sshd local en 127.0.0.1:2222 (`/usr/sbin/sshd -f cfg -E log`, `UsePAM no`, `/run/sshd` creado), usuario de prueba con `useradd`/`chpasswd`. El `ssh` usa el HOME del `passwd` (no `$HOME`) para `known_hosts` y claves por defecto → en pruebas pasar `-i` y `--ssh-arg '-o UserKnownHostsFile=...'`.
- Pruebas interactivas con módulo `pty`. Stubs en `/tmp/t/stubs` (systemctl, crontab, herramientas de Apache) y un stub de `curl` para la API de GitHub (el patrón debe ser `*"&page=1"`, no `page=1`, que coincide con `per_page=100`).
- El comprobador de seguridad bloquea `rm -rf` sobre variables/HOME: usar directorios nuevos en lugar de borrar.
- Probado en Linux: RSA, contraseña (askpass y pty), sudo con/sin contraseña, multi-destino JSON, huella de host, contraseña errónea, install/check-key (idempotencia, permisos 666, clave no autorizada, destino inexistente, `.pub` derivado). **No probado**: Windows/macOS (askpass en Windows), arranque real de systemd, variantes ISA ejecutadas de punta a punta.

## 7. Pendiente / ofertas abiertas
- Renombrar ficheros con `_` en `linux/`, `macos/`, `windows/` (solo si Rafa lo pide).
- Verificaciones reales por Rafa: colector tras el arreglo del BOM; historial de 7 días de Aspe y límite 429 frente a cadencia de 3 min; configuración del colector de Novelda.
- Posible mejora: `--install-key` con `AuthorizedKeysFile` personalizado; auditoría de bloques `Match` / `sshd -T` si hay root.
- Opción `-i` junto con frase de paso en `--check-key` requiere clave cargada en ssh-agent (BatchMode).

## 8. Para retomar
1. Clonar `RafaUMH2110/code` y `RafaUMH2110/apps`; `git log --oneline` (último e28c596).
2. Leer `scripts/README.md` y el `MANUAL.md` de la carpeta correspondiente.
3. Respetar las convenciones del §2; al terminar, zip con fecha y hora y commit con las líneas de atribución.

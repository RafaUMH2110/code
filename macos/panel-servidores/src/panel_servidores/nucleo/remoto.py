"""Constructores de comandos que se ejecutan EN EL SERVIDOR.

Todos devuelven una cadena para el shell remoto (``sh``, normalmente dash en Debian) y
siguen tres reglas que evitan los fallos típicos de mezclar shells y comillas:

1. **Se cita todo lo que viene de fuera** con ``shlex.quote`` (rutas, nombres de servicio,
   claves públicas…): jamás se concatena texto del usuario sin citar.
2. **Los secretos nunca van en la línea de comandos** (se verían con ``ps``): viajan por la
   entrada estándar de la conexión cifrada o por variables de entorno que se leen de ella.
3. **El script va en un único argumento de ``sh -c``** y los datos variables se pasan como
   parámetros posicionales (``$1``, ``$2``…), de modo que no hay doble interpretación.

Las funciones de este módulo son puras (no ejecutan nada) y por eso se prueban fácilmente.
"""

from __future__ import annotations

import base64
import io
import re
import shlex
import tarfile
import time
import zlib
from typing import Iterable

_RE_NOMBRE_SERVICIO = re.compile(r"^[A-Za-z0-9@._-]+$")
_RE_NOMBRE_VARIABLE = re.compile(r"^[A-Z_][A-Z0-9_]*$")

#: Instrucción de shell que expande ``~`` en el parámetro $1 (el shell no lo hace dentro de comillas).
_EXPANDIR_TILDE = 'case "$P" in "~"|"~/"*) P="$HOME${P#"~"}";; esac; '


def citar(texto: str) -> str:
    """Cita un texto para el shell (alias corto de ``shlex.quote``)."""
    return shlex.quote(texto)


def sh_c(script: str, *parametros: str) -> str:
    """``sh -c 'script' sh p1 p2 …`` con todo citado. Los parámetros llegan como $1, $2…"""
    partes = ["sh", "-c", citar(script), "sh"] + [citar(p) for p in parametros]
    return " ".join(partes)


def nombre_servicio_valido(nombre: str) -> bool:
    """Los nombres de unidad systemd solo admiten letras, cifras y ``@ . _ -``."""
    return bool(_RE_NOMBRE_SERVICIO.match(nombre or ""))


# ----------------------------------------------------------------------------- sudo
def prefijo_sudo(usar: bool) -> str:
    """Fragmento que deja en ``$@`` el prefijo ``sudo -S -p ""`` (o nada si eres root o no usas sudo).

    ``set --`` conserva el argumento vacío de ``-p ''`` (una variable normal lo perdería).
    La contraseña de sudo llega por la entrada estándar (``-S``).
    """
    if not usar:
        return "set --; "
    return 'if [ "$(id -u)" -ne 0 ]; then set -- sudo -S -p ""; else set --; fi; '


def como_root(orden: str, usar_sudo: bool = True) -> str:
    """Ejecuta ``orden`` (ya citada/compuesta) como root: directo si lo eres, con sudo si no."""
    return sh_c(prefijo_sudo(usar_sudo) + '"$@" ' + orden)


# ----------------------------------------------------------------------------- informe del colector
def _codigo_python(ruta_ficticia: str) -> str:
    """Programa de una línea que descomprime y ejecuta el informe en memoria.

    ``__file__`` se fija a una ruta ficticia dentro del directorio del colector porque el
    informe busca ``config.ini`` junto a su propio fichero si no se le indica otra ruta.
    """
    return ("import base64,sys,zlib;src=zlib.decompress(base64.b64decode(sys.argv.pop(1)));"
            "sys.argv[0]='telemet-collector-info.py';"
            "exec(compile(src,'telemet-collector-info.py','exec'),"
            "{'__name__':'__main__','__file__':%r})" % ruta_ficticia)


def comando_informe(carga: bytes, argumentos: Iterable[str], usar_sudo: bool, python: str = "python3",
                    ruta_ficticia: str = "/opt/telemet-collector/telemet-collector-info.py") -> str:
    """Comando que ejecuta ``telemet-collector-info.py`` EN MEMORIA en el servidor.

    El script va comprimido (zlib) y en base64 dentro de la propia línea de comandos de
    ``python3 -c``: no se copia ningún fichero y no queda nada en disco (igual que el original).
    """
    b64 = base64.b64encode(zlib.compress(carga, 9)).decode("ascii")
    orden = "%s -c %s %s %s" % (citar(python), citar(_codigo_python(ruta_ficticia)), citar(b64),
                                " ".join(citar(a) for a in argumentos))
    return como_root(orden, usar_sudo)


def comando_comprobar(ruta_config: str, python: str = "python3") -> str:
    """Equivalente de ``--check``: usuario, python, config.ini, sudo y servicios (texto plano)."""
    script = (
        'echo "user=$(id -un) uid=$(id -u) host=$(hostname)"; '
        '%(py)s --version 2>&1 || echo "python=MISSING"; '
        'ls -l %(cfg)s 2>&1; '
        'if [ "$(id -u)" -eq 0 ]; then echo "sudo=not needed (root)"; '
        'elif sudo -n true 2>/dev/null; then echo "sudo=OK without password"; '
        'else echo "sudo=needs password (or not allowed)"; fi; '
        'for s in telemet-collector telemet-colector; do '
        'if [ -f /etc/systemd/system/$s.service ]; then echo "service $s=installed ($(systemctl is-active $s 2>/dev/null))"; fi; done'
    ) % {"py": citar(python), "cfg": citar(ruta_config)}
    return sh_c(script)


def comando_resumen(ruta_config: str, python: str = "python3") -> str:
    """Datos de estado del servidor en formato ``clave=valor`` (una por línea) para el Resumen."""
    script = r"""
p() { printf '%s=%s\n' "$1" "$2"; }
p usuario "$(id -un)"; p uid "$(id -u)"; p host "$(hostname)"
p kernel "$(uname -sr)"
p sistema "$( (. /etc/os-release 2>/dev/null && printf %s "$PRETTY_NAME") )"
p actividad "$(uptime -p 2>/dev/null)"
p python "$($1 --version 2>&1 || echo MISSING)"
if [ "$(id -u)" -eq 0 ]; then p sudo root
elif sudo -n true 2>/dev/null; then p sudo nopasswd
elif command -v sudo >/dev/null 2>&1; then p sudo password
else p sudo ausente; fi
p disco "$(df -h / 2>/dev/null | awk 'NR==2{print $3" usados de "$2" ("$5")"}')"
p config "$(ls -l "$2" 2>&1)"
p apache "$(systemctl is-active apache2 2>/dev/null || echo n/d)"
for s in telemet-collector telemet-colector; do
  if [ -f /etc/systemd/system/$s.service ]; then p "servicio_$s" "$(systemctl is-active $s 2>/dev/null)"; fi
done
p cron "$(crontab -l 2>/dev/null | grep -c 'instalar-todo')"
p git "$(git --version 2>/dev/null || echo n/d)"
"""
    return sh_c(script, python, ruta_config)


# ----------------------------------------------------------------------------- authorized_keys
def comando_instalar_clave(clave_publica: str) -> str:
    """Añade una clave pública a ``~/.ssh/authorized_keys`` (como ``ssh-copy-id``). Idempotente.

    Crea ``~/.ssh`` (700) y el fichero (600) si faltan, no duplica la clave y añade un salto de
    línea si el fichero no terminaba en uno. Responde con ``KEY=added|already`` y ``FILE=…``.
    """
    script = (
        'umask 077; KEY="$1"; B64=$(printf "%s" "$KEY" | awk \'{print $2}\'); '
        'D="$HOME/.ssh"; F="$D/authorized_keys"; '
        'mkdir -p "$D" && chmod 700 "$D" || exit 20; '
        '[ -e "$F" ] || : > "$F"; chmod 600 "$F"; '
        'if grep -qF -- "$B64" "$F"; then echo "KEY=already"; else '
        '  if [ -s "$F" ] && [ -n "$(tail -c1 "$F")" ]; then echo >> "$F"; fi; '
        '  printf "%s\\n" "$KEY" >> "$F" && echo "KEY=added"; fi; '
        'echo "FILE=$F"; '
        'command -v restorecon >/dev/null 2>&1 && restorecon -R "$D" >/dev/null 2>&1; true')
    return sh_c(script, clave_publica)


def comando_revocar_clave(cuerpo_base64: str) -> str:
    """Quita de ``authorized_keys`` la(s) línea(s) que contienen esa clave. Hace copia antes.

    ``cuerpo_base64`` es el segundo campo de la clave pública (``AAAA…``). Responde con
    ``KEY=removed|absent|missing``, ``COUNT=n`` y ``BACKUP=ruta``.
    """
    script = (
        'umask 077; B64="$1"; F="$HOME/.ssh/authorized_keys"; '
        '[ -f "$F" ] || { echo "KEY=missing"; exit 0; }; '
        'N=$(grep -cF -- "$B64" "$F"); '
        '[ "$N" -gt 0 ] || { echo "KEY=absent"; exit 0; }; '
        'B="$F.bak-$(date +%Y%m%d-%H%M%S)"; cp -p "$F" "$B" || exit 21; '
        'grep -vF -- "$B64" "$F" > "$F.tmp.$$"; cat "$F.tmp.$$" > "$F" && rm -f "$F.tmp.$$"; '
        'echo "KEY=removed"; echo "COUNT=$N"; echo "BACKUP=$B"')
    return sh_c(script, cuerpo_base64)


# ----------------------------------------------------------------------------- servicios systemd
ACCIONES_SERVICIO = ("start", "stop", "restart", "reload", "enable", "disable")


def comando_estado_servicio(nombre: str) -> str:
    """Estado, arranque y datos de un servicio (no necesita root)."""
    script = (
        'N="$1"; '
        'printf "active=%s\\n" "$(systemctl is-active "$N" 2>/dev/null)"; '
        'printf "enabled=%s\\n" "$(systemctl is-enabled "$N" 2>/dev/null)"; '
        'systemctl show "$N" -p NRestarts -p ActiveEnterTimestamp -p MainPID -p FragmentPath -p User 2>/dev/null; '
        'echo "---"; systemctl status "$N" --no-pager -l 2>&1 | head -n 25')
    return sh_c(script, nombre)


def comando_accion_servicio(accion: str, nombre: str, usar_sudo: bool = True) -> str:
    """``systemctl <accion> <nombre>`` como root."""
    if accion not in ACCIONES_SERVICIO:
        raise ValueError("Acción de servicio no permitida: %r" % accion)
    if not nombre_servicio_valido(nombre):
        raise ValueError("Nombre de servicio no válido: %r" % nombre)
    return como_root("systemctl %s %s" % (accion, citar(nombre)), usar_sudo)


def comando_registro_servicio(nombre: str, lineas: int = 200, usar_sudo: bool = True) -> str:
    """Últimas líneas del registro del servicio (``journalctl -u``)."""
    if not nombre_servicio_valido(nombre):
        raise ValueError("Nombre de servicio no válido: %r" % nombre)
    return como_root("journalctl -u %s -n %d --no-pager" % (citar(nombre), int(lineas)), usar_sudo)


def comando_desinstalar_servicio(nombre: str, directorio: str, borrar_programa: bool, hacer_copia: bool,
                                 usar_sudo: bool = True) -> str:
    """Para, desactiva y elimina la unidad systemd; opcionalmente copia y borra ``/opt/...``.

    Es la receta que se da a mano para quitar el servicio, convertida en operación. Por
    seguridad solo borra directorios bajo ``/opt/``.
    """
    if not nombre_servicio_valido(nombre):
        raise ValueError("Nombre de servicio no válido: %r" % nombre)
    cuerpo = r"""
N="$1"; DIR="$2"; BORRAR="$3"; COPIA="$4"
U="/etc/systemd/system/$N.service"
echo "== Parando y desactivando $N"
systemctl disable --now "$N" 2>&1 || true
if [ -f "$U" ]; then rm -f "$U" && echo "Unidad eliminada: $U"; else echo "No existía $U"; fi
systemctl daemon-reload
systemctl reset-failed "$N" 2>/dev/null || true
case "$DIR" in /opt/?*) ;; *) DIR="";; esac
if [ "$COPIA" = 1 ] && [ -n "$DIR" ] && [ -d "$DIR" ]; then
  DEST="/var/backups/$(basename "$DIR")-copia-$(date +%Y%m%d-%H%M%S)"
  cp -a "$DIR" "$DEST" && echo "Copia de seguridad en $DEST"
fi
if [ "$BORRAR" = 1 ]; then
  if [ -n "$DIR" ] && [ -d "$DIR" ]; then rm -r "$DIR" && echo "Borrado $DIR"; else echo "No se borra nada (directorio vacío, inexistente o fuera de /opt)"; fi
fi
if systemctl list-unit-files 2>/dev/null | grep -qF "$N"; then echo "AVISO: $N sigue figurando en systemd"; else echo "OK: $N ya no figura en systemd"; fi
"""
    orden = "sh -c %s sh %s %s %s %s" % (citar(cuerpo), citar(nombre), citar(directorio),
                                         "1" if borrar_programa else "0", "1" if hacer_copia else "0")
    return como_root(orden, usar_sudo)


# ----------------------------------------------------------------------------- lectura de ficheros
def comando_leer_fichero(ruta: str, ultimas_lineas: int = 0) -> str:
    """``cat`` (o ``tail -n``) de un fichero; expande ``~``. Código 66 si no existe."""
    script = _EXPANDIR_TILDE + 'N="$2"; [ -r "$P" ] || exit 66; if [ "$N" -gt 0 ]; then tail -n "$N" "$P"; else cat "$P"; fi'
    return sh_c('P="$1"; ' + script, ruta, str(int(ultimas_lineas)))


def comando_listar_copias() -> str:
    """Copias de seguridad que deja el instalador en ``/var/backups``."""
    return sh_c('ls -1dt /var/backups/instalar-todo-* /var/backups/entrada-apache-* 2>/dev/null | head -n 30; true')


# ----------------------------------------------------------------------------- instalador
def empaquetar(ficheros: dict) -> bytes:
    """tar.gz en memoria con ``{nombre: bytes}``. Los ``.sh`` salen ejecutables (755)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tar:
        for nombre, datos in ficheros.items():
            info = tarfile.TarInfo(nombre)
            info.size = len(datos)
            info.mode = 0o755 if nombre.endswith(".sh") else 0o644
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(datos))
    return buf.getvalue()


#: Programa remoto del instalador. Lee de la entrada estándar, por este orden:
#:   1) una línea con N = número de variables;  2) N líneas ``NOMBRE=base64(valor)``;
#:   3) el resto: el tar.gz con el instalador y el portal.
#: Los parámetros posicionales son: $1 = directorio donde dejar los ficheros, $2 = nombre del
#: script a ejecutar y $3… = argumentos del instalador.
_SCRIPT_ENVOLTORIO = r"""
DEST=$1; SCRIPT=$2; shift 2
case "$DEST" in "~"|"~/"*) DEST="$HOME${DEST#"~"}";; esac
IFS= read -r N || exit 70
i=0
while [ "$i" -lt "$N" ]; do
  IFS= read -r L || exit 71
  K=${L%%=*}
  case "$K" in ""|[0-9]*|*[!A-Z0-9_]*) exit 72;; esac
  V=$(printf %s "${L#*=}" | base64 -d) || exit 72
  export "$K=$V"
  i=$((i+1))
done
mkdir -p "$DEST" || exit 73
tar -xzf - -C "$DEST" || exit 74
chmod 755 "$DEST"/*.sh
T=$(mktemp -d "${TMPDIR:-/tmp}/panel-XXXXXXXX") || exit 75
trap 'rm -rf "$T"' EXIT HUP INT TERM
# Si no eres root, el instalador llama a «sudo» muchas veces. Se antepone a PATH un sudo
# mínimo que usa «sudo -A» con un askpass que lee la contraseña del entorno: así sudo no
# necesita terminal y la contraseña no aparece en ningún comando ni fichero.
REAL=$(command -v sudo 2>/dev/null)
if [ "$(id -u)" -ne 0 ] && [ -n "$REAL" ]; then
  mkdir "$T/bin"
  printf '#!/bin/sh\nprintf "%%s\\n" "$PANEL_SUDO_PW"\n' > "$T/askpass"
  printf '#!/bin/sh\nexec "%s" -A "$@"\n' "$REAL" > "$T/bin/sudo"
  chmod 700 "$T/askpass" "$T/bin/sudo"
  export SUDO_ASKPASS="$T/askpass" PATH="$T/bin:$PATH"
fi
cd "$DEST" || exit 76
bash "$DEST/$SCRIPT" "$@" </dev/null
"""


def comando_instalador(directorio: str, script: str, argumentos: Iterable[str]) -> str:
    """Comando que ejecuta el instalador subido por la entrada estándar (ver ``_SCRIPT_ENVOLTORIO``)."""
    return sh_c(_SCRIPT_ENVOLTORIO, directorio, script, *list(argumentos))


def cabecera_entrada(variables: dict) -> bytes:
    """Primera parte de la entrada estándar del instalador: las variables de entorno codificadas.

    Los valores van en base64 para soportar cualquier carácter (comillas, ``$``, saltos…).
    """
    lineas = []
    for nombre, valor in variables.items():
        if not _RE_NOMBRE_VARIABLE.match(nombre):
            raise ValueError("Nombre de variable no válido: %r" % nombre)
        lineas.append("%s=%s" % (nombre, base64.b64encode(valor.encode("utf-8")).decode("ascii")))
    return ("%d\n" % len(lineas) + "".join(l + "\n" for l in lineas)).encode("ascii")


def comando_comprobar_sudo() -> str:
    """Devuelve ``sudo=root|nopasswd|password|ausente`` (para decidir si hay que pedir contraseña)."""
    return sh_c(
        'if [ "$(id -u)" -eq 0 ]; then echo sudo=root; '
        'elif sudo -n true 2>/dev/null; then echo sudo=nopasswd; '
        'elif command -v sudo >/dev/null 2>&1; then echo sudo=password; else echo sudo=ausente; fi')

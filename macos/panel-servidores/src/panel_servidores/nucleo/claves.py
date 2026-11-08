"""Claves SSH: las locales (``~/.ssh``) y el ``authorized_keys`` del servidor.

Reúne lo que en el script original eran ``--generate-key``, ``--install-key`` y
``--check-key``, más lo que una interfaz gráfica permite añadir con poco esfuerzo:

* listar las claves locales con su huella, tipo y si tienen frase de paso,
* generar claves RSA 4096 o ed25519 **con frase de paso** (se pide en un diálogo),
* cargar una clave en el ``ssh-agent`` / Llavero de macOS,
* instalar, comprobar, auditar y **revocar** claves en el servidor,
* olvidar la huella de un servidor en ``known_hosts``.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .. import rutas
from . import remoto
from .askpass import GestorAskpass
from .modelos import Ajustes, Resultado, RC_SSH_FALLO, RC_TIMEOUT
from .ssh import Cancelador, Conexion, ejecutar_proceso

PUB_RE = re.compile(r"^((?:ssh-(?:rsa|dss|ed25519)|ecdsa-sha2-nistp\d+|sk-[a-z0-9@.-]+))\s+"
                    r"([A-Za-z0-9+/]+={0,3})(?:\s+(.*))?$")
OFERTA_RE = re.compile(r"Offering public key: (.+?) (SHA256:\S+)")
ACEPTADA_RE = re.compile(r"Server accepts key: (.+?) (SHA256:\S+)")
AUTENTICADO_RE = re.compile(r'Authenticated to .* using "publickey"|Authentication succeeded \(publickey\)')
RUIDO_DEBUG_RE = re.compile(r"^(debug\d:|OpenSSH_)")

TIPOS_CLAVE = {"ed25519": "Ed25519 (recomendada)", "rsa": "RSA 4096"}


def ssh_dir() -> Path:
    return Path.home() / ".ssh"


def limpiar_error(texto: str) -> str:
    """stderr de ``ssh -v`` sin el ruido de depuración."""
    return "\n".join(l for l in texto.splitlines() if not RUIDO_DEBUG_RE.match(l)).strip()


# ----------------------------------------------------------------------------- claves públicas
def leer_publica(ruta) -> Optional[str]:
    """Primera línea válida de clave pública de un fichero ``.pub`` (o ``None``)."""
    try:
        for linea in Path(ruta).read_text(encoding="utf-8", errors="replace").splitlines():
            if PUB_RE.match(linea.strip()):
                return linea.strip()
    except OSError:
        pass
    return None


def huella_sha256(linea_publica: str) -> str:
    """Huella ``SHA256:…`` de una clave pública, calculada sin ejecutar nada (igual que ssh-keygen -l)."""
    m = PUB_RE.match(linea_publica.strip())
    if not m:
        return ""
    digest = hashlib.sha256(base64.b64decode(m.group(2))).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def cuerpo_base64(linea_publica: str) -> str:
    """El campo ``AAAA…`` de la clave (lo que identifica la clave dentro de authorized_keys)."""
    m = PUB_RE.match(linea_publica.strip())
    return m.group(2) if m else ""


@dataclass
class ClaveLocal:
    """Una clave del equipo (``~/.ssh``)."""

    ruta_privada: str
    ruta_publica: str
    tipo: str = ""
    bits: Optional[int] = None
    huella: str = ""
    comentario: str = ""
    protegida: Optional[bool] = None     # ``None`` = no se pudo saber
    tiene_privada: bool = True


def _ssh_keygen(ajustes: Ajustes) -> str:
    return rutas.buscar_ejecutable("ssh-keygen")


def _ssh_add() -> str:
    return rutas.buscar_ejecutable("ssh-add")


def _correr(args: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, **kw)


def listar_claves_locales(ajustes: Ajustes, carpeta: Optional[Path] = None) -> list:
    """Claves públicas de ``~/.ssh`` con tipo, bits, huella y si la privada tiene frase de paso."""
    carpeta = Path(carpeta) if carpeta else ssh_dir()
    claves = []
    if not carpeta.is_dir():
        return claves
    for pub in sorted(carpeta.glob("*.pub")):
        linea = leer_publica(pub)
        if not linea:
            continue
        priv = pub.with_suffix("")
        r = _correr([_ssh_keygen(ajustes), "-lf", str(pub)])
        tipo, bits, comentario = "", None, ""
        if r.returncode == 0 and r.stdout.strip():
            # «4096 SHA256:abc… comentario (RSA)»
            partes = r.stdout.strip().split(None, 2)
            try:
                bits = int(partes[0])
            except (ValueError, IndexError):
                bits = None
            m = re.search(r"\(([A-Z0-9-]+)\)\s*$", r.stdout.strip())
            tipo = m.group(1) if m else PUB_RE.match(linea).group(1)
            comentario = PUB_RE.match(linea).group(3) or ""
        clave = ClaveLocal(str(priv), str(pub), tipo or PUB_RE.match(linea).group(1), bits,
                           huella_sha256(linea), comentario, tiene_privada=priv.is_file())
        if priv.is_file():
            # -P "" no pide nada: si la clave tiene frase, ssh-keygen falla y lo sabemos.
            y = _correr([_ssh_keygen(ajustes), "-y", "-P", "", "-f", str(priv)])
            clave.protegida = y.returncode != 0
        claves.append(clave)
    return claves


def buscar_publica(identidad: str = "", pubkey: str = "") -> tuple:
    """Clave pública a instalar → ``(linea | None, ruta)``.

    Prioridad (igual que el script): ``pubkey`` explícita; la ``.pub`` de la identidad (o derivada
    de la privada con ``ssh-keygen -y``); y por último ``~/.ssh/id_ed25519.pub``, ``id_rsa.pub``,
    ``id_ecdsa.pub``.
    """
    if pubkey:
        p = os.path.expanduser(pubkey)
        return leer_publica(p), p
    if identidad:
        priv = os.path.expanduser(identidad)
        pub = priv if priv.endswith(".pub") else priv + ".pub"
        linea = leer_publica(pub)
        if linea:
            return linea, pub
        if os.path.isfile(priv):
            r = _correr([rutas.buscar_ejecutable("ssh-keygen"), "-y", "-f", priv])
            if r.returncode == 0 and PUB_RE.match(r.stdout.strip()):
                return r.stdout.strip(), priv + " (-y)"
        return None, pub
    for nombre in ("id_ed25519", "id_rsa", "id_ecdsa"):
        p = ssh_dir() / (nombre + ".pub")
        linea = leer_publica(p)
        if linea:
            return linea, str(p)
    return None, str(ssh_dir() / "id_rsa.pub")


# ----------------------------------------------------------------------------- operaciones locales con askpass
def _correr_con_askpass(askpass: GestorAskpass, respondedor: Callable[[str], Optional[str]], args: list,
                        cancelador: Optional[Cancelador] = None, timeout: float = 120) -> Resultado:
    """Ejecuta un programa de OpenSSH local (``ssh-keygen``, ``ssh-add``) con el askpass gráfico."""
    token = askpass.registrar(respondedor)
    try:
        entorno = dict(os.environ)
        entorno.update(askpass.entorno(token))
        codigo, salida, error, dur = ejecutar_proceso(args, entorno, b"", None, None, timeout, cancelador)
        return Resultado(codigo, salida, error, dur)
    finally:
        askpass.liberar(token)


def generar_clave(ajustes: Ajustes, askpass: GestorAskpass, ruta: str, tipo: str = "ed25519",
                  frase: str = "", comentario: str = "") -> Resultado:
    """Crea un par de claves. **Nunca sobrescribe** una clave existente.

    Si hay ``frase``, ssh-keygen la pide por el askpass (dos veces) y la aplicación contesta: así la
    frase no aparece en la línea de comandos (a diferencia de ``-N frase``).
    """
    destino = Path(os.path.expanduser(ruta))
    if destino.suffix == ".pub":
        destino = destino.with_suffix("")
    if destino.exists() or destino.with_suffix(destino.suffix + ".pub").exists():
        return Resultado(1, "", "Ya existe la clave %s: no se sobrescribe.\n" % destino)
    destino.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    comentario = comentario or "panel-servidores@%s" % socket.gethostname()
    args = [_ssh_keygen(ajustes), "-q", "-t", tipo]
    if tipo == "rsa":
        args += ["-b", "4096"]
    args += ["-C", comentario, "-f", str(destino)]
    if not frase:
        args += ["-N", ""]
    r = _correr_con_askpass(askpass, lambda _p: frase, args)
    if r.ok and not destino.is_file():
        return Resultado(1, r.salida, "ssh-keygen terminó sin crear la clave.\n" + r.error)
    return r


def agregar_al_agente(ajustes: Ajustes, askpass: GestorAskpass, ruta: str,
                      respondedor_frase: Callable[[str], Optional[str]], llavero_macos: bool = True) -> Resultado:
    """``ssh-add`` de una clave; en macOS con ``--apple-use-keychain`` para recordar la frase."""
    ruta = os.path.expanduser(ruta)
    args = [_ssh_add()]
    if llavero_macos and rutas.es_macos():
        args.append("--apple-use-keychain")
    args.append(ruta)
    r = _correr_con_askpass(askpass, respondedor_frase, args)
    if not r.ok and "--apple-use-keychain" in args and re.search(r"unknown option|illegal option|usage", r.error, re.I):
        args.remove("--apple-use-keychain")       # ssh-add antiguo o de Homebrew sin esa opción
        r = _correr_con_askpass(askpass, respondedor_frase, args)
    return r


def listar_agente() -> list:
    """Huellas de las claves cargadas en el ssh-agent (lista de ``(huella, comentario)``)."""
    r = _correr([_ssh_add(), "-l"])
    if r.returncode != 0:
        return []
    filas = []
    for l in r.stdout.splitlines():
        partes = l.split(None, 3)
        if len(partes) >= 3 and partes[1].startswith("SHA256:"):
            filas.append((partes[1], partes[2]))
    return filas


def olvidar_huella(host: str, puerto: int = 0) -> Resultado:
    """Quita un servidor de ``known_hosts`` (``ssh-keygen -R``). Para cuando la huella cambió a propósito."""
    objetivo = "[%s]:%d" % (host, puerto) if puerto and puerto != 22 else host
    r = _correr([rutas.buscar_ejecutable("ssh-keygen"), "-R", objetivo])
    return Resultado(r.returncode, r.stdout, r.stderr)


# ----------------------------------------------------------------------------- authorized_keys remoto
def instalar_clave(conexion: Conexion, linea_publica: str, cancelador: Optional[Cancelador] = None) -> dict:
    """Instala la clave en el servidor. Devuelve ``{"ok", "resultado": added|already, "fichero", "error"}``.

    Como ``ssh-copy-id``, pero idempotente y reparando permisos. Escribe SOLO en el
    ``~/.ssh/authorized_keys`` del usuario con el que se entra.
    """
    r = conexion.ejecutar(remoto.comando_instalar_clave(linea_publica), cancelador=cancelador,
                          etiqueta="instalar clave pública")
    if not r.ok:
        return {"ok": False, "resultado": None, "fichero": None, "error": r.error.strip() or conexion.explicar_fallo(r),
                "codigo": r.codigo}
    info = dict(l.split("=", 1) for l in r.salida.splitlines() if "=" in l)
    return {"ok": True, "resultado": info.get("KEY"), "fichero": info.get("FILE"), "error": "", "codigo": 0}


def revocar_clave(conexion: Conexion, linea_publica: str, cancelador: Optional[Cancelador] = None) -> dict:
    """Quita la clave de ``authorized_keys`` (con copia previa). Devuelve ``resultado``: removed|absent|missing."""
    cuerpo = cuerpo_base64(linea_publica)
    if not cuerpo:
        return {"ok": False, "error": "La clave pública no es válida."}
    r = conexion.ejecutar(remoto.comando_revocar_clave(cuerpo), cancelador=cancelador, etiqueta="revocar clave")
    if not r.ok:
        return {"ok": False, "error": r.error.strip() or conexion.explicar_fallo(r)}
    info = dict(l.split("=", 1) for l in r.salida.splitlines() if "=" in l)
    return {"ok": True, "resultado": info.get("KEY"), "cantidad": int(info.get("COUNT", "0") or 0),
            "copia": info.get("BACKUP"), "error": ""}


def comprobar_acceso_clave(conexion: Conexion, identidad: str = "",
                           cancelador: Optional[Cancelador] = None) -> dict:
    """Valida el acceso **solo con clave** (``--check-key``).

    Abre una conexión con contraseñas desactivadas y ``-v``: si entra, es que ``authorized_keys``
    funciona de verdad. Si la clave tiene frase de paso, el askpass gráfico la pide (mejora sobre
    el script, que exigía tenerla cargada en el ssh-agent).

    Devuelve ``ok, usuario, host, clave{huella,origen,descripcion}, motivo, error`` donde
    ``motivo`` ∈ {timeout, no_keys, not_authorized, connection, other}.
    """
    r = conexion.ejecutar("echo KEYLOGIN_OK; id -un; hostname", solo_clave=True, identidad=identidad,
                          cancelador=cancelador, etiqueta="comprobar acceso solo con clave")
    ofrecidas = OFERTA_RE.findall(r.error)
    aceptadas = ACEPTADA_RE.findall(r.error)
    res = {"ok": False, "codigo": r.codigo, "clave": None, "metodo": None, "usuario": None,
           "host": None, "motivo": None, "error": ""}
    if aceptadas:
        donde, huella = aceptadas[-1]
        res["clave"] = {"huella": huella, "descripcion": donde,
                        "origen": donde.split(" ")[0] if "/" in donde or "\\" in donde else "agent"}
    if r.codigo == 0 and "KEYLOGIN_OK" in r.salida:
        lineas = r.salida.splitlines()
        i = lineas.index("KEYLOGIN_OK")
        res.update(ok=True, usuario=lineas[i + 1].strip() if len(lineas) > i + 1 else "",
                   host=lineas[i + 2].strip() if len(lineas) > i + 2 else "")
        res["metodo"] = "publickey" if AUTENTICADO_RE.search(r.error) else "publickey?"
        return res
    res["error"] = limpiar_error(r.error)
    if r.codigo == RC_TIMEOUT:
        res["motivo"] = "timeout"
    elif r.codigo == RC_SSH_FALLO and "Permission denied" in r.error:
        res["motivo"] = "not_authorized" if ofrecidas else "no_keys"
    elif r.codigo == RC_SSH_FALLO:
        res["motivo"] = "connection"
    else:
        res["motivo"] = "other"
    return res


EXPLICACION_MOTIVO = {
    "no_keys": "ssh no tiene ninguna clave privada que ofrecer. Indica una en el perfil, cárgala en el ssh-agent o créala.",
    "not_authorized": ("La clave se ofreció pero el servidor no la aceptó: no está en authorized_keys o sshd la ignora "
                       "por permisos incorrectos. «Instalar clave» la añade (si falta) y corrige los permisos."),
    "connection": "No se pudo conectar por SSH. Revisa servidor, puerto y huella.",
    "timeout": "Tiempo agotado al conectar.",
    "other": ("Revisa en el servidor los permisos (chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; carpeta "
              "personal no escribible por otros), PubkeyAuthentication y el registro (journalctl -u ssh)."),
}

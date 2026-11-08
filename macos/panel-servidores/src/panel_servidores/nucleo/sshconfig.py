"""Lectura (solo lectura) de ``~/.ssh/config`` para importar servidores como perfiles.

No se intenta implementar todo el lenguaje de ``ssh_config``: se leen los bloques ``Host`` con
nombre concreto (sin comodines) y las opciones que un perfil sabe representar: ``HostName``,
``User``, ``Port``, ``IdentityFile`` y ``ProxyJump``. Cualquier otra cosa sigue funcionando
porque ``ssh`` la lee por su cuenta cuando el perfil usa el alias como destino.

Los perfiles importados usan el **alias** como destino (``destino = alias``): así ``ssh`` aplica
el resto de directivas (``ProxyCommand``, ``Include``, ``Match``…) sin que la aplicación tenga
que entenderlas.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from .modelos import AUTH_AUTO, AUTH_CLAVE, Perfil

_RE_LINEA = re.compile(r"^\s*(?P<clave>[A-Za-z]+)\s*(?:=|\s)\s*(?P<valor>.*?)\s*$")


def ruta_config() -> Path:
    return Path(os.path.expanduser("~/.ssh/config"))


def leer_hosts(ruta: Optional[Path] = None) -> list:
    """Devuelve una lista de diccionarios ``{alias, hostname, user, port, identity, proxyjump}``."""
    ruta = Path(ruta) if ruta else ruta_config()
    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    bloques: list = []
    actual: Optional[list] = None          # lista de bloques que comparten las directivas siguientes
    for bruto in texto.splitlines():
        linea = bruto.split("#", 1)[0].strip() if not bruto.strip().startswith("#") else ""
        if not linea:
            continue
        m = _RE_LINEA.match(linea)
        if not m:
            continue
        clave, valor = m.group("clave").lower(), m.group("valor").strip().strip('"')
        if clave == "host":
            actual = []
            for alias in valor.split():
                if any(c in alias for c in "*?!"):
                    continue                                  # comodines y negaciones: no son servidores
                bloque = {"alias": alias, "hostname": "", "user": "", "port": 0, "identity": "", "proxyjump": ""}
                bloques.append(bloque)
                actual.append(bloque)
        elif clave == "match":
            actual = None
        elif actual:
            for b in actual:
                if clave == "hostname" and not b["hostname"]:
                    b["hostname"] = valor
                elif clave == "user" and not b["user"]:
                    b["user"] = valor
                elif clave == "port" and not b["port"] and valor.isdigit():
                    b["port"] = int(valor)
                elif clave == "identityfile" and not b["identity"]:
                    b["identity"] = valor
                elif clave == "proxyjump" and not b["proxyjump"]:
                    b["proxyjump"] = valor
    return bloques


def a_perfil(bloque: dict) -> Perfil:
    """Perfil con el alias como destino (ssh resuelve el resto desde su configuración)."""
    p = Perfil(nombre=bloque["alias"], destino=bloque["alias"])
    if bloque.get("identity"):
        p.autenticacion = AUTH_CLAVE
        p.identidad = bloque["identity"]
    else:
        p.autenticacion = AUTH_AUTO
    detalle = []
    if bloque.get("hostname"):
        detalle.append("HostName %s" % bloque["hostname"])
    if bloque.get("user"):
        detalle.append("User %s" % bloque["user"])
    if bloque.get("port"):
        detalle.append("Port %d" % bloque["port"])
    if bloque.get("proxyjump"):
        detalle.append("ProxyJump %s" % bloque["proxyjump"])
    p.notas = "Importado de ~/.ssh/config" + (": " + ", ".join(detalle) if detalle else "")
    return p

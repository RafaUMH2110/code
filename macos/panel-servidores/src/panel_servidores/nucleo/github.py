"""API pública de GitHub: repos y carpetas para elegir qué instalar, y descarga de scripts.

Se usa ``urllib`` (sin dependencias). Sin token la API permite 60 peticiones/hora por IP; un
*token personal* (solo lectura de repos públicos, sin permisos) las sube a 5000. El token, si lo
das, se guarda en el Llavero de macOS y nunca en ``ajustes.json``.

Como en el instalador, **se omiten los repos archivados**.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .recursos import ACOMPANANTES, INFORME, INSTALADOR_ISA, INSTALADOR_LOCAL

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
TIMEOUT_S = 15

#: Dónde vive cada script en el repositorio ``code`` (para «Actualizar scripts desde GitHub»).
RUTAS_SCRIPTS = {
    INSTALADOR_LOCAL: "scripts/instalar-todo/instalar-todo.sh",
    INSTALADOR_ISA: "scripts/instalar-todo/instalar-todo-isa.sh",
    INFORME: "scripts/telemet-collector-info/telemet-collector-info.py",
    **{n: "scripts/instalar-todo/" + n for n in ACOMPANANTES},
}


class ErrorGitHub(Exception):
    """Fallo al consultar GitHub (red, límite de peticiones, repo inexistente…)."""


class LimiteGitHub(ErrorGitHub):
    """Se agotó el límite de peticiones sin token."""


@dataclass
class Repo:
    nombre: str
    lenguaje: str = "-"
    tamano_kb: int = 0
    descripcion: str = ""

    def etiqueta(self) -> str:
        return "%s  (%s, %d KB)" % (self.nombre, self.lenguaje, self.tamano_kb)


def _contexto_ssl() -> ssl.SSLContext:
    """Contexto TLS; usa los certificados de ``certifi`` si está (Python de python.org en macOS)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _pedir(url: str, token: str = "", base: str = "") -> object:
    cabeceras = {"Accept": "application/vnd.github+json", "User-Agent": "panel-servidores"}
    if token:
        cabeceras["Authorization"] = "Bearer " + token
    peticion = urllib.request.Request(url, headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_S, context=_contexto_ssl()) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 403 and exc.headers.get("X-RateLimit-Remaining") == "0":
            raise LimiteGitHub("Límite de peticiones de GitHub agotado. Añade un token en Preferencias o espera.") from exc
        if exc.code == 404:
            raise ErrorGitHub("No existe: %s" % url) from exc
        raise ErrorGitHub("GitHub respondió HTTP %d" % exc.code) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ErrorGitHub("No se pudo consultar GitHub: %s" % exc) from exc


def listar_repos(usuario: str, token: str = "", api: str = API) -> list:
    """Repos públicos y **no archivados** de ``usuario`` (todas las páginas)."""
    repos: list = []
    pagina = 1
    while True:
        datos = _pedir("%s/users/%s/repos?type=public&per_page=100&page=%d" % (api, usuario, pagina), token)
        if not isinstance(datos, list):
            raise ErrorGitHub("Respuesta inesperada de GitHub")
        if not datos:
            break
        for d in datos:
            if d.get("archived"):
                continue
            repos.append(Repo(d["name"], d.get("language") or "-", int(d.get("size") or 0), d.get("description") or ""))
        pagina += 1
    if not repos:
        raise ErrorGitHub("No hay repos públicos para %s" % usuario)
    return repos


def listar_carpetas(usuario: str, repo: str, token: str = "", api: str = API) -> list:
    """Carpetas de primer nivel de un repo (sin las que empiezan por punto)."""
    datos = _pedir("%s/repos/%s/%s/contents" % (api, usuario, repo), token)
    if not isinstance(datos, list):
        return []
    return sorted(d["name"] for d in datos if d.get("type") == "dir" and not d["name"].startswith("."))


def descargar_scripts(destino: Path, usuario: str = "RafaUMH2110", repo: str = "code", rama: str = "main",
                      base: str = RAW) -> dict:
    """Descarga los scripts actuales del repo a ``destino``. Devuelve ``{nombre: bytes_descargados}``.

    Si falla alguno no se modifica ninguno (se descarga todo antes de escribir).
    """
    contexto = _contexto_ssl()
    recibidos: dict = {}
    for nombre, ruta in RUTAS_SCRIPTS.items():
        url = "%s/%s/%s/%s/%s" % (base, usuario, repo, rama, ruta)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "panel-servidores"}),
                                        timeout=TIMEOUT_S, context=contexto) as r:
                recibidos[nombre] = r.read()
        except (urllib.error.URLError, OSError) as exc:
            raise ErrorGitHub("No se pudo descargar %s: %s" % (ruta, exc)) from exc
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, datos in recibidos.items():
        fichero = destino / nombre
        fichero.write_bytes(datos)
        fichero.chmod(0o755 if nombre.endswith(".sh") else 0o644)
    return {n: len(d) for n, d in recibidos.items()}

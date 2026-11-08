"""Rutas de la aplicación: datos del usuario, recursos incluidos y utilidades de SSH.

Todo lo que depende del sistema de ficheros del equipo (dónde se guardan los perfiles,
dónde están los scripts incluidos, qué ``ssh`` usar) se concentra aquí, de modo que el
resto del código no tenga que saber si se ejecuta desde VS Code, desde un entorno virtual
o desde el ``.app`` empaquetado.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

#: Variable de entorno que redirige TODOS los datos de la aplicación (útil en pruebas).
VAR_HOME = "PANEL_SERVIDORES_HOME"


def es_macos() -> bool:
    """``True`` si se ejecuta en macOS (la plataforma objetivo)."""
    return sys.platform == "darwin"


def dir_datos() -> Path:
    """Carpeta donde se guardan perfiles y ajustes (se crea si no existe).

    * macOS:  ``~/Library/Application Support/Panel de Servidores``
    * Otros:  ``$XDG_DATA_HOME/panel-servidores`` (solo para desarrollo/pruebas)
    * ``PANEL_SERVIDORES_HOME`` tiene prioridad sobre todo lo anterior.
    """
    forzada = os.environ.get(VAR_HOME)
    if forzada:
        base = Path(forzada)
    elif es_macos():
        base = Path.home() / "Library" / "Application Support" / "Panel de Servidores"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "panel-servidores"
    base.mkdir(parents=True, exist_ok=True)
    return base


def dir_scripts_personalizados() -> Path:
    """Carpeta donde ``Actualizar scripts desde GitHub`` deja las copias descargadas."""
    return dir_datos() / "scripts"


def dir_recursos() -> Path:
    """Carpeta con los recursos incluidos (scripts del repo, icono…).

    Si la aplicación está congelada con PyInstaller, los recursos viven en ``sys._MEIPASS``.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "panel_servidores" / "recursos"
    return Path(__file__).resolve().parent / "recursos"


def buscar_ejecutable(nombre: str, indicada: str = "") -> str:
    """Localiza un ejecutable (``ssh``, ``ssh-keygen``…).

    Una aplicación lanzada desde Finder hereda un ``PATH`` mínimo; por eso, si ``which``
    no lo encuentra, se prueban las carpetas habituales de macOS y Homebrew.
    """
    if indicada:
        return indicada
    hallado = shutil.which(nombre)
    if hallado:
        return hallado
    for carpeta in ("/usr/bin", "/usr/local/bin", "/opt/homebrew/bin", "/bin", "/usr/sbin"):
        candidato = os.path.join(carpeta, nombre)
        if os.access(candidato, os.X_OK):
            return candidato
    return nombre

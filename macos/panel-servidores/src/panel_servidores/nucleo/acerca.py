"""Datos para la ventana «Acerca de»: versiones, rutas y fecha de la última modificación.

Sin Qt: se puede probar con pytest. La interfaz solo añade lo que depende de Qt (versión de PySide6).
"""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import datetime
from typing import List, Tuple

from .. import NOMBRE_APP, ULTIMA_MODIFICACION, __version__, rutas

FORMATO_FECHA = "%Y-%m-%d %H:%M"


def fecha_modificacion() -> datetime:
    """``ULTIMA_MODIFICACION`` como fecha; lanza ``ValueError`` si el formato es incorrecto."""
    return datetime.strptime(ULTIMA_MODIFICACION, FORMATO_FECHA)


def fecha_modificacion_legible() -> str:
    """Por ejemplo «9 de noviembre de 2026, 01:34»."""
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre"]
    d = fecha_modificacion()
    return "%d de %s de %d, %02d:%02d" % (d.day, meses[d.month - 1], d.year, d.hour, d.minute)


def version_ssh(ruta_ssh: str = "") -> str:
    """Primera línea de ``ssh -V`` (OpenSSH escribe la versión en stderr). «no encontrado» si falla."""
    exe = rutas.buscar_ejecutable("ssh", ruta_ssh)
    try:
        r = subprocess.run([exe, "-V"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "no encontrado (%s)" % exe
    linea = ((r.stderr or "") + (r.stdout or "")).strip().splitlines()
    return linea[0] if linea else "desconocida"


def informacion(ruta_ssh: str = "") -> List[Tuple[str, str]]:
    """Pares (etiqueta, valor) con lo relevante para soporte. No incluye ningún secreto."""
    return [
        ("Versión", __version__),
        ("Última modificación", "%s (%s)" % (fecha_modificacion_legible(), ULTIMA_MODIFICACION)),
        ("Python", "%s (%s)" % (platform.python_version(), "empaquetada" if getattr(sys, "frozen", False) else "código fuente")),
        ("Sistema", "%s %s · %s" % (platform.system(), platform.release(), platform.machine())),
        ("Cliente SSH", version_ssh(ruta_ssh)),
        ("Datos y ajustes", str(rutas.dir_datos())),
        ("Scripts propios", str(rutas.dir_scripts_personalizados())),
        ("Scripts incluidos", str(rutas.dir_recursos())),
    ]


def texto_para_copiar(extra: List[Tuple[str, str]] = (), ruta_ssh: str = "") -> str:
    """Bloque de texto plano para pegar en un correo o una incidencia."""
    filas = informacion(ruta_ssh) + list(extra)
    ancho = max(len(e) for e, _ in filas)
    return "%s\n%s\n" % (NOMBRE_APP, "\n".join("%s  %s" % ((e + ":").ljust(ancho + 1), v) for e, v in filas))

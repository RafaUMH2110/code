"""Abrir una sesión interactiva en la aplicación Terminal (o iTerm) de macOS.

Útil cuando se quiere «entrar» en el servidor a mano con el mismo destino y las mismas opciones
que usa la aplicación. Se usa ``osascript`` (AppleScript), que viene con macOS.
"""

from __future__ import annotations

import subprocess

from .modelos import Resultado


def escapar_applescript(texto: str) -> str:
    """Escapa un texto para meterlo entre comillas dobles en AppleScript."""
    return texto.replace("\\", "\\\\").replace('"', '\\"')


def guion_terminal(comando: str, aplicacion: str = "Terminal") -> str:
    """Programa AppleScript que abre ``comando`` en una ventana nueva de Terminal o iTerm."""
    c = escapar_applescript(comando)
    if aplicacion.lower().startswith("iterm"):
        return ('tell application "iTerm"\n activate\n set w to (create window with default profile)\n'
                ' tell current session of w to write text "%s"\nend tell' % c)
    return 'tell application "Terminal"\n activate\n do script "%s"\nend tell' % c


def abrir_en_terminal(comando: str, aplicacion: str = "Terminal") -> Resultado:
    """Abre ``comando`` en la terminal. Falla con un mensaje claro fuera de macOS."""
    try:
        p = subprocess.run(["osascript", "-e", guion_terminal(comando, aplicacion)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=20)
    except FileNotFoundError:
        return Resultado(127, "", "osascript no existe: esta función solo está disponible en macOS.\n")
    except subprocess.TimeoutExpired:
        return Resultado(124, "", "Tiempo agotado al abrir la terminal.\n")
    return Resultado(p.returncode, p.stdout, p.stderr)

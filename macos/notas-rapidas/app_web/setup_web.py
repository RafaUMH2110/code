"""Empaquetado con py2app de la variante pywebview.

    python setup_web.py py2app        # -> dist/Notas Rápidas Web.app
    python setup_web.py py2app -A     # modo alias (desarrollo)
"""

from pathlib import Path

from setuptools import setup

APP = ["notas_web.py"]
ICONO = Path("icono.icns")

OPTIONS = {
    "argv_emulation": False,
    "packages": ["webview", "bottle", "proxy_tools"],   # pywebview y dependencias
    "resources": ["ui"],                                # la interfaz HTML va a Contents/Resources
    "plist": {
        "CFBundleName": "Notas Rápidas Web",
        "CFBundleDisplayName": "Notas Rápidas Web",
        "CFBundleIdentifier": "com.ejemplo.notasrapidasweb",   # cámbialo por el tuyo
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHumanReadableCopyright": "© 2026 Tu nombre",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    },
}
if ICONO.exists():
    OPTIONS["iconfile"] = str(ICONO)

setup(app=APP, name="Notas Rápidas Web", options={"py2app": OPTIONS})

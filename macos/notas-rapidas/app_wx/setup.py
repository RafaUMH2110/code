"""Empaquetado con py2app de la variante wxPython.

    python setup.py py2app        # -> dist/Notas Rápidas Wx.app
    python setup.py py2app -A     # modo alias (desarrollo)
"""

from pathlib import Path

from setuptools import setup

APP = ["notas_wx.py"]
ICONO = Path("icono.icns")

OPTIONS = {
    "argv_emulation": False,        # wx gestiona los ficheros con MacOpenFiles
    "packages": ["wx"],
    "plist": {
        "CFBundleName": "Notas Rápidas Wx",
        "CFBundleDisplayName": "Notas Rápidas Wx",
        "CFBundleIdentifier": "com.ejemplo.notasrapidas.wx",   # cámbialo por el tuyo
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHumanReadableCopyright": "© 2026 Tu nombre",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Texto",
                "CFBundleTypeRole": "Editor",
                "LSItemContentTypes": ["public.plain-text"],
            }
        ],
    },
}
if ICONO.exists():
    OPTIONS["iconfile"] = str(ICONO)

setup(app=APP, name="Notas Rápidas Wx", options={"py2app": OPTIONS})

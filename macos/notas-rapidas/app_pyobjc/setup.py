"""Empaquetado con py2app de la variante PyObjC (AppKit).

    python setup.py py2app        # -> dist/Notas Rápidas PyObjC.app
    python setup.py py2app -A     # modo alias (desarrollo)
"""

from pathlib import Path

from setuptools import setup

APP = ["notas_pyobjc.py"]
ICONO = Path("icono.icns")

OPTIONS = {
    "argv_emulation": False,        # Cocoa entrega los ficheros con application:openFile:
    "includes": ["objc", "AppKit", "Foundation", "PyObjCTools"],
    "plist": {
        "CFBundleName": "Notas Rápidas PyObjC",
        "CFBundleDisplayName": "Notas Rápidas PyObjC",
        "CFBundleIdentifier": "com.ejemplo.notasrapidas.pyobjc",   # cámbialo por el tuyo
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHumanReadableCopyright": "© 2026 Tu nombre",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
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

setup(app=APP, name="Notas Rápidas PyObjC", options={"py2app": OPTIONS})

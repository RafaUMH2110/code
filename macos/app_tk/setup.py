"""Empaquetado con py2app.

Uso (en macOS, dentro de un entorno virtual con py2app instalado):

    python setup.py py2app        # app independiente  -> dist/Notas Rápidas.app
    python setup.py py2app -A     # modo alias (desarrollo, enlaza al código fuente)
"""

from pathlib import Path

from setuptools import setup

APP = ["notas_app.py"]
ICONO = Path("icono.icns")

OPTIONS = {
    "argv_emulation": False,   # Tk ya gestiona OpenDocument; evita problemas en macOS recientes
    "packages": [],            # añade aquí paquetes que py2app no detecte solo
    "includes": ["tkinter"],
    "plist": {
        "CFBundleName": "Notas Rápidas",
        "CFBundleDisplayName": "Notas Rápidas",
        "CFBundleIdentifier": "com.ejemplo.notasrapidas",   # cámbialo por el tuyo
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHumanReadableCopyright": "© 2026 Tu nombre",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,    # nitidez en pantallas Retina
        # Tipos de documento: permite «Abrir con…» y arrastrar ficheros al icono
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

setup(
    app=APP,
    name="Notas Rápidas",
    options={"py2app": OPTIONS},
)

"""Tipografías y hoja de estilo. Mínima a propósito: se respeta el aspecto nativo de macOS."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

COLOR_OK = "#2e9e5b"
COLOR_AVISO = "#c98a00"
COLOR_ERROR = "#d64545"
COLOR_TENUE = "#8a8f98"

HOJA = """
QLabel[rol="titulo"] { font-size: 18px; font-weight: 600; }
QLabel[rol="subtitulo"] { color: palette(mid); }
QLabel[rol="ok"] { color: %(ok)s; }
QLabel[rol="aviso"] { color: %(aviso)s; }
QLabel[rol="error"] { color: %(error)s; }
QGroupBox { font-weight: 600; margin-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
""" % {"ok": COLOR_OK, "aviso": COLOR_AVISO, "error": COLOR_ERROR}


def fuente_mono(tamano: int = 12) -> QFont:
    """Fuente de ancho fijo del sistema (Menlo en macOS)."""
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    f.setPointSize(tamano)
    return f

"""Tipografías, colores y hoja de estilo. Se respeta el aspecto nativo de macOS y solo se añaden
colores semánticos (correcto / aviso / error) que cambian con el tema claro u oscuro.

Reglas de la casa para que todo se vea igual en las dos apariencias:
  * Nunca se escribe un color fijo en una pestaña: se pone un *rol* (``poner_rol(widget, "ok")``) y la
    hoja de estilo decide el color según el tema. Cuando el tema cambia, la hoja se vuelve a aplicar sola.
  * Si hace falta un color en HTML o en un ``QColor``, se pide con ``color("ok")`` (el del tema actual) y
    se suscribe uno a ``notificador.cambiado`` para repintar cuando cambie el tema.
  * La letra de ancho fijo se calcula a partir de la del sistema, no con un tamaño absoluto, para que
    quede proporcionada en cualquier pantalla.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QWidget

# Colores semánticos por tema. Cumplen un contraste mínimo de 4,5:1 con el fondo habitual de cada tema
# (blanco / gris oscuro); lo comprueba tests/test_visual.py.
COLORES = {
    "claro": {"ok": "#1e7a43", "aviso": "#8f5f00", "error": "#c0392b", "tenue": "#6b7280"},
    "oscuro": {"ok": "#4cc26e", "aviso": "#e0a800", "error": "#ff7b72", "tenue": "#9ca3af"},
}

TEMAS = (("sistema", "Según el sistema"), ("claro", "Claro"), ("oscuro", "Oscuro"))


class _Notificador(QObject):
    """Avisa a quien pinte colores «a mano» (HTML, consola) de que el tema ha cambiado."""

    cambiado = Signal()


notificador = _Notificador()


def es_oscuro(paleta: Optional[QPalette] = None) -> bool:
    """¿El fondo de ventana actual es oscuro? Se mira la paleta real, que es lo que se ve en pantalla."""
    p = paleta or QGuiApplication.palette()
    return p.color(QPalette.ColorRole.Window).lightness() < 128


def nombre_tema() -> str:
    return "oscuro" if es_oscuro() else "claro"


def color(rol: str) -> str:
    """Color (``#rrggbb``) del rol semántico ``ok | aviso | error | tenue`` en el tema actual."""
    return COLORES[nombre_tema()][rol]


def qcolor(rol: str) -> QColor:
    return QColor(color(rol))


def hoja() -> str:
    """Hoja de estilo de la aplicación, con los colores del tema actual."""
    c = COLORES[nombre_tema()]
    return """
QLabel[rol="titulo"] { font-size: 18px; font-weight: 600; }
QLabel[rol="subtitulo"] { color: palette(mid); }
QLabel[rol="tenue"] { color: %(tenue)s; }
QLabel[rol="activo"] { font-weight: 600; }
QLabel[rol="ok"] { color: %(ok)s; }
QLabel[rol="aviso"] { color: %(aviso)s; }
QLabel[rol="error"] { color: %(error)s; }
QLabel[rol="ok"][grande="true"], QLabel[rol="error"][grande="true"] { font-size: 18px; font-weight: 600; }
QGroupBox { font-weight: 600; margin-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
""" % c


def poner_rol(widget: QWidget, rol: str) -> None:
    """Asigna un rol de color/estilo a ``widget`` y fuerza que Qt lo vuelva a evaluar."""
    widget.setProperty("rol", rol)
    estilo = widget.style()
    estilo.unpolish(widget)
    estilo.polish(widget)
    widget.update()


def _reaplicar() -> None:
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(hoja())
    notificador.cambiado.emit()


def instalar(app: QApplication) -> None:
    """Aplica la hoja de estilo y la mantiene al día cuando el sistema cambia de tema."""
    app.setStyleSheet(hoja())
    hints = app.styleHints()
    if hasattr(hints, "colorSchemeChanged"):
        # La paleta se actualiza justo después de la señal: se espera un instante para leerla ya cambiada.
        hints.colorSchemeChanged.connect(lambda _e: QTimer.singleShot(0, _reaplicar))


def aplicar_tema(modo: str) -> None:
    """Fuerza ``claro`` u ``oscuro``, o vuelve al del sistema con ``sistema``. Requiere Qt 6.8 o superior."""
    from PySide6.QtCore import Qt
    hints = QGuiApplication.styleHints()
    if not hasattr(hints, "setColorScheme"):
        return
    if modo == "claro":
        hints.setColorScheme(Qt.ColorScheme.Light)
    elif modo == "oscuro":
        hints.setColorScheme(Qt.ColorScheme.Dark)
    else:
        hints.unsetColorScheme()
    QTimer.singleShot(0, _reaplicar)


def fuente_mono(tamano: Optional[float] = None) -> QFont:
    """Fuente de ancho fijo del sistema (Menlo en macOS). Sin ``tamano`` es un punto menor que la de la
    interfaz, que es lo que mejor casa con ella en cualquier plataforma."""
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if tamano is None:
        base = QGuiApplication.font().pointSizeF()
        tamano = max(9.0, (base if base > 0 else 13.0) - 1)
    f.setPointSizeF(float(tamano))
    return f


def instalar_traduccion(app: QApplication) -> None:
    """Carga la traducción al español de Qt (botones Sí/No, menús del sistema, «Buscar»…). Si el paquete no la
    incluye no pasa nada: los diálogos propios ya llevan sus botones en español (``widgets.botones_es``)."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    tr = QTranslator(app)
    carpeta = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if tr.load(QLocale("es_ES"), "qtbase", "_", carpeta):
        app.installTranslator(tr)

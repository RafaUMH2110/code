"""Arranque de la aplicación gráfica."""

from __future__ import annotations

import sys

from . import IDENTIFICADOR_APP, NOMBRE_APP, __version__


def main(argv=None) -> int:
    """Crea la aplicación Qt, el contexto y la ventana principal, y entra en el bucle de eventos."""
    from PySide6.QtWidgets import QApplication

    from .nucleo.almacen import Almacen
    from .nucleo.askpass import GestorAskpass
    from .nucleo.secretos import Llavero
    from . import rutas
    from .ui import estilo, hilos
    from .ui.contexto import Contexto
    from .ui.puente import PuenteInteraccion
    from .ui.ventana_principal import VentanaPrincipal

    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName(NOMBRE_APP)
    app.setApplicationVersion(__version__)
    app.setOrganizationDomain(IDENTIFICADOR_APP)
    estilo.instalar(app)
    estilo.instalar_traduccion(app)
    hilos.iniciar()

    icono = rutas.dir_recursos().parent / "icono.png"
    if icono.is_file():
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(icono)))

    almacen = Almacen()
    estilo.aplicar_tema(almacen.ajustes.tema)      # apariencia guardada (sistema / claro / oscuro)
    askpass = GestorAskpass()
    askpass.iniciar()
    llavero = Llavero()
    ventana_ref: list = [None]
    puente = PuenteInteraccion(lambda: ventana_ref[0], lambda: llavero.disponible)
    ctx = Contexto(almacen, askpass, llavero, puente)
    ventana = VentanaPrincipal(ctx)
    ventana_ref[0] = ventana
    ventana.show()
    try:
        return app.exec()
    finally:
        ctx.cerrar_todo()
        askpass.detener()

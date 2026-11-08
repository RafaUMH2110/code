"""Trabajo en segundo plano y comunicación segura con el hilo de la interfaz.

Qt solo permite tocar widgets desde el hilo principal. Las operaciones SSH tardan (y pueden
quedarse esperando una contraseña), así que se ejecutan en hilos normales de Python; cuando
necesitan avisar a la interfaz lo hacen con :func:`en_gui`, que **encola** la llamada para que
se ejecute en el hilo principal.

Nota técnica: conectar una señal directamente a una ``lambda`` ejecuta la lambda en el hilo del
que *emite*, no en el de la interfaz. Por eso todo pasa por un único ``QObject`` que vive en el
hilo principal (``_Despachador``): una señal con un slot de un ``QObject`` sí se entrega en el
hilo de ese objeto.
"""

from __future__ import annotations

import threading
import traceback
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal, Slot, QThread, QCoreApplication

from ..nucleo.ssh import Cancelador


class _Despachador(QObject):
    """Recibe llamadas desde cualquier hilo y las ejecuta en el hilo en el que vive (el principal)."""

    _solicitud = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._solicitud.connect(self._ejecutar, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def _ejecutar(self, funcion: Callable[[], None]) -> None:
        try:
            funcion()
        except Exception:                           # una devolución de llamada defectuosa no debe tumbar la app
            traceback.print_exc()

    def publicar(self, funcion: Callable[[], None]) -> None:
        self._solicitud.emit(funcion)


_despachador: Optional[_Despachador] = None


def iniciar() -> None:
    """Crea el despachador. Debe llamarse una vez, desde el hilo principal, tras crear la QApplication."""
    global _despachador
    if _despachador is None:
        _despachador = _Despachador()
        _despachador.moveToThread(QCoreApplication.instance().thread())


def en_gui(funcion: Callable[[], None]) -> None:
    """Ejecuta ``funcion`` en el hilo de la interfaz (se puede llamar desde cualquier hilo)."""
    if _despachador is None:                        # sin Qt inicializado (pruebas de núcleo): ejecución directa
        funcion()
    else:
        _despachador.publicar(funcion)


def es_hilo_gui() -> bool:
    return QThread.currentThread() is QCoreApplication.instance().thread()


class Trabajo:
    """Una operación en segundo plano con cancelación y devoluciones de llamada en el hilo de la interfaz.

    ``funcion(trabajo)`` se ejecuta en un hilo; dentro puede usar ``trabajo.cancelador`` (para pasarlo
    al núcleo) y ``trabajo.linea(texto, es_error)`` (para enviar salida en vivo a la interfaz).
    """

    def __init__(self, funcion: Callable[["Trabajo"], object], titulo: str = "",
                 al_terminar: Optional[Callable[[object], None]] = None,
                 al_error: Optional[Callable[[str], None]] = None,
                 al_linea: Optional[Callable[[str, bool], None]] = None,
                 al_fin: Optional[Callable[[], None]] = None) -> None:
        self.funcion = funcion
        self.titulo = titulo
        self.cancelador = Cancelador()
        self._al_terminar, self._al_error, self._al_linea, self._al_fin = al_terminar, al_error, al_linea, al_fin
        self._hilo: Optional[threading.Thread] = None
        self.en_curso = False

    def linea(self, texto: str, es_error: bool = False) -> None:
        """Envía una línea de salida a la interfaz (thread-safe)."""
        if self._al_linea:
            en_gui(lambda: self._al_linea(texto, es_error))        # type: ignore[misc]

    def cancelar(self) -> None:
        self.cancelador.cancelar()

    def iniciar(self) -> "Trabajo":
        self.en_curso = True
        self._hilo = threading.Thread(target=self._correr, name="trabajo-" + (self.titulo or "?"), daemon=True)
        self._hilo.start()
        return self

    def _correr(self) -> None:
        try:
            resultado = self.funcion(self)
        except Exception:
            detalle = traceback.format_exc()
            self.en_curso = False
            if self._al_error:
                en_gui(lambda: self._al_error(detalle))            # type: ignore[misc]
        else:
            self.en_curso = False
            if self._al_terminar:
                en_gui(lambda: self._al_terminar(resultado))       # type: ignore[misc]
        finally:
            self.en_curso = False
            if self._al_fin:
                en_gui(self._al_fin)

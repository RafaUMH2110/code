"""Clase base de las pestañas: gestión del servidor activo y de las tareas en segundo plano."""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from PySide6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from ...nucleo.modelos import Perfil
from ..contexto import Contexto
from ..hilos import Trabajo
from ..widgets import BarraTarea


class PaginaBase(QWidget):
    """Una pestaña. Las subclases construyen su interfaz y sobrescriben ``perfil_cambiado``."""

    #: Texto de la pestaña.
    titulo = ""

    def __init__(self, ctx: Contexto, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ctx = ctx
        self.perfil: Optional[Perfil] = None
        self.barra = BarraTarea()
        self._trabajo: Optional[Trabajo] = None
        self.raiz = QVBoxLayout(self)

    # ------------------------------------------------------------------ servidor activo
    def poner_perfil(self, perfil: Optional[Perfil]) -> None:
        """La ventana avisa de que el servidor seleccionado cambió (o se editó)."""
        self.perfil = perfil
        self.perfil_cambiado()

    def perfil_cambiado(self) -> None:
        """Las subclases limpian o recalculan lo que dependa del servidor."""

    def hay_perfil(self) -> bool:
        if self.perfil is None:
            self.barra.poner("Elige un servidor en la lista de la izquierda (o crea uno con «+»).", "aviso")
            return False
        return True

    # ------------------------------------------------------------------ diálogos
    def confirmar(self, titulo: str, texto: str, forzar: bool = False) -> bool:
        """Pide confirmación antes de acciones que modifican el servidor (se puede desactivar en Preferencias)."""
        if not forzar and not self.ctx.ajustes.confirmar_acciones:
            return True
        r = QMessageBox.question(self, titulo, texto, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        return r == QMessageBox.StandardButton.Yes

    def error(self, texto: str) -> None:
        self.barra.poner(texto.strip().splitlines()[0] if texto.strip() else "Error", "error")
        self.ctx.registrar("ERROR: " + texto.strip().replace("\n", " | ")[:400])
        QMessageBox.warning(self, "Panel de Servidores", texto.strip())

    # ------------------------------------------------------------------ tareas
    @property
    def ocupada(self) -> bool:
        return self._trabajo is not None and self._trabajo.en_curso

    def correr(self, texto: str, funcion: Callable[[Trabajo], object], al_terminar: Callable[[object], None], *,
               deshabilitar: Iterable[QWidget] = (), al_linea: Optional[Callable[[str, bool], None]] = None,
               al_fin: Optional[Callable[[], None]] = None) -> Optional[Trabajo]:
        """Ejecuta ``funcion`` en segundo plano. Una sola tarea a la vez por pestaña."""
        if self.ocupada:
            self.barra.poner("Ya hay una operación en curso en esta pestaña.", "aviso")
            return None
        botones = list(deshabilitar)
        for b in botones:
            b.setEnabled(False)

        def terminar() -> None:
            for b in botones:
                b.setEnabled(True)
            self.barra.fin()
            if al_fin:
                al_fin()

        def fallo(detalle: str) -> None:
            self.error("Error interno:\n" + detalle)

        t = Trabajo(funcion, texto, al_terminar=al_terminar, al_error=fallo, al_linea=al_linea, al_fin=terminar)
        self._trabajo = t
        self.barra.iniciar(t, texto)
        self.ctx.registrar("▶ " + texto)
        t.iniciar()
        return t

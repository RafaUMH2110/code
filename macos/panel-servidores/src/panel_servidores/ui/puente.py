"""Puente entre el núcleo y los diálogos: contesta a las preguntas del núcleo con ventanas.

El núcleo pide datos mediante el protocolo ``Interaccion`` (``pedir_secreto`` / ``confirmar``)
desde hilos de trabajo —incluido el hilo del *askpass*, que atiende a ``ssh``—. Aquí cada
petición se traslada al hilo de la interfaz, se muestra el diálogo y el hilo que preguntó
**espera** a que el usuario conteste.

Solo se muestra un diálogo a la vez (cerrojo): si dos operaciones piden contraseña a la vez, la
segunda espera su turno en lugar de apilar ventanas.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
                               QWidget)

from . import hilos
from .widgets import botones_es


class DialogoSecreto(QDialog):
    """Pide una contraseña, frase de paso o código con el texto oculto."""

    def __init__(self, titulo: str, mensaje: str, permitir_recordar: bool, padre: Optional[QWidget] = None):
        super().__init__(padre)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumWidth(440)
        capa = QVBoxLayout(self)
        etiqueta = QLabel(mensaje)
        etiqueta.setWordWrap(True)
        capa.addWidget(etiqueta)
        self.campo = QLineEdit()
        self.campo.setEchoMode(QLineEdit.EchoMode.Password)
        capa.addWidget(self.campo)
        self.ver = QCheckBox("Mostrar lo que escribo")
        self.ver.toggled.connect(lambda v: self.campo.setEchoMode(QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password))
        capa.addWidget(self.ver)
        self.recordar = QCheckBox("Guardar en el Llavero de macOS")
        self.recordar.setVisible(permitir_recordar)
        capa.addWidget(self.recordar)
        botones = botones_es(QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel))
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)
        self.campo.setFocus()


class PuenteInteraccion:
    """Implementa ``nucleo.modelos.Interaccion`` con diálogos Qt."""

    def __init__(self, obtener_ventana: Callable[[], Optional[QWidget]], llavero_disponible: Callable[[], bool]):
        self._ventana = obtener_ventana
        self._llavero_disponible = llavero_disponible
        self._turno = threading.Lock()

    # ------------------------------------------------------------------ mecanismo común
    def _preguntar_en_gui(self, construir_y_mostrar: Callable[[], object]) -> object:
        """Ejecuta ``construir_y_mostrar`` en el hilo de la interfaz y devuelve su resultado."""
        if hilos.es_hilo_gui():
            return construir_y_mostrar()
        hecho = threading.Event()
        caja: list = [None]

        def tarea() -> None:
            try:
                caja[0] = construir_y_mostrar()
            finally:
                hecho.set()

        with self._turno:
            hilos.en_gui(tarea)
            hecho.wait()
        return caja[0]

    # ------------------------------------------------------------------ protocolo Interaccion
    def pedir_secreto(self, titulo: str, mensaje: str, permitir_recordar: bool = False) -> Optional[tuple]:
        def mostrar():
            dlg = DialogoSecreto(titulo, mensaje, permitir_recordar and self._llavero_disponible(), self._ventana())
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return None
            return dlg.campo.text(), dlg.recordar.isChecked()
        return self._preguntar_en_gui(mostrar)               # type: ignore[return-value]

    def confirmar(self, titulo: str, mensaje: str) -> bool:
        def mostrar():
            caja = QMessageBox(self._ventana())
            caja.setIcon(QMessageBox.Icon.Question)
            caja.setWindowTitle(titulo)
            caja.setText(mensaje)
            caja.setTextFormat(caja.textFormat().PlainText)
            caja.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            caja.setDefaultButton(QMessageBox.StandardButton.No)
            return caja.exec() == QMessageBox.StandardButton.Yes
        return bool(self._preguntar_en_gui(mostrar))

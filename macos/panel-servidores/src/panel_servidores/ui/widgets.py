"""Piezas de interfaz reutilizables por varias pestañas."""

from __future__ import annotations

import json
from typing import Optional

from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QWidget, QHeaderView, QAbstractItemView)

from ..nucleo.ansi import ansi_a_html, quitar_ansi
from . import estilo
from .hilos import Trabajo


class ConsolaAnsi(QPlainTextEdit):
    """Registro de solo lectura que entiende los colores ANSI y limita su tamaño."""

    def __init__(self, maximo_lineas: int = 20000, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(estilo.fuente_mono(11))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setMaximumBlockCount(maximo_lineas)

    def anadir(self, texto: str, es_error: bool = False) -> None:
        """Añade una o varias líneas (con ANSI) al final y mantiene el desplazamiento si el usuario estaba abajo."""
        barra = self.verticalScrollBar()
        abajo = barra.value() >= barra.maximum() - 4
        html = ansi_a_html(texto.rstrip("\n"), envolver=False)
        if es_error:
            html = '<span style="color:%s">%s</span>' % (estilo.COLOR_ERROR, html)
        self.appendHtml(html.replace("\n", "<br>"))
        if abajo:
            barra.setValue(barra.maximum())

    def texto_plano(self) -> str:
        return self.toPlainText()


class VisorTexto(QTextBrowser):
    """Muestra un informe con colores ANSI (solo lectura, con búsqueda por Cmd+F del sistema)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFont(estilo.fuente_mono(11))
        self.setOpenLinks(False)
        self._crudo = ""

    def poner(self, texto_ansi: str) -> None:
        self._crudo = texto_ansi
        self.setHtml(ansi_a_html(texto_ansi))

    def texto_sin_color(self) -> str:
        return quitar_ansi(self._crudo)


class BarraTarea(QWidget):
    """Fila «estado + progreso + Cancelar» que acompaña a cada pestaña."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        self.estado = QLabel("")
        self.estado.setWordWrap(True)
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 0)
        self.progreso.setMaximumWidth(140)
        self.progreso.setTextVisible(False)
        self.progreso.hide()
        self.cancelar = QPushButton("Cancelar")
        self.cancelar.hide()
        capa.addWidget(self.estado, 1)
        capa.addWidget(self.progreso)
        capa.addWidget(self.cancelar)
        self._trabajo: Optional[Trabajo] = None
        self.cancelar.clicked.connect(self._cancelar)

    def _cancelar(self) -> None:
        if self._trabajo:
            self._trabajo.cancelar()
            self.estado.setText("Cancelando…")

    def iniciar(self, trabajo: Trabajo, texto: str) -> None:
        self._trabajo = trabajo
        self.poner(texto)
        self.progreso.show()
        self.cancelar.show()

    def fin(self) -> None:
        self._trabajo = None
        self.progreso.hide()
        self.cancelar.hide()

    def poner(self, texto: str, rol: str = "") -> None:
        self.estado.setProperty("rol", rol)
        self.estado.style().unpolish(self.estado)
        self.estado.style().polish(self.estado)
        self.estado.setText(texto)


def tabla(columnas: list, parent: Optional[QWidget] = None, seleccion_filas: bool = True) -> QTableWidget:
    """Tabla de solo lectura con cabeceras ajustables, filas alternas y sin edición."""
    t = QTableWidget(0, len(columnas), parent)
    t.setHorizontalHeaderLabels(columnas)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    t.horizontalHeader().setStretchLastSection(True)
    if seleccion_filas:
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    return t


def rellenar(t: QTableWidget, filas: list, colores: Optional[list] = None) -> None:
    """Sustituye el contenido de ``t`` por ``filas`` (lista de tuplas de texto)."""
    t.setRowCount(0)
    t.setRowCount(len(filas))
    for i, fila in enumerate(filas):
        for j, valor in enumerate(fila):
            item = QTableWidgetItem(str(valor))
            if colores and colores[i]:
                item.setForeground(QColor(colores[i]))
            t.setItem(i, j, item)
    t.resizeColumnsToContents()
    t.horizontalHeader().setStretchLastSection(True)


def copiar(texto: str) -> None:
    QGuiApplication.clipboard().setText(texto)


def guardar_texto(parent: QWidget, titulo: str, nombre: str, contenido: str, filtro: str = "Todos (*)") -> Optional[str]:
    """Diálogo «Guardar como…» y escritura UTF-8. Devuelve la ruta o ``None`` si se cancela."""
    ruta, _ = QFileDialog.getSaveFileName(parent, titulo, nombre, filtro)
    if not ruta:
        return None
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)
    return ruta


def json_bonito(datos: object) -> str:
    return json.dumps(datos, indent=2, ensure_ascii=False)

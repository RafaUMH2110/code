"""Piezas de interfaz reutilizables por varias pestañas."""

from __future__ import annotations

import json
from collections import deque
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QWidget, QHeaderView, QAbstractItemView,
                               QDialogButtonBox, QTreeWidget)

from ..nucleo.ansi import ansi_a_html, quitar_ansi
from . import estilo
from .hilos import Trabajo


class ConsolaAnsi(QPlainTextEdit):
    """Registro de solo lectura que entiende los colores ANSI y limita su tamaño.

    Guarda el texto original de cada anotación para poder repintarlo con la paleta del otro tema cuando el
    usuario cambia entre claro y oscuro (los colores ya convertidos a HTML no se pueden «recolorear»)."""

    def __init__(self, maximo_lineas: int = 20000, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(estilo.fuente_mono())
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setMaximumBlockCount(maximo_lineas)
        self._anotaciones: deque = deque(maxlen=maximo_lineas)
        estilo.notificador.cambiado.connect(self._repintar)

    def _html(self, texto: str, es_error: bool) -> str:
        html = ansi_a_html(texto.rstrip("\n"), envolver=False, oscuro=estilo.es_oscuro())
        if es_error:
            html = '<span style="color:%s">%s</span>' % (estilo.color("error"), html)
        return html.replace("\n", "<br>")

    def anadir(self, texto: str, es_error: bool = False) -> None:
        """Añade una o varias líneas (con ANSI) al final y mantiene el desplazamiento si el usuario estaba abajo."""
        barra = self.verticalScrollBar()
        abajo = barra.value() >= barra.maximum() - 4
        self._anotaciones.append((texto, es_error))
        self.appendHtml(self._html(texto, es_error))
        if abajo:
            barra.setValue(barra.maximum())

    def clear(self) -> None:  # noqa: D401 - sobrescribe QPlainTextEdit.clear
        self._anotaciones.clear()
        super().clear()

    def _repintar(self) -> None:
        """Vuelve a escribir todo con los colores del tema actual."""
        self.setFont(estilo.fuente_mono())
        super().clear()
        for texto, es_error in self._anotaciones:
            self.appendHtml(self._html(texto, es_error))
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def texto_plano(self) -> str:
        return self.toPlainText()


class VisorTexto(QTextBrowser):
    """Muestra un informe con colores ANSI (solo lectura, con búsqueda por Cmd+F del sistema)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFont(estilo.fuente_mono())
        self.setOpenLinks(False)
        self._crudo = ""
        estilo.notificador.cambiado.connect(lambda: self.poner(self._crudo) if self._crudo else None)

    def poner(self, texto_ansi: str) -> None:
        self._crudo = texto_ansi
        self.setHtml(ansi_a_html(texto_ansi, oscuro=estilo.es_oscuro()))

    def texto_sin_color(self) -> str:
        return quitar_ansi(self._crudo)


class VistaComando(QPlainTextEdit):
    """Línea de comando de solo lectura que **se ajusta al ancho** (una QLineEdit cortaría el final de las
    órdenes largas). Mantiene ``text()`` / ``setText()`` para usarse como un campo de texto."""

    def __init__(self, parent: Optional[QWidget] = None, lineas: int = 2):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(estilo.fuente_mono())
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(self.wordWrapMode().WrapAnywhere)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTabChangesFocus(True)
        alto = self.fontMetrics().lineSpacing() * lineas + 2 * self.frameWidth() + 12
        self.setFixedHeight(alto)

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, texto: str) -> None:
        self.setPlainText(texto)


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
        estilo.poner_rol(self.estado, rol)
        self.estado.setText(texto)


ANCHO_MAX_COLUMNA = 460      # una columna de texto largo no se come toda la tabla; el resto se ve con el tooltip
MARGEN_COLUMNA = 14          # aire a cada lado del contenido


def ajustar_columnas(t: QTableWidget) -> None:
    """Da a cada columna el ancho de su contenido **o de su cabecera, el mayor**, con un tope.

    ``resizeColumnsToContents`` por sí solo deja la cabecera cortada en tablas vacías o con textos cortos;
    aquí se parte de ``sectionSizeHint`` (lo que de verdad necesita la cabecera, con sus márgenes)."""
    cab = t.horizontalHeader()
    for c in range(t.columnCount()):
        ancho = max(cab.sectionSizeHint(c) + MARGEN_COLUMNA, t.sizeHintForColumn(c) + MARGEN_COLUMNA)
        t.setColumnWidth(c, min(ancho, max(ANCHO_MAX_COLUMNA, cab.sectionSizeHint(c))))
    cab.setStretchLastSection(True)


def tabla(columnas: list, parent: Optional[QWidget] = None, seleccion_filas: bool = True) -> QTableWidget:
    """Tabla de solo lectura con el mismo aspecto en todas las pestañas: cabeceras alineadas a la izquierda y
    sin resaltar, columnas ajustables, filas alternas, texto largo abreviado por el centro y sin edición."""
    t = QTableWidget(0, len(columnas), parent)
    t.setHorizontalHeaderLabels(columnas)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.setWordWrap(False)
    t.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    t.setShowGrid(False)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(max(24, t.fontMetrics().height() + 10))
    cab = t.horizontalHeader()
    cab.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    cab.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    cab.setHighlightSections(False)
    cab.setMinimumSectionSize(40)
    cab.setStretchLastSection(True)
    if seleccion_filas:
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    ajustar_columnas(t)
    return t


def preparar_arbol(a: QTreeWidget) -> QTreeWidget:
    """Mismo aspecto de cabecera y de filas que ``tabla`` para los árboles (checkbox + columnas)."""
    cab = a.header()
    cab.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    cab.setHighlightSections(False)
    cab.setMinimumSectionSize(40)
    cab.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    cab.setStretchLastSection(True)
    a.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    a.setAlternatingRowColors(True)
    a.setUniformRowHeights(True)
    ajustar_arbol(a)
    return a


def ajustar_arbol(a: QTreeWidget) -> None:
    """Como ``ajustar_columnas``: cada columna, al menos tan ancha como su cabecera y su contenido (con tope)."""
    cab = a.header()
    for c in range(a.columnCount()):
        a.resizeColumnToContents(c)
        ancho = max(cab.sectionSizeHint(c) + MARGEN_COLUMNA, a.columnWidth(c) + MARGEN_COLUMNA)
        a.setColumnWidth(c, min(ancho, max(ANCHO_MAX_COLUMNA, cab.sectionSizeHint(c))))
    cab.setStretchLastSection(True)


def rellenar(t: QTableWidget, filas: list, colores: Optional[list] = None) -> None:
    """Sustituye el contenido de ``t`` por ``filas`` (lista de tuplas de texto).

    ``colores`` es una lista (una entrada por fila) con un rol de ``estilo`` (``ok | aviso | error | tenue``)
    o ``None``; se resuelve con el tema actual al pintar."""
    t.setRowCount(0)
    t.setRowCount(len(filas))
    for i, fila in enumerate(filas):
        for j, valor in enumerate(fila):
            item = QTableWidgetItem(str(valor))
            item.setToolTip(str(valor))       # el texto abreviado se puede leer entero al pasar el ratón
            if colores and colores[i]:
                item.setForeground(estilo.qcolor(colores[i]))
            t.setItem(i, j, item)
    ajustar_columnas(t)


_TEXTOS_BOTONES = {QDialogButtonBox.StandardButton.Save: "Guardar", QDialogButtonBox.StandardButton.Cancel: "Cancelar",
                   QDialogButtonBox.StandardButton.Ok: "Aceptar", QDialogButtonBox.StandardButton.Close: "Cerrar"}


def botones_es(caja: QDialogButtonBox) -> QDialogButtonBox:
    """Pone en español los botones estándar de un diálogo aunque no esté cargada la traducción de Qt
    (por ejemplo en la app empaquetada). Devuelve la misma caja para poder encadenarlo."""
    for boton_std, texto in _TEXTOS_BOTONES.items():
        b = caja.button(boton_std)
        if b is not None:
            b.setText(texto)
    return caja


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

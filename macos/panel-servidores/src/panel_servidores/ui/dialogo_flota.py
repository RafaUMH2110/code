"""Informe de varios servidores a la vez: una tabla comparativa de estado.

Recorre los servidores marcados, uno tras otro (cada uno con su propia conexión y credenciales) y
muestra errores, avisos y tiempo. Con doble clic se abre el informe completo de ese servidor.
Se puede exportar a CSV para guardarlo o pegarlo en una hoja de cálculo.
"""

from __future__ import annotations

import csv
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QSplitter, QVBoxLayout, QWidget)

from ..nucleo import colector
from ..nucleo.colector import Informe, OpcionesInforme
from . import estilo
from .widgets import BarraTarea, VisorTexto, rellenar, tabla
from .hilos import Trabajo, en_gui


class DialogoFlota(QDialog):
    def __init__(self, ctx, padre: Optional[QWidget] = None):
        super().__init__(padre)
        self.ctx = ctx
        self.setWindowTitle("Informe de varios servidores")
        self.resize(980, 640)
        self._informes: dict = {}
        self._trabajo: Optional[Trabajo] = None
        capa = QVBoxLayout(self)

        arriba = QHBoxLayout()
        self.lista = QListWidget()
        self.lista.setMaximumWidth(260)
        for p in ctx.almacen.perfiles:
            it = QListWidgetItem(p.etiqueta())
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            it.setData(Qt.ItemDataRole.UserRole, p.id)
            self.lista.addItem(it)
        izq = QVBoxLayout()
        izq.addWidget(QLabel("Servidores:"))
        izq.addWidget(self.lista, 1)
        self.c_servicio = QCheckBox("Consultar el servicio systemd")
        self.c_servicio.setChecked(True)
        izq.addWidget(self.c_servicio)
        arriba.addLayout(izq)
        der = QVBoxLayout()
        self.tabla = tabla(["Servidor", "Estado", "Errores", "Avisos", "Segundos", "Detalle"])
        self.visor = VisorTexto()
        div = QSplitter(Qt.Orientation.Vertical)
        div.addWidget(self.tabla)
        div.addWidget(self.visor)
        div.setSizes([260, 300])
        der.addWidget(div, 1)
        arriba.addLayout(der, 1)
        capa.addLayout(arriba, 1)

        fila = QHBoxLayout()
        self.barra = BarraTarea()
        self.b_ejecutar = QPushButton("Generar informes")
        self.b_csv = QPushButton("Exportar CSV…")
        self.b_csv.setEnabled(False)
        fila.addWidget(self.barra, 1)
        fila.addWidget(self.b_csv)
        fila.addWidget(self.b_ejecutar)
        capa.addLayout(fila)
        self.b_ejecutar.clicked.connect(self.ejecutar)
        self.b_csv.clicked.connect(self.exportar)
        self.tabla.itemSelectionChanged.connect(self._mostrar_seleccion)
        self._filas: list = []

    def _marcados(self) -> list:
        ids = [self.lista.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lista.count())
               if self.lista.item(i).checkState() == Qt.CheckState.Checked]
        return [p for p in self.ctx.almacen.perfiles if p.id in ids]

    def ejecutar(self) -> None:
        perfiles = self._marcados()
        if not perfiles:
            self.barra.poner("Marca al menos un servidor.", "aviso")
            return
        recursos, idioma, sin_servicio = self.ctx.recursos(), self.ctx.ajustes.idioma_informe, not self.c_servicio.isChecked()
        self._informes.clear()
        self._filas = []
        self.tabla.setRowCount(0)
        self.b_ejecutar.setEnabled(False)

        def trabajo(t: Trabajo):
            for n, p in enumerate(perfiles, 1):
                if t.cancelador.cancelado:
                    break
                en_gui(lambda p=p, n=n: self.barra.poner("(%d/%d) %s…" % (n, len(perfiles), p.etiqueta())))
                con = self.ctx.conexion(p)
                o = OpcionesInforme(ruta_config=p.ruta_config, servicio=p.servicio, sin_servicio=sin_servicio, idioma=idioma)
                inf = colector.generar_informe(con, recursos, o, t.cancelador)
                en_gui(lambda p=p, inf=inf: self._anadir(p, inf))
            return len(perfiles)

        def fin():
            self.b_ejecutar.setEnabled(True)
            self.barra.fin()
            self.b_csv.setEnabled(bool(self._filas))
            self.barra.poner("Terminado.", "ok")

        self._trabajo = Trabajo(trabajo, "flota", al_error=lambda d: self.barra.poner(d.strip().splitlines()[-1], "error"),
                                al_fin=fin)
        self.barra.iniciar(self._trabajo, "Generando informes…")
        self._trabajo.iniciar()

    def _anadir(self, perfil, inf: Informe) -> None:
        if inf.ok:
            estado = "correcto" if inf.codigo == 0 else "con errores"
            detalle = "; ".join(d["message"] for d in inf.diagnostico if d.get("level") == "err")[:200]
        else:
            estado = "sin informe"
            detalle = (inf.error.splitlines() or ["código %d" % inf.codigo])[0][:200]
        fila = (perfil.etiqueta(), estado, inf.errores, inf.avisos, "%.1f" % inf.duracion, detalle)
        self._filas.append(fila)
        self._informes[perfil.etiqueta()] = inf
        colores = [estilo.COLOR_OK if f[1] == "correcto" else (estilo.COLOR_AVISO if f[1] == "con errores" else estilo.COLOR_ERROR)
                   for f in self._filas]
        rellenar(self.tabla, self._filas)
        from PySide6.QtGui import QColor
        for i, c in enumerate(colores):
            self.tabla.item(i, 1).setForeground(QColor(c))

    def _mostrar_seleccion(self) -> None:
        filas = self.tabla.selectionModel().selectedRows()
        if filas:
            inf = self._informes.get(self.tabla.item(filas[0].row(), 0).text())
            if inf:
                self.visor.poner(inf.texto or inf.error)

    def exportar(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar CSV", "informe-servidores.csv", "CSV (*.csv)")
        if not ruta:
            return
        with open(ruta, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["servidor", "estado", "errores", "avisos", "segundos", "detalle"])
            w.writerows(self._filas)
        self.barra.poner("Guardado en %s" % ruta, "ok")

    def done(self, r: int) -> None:
        if self._trabajo and self._trabajo.en_curso:
            self._trabajo.cancelar()
        super().done(r)

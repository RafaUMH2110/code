"""Pestaña «Aplicaciones»: lo que hay publicado en el portal (apps.json) del servidor."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton

from ...nucleo import instalador
from ...nucleo.instalador import OpcionesInstalador
from ..widgets import copiar, rellenar, tabla
from .base import PaginaBase


class PaginaAplicaciones(PaginaBase):
    titulo = "Aplicaciones"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._apps: list = []
        fila = QHBoxLayout()
        self.b_leer = QPushButton("Leer apps.json del servidor")
        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText("Filtrar por nombre, repo o descripción…")
        self.b_copiar = QPushButton("Copiar URL")
        fila.addWidget(self.b_leer)
        fila.addWidget(self.buscador, 1)
        fila.addWidget(self.b_copiar)
        self.raiz.addLayout(fila)
        self.info = QLabel("")
        self.info.setProperty("rol", "subtitulo")
        self.raiz.addWidget(self.info)
        self.tabla = tabla(["Título", "Repo", "Ruta", "Proyecto", "Descripción", "KB", "Actualizado"])
        self.raiz.addWidget(self.tabla, 1)
        self.raiz.addWidget(self.barra)
        self.b_leer.clicked.connect(self.leer)
        self.buscador.textChanged.connect(self._filtrar)
        self.b_copiar.clicked.connect(self._copiar_url)
        self.perfil_cambiado()

    def perfil_cambiado(self) -> None:
        self.b_leer.setEnabled(self.perfil is not None)
        self._apps = []
        self.tabla.setRowCount(0)
        self.info.setText("")
        self.barra.poner("")

    def _opciones(self) -> OpcionesInstalador:
        return OpcionesInstalador.desde_dict(self.perfil.instalador) if self.perfil else OpcionesInstalador()

    def leer(self) -> None:
        if not self.hay_perfil():
            return
        o, con = self._opciones(), self.ctx.conexion(self.perfil)

        def trabajo(t):
            try:
                return instalador.leer_apps(con, o)
            except (RuntimeError, ValueError) as exc:
                return exc

        def listo(res):
            if isinstance(res, Exception):
                self.barra.poner(str(res), "error")
                return
            self._apps = res.get("apps", [])
            self.info.setText("Generado: %s · %d aplicaciones · %s/apps.json" % (res.get("generated", "?"), len(self._apps), o.destino_efectivo()))
            self._filtrar()
            self.barra.poner("Catálogo leído.", "ok")

        self.correr("Leyendo apps.json…", trabajo, listo, deshabilitar=[self.b_leer])

    def _filtrar(self) -> None:
        q = self.buscador.text().lower()
        filas = []
        for a in self._apps:
            fila = (a.get("title", ""), a.get("repo", ""), a.get("path", ""), a.get("project", ""),
                    a.get("description", ""), "%.1f" % (int(a.get("size", 0)) / 1024), a.get("updated", ""))
            if not q or any(q in str(c).lower() for c in fila):
                filas.append(fila)
        rellenar(self.tabla, filas)

    def _copiar_url(self) -> None:
        filas = self.tabla.selectionModel().selectedRows()
        if not filas or not self.perfil:
            return
        fila = filas[0].row()
        repo, ruta = self.tabla.item(fila, 1).text(), self.tabla.item(fila, 2).text()
        base = self.perfil.url_base.rstrip("/")
        copiar("%s%s%s/%s" % (base, self._opciones().entrada_web(), repo, ruta))
        self.barra.poner("URL copiada.", "ok")

"""Ventana principal: lista de servidores, pestañas de función y consola de actividad."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (QDialog, QDockWidget, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QTabWidget, QVBoxLayout,
                               QWidget)

from .. import LEYENDA_IA, AUTOR, NOMBRE_APP, __version__
from ..nucleo import sshconfig
from ..nucleo.modelos import Perfil
from . import estilo
from .contexto import Contexto
from .dialogo_acerca import DialogoAcerca
from .dialogo_ajustes import DialogoAjustes
from .dialogo_flota import DialogoFlota
from .dialogo_servidor import DialogoServidor
from .paginas.aplicaciones import PaginaAplicaciones
from .paginas.claves import PaginaClaves
from .paginas.informe import PaginaInforme
from .paginas.instalador import PaginaInstalador
from .paginas.resumen import PaginaResumen
from .paginas.servicio import PaginaServicio
from .widgets import botones_es, ConsolaAnsi, guardar_texto


class VentanaPrincipal(QMainWindow):
    def __init__(self, ctx: Contexto):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(NOMBRE_APP)
        self.resize(1280, 820)
        self._construir_lista()
        self._construir_paginas()
        self._construir_actividad()
        self._construir_menus()

        div = QSplitter()
        div.addWidget(self.panel_lista)
        div.addWidget(self.pestanas)
        div.setStretchFactor(1, 1)
        div.setSizes([260, 1000])
        self.setCentralWidget(div)

        ctx.actividad.connect(self.actividad.anadir)
        ctx.sesion_cambiada.connect(lambda _id: self._refrescar_lista())
        ctx.perfiles_cambiados.connect(self._refrescar_lista)
        estilo.notificador.cambiado.connect(self._refrescar_lista)   # los colores de la lista dependen del tema
        self._refrescar_lista()
        if self.lista.count():
            self.lista.setCurrentRow(0)
        else:
            self._seleccionar()
        self.statusBar().showMessage("%s · %s" % (NOMBRE_APP, LEYENDA_IA))

    # ------------------------------------------------------------------ construcción
    def _construir_lista(self) -> None:
        self.panel_lista = QWidget()
        capa = QVBoxLayout(self.panel_lista)
        capa.setContentsMargins(6, 6, 0, 6)
        titulo = QLabel("Servidores")
        titulo.setProperty("rol", "titulo")
        capa.addWidget(titulo)
        self.lista = QListWidget()
        self.lista.currentRowChanged.connect(lambda _i: self._seleccionar())
        self.lista.itemDoubleClicked.connect(lambda _i: self.editar_servidor())
        capa.addWidget(self.lista, 1)
        fila = QHBoxLayout()
        self.b_nuevo = QPushButton("+")
        self.b_nuevo.setToolTip("Nuevo servidor")
        self.b_editar = QPushButton("Editar")
        self.b_quitar = QPushButton("−")
        self.b_quitar.setToolTip("Eliminar servidor")
        for b in (self.b_nuevo, self.b_editar, self.b_quitar):
            fila.addWidget(b)
        capa.addLayout(fila)
        self.b_nuevo.clicked.connect(self.nuevo_servidor)
        self.b_editar.clicked.connect(self.editar_servidor)
        self.b_quitar.clicked.connect(self.eliminar_servidor)

    def _construir_paginas(self) -> None:
        self.paginas = [PaginaResumen(self.ctx), PaginaInforme(self.ctx), PaginaServicio(self.ctx),
                        PaginaInstalador(self.ctx), PaginaClaves(self.ctx), PaginaAplicaciones(self.ctx)]
        self.pestanas = QTabWidget()
        for p in self.paginas:
            self.pestanas.addTab(p, p.titulo)

    def _construir_actividad(self) -> None:
        self.actividad = ConsolaAnsi(self.ctx.ajustes.max_lineas_consola)
        caja = QWidget()
        capa = QVBoxLayout(caja)
        capa.setContentsMargins(4, 4, 4, 4)
        capa.addWidget(self.actividad)
        fila = QHBoxLayout()
        b_limpiar, b_guardar = QPushButton("Limpiar"), QPushButton("Guardar registro…")
        fila.addStretch(1)
        fila.addWidget(b_limpiar)
        fila.addWidget(b_guardar)
        capa.addLayout(fila)
        b_limpiar.clicked.connect(self.actividad.clear)
        b_guardar.clicked.connect(lambda: guardar_texto(self, "Guardar registro", "actividad.log",
                                                         self.actividad.texto_plano(), "Registro (*.log *.txt)"))
        self.dock = QDockWidget("Actividad (comandos ejecutados)", self)
        self.dock.setWidget(caja)
        self.dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock)
        self.dock.setMaximumHeight(170)

    def _accion(self, menu, texto: str, funcion, atajo: Optional[str] = None, rol=None) -> QAction:
        a = QAction(texto, self)
        if atajo:
            a.setShortcut(QKeySequence(atajo))
        if rol is not None:
            a.setMenuRole(rol)
        a.triggered.connect(lambda _=False: funcion())
        menu.addAction(a)
        return a

    def _construir_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("Archivo")
        self._accion(m, "Nuevo servidor…", self.nuevo_servidor, "Ctrl+N")
        self._accion(m, "Importar de ~/.ssh/config…", self.importar_ssh_config)
        m.addSeparator()
        self._accion(m, "Importar servidores desde fichero…", self.importar_perfiles)
        self._accion(m, "Exportar servidores a fichero…", self.exportar_perfiles)
        m.addSeparator()
        self._accion(m, "Preferencias…", self.preferencias, "Ctrl+,", QAction.MenuRole.PreferencesRole)
        self._accion(m, "Salir", self.close, "Ctrl+Q", QAction.MenuRole.QuitRole)

        m = mb.addMenu("Servidor")
        self._accion(m, "Editar…", self.editar_servidor, "Ctrl+E")
        self._accion(m, "Duplicar", self.duplicar_servidor)
        self._accion(m, "Eliminar", self.eliminar_servidor)
        m.addSeparator()
        self._accion(m, "Desconectar", self.desconectar)
        self._accion(m, "Desconectar de todos y olvidar contraseñas", self.desconectar_todos)

        m = mb.addMenu("Herramientas")
        self._accion(m, "Informe de varios servidores…", self.flota)

        m = mb.addMenu("Ver")
        m.addAction(self.dock.toggleViewAction())
        m.addMenu(self._menu_apariencia())
        m.addSeparator()
        for i, p in enumerate(self.paginas):
            self._accion(m, p.titulo, lambda i=i: self.pestanas.setCurrentIndex(i), "Ctrl+%d" % (i + 1))

        m = mb.addMenu("Ayuda")
        self._accion(m, "Acerca de %s" % NOMBRE_APP, self.acerca_de, None, QAction.MenuRole.AboutRole)

    def _menu_apariencia(self) -> QMenu:
        """Submenú Ver ▸ Apariencia: según el sistema / claro / oscuro. Se recuerda en las preferencias."""
        menu = QMenu("Apariencia", self)
        self._grupo_tema = QActionGroup(self)
        self._grupo_tema.setExclusive(True)
        actual = self.ctx.almacen.ajustes.tema
        for clave, texto in estilo.TEMAS:
            a = QAction(texto, self, checkable=True)
            a.setChecked(clave == actual)
            a.triggered.connect(lambda _=False, c=clave: self.cambiar_tema(c))
            self._grupo_tema.addAction(a)
            menu.addAction(a)
        return menu

    def cambiar_tema(self, modo: str) -> None:
        """Aplica y guarda la apariencia elegida."""
        self.ctx.almacen.ajustes.tema = modo
        self.ctx.almacen.guardar_ajustes()
        estilo.aplicar_tema(modo)
        for a in self._grupo_tema.actions():       # por si se llamó desde Preferencias
            a.setChecked(a.text() == dict(estilo.TEMAS)[modo])

    # ------------------------------------------------------------------ lista de servidores
    def perfil_actual(self) -> Optional[Perfil]:
        it = self.lista.currentItem()
        return self.ctx.almacen.obtener(it.data(Qt.ItemDataRole.UserRole)) if it else None

    def _refrescar_lista(self, seleccionar_id: Optional[str] = None) -> None:
        actual = seleccionar_id or (self.perfil_actual().id if self.perfil_actual() else None)
        self.lista.blockSignals(True)
        self.lista.clear()
        for p in self.ctx.almacen.perfiles:
            abierta = self.ctx.abierta(p.id)
            it = QListWidgetItem(("● " if abierta else "○ ") + p.etiqueta())
            it.setToolTip("%s\n%s" % (p.destino, "conectado" if abierta else "sin conexión"))
            it.setData(Qt.ItemDataRole.UserRole, p.id)
            if abierta:
                it.setForeground(estilo.qcolor("ok"))
            self.lista.addItem(it)
            if p.id == actual:
                self.lista.setCurrentItem(it)
        self.lista.blockSignals(False)

    def _seleccionar(self) -> None:
        p = self.perfil_actual()
        for pagina in self.paginas:
            pagina.poner_perfil(p)
        hay = p is not None
        self.b_editar.setEnabled(hay)
        self.b_quitar.setEnabled(hay)
        self.setWindowTitle("%s — %s" % (NOMBRE_APP, p.etiqueta()) if p else NOMBRE_APP)

    def nuevo_servidor(self) -> None:
        dlg = DialogoServidor(self.ctx, None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.perfil_resultante:
            self.ctx.almacen.anadir(dlg.perfil_resultante)
            self._refrescar_lista(dlg.perfil_resultante.id)
            self._seleccionar()

    def editar_servidor(self) -> None:
        p = self.perfil_actual()
        if not p:
            return
        dlg = DialogoServidor(self.ctx, p, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.perfil_resultante:
            self.ctx.almacen.actualizar(dlg.perfil_resultante)
            self._refrescar_lista(dlg.perfil_resultante.id)
            self._seleccionar()

    def duplicar_servidor(self) -> None:
        p = self.perfil_actual()
        if p:
            copia = self.ctx.almacen.duplicar(p.id)
            self._refrescar_lista(copia.id if copia else None)
            self._seleccionar()

    def eliminar_servidor(self) -> None:
        p = self.perfil_actual()
        if not p:
            return
        if QMessageBox.question(self, "Eliminar servidor", "¿Eliminar «%s»? (No se toca el servidor real; "
                                "se borran sus datos guardados aquí, incluido el Llavero.)" % p.etiqueta()) \
                != QMessageBox.StandardButton.Yes:
            return
        self.ctx.desconectar(p.id, olvidar_llavero=True)
        self.ctx.almacen.eliminar(p.id)
        self._refrescar_lista()
        if self.lista.count():
            self.lista.setCurrentRow(0)
        self._seleccionar()

    def desconectar(self) -> None:
        p = self.perfil_actual()
        if p:
            self.ctx.desconectar(p.id)

    def desconectar_todos(self) -> None:
        self.ctx.cerrar_todo()
        self._refrescar_lista()

    # ------------------------------------------------------------------ importar / exportar
    def importar_ssh_config(self) -> None:
        hosts = sshconfig.leer_hosts()
        if not hosts:
            QMessageBox.information(self, "Importar", "No se encontraron servidores en ~/.ssh/config.")
            return
        existentes = {p.destino for p in self.ctx.almacen.perfiles}
        nuevos = [h for h in hosts if h["alias"] not in existentes]
        if not nuevos:
            QMessageBox.information(self, "Importar", "Todos los alias de ~/.ssh/config ya están en la lista.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Importar de ~/.ssh/config")
        capa = QVBoxLayout(dlg)
        capa.addWidget(QLabel("Marca los servidores que quieres añadir (el alias se usa como destino, "
                              "así ssh aplica el resto de tu configuración):"))
        lista = QListWidget()
        for h in nuevos:
            it = QListWidgetItem("%s  (%s%s)" % (h["alias"], h["hostname"] or "?", " · " + h["user"] if h["user"] else ""))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            it.setData(Qt.ItemDataRole.UserRole, h)
            lista.addItem(it)
        capa.addWidget(lista)
        from PySide6.QtWidgets import QDialogButtonBox
        botones = botones_es(QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel))
        botones.accepted.connect(dlg.accept)
        botones.rejected.connect(dlg.reject)
        capa.addWidget(botones)
        dlg.resize(520, 420)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        n = 0
        for i in range(lista.count()):
            it = lista.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                self.ctx.almacen.anadir(sshconfig.a_perfil(it.data(Qt.ItemDataRole.UserRole)))
                n += 1
        self._refrescar_lista()
        self.statusBar().showMessage("%d servidores importados." % n, 5000)

    def exportar_perfiles(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar servidores", "servidores.json", "JSON (*.json)")
        if ruta:
            n = self.ctx.almacen.exportar(ruta)
            self.statusBar().showMessage("%d servidores exportados (sin contraseñas)." % n, 5000)

    def importar_perfiles(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Importar servidores", "", "JSON (*.json)")
        if not ruta:
            return
        try:
            n = self.ctx.almacen.importar(ruta)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Importar", "No se pudo leer el fichero: %s" % exc)
            return
        self._refrescar_lista()
        self.statusBar().showMessage("%d servidores importados." % n, 5000)

    # ------------------------------------------------------------------ diálogos
    def preferencias(self) -> None:
        if DialogoAjustes(self.ctx, self).exec() == QDialog.DialogCode.Accepted:
            self._seleccionar()

    def flota(self) -> None:
        if not self.ctx.almacen.perfiles:
            QMessageBox.information(self, "Informe", "Primero añade algún servidor.")
            return
        DialogoFlota(self.ctx, self).exec()

    def acerca_de(self) -> None:
        DialogoAcerca(self.ctx.ajustes.ssh_path, self).exec()

    # ------------------------------------------------------------------ cierre
    def closeEvent(self, ev: QCloseEvent) -> None:
        if any(p.ocupada for p in self.paginas):
            if QMessageBox.question(self, "Salir", "Hay operaciones en curso. ¿Salir de todos modos? "
                                    "Se cancelarán.") != QMessageBox.StandardButton.Yes:
                ev.ignore()
                return
            for p in self.paginas:
                if p._trabajo and p._trabajo.en_curso:
                    p._trabajo.cancelar()
        self.ctx.cerrar_todo()
        ev.accept()

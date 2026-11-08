"""Preferencias globales de la aplicación (no dependen de un servidor concreto)."""

from __future__ import annotations

import shutil
from typing import Optional

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
                               QWidget)

from .. import rutas
from ..nucleo import github
from ..nucleo.recursos import Recursos
from .hilos import Trabajo
from .widgets import rellenar, tabla


class DialogoAjustes(QDialog):
    def __init__(self, ctx, padre: Optional[QWidget] = None):
        super().__init__(padre)
        self.ctx = ctx
        self.setWindowTitle("Preferencias")
        self.setMinimumSize(640, 520)
        capa = QVBoxLayout(self)
        pestanas = QTabWidget()
        capa.addWidget(pestanas, 1)
        a = ctx.ajustes

        # --- General
        w = QWidget()
        f = QFormLayout(w)
        self.ssh_path = QLineEdit(a.ssh_path)
        self.ssh_path.setPlaceholderText("vacío = autodetectar (%s)" % rutas.buscar_ejecutable("ssh"))
        self.idioma = QComboBox()
        self.idioma.addItem("Español", "es")
        self.idioma.addItem("English", "en")
        self.idioma.setCurrentIndex(max(self.idioma.findData(a.idioma_informe), 0))
        self.terminal = QComboBox()
        self.terminal.addItems(["Terminal", "iTerm"])
        self.terminal.setCurrentText(a.terminal)
        self.confirmar = QCheckBox("Pedir confirmación antes de acciones que modifican el servidor")
        self.confirmar.setChecked(a.confirmar_acciones)
        self.mostrar_clave = QCheckBox("Mostrar la clave API completa en los informes por defecto (--show-key)")
        self.mostrar_clave.setChecked(a.mostrar_clave_api)
        self.max_lineas = QSpinBox()
        self.max_lineas.setRange(1000, 500000)
        self.max_lineas.setValue(a.max_lineas_consola)
        f.addRow("Ejecutable ssh:", self.ssh_path)
        f.addRow("Idioma del informe:", self.idioma)
        f.addRow("Abrir sesiones en:", self.terminal)
        f.addRow("Líneas máximas de consola:", self.max_lineas)
        f.addRow("", self.confirmar)
        f.addRow("", self.mostrar_clave)
        pestanas.addTab(w, "General")

        # --- GitHub y scripts
        w2 = QWidget()
        c2 = QVBoxLayout(w2)
        g = QGroupBox("GitHub")
        fg = QFormLayout(g)
        self.usuario = QLineEdit(a.usuario_github)
        self.rama = QLineEdit(a.rama_github)
        self.token = QLineEdit(a.token_github)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("opcional: sube el límite de 60 peticiones/hora de la API")
        fg.addRow("Usuario:", self.usuario)
        fg.addRow("Rama de los scripts:", self.rama)
        fg.addRow("Token (opcional):", self.token)
        c2.addWidget(g)
        g2 = QGroupBox("Scripts que se envían al servidor")
        c = QVBoxLayout(g2)
        fila = QHBoxLayout()
        self.carpeta = QLineEdit(a.carpeta_scripts)
        self.carpeta.setPlaceholderText("carpeta propia con versiones modificadas de los scripts (opcional)")
        b = QPushButton("Examinar…")
        b.clicked.connect(self._examinar)
        fila.addWidget(self.carpeta, 1)
        fila.addWidget(b)
        c.addLayout(fila)
        self.tabla = tabla(["Fichero", "Origen", "Huella"], seleccion_filas=False)
        c.addWidget(self.tabla)
        f2 = QHBoxLayout()
        self.b_actualizar = QPushButton("Actualizar desde GitHub")
        self.b_incluidos = QPushButton("Volver a los incluidos")
        f2.addWidget(self.b_actualizar)
        f2.addWidget(self.b_incluidos)
        f2.addStretch(1)
        c.addLayout(f2)
        self.estado = QLabel("")
        self.estado.setWordWrap(True)
        c.addWidget(self.estado)
        c2.addWidget(g2, 1)
        pestanas.addTab(w2, "GitHub y scripts")
        self.b_actualizar.clicked.connect(self._descargar)
        self.b_incluidos.clicked.connect(self._borrar_descargados)
        self.carpeta.textChanged.connect(self._inventario)
        self._inventario()

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)

    def _examinar(self) -> None:
        ruta = QFileDialog.getExistingDirectory(self, "Carpeta de scripts propios")
        if ruta:
            self.carpeta.setText(ruta)

    def _inventario(self) -> None:
        rellenar(self.tabla, Recursos(self.carpeta.text().strip()).inventario())

    def _descargar(self) -> None:
        self.b_actualizar.setEnabled(False)
        self.estado.setText("Descargando…")
        usuario, rama = self.usuario.text().strip(), self.rama.text().strip() or "main"

        def trabajo(t):
            try:
                return github.descargar_scripts(rutas.dir_scripts_personalizados(), usuario, "code", rama)
            except github.ErrorGitHub as exc:
                return exc

        def listo(r):
            if isinstance(r, Exception):
                self.estado.setText("✖ " + str(r))
            else:
                self.estado.setText("✔ Scripts actualizados (%d ficheros)." % len(r))
            self._inventario()

        Trabajo(trabajo, "descargar scripts", al_terminar=listo, al_fin=lambda: self.b_actualizar.setEnabled(True)).iniciar()

    def _borrar_descargados(self) -> None:
        carpeta = rutas.dir_scripts_personalizados()
        if carpeta.is_dir():
            shutil.rmtree(carpeta, ignore_errors=True)
        self.estado.setText("Se usarán los scripts incluidos en la aplicación.")
        self._inventario()

    def _guardar(self) -> None:
        a = self.ctx.almacen.ajustes
        a.ssh_path = self.ssh_path.text().strip()
        a.idioma_informe = self.idioma.currentData()
        a.terminal = self.terminal.currentText()
        a.confirmar_acciones = self.confirmar.isChecked()
        a.mostrar_clave_api = self.mostrar_clave.isChecked()
        a.max_lineas_consola = self.max_lineas.value()
        a.usuario_github = self.usuario.text().strip() or "RafaUMH2110"
        a.rama_github = self.rama.text().strip() or "main"
        a.token_github = self.token.text().strip()
        a.carpeta_scripts = self.carpeta.text().strip()
        self.ctx.almacen.guardar_ajustes()
        self.accept()

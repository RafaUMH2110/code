"""Pestaña «Servicio»: control del servicio systemd del colector, su registro y su desinstalación.

Convierte en botones las órdenes que antes se escribían a mano (``systemctl status/restart``,
``journalctl -u``, y la receta de desinstalación del servicio).
"""

from __future__ import annotations

import re

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QVBoxLayout)

from ...nucleo import colector, remoto
from ...nucleo.colector import PRESETS_COLECTOR
from .. import estilo
from ..widgets import ConsolaAnsi
from .base import PaginaBase

ACCIONES = [("Iniciar", "start"), ("Detener", "stop"), ("Reiniciar", "restart"), ("Recargar", "reload"),
            ("Activar al arrancar", "enable"), ("Desactivar", "disable")]
DESTRUCTIVAS = {"stop", "disable"}


class PaginaServicio(PaginaBase):
    titulo = "Servicio"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        # --- selección del servicio
        caja = QGroupBox("Servicio")
        form = QFormLayout(caja)
        self.preset = QComboBox()
        self.preset.addItem("(personalizado)")
        self.preset.addItems(list(PRESETS_COLECTOR))
        self.nombre = QLineEdit()
        self.directorio = QLineEdit()
        form.addRow("Colector:", self.preset)
        form.addRow("Nombre de la unidad:", self.nombre)
        form.addRow("Programa en el servidor:", self.directorio)
        self.raiz.addWidget(caja)

        # --- estado y acciones
        self.estado = QLabel("Estado: —")
        estilo.poner_rol(self.estado, "titulo")
        self.estado.setProperty("grande", True)      # conserva el tamaño de título al cambiar a ok/error
        self.detalle = QLabel("")
        self.detalle.setProperty("rol", "subtitulo")
        self.raiz.addWidget(self.estado)
        self.raiz.addWidget(self.detalle)
        fila = QHBoxLayout()
        self.b_estado = QPushButton("Consultar estado")
        fila.addWidget(self.b_estado)
        self.b_acciones = []
        for etiqueta, accion in ACCIONES:
            b = QPushButton(etiqueta)
            b.clicked.connect(lambda _=False, a=accion, e=etiqueta: self.accion(a, e))
            fila.addWidget(b)
            self.b_acciones.append(b)
        fila.addStretch(1)
        self.raiz.addLayout(fila)

        # --- registro
        caja2 = QGroupBox("Registro (journalctl -u)")
        capa = QVBoxLayout(caja2)
        fila2 = QHBoxLayout()
        self.lineas = QSpinBox()
        self.lineas.setRange(10, 5000)
        self.lineas.setValue(200)
        self.filtro = QLineEdit()
        self.filtro.setPlaceholderText("Filtrar líneas (texto)…")
        self.b_registro = QPushButton("Leer registro")
        fila2.addWidget(QLabel("Últimas líneas:"))
        fila2.addWidget(self.lineas)
        fila2.addWidget(self.filtro, 1)
        fila2.addWidget(self.b_registro)
        capa.addLayout(fila2)
        self.consola = ConsolaAnsi()
        capa.addWidget(self.consola)
        self.raiz.addWidget(caja2, 1)

        # --- desinstalar
        caja3 = QGroupBox("Desinstalar el servicio")
        capa3 = QHBoxLayout(caja3)
        self.c_copia = QCheckBox("Hacer copia en /var/backups")
        self.c_copia.setChecked(True)
        self.c_borrar = QCheckBox("Borrar también el programa (solo bajo /opt)")
        self.b_desinstalar = QPushButton("Desinstalar…")
        capa3.addWidget(self.c_copia)
        capa3.addWidget(self.c_borrar)
        capa3.addStretch(1)
        capa3.addWidget(self.b_desinstalar)
        self.raiz.addWidget(caja3)
        self.raiz.addWidget(self.barra)

        self.preset.currentTextChanged.connect(self._preset)
        self.b_estado.clicked.connect(self.consultar)
        self.b_registro.clicked.connect(self.leer_registro)
        self.b_desinstalar.clicked.connect(self.desinstalar)
        self.filtro.textChanged.connect(self._refiltrar)
        self._registro_completo = ""
        self.perfil_cambiado()

    def _preset(self, nombre: str) -> None:
        if nombre in PRESETS_COLECTOR:
            cfg, srv, dir_ = PRESETS_COLECTOR[nombre]
            self.nombre.setText(srv)
            self.directorio.setText(dir_)

    def perfil_cambiado(self) -> None:
        p = self.perfil
        for b in [self.b_estado, self.b_registro, self.b_desinstalar] + self.b_acciones:
            b.setEnabled(p is not None)
        self.estado.setText("Estado: —")
        self.detalle.setText("")
        self.consola.clear()
        self._registro_completo = ""
        self.barra.poner("")
        if p:
            self.nombre.setText(p.servicio)
            self.directorio.setText(p.ruta_config.rsplit("/", 1)[0] if "/" in p.ruta_config else "")
            for nombre, (cfg, srv, _d) in PRESETS_COLECTOR.items():
                if srv == p.servicio:
                    self.preset.setCurrentText(nombre)
                    break
            else:
                self.preset.setCurrentIndex(0)

    def _nombre(self) -> str:
        n = self.nombre.text().strip()
        if not remoto.nombre_servicio_valido(n):
            self.barra.poner("El nombre del servicio solo admite letras, cifras y @ . _ -", "error")
            return ""
        return n

    # ------------------------------------------------------------------ acciones
    def consultar(self) -> None:
        if not self.hay_perfil() or not self._nombre():
            return
        perfil, con, nombre = self.perfil, self.ctx.conexion(self.perfil), self._nombre()

        def listo(r):
            if perfil is not self.perfil:
                return
            if not r["ok"]:
                self.estado.setText("Estado: sin datos")
                self.barra.poner(r["error"].splitlines()[0] if r["error"] else "Fallo", "error")
                return
            d = r["datos"]
            activo = d.get("active", "?")
            self.estado.setText("Estado: %s (%s)" % (activo, "arranca con el sistema" if d.get("enabled") == "enabled"
                                                    else "arranque: " + d.get("enabled", "?")))
            estilo.poner_rol(self.estado, "ok" if activo == "active" else "error")
            self.detalle.setText("Reinicios: %s · PID: %s · usuario: %s · desde: %s" % (
                d.get("NRestarts", "—"), d.get("MainPID", "—"), d.get("User", "—") or "—", d.get("ActiveEnterTimestamp", "—")))
            self.consola.clear()
            self.consola.anadir(r["texto"])
            self.barra.poner("Estado actualizado.", "ok")

        self.correr("Consultando %s…" % nombre, lambda t: colector.estado_servicio(con, nombre, t.cancelador), listo,
                    deshabilitar=[self.b_estado])

    def accion(self, accion: str, etiqueta: str) -> None:
        if not self.hay_perfil() or not self._nombre():
            return
        perfil, con, nombre = self.perfil, self.ctx.conexion(self.perfil), self._nombre()
        if not self.confirmar(etiqueta, "¿%s el servicio «%s» en %s?" % (etiqueta, nombre, perfil.etiqueta()),
                              forzar=accion in DESTRUCTIVAS):
            return

        def listo(r):
            if perfil is not self.perfil:
                return
            if r.ok:
                self.barra.poner("%s: hecho." % etiqueta, "ok")
                self.consultar()
            else:
                self.barra.poner(con.explicar_fallo(r) if r.fallo_conexion else (r.error.strip() or "Error %d" % r.codigo), "error")
                self.consola.anadir(r.error, True)

        self.correr("%s %s…" % (etiqueta, nombre), lambda t: colector.accion_servicio(con, accion, nombre, t.cancelador),
                    listo, deshabilitar=self.b_acciones)

    def leer_registro(self) -> None:
        if not self.hay_perfil() or not self._nombre():
            return
        perfil, con, nombre, n = self.perfil, self.ctx.conexion(self.perfil), self._nombre(), self.lineas.value()

        def listo(r):
            if perfil is not self.perfil:
                return
            self._registro_completo = r.salida if r.ok else r.error
            self._refiltrar()
            self.barra.poner("Registro leído." if r.ok else (r.error.strip().splitlines() or ["Error"])[0], "ok" if r.ok else "error")

        self.correr("Leyendo registro de %s…" % nombre, lambda t: colector.registro_servicio(con, nombre, n, t.cancelador),
                    listo, deshabilitar=[self.b_registro])

    def _refiltrar(self) -> None:
        texto = self.filtro.text().lower()
        self.consola.clear()
        for linea in self._registro_completo.splitlines():
            if not texto or texto in linea.lower():
                self.consola.anadir(linea, bool(re.search(r"\b(error|fail|traceback)\b", linea, re.I)))

    def desinstalar(self) -> None:
        if not self.hay_perfil() or not self._nombre():
            return
        perfil, con, nombre = self.perfil, self.ctx.conexion(self.perfil), self._nombre()
        directorio, borrar, copia = self.directorio.text().strip(), self.c_borrar.isChecked(), self.c_copia.isChecked()
        resumen = "Se parará y desactivará «%s» y se eliminará su unidad de systemd." % nombre
        if borrar:
            resumen += "\nSe BORRARÁ %s%s." % (directorio or "(directorio vacío: no se borra nada)",
                                              " (con copia previa en /var/backups)" if copia else " SIN copia")
        if not self.confirmar("Desinstalar servicio", resumen + "\n\n¿Continuar en %s?" % perfil.etiqueta(), forzar=True):
            return
        self.consola.clear()

        def trabajo(t):
            return colector.desinstalar_servicio(con, nombre, directorio, borrar, copia, t.cancelador,
                                                 al_linea=lambda l: t.linea(l))

        def listo(r):
            self.barra.poner("Servicio desinstalado." if r.ok else (r.error.strip().splitlines() or ["Error"])[0],
                             "ok" if r.ok else "error")
            if not r.ok:
                self.consola.anadir(r.error, True)

        self.correr("Desinstalando %s…" % nombre, trabajo, listo, deshabilitar=[self.b_desinstalar],
                    al_linea=lambda texto, e: self.consola.anadir(texto, e))

"""Pestaña «Informe»: ``telemet-collector-info.py`` ejecutado en el servidor.

Reproduce todas las opciones del script: ``-c``, ``--service`` / ``--no-service``, ``--show-key``,
``--authorized-keys`` y ``--lang``. El informe se muestra de tres formas: **Diagnóstico** (lo que hay
que arreglar, ordenado por gravedad), **Informe** (el texto con colores del script) y **JSON**
(los datos tal cual, para otros programas). Se puede exportar y copiar.
"""

from __future__ import annotations

import html
from typing import Optional

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QPushButton, QTabWidget, QTextBrowser)

from ...nucleo import colector
from ...nucleo.colector import Informe, OpcionesInforme, PRESETS_COLECTOR
from ...nucleo.ansi import quitar_ansi
from .. import estilo
from ..widgets import VisorTexto, copiar, json_bonito
from .base import PaginaBase

# nivel -> (símbolo, rol de color, nombre). El color se resuelve al generar el HTML, con el tema actual.
ICONOS = {"err": ("✖", "error", "Error"), "warn": ("▲", "aviso", "Aviso"),
          "ok": ("✔", "ok", "Correcto"), "info": ("●", "tenue", "Info")}


def html_diagnostico(informe: Informe) -> str:
    """Resumen HTML del diagnóstico (errores primero)."""
    orden = {"err": 0, "warn": 1, "info": 2, "ok": 3}
    filas = sorted(informe.diagnostico, key=lambda d: orden.get(d.get("level"), 9))
    if not filas:
        return '<p style="color:%s"><b>✔ El diagnóstico no ha encontrado problemas.</b></p>' % estilo.color("ok")
    partes = ["<h3>Diagnóstico: %d error(es), %d aviso(s)</h3><table cellpadding='4'>" % (informe.errores, informe.avisos)]
    for d in filas:
        simbolo, rol, nombre = ICONOS.get(d.get("level"), ICONOS["info"])
        partes.append("<tr><td style='color:%s'><b>%s %s</b></td><td>%s</td></tr>" %
                      (estilo.color(rol), simbolo, nombre, html.escape(d.get("message", ""))))
    partes.append("</table>")
    return "".join(partes)


class PaginaInforme(PaginaBase):
    titulo = "Informe"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.informe: Optional[Informe] = None

        caja = QGroupBox("Opciones del informe")
        form = QFormLayout(caja)
        self.preset = QComboBox()
        self.preset.addItem("(personalizado)")
        self.preset.addItems(list(PRESETS_COLECTOR))
        self.ruta = QLineEdit()
        self.servicio = QLineEdit()
        self.sin_servicio = QCheckBox("No consultar el servicio (--no-service)")
        self.mostrar_clave = QCheckBox("Mostrar la clave API completa (--show-key)")
        self.auditar = QCheckBox("Auditar authorized_keys del usuario (--authorized-keys)")
        self.idioma = QComboBox()
        self.idioma.addItem("Español", "es")
        self.idioma.addItem("English", "en")
        form.addRow("Colector:", self.preset)
        form.addRow("config.ini en el servidor (-c):", self.ruta)
        form.addRow("Servicio systemd (--service):", self.servicio)
        form.addRow("", self.sin_servicio)
        form.addRow("", self.mostrar_clave)
        form.addRow("", self.auditar)
        form.addRow("Idioma (--lang):", self.idioma)
        self.raiz.addWidget(caja)

        fila = QHBoxLayout()
        self.b_generar = QPushButton("Generar informe")
        self.b_exportar = QPushButton("Exportar…")
        self.b_copiar = QPushButton("Copiar texto")
        fila.addWidget(self.b_generar)
        fila.addWidget(self.b_exportar)
        fila.addWidget(self.b_copiar)
        fila.addStretch(1)
        self.raiz.addLayout(fila)

        self.pestanas = QTabWidget()
        self.vista_diag = QTextBrowser()
        self.vista_texto = VisorTexto()
        self.vista_json = QPlainTextEdit()
        self.vista_json.setReadOnly(True)
        self.vista_json.setFont(estilo.fuente_mono())
        self.pestanas.addTab(self.vista_diag, "Diagnóstico")
        self.pestanas.addTab(self.vista_texto, "Informe")
        self.pestanas.addTab(self.vista_json, "JSON")
        self.raiz.addWidget(self.pestanas, 1)
        self.raiz.addWidget(self.barra)

        estilo.notificador.cambiado.connect(self._repintar_diagnostico)
        self.preset.currentTextChanged.connect(self._aplicar_preset)
        self.b_generar.clicked.connect(self.generar)
        self.b_exportar.clicked.connect(self.exportar)
        self.b_copiar.clicked.connect(self.copiar_texto)
        self.perfil_cambiado()

    # ------------------------------------------------------------------ estado
    def _aplicar_preset(self, nombre: str) -> None:
        if nombre in PRESETS_COLECTOR:
            self.ruta.setText(PRESETS_COLECTOR[nombre][0])
            self.servicio.setText(PRESETS_COLECTOR[nombre][1])

    def perfil_cambiado(self) -> None:
        p = self.perfil
        activo = p is not None
        self.b_generar.setEnabled(activo)
        self.informe = None
        self.vista_diag.setHtml("<p><i>Pulsa «Generar informe».</i></p>")
        self.vista_texto.clear()
        self.vista_json.clear()
        self.b_exportar.setEnabled(False)
        self.b_copiar.setEnabled(False)
        self.barra.poner("")
        if p:
            self.ruta.setText(p.ruta_config)
            self.servicio.setText(p.servicio)
            self.mostrar_clave.setChecked(self.ctx.ajustes.mostrar_clave_api)
            i = self.idioma.findData(self.ctx.ajustes.idioma_informe)
            self.idioma.setCurrentIndex(max(i, 0))
            for nombre, (cfg, srv, _d) in PRESETS_COLECTOR.items():
                if cfg == p.ruta_config and srv == p.servicio:
                    self.preset.setCurrentText(nombre)
                    break
            else:
                self.preset.setCurrentIndex(0)

    def opciones(self) -> OpcionesInforme:
        return OpcionesInforme(ruta_config=self.ruta.text().strip(), servicio=self.servicio.text().strip(),
                               sin_servicio=self.sin_servicio.isChecked(), mostrar_clave=self.mostrar_clave.isChecked(),
                               auditar_claves=self.auditar.isChecked(), idioma=self.idioma.currentData())

    # ------------------------------------------------------------------ acciones
    def generar(self) -> None:
        if not self.hay_perfil():
            return
        perfil, con, opciones, recursos = self.perfil, self.ctx.conexion(self.perfil), self.opciones(), self.ctx.recursos()

        def trabajo(t):
            return colector.generar_informe(con, recursos, opciones, t.cancelador)

        def listo(inf: Informe):
            if perfil is not self.perfil:
                return
            self.informe = inf
            self.ctx.sesion_cambiada.emit(perfil.id)
            self.vista_texto.poner(inf.texto)
            self.vista_json.setPlainText(json_bonito(inf.datos) if inf.datos is not None else "")
            self.b_exportar.setEnabled(bool(inf.texto or inf.datos))
            self.b_copiar.setEnabled(bool(inf.texto))
            if inf.ok:
                self.vista_diag.setHtml(html_diagnostico(inf))
                self.pestanas.setCurrentIndex(0)
                rol = "ok" if inf.codigo == 0 else "aviso"
                self.barra.poner("Informe generado en %.1f s · %d error(es), %d aviso(s)." % (inf.duracion, inf.errores, inf.avisos), rol)
            else:
                mensajes = {2: "Se conectó, pero no se pudo leer config.ini (ruta incorrecta o sin permisos).",
                            4: "No se pudo ejecutar el informe (conexión, autenticación, sudo o python3)."}
                cabecera = mensajes.get(inf.codigo, "El informe terminó con código %d." % inf.codigo)
                self.vista_diag.setHtml("<p style='color:%s'><b>%s</b></p><pre>%s</pre>" %
                                        (estilo.color("error"), html.escape(cabecera), html.escape(inf.error)))
                self.pestanas.setCurrentIndex(0)
                self.barra.poner(cabecera, "error")

        self.correr("Generando informe de %s…" % perfil.etiqueta(), trabajo, listo, deshabilitar=[self.b_generar])

    def _repintar_diagnostico(self) -> None:
        """Al cambiar de tema, el HTML del diagnóstico (con sus colores ya escritos) se genera de nuevo."""
        if self.informe is not None and self.informe.ok:
            self.vista_diag.setHtml(html_diagnostico(self.informe))

    def exportar(self) -> None:
        if not self.informe:
            return
        nombre = (self.perfil.etiqueta() if self.perfil else "servidor").replace(" ", "_")
        filtro = "Texto (*.txt);;JSON (*.json);;HTML (*.html)"
        from PySide6.QtWidgets import QFileDialog
        ruta, sel = QFileDialog.getSaveFileName(self, "Exportar informe", "informe-%s.txt" % nombre, filtro)
        if not ruta:
            return
        if ruta.endswith(".json") and self.informe.datos is not None:
            contenido = json_bonito(self.informe.datos)
        elif ruta.endswith(".html"):
            from ...nucleo.ansi import ansi_a_html
            contenido = "<!doctype html><meta charset='utf-8'><title>Informe</title>" + ansi_a_html(self.informe.texto)
        else:
            contenido = quitar_ansi(self.informe.texto)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        self.barra.poner("Informe guardado en %s" % ruta, "ok")

    def copiar_texto(self) -> None:
        if self.informe:
            copiar(quitar_ansi(self.informe.texto))
            self.barra.poner("Informe copiado al portapapeles.", "ok")

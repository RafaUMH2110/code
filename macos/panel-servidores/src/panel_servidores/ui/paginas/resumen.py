"""Pestaña «Resumen»: estado general del servidor, comprobación rápida y acceso a la terminal.

Equivale a las opciones ``--check`` del script ``telemet-collector-info-ssh.py`` más una vista de
estado (usuario, sistema, disco, Apache, servicios, cron) para saber de un vistazo cómo está
la máquina antes de hacer nada.
"""

from __future__ import annotations

from PySide6.QtWidgets import (QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QVBoxLayout)

from ...nucleo import colector, terminal
from .. import estilo
from ..widgets import copiar
from .base import PaginaBase

#: (clave devuelta por el servidor, etiqueta en pantalla)
CAMPOS = [("usuario", "Usuario"), ("host", "Nombre de máquina"), ("sistema", "Sistema"), ("kernel", "Núcleo"),
          ("actividad", "Encendido"), ("disco", "Disco /"), ("python", "Python"), ("git", "Git"),
          ("apache", "Apache"), ("cron", "Entradas de cron (instalar-todo)"), ("config", "config.ini")]

TEXTO_SUDO = {"root": "Eres root: no hace falta sudo", "nopasswd": "sudo sin contraseña (NOPASSWD)",
              "password": "sudo con contraseña", "ausente": "sudo no está instalado"}


class PaginaResumen(PaginaBase):
    titulo = "Resumen"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.cabecera = QLabel("Sin servidor seleccionado")
        self.cabecera.setProperty("rol", "titulo")
        self.subcabecera = QLabel("")
        self.subcabecera.setProperty("rol", "subtitulo")
        self.raiz.addWidget(self.cabecera)
        self.raiz.addWidget(self.subcabecera)

        fila = QHBoxLayout()
        self.b_actualizar = QPushButton("Conectar y actualizar")
        self.b_comprobar = QPushButton("Comprobar (--check)")
        self.b_terminal = QPushButton("Abrir en Terminal")
        self.b_copiar = QPushButton("Copiar comando ssh")
        self.b_desconectar = QPushButton("Desconectar")
        for b in (self.b_actualizar, self.b_comprobar, self.b_terminal, self.b_copiar, self.b_desconectar):
            fila.addWidget(b)
        fila.addStretch(1)
        self.raiz.addLayout(fila)

        caja = QGroupBox("Estado del servidor")
        self.formulario = QFormLayout(caja)
        self.valores: dict = {}
        for clave, etiqueta in CAMPOS + [("sudo", "sudo"), ("servicios", "Servicios del colector")]:
            v = QLabel("—")
            v.setTextInteractionFlags(v.textInteractionFlags() | v.textInteractionFlags().TextSelectableByMouse)
            v.setWordWrap(True)
            self.valores[clave] = v
            self.formulario.addRow(etiqueta + ":", v)
        self.raiz.addWidget(caja)

        caja2 = QGroupBox("Comprobación")
        capa = QVBoxLayout(caja2)
        self.texto = QPlainTextEdit()
        self.texto.setReadOnly(True)
        self.texto.setFont(estilo.fuente_mono(11))
        self.texto.setMaximumHeight(160)
        capa.addWidget(self.texto)
        self.raiz.addWidget(caja2)
        self.raiz.addStretch(1)
        self.raiz.addWidget(self.barra)

        self.b_actualizar.clicked.connect(self.actualizar)
        self.b_comprobar.clicked.connect(self.comprobar)
        self.b_terminal.clicked.connect(self.abrir_terminal)
        self.b_copiar.clicked.connect(self.copiar_comando)
        self.b_desconectar.clicked.connect(self.desconectar)
        self.perfil_cambiado()

    # ------------------------------------------------------------------ servidor activo
    def perfil_cambiado(self) -> None:
        p = self.perfil
        activo = p is not None
        for b in (self.b_actualizar, self.b_comprobar, self.b_terminal, self.b_copiar, self.b_desconectar):
            b.setEnabled(activo)
        self.cabecera.setText(p.etiqueta() if p else "Sin servidor seleccionado")
        self.subcabecera.setText("%s · autenticación: %s · sudo: %s" % (p.destino, p.autenticacion, p.sudo_modo) if p else
                                 "Crea o elige un servidor en la lista de la izquierda.")
        for v in self.valores.values():
            v.setText("—")
        self.texto.clear()
        self.barra.poner("")

    # ------------------------------------------------------------------ acciones
    def actualizar(self) -> None:
        if not self.hay_perfil():
            return
        perfil, con = self.perfil, self.ctx.conexion(self.perfil)

        def trabajo(t):
            return colector.resumen_servidor(con, perfil.ruta_config, t.cancelador)

        def listo(res):
            self.ctx.sesion_cambiada.emit(perfil.id)
            if perfil is not self.perfil:
                return
            if not res["ok"]:
                self.barra.poner(res["error"].splitlines()[0] if res["error"] else "Fallo", "error")
                self.texto.setPlainText(res["error"])
                return
            d = res["datos"]
            for clave, _ in CAMPOS:
                self.valores[clave].setText(d.get(clave, "—") or "—")
            self.valores["sudo"].setText(TEXTO_SUDO.get(d.get("sudo", ""), d.get("sudo", "—")))
            servicios = ["%s: %s" % (k[len("servicio_"):], v) for k, v in d.items() if k.startswith("servicio_")]
            self.valores["servicios"].setText("; ".join(servicios) or "ninguno instalado")
            self.barra.poner("Conectado. Datos actualizados.", "ok")

        self.correr("Consultando %s…" % perfil.etiqueta(), trabajo, listo, deshabilitar=[self.b_actualizar])

    def comprobar(self) -> None:
        if not self.hay_perfil():
            return
        perfil, con = self.perfil, self.ctx.conexion(self.perfil)

        def trabajo(t):
            r = colector.comprobar(con, perfil.ruta_config, t.cancelador)
            return r, (con.explicar_fallo(r) if not r.ok else "")

        def listo(res):
            r, explicacion = res
            if perfil is not self.perfil:
                return
            self.texto.setPlainText((r.salida + (("\n" + explicacion) if explicacion else "")).strip())
            self.barra.poner("Comprobación terminada." if r.ok else explicacion.splitlines()[0], "ok" if r.ok else "error")
            self.ctx.sesion_cambiada.emit(perfil.id)

        self.correr("Comprobando %s…" % perfil.etiqueta(), trabajo, listo, deshabilitar=[self.b_comprobar])

    def abrir_terminal(self) -> None:
        if not self.hay_perfil():
            return
        r = terminal.abrir_en_terminal(self.ctx.conexion(self.perfil).comando_terminal(), self.ctx.ajustes.terminal)
        if not r.ok:
            self.error(r.error or "No se pudo abrir la terminal.")

    def copiar_comando(self) -> None:
        if not self.hay_perfil():
            return
        copiar(self.ctx.conexion(self.perfil).comando_terminal())
        self.barra.poner("Comando ssh copiado al portapapeles.", "ok")

    def desconectar(self) -> None:
        if not self.hay_perfil():
            return
        self.ctx.desconectar(self.perfil.id)
        self.barra.poner("Conexión cerrada y contraseñas de la sesión olvidadas.")

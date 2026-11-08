"""Editor de un servidor (perfil): destino, autenticación, sudo, opciones de conexión y colector.

Cada pestaña del diálogo corresponde a un grupo de opciones del script SSH original
(``-u``, ``-p``, ``-i``, ``--ask-password``, ``--password-env``, ``--accept-new-host-key``,
``--ssh-arg``, ``--ask-sudo-password``, ``--sudo-password-env``, ``--no-sudo``, ``--timeout``…).
"""

from __future__ import annotations

import copy
from typing import Optional

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..nucleo.colector import PRESETS_COLECTOR
from ..nucleo.modelos import (AUTH_AUTO, AUTH_CLAVE, AUTH_INTERACTIVA, AUTH_PASSWORD, FuenteSecreto, ORIGEN_ENTORNO,
                              ORIGEN_LLAVERO, ORIGEN_PREGUNTAR, Perfil, SUDO_AUTO, SUDO_NUNCA, SUDO_SECRETO,
                              VARIANTE_ISA, VARIANTE_LOCAL)
from ..nucleo.ssh import analizar_destino

AYUDA_AUTH = {
    AUTH_AUTO: "ssh decide: prueba tus claves (~/.ssh), el ssh-agent y, si hace falta, pide la contraseña. "
               "Respeta ~/.ssh/config. Es lo más cómodo.",
    AUTH_CLAVE: "Usa SOLO la clave indicada (-i, IdentitiesOnly). Si tiene frase de paso se pedirá en un diálogo.",
    AUTH_PASSWORD: "Solo contraseña (se desactiva la autenticación por clave). Equivale a --ask-password / --password-env.",
    AUTH_INTERACTIVA: "keyboard-interactive: contraseña y código de segundo factor (2FA/OTP). Cada pregunta del "
                      "servidor se muestra en un diálogo.",
}


class SelectorFuente(QWidget):
    """Elige de dónde sale un secreto: preguntar / Llavero de macOS / variable de entorno."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        capa = QHBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        self.origen = QComboBox()
        self.origen.addItem("Preguntar (se recuerda mientras dure la sesión)", ORIGEN_PREGUNTAR)
        self.origen.addItem("Llavero de macOS (opción de guardar al preguntar)", ORIGEN_LLAVERO)
        self.origen.addItem("Variable de entorno", ORIGEN_ENTORNO)
        self.variable = QLineEdit()
        self.variable.setPlaceholderText("NOMBRE_VARIABLE")
        capa.addWidget(self.origen, 1)
        capa.addWidget(self.variable)
        self.origen.currentIndexChanged.connect(self._ver)
        self._ver()

    def _ver(self) -> None:
        self.variable.setVisible(self.origen.currentData() == ORIGEN_ENTORNO)

    def poner(self, f: FuenteSecreto) -> None:
        self.origen.setCurrentIndex(max(self.origen.findData(f.origen), 0))
        self.variable.setText(f.variable)

    def leer(self) -> FuenteSecreto:
        return FuenteSecreto(self.origen.currentData(), self.variable.text().strip())


class DialogoServidor(QDialog):
    """Crea o edita un ``Perfil``. ``perfil_resultante`` contiene el resultado si se aceptó."""

    def __init__(self, ctx, perfil: Optional[Perfil] = None, padre: Optional[QWidget] = None):
        super().__init__(padre)
        self.ctx = ctx
        self.original = perfil
        self.perfil_resultante: Optional[Perfil] = None
        self.setWindowTitle("Editar servidor" if perfil else "Nuevo servidor")
        self.setMinimumSize(620, 560)
        capa = QVBoxLayout(self)
        self.pestanas = QTabWidget()
        capa.addWidget(self.pestanas, 1)
        self._pestana_general()
        self._pestana_autenticacion()
        self._pestana_sudo()
        self._pestana_conexion()
        self._pestana_colector()

        self.resultado = QLabel("")
        self.resultado.setWordWrap(True)
        capa.addWidget(self.resultado)
        fila = QHBoxLayout()
        self.b_probar = QPushButton("Probar conexión")
        fila.addWidget(self.b_probar)
        fila.addStretch(1)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)
        fila.addWidget(botones)
        capa.addLayout(fila)
        self.b_probar.clicked.connect(self._probar)
        self._cargar(perfil or Perfil())

    # ------------------------------------------------------------------ pestañas
    def _pestana_general(self) -> None:
        w = QWidget()
        f = QFormLayout(w)
        self.nombre = QLineEdit()
        self.destino = QLineEdit()
        self.destino.setPlaceholderText("usuario@servidor[:puerto]  o un alias de ~/.ssh/config")
        self.usuario = QLineEdit()
        self.usuario.setPlaceholderText("(opcional si ya va en el destino) -u")
        self.puerto = QSpinBox()
        self.puerto.setRange(0, 65535)
        self.puerto.setSpecialValueText("el de ssh (22)")
        self.variante = QComboBox()
        self.variante.addItem("Servidor local (Debian · instalar-todo.sh)", VARIANTE_LOCAL)
        self.variante.addItem("Producción isa.umh.es (instalar-todo-isa.sh)", VARIANTE_ISA)
        self.url_base = QLineEdit()
        self.url_base.setPlaceholderText("http://192.168.0.129  ·  https://isa.umh.es")
        self.notas = QPlainTextEdit()
        self.notas.setMaximumHeight(90)
        f.addRow("Nombre:", self.nombre)
        f.addRow("Destino:", self.destino)
        f.addRow("Usuario:", self.usuario)
        f.addRow("Puerto:", self.puerto)
        f.addRow("Tipo de servidor:", self.variante)
        f.addRow("URL pública:", self.url_base)
        f.addRow("Notas:", self.notas)
        self.pestanas.addTab(w, "General")

    def _pestana_autenticacion(self) -> None:
        w = QWidget()
        f = QFormLayout(w)
        self.auth = QComboBox()
        self.auth.addItem("Automática (claves, agente, contraseña)", AUTH_AUTO)
        self.auth.addItem("Clave concreta", AUTH_CLAVE)
        self.auth.addItem("Contraseña", AUTH_PASSWORD)
        self.auth.addItem("Interactiva (contraseña + 2FA)", AUTH_INTERACTIVA)
        self.ayuda_auth = QLabel("")
        self.ayuda_auth.setWordWrap(True)
        self.ayuda_auth.setProperty("rol", "subtitulo")
        self.identidad = QLineEdit()
        self.identidad.setPlaceholderText("~/.ssh/id_ed25519")
        b = QPushButton("Examinar…")
        b.clicked.connect(self._examinar_identidad)
        fi = QHBoxLayout()
        fi.addWidget(self.identidad, 1)
        fi.addWidget(b)
        self.fuente_password = SelectorFuente()
        self.fuente_frase = SelectorFuente()
        self.b_borrar_llavero = QPushButton("Borrar secretos guardados de este servidor")
        self.b_borrar_llavero.clicked.connect(self._borrar_llavero)
        f.addRow("Método:", self.auth)
        f.addRow(self.ayuda_auth)
        f.addRow("Clave privada (-i):", fi)
        f.addRow("Contraseña SSH:", self.fuente_password)
        f.addRow("Frase de la clave:", self.fuente_frase)
        f.addRow("", self.b_borrar_llavero)
        self.auth.currentIndexChanged.connect(self._auth_cambiada)
        self.pestanas.addTab(w, "Autenticación")

    def _pestana_sudo(self) -> None:
        w = QWidget()
        f = QFormLayout(w)
        self.sudo_modo = QComboBox()
        self.sudo_modo.addItem("Automático: sudo si no soy root", SUDO_AUTO)
        self.sudo_modo.addItem("Nunca usar sudo (--no-sudo)", SUDO_NUNCA)
        self.sudo_modo.addItem("Contraseña de sudo propia", SUDO_SECRETO)
        self.reutilizar = QCheckBox("Reutilizar la contraseña SSH como contraseña de sudo (habitual en Debian)")
        self.fuente_sudo = SelectorFuente()
        ayuda = QLabel("El informe del colector necesita leer config.ini, que suele ser de root: por eso se ejecuta con sudo. "
                       "La contraseña viaja por la conexión cifrada, nunca en la línea de comandos.")
        ayuda.setWordWrap(True)
        ayuda.setProperty("rol", "subtitulo")
        f.addRow("Uso de sudo:", self.sudo_modo)
        f.addRow("", self.reutilizar)
        f.addRow("Contraseña de sudo:", self.fuente_sudo)
        f.addRow(ayuda)
        self.sudo_modo.currentIndexChanged.connect(self._sudo_cambiado)
        self.pestanas.addTab(w, "sudo")

    def _pestana_conexion(self) -> None:
        w = QWidget()
        f = QFormLayout(w)
        self.aceptar_huella = QCheckBox("Aceptar automáticamente la huella de un servidor NUEVO (--accept-new-host-key)")
        self.multiplexar = QCheckBox("Reutilizar una única conexión (ControlMaster): autenticarse una sola vez")
        self.salto = QLineEdit()
        self.salto.setPlaceholderText("usuario@bastion:22  (ProxyJump -J)")
        self.opciones_ssh = QPlainTextEdit()
        self.opciones_ssh.setPlaceholderText("Una por línea, p. ej.:\n-o ServerAliveInterval=30\n-o HostKeyAlgorithms=+ssh-rsa")
        self.opciones_ssh.setMaximumHeight(110)
        self.t_conexion = QSpinBox()
        self.t_conexion.setRange(2, 300)
        self.t_conexion.setSuffix(" s")
        self.t_total = QSpinBox()
        self.t_total.setRange(10, 7200)
        self.t_total.setSuffix(" s")
        self.python_remoto = QLineEdit()
        f.addRow("", self.aceptar_huella)
        f.addRow("", self.multiplexar)
        f.addRow("Salto (bastión):", self.salto)
        f.addRow("Opciones de ssh (--ssh-arg):", self.opciones_ssh)
        f.addRow("Espera de conexión:", self.t_conexion)
        f.addRow("Espera por operación:", self.t_total)
        f.addRow("Python en el servidor:", self.python_remoto)
        self.pestanas.addTab(w, "Conexión")

    def _pestana_colector(self) -> None:
        w = QWidget()
        f = QFormLayout(w)
        self.preset = QComboBox()
        self.preset.addItem("(personalizado)")
        self.preset.addItems(list(PRESETS_COLECTOR))
        self.ruta_config = QLineEdit()
        self.servicio = QLineEdit()
        f.addRow("Colector:", self.preset)
        f.addRow("config.ini:", self.ruta_config)
        f.addRow("Servicio systemd:", self.servicio)
        self.preset.currentTextChanged.connect(self._preset)
        self.pestanas.addTab(w, "Colector")

    # ------------------------------------------------------------------ comportamiento
    def _examinar_identidad(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Clave privada", "~/.ssh")
        if ruta:
            self.identidad.setText(ruta)

    def _auth_cambiada(self) -> None:
        m = self.auth.currentData()
        self.ayuda_auth.setText(AYUDA_AUTH[m])
        self.identidad.setEnabled(m in (AUTH_CLAVE, AUTH_AUTO))
        self.fuente_password.setEnabled(m in (AUTH_PASSWORD, AUTH_INTERACTIVA, AUTH_AUTO))
        self.fuente_frase.setEnabled(m in (AUTH_CLAVE, AUTH_AUTO))

    def _sudo_cambiado(self) -> None:
        m = self.sudo_modo.currentData()
        self.reutilizar.setEnabled(m == SUDO_AUTO)
        self.fuente_sudo.setEnabled(m == SUDO_SECRETO)

    def _preset(self, nombre: str) -> None:
        if nombre in PRESETS_COLECTOR:
            self.ruta_config.setText(PRESETS_COLECTOR[nombre][0])
            self.servicio.setText(PRESETS_COLECTOR[nombre][1])

    def _borrar_llavero(self) -> None:
        if self.original:
            self.ctx.llavero.borrar_todos(self.original.id)
            self.resultado.setText("Secretos de este servidor borrados del Llavero.")

    def _cargar(self, p: Perfil) -> None:
        self.nombre.setText(p.nombre)
        self.destino.setText(p.destino)
        self.usuario.setText(p.usuario)
        self.puerto.setValue(p.puerto)
        self.variante.setCurrentIndex(max(self.variante.findData(p.variante), 0))
        self.url_base.setText(p.url_base)
        self.notas.setPlainText(p.notas)
        self.auth.setCurrentIndex(max(self.auth.findData(p.autenticacion), 0))
        self.identidad.setText(p.identidad)
        self.fuente_password.poner(p.password)
        self.fuente_frase.poner(p.frase)
        self.sudo_modo.setCurrentIndex(max(self.sudo_modo.findData(p.sudo_modo), 0))
        self.reutilizar.setChecked(p.reutilizar_password_sudo)
        self.fuente_sudo.poner(p.sudo)
        self.aceptar_huella.setChecked(p.aceptar_huella_nueva)
        self.multiplexar.setChecked(p.multiplexar)
        self.salto.setText(p.salto)
        self.opciones_ssh.setPlainText("\n".join(p.opciones_ssh))
        self.t_conexion.setValue(p.timeout_conexion)
        self.t_total.setValue(p.timeout_total)
        self.python_remoto.setText(p.python_remoto)
        self.ruta_config.setText(p.ruta_config)
        self.servicio.setText(p.servicio)
        self._auth_cambiada()
        self._sudo_cambiado()

    def _construir(self) -> Perfil:
        p = copy.deepcopy(self.original) if self.original else Perfil()
        p.nombre = self.nombre.text().strip()
        p.destino = self.destino.text().strip()
        p.usuario = self.usuario.text().strip()
        p.puerto = self.puerto.value()
        p.variante = self.variante.currentData()
        p.url_base = self.url_base.text().strip()
        p.notas = self.notas.toPlainText().strip()
        p.autenticacion = self.auth.currentData()
        p.identidad = self.identidad.text().strip()
        p.password = self.fuente_password.leer()
        p.frase = self.fuente_frase.leer()
        p.sudo_modo = self.sudo_modo.currentData()
        p.reutilizar_password_sudo = self.reutilizar.isChecked()
        p.sudo = self.fuente_sudo.leer()
        p.aceptar_huella_nueva = self.aceptar_huella.isChecked()
        p.multiplexar = self.multiplexar.isChecked()
        p.salto = self.salto.text().strip()
        p.opciones_ssh = [l.strip() for l in self.opciones_ssh.toPlainText().splitlines() if l.strip()]
        p.timeout_conexion = self.t_conexion.value()
        p.timeout_total = self.t_total.value()
        p.python_remoto = self.python_remoto.text().strip() or "python3"
        p.ruta_config = self.ruta_config.text().strip()
        p.servicio = self.servicio.text().strip()
        return p

    def _validar(self, p: Perfil) -> str:
        if analizar_destino(p.destino) is None:
            return "El destino no es válido. Formato: [usuario@]servidor[:puerto] o un alias de ~/.ssh/config."
        if p.autenticacion == AUTH_CLAVE and not p.identidad:
            return "Indica la clave privada o cambia el método de autenticación."
        for nombre, f in (("contraseña SSH", p.password), ("frase", p.frase), ("sudo", p.sudo)):
            if f.origen == ORIGEN_ENTORNO and not f.variable:
                return "Indica el nombre de la variable de entorno para la %s." % nombre
        return ""

    def _guardar(self) -> None:
        p = self._construir()
        error = self._validar(p)
        if error:
            self.resultado.setText(error)
            self.resultado.setProperty("rol", "error")
            self.resultado.style().unpolish(self.resultado)
            self.resultado.style().polish(self.resultado)
            return
        if not p.nombre:
            p.nombre = p.destino
        self.perfil_resultante = p
        self.accept()

    def _probar(self) -> None:
        """Abre una conexión temporal con los valores del formulario (sin guardar nada)."""
        p = self._construir()
        error = self._validar(p)
        if error:
            self.resultado.setText(error)
            return
        from ..nucleo.secretos import ResolutorSecretos
        from ..nucleo.ssh import Conexion
        p.id = "prueba-" + p.id
        secretos = ResolutorSecretos(p, self.ctx.interaccion, self.ctx.llavero)
        con = Conexion(p, self.ctx.ajustes, self.ctx.askpass, self.ctx.interaccion, secretos, registro=self.ctx.registrar)
        self.b_probar.setEnabled(False)
        self.resultado.setText("Conectando…")

        def trabajo(t):
            r = con.conectar(t.cancelador)
            texto = r.salida.strip() if r.ok else con.explicar_fallo(r)
            con.destruir()
            return r.ok, texto

        def listo(res):
            ok, texto = res
            self.resultado.setText(("✔ Conexión correcta: " if ok else "✖ ") + texto)

        from .hilos import Trabajo
        Trabajo(trabajo, "probar", al_terminar=listo, al_error=lambda d: self.resultado.setText("Error: " + d[-300:]),
                al_fin=lambda: self.b_probar.setEnabled(True)).iniciar()

"""Pestaña «Claves SSH»: claves locales, ssh-agent y ``authorized_keys`` del servidor.

Reúne las opciones del script SSH original relacionadas con claves: ``--generate-key``,
``--install-key``, ``--check-key``, ``--pubkey`` y ``--authorized-keys``; y añade lo que un script
no puede ofrecer cómodamente: ver las claves del equipo con su huella, cargarlas en el agente
(con el Llavero de macOS), revocar una clave del servidor y olvidar una huella de known_hosts.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

from ...nucleo import claves, colector
from ...nucleo.claves import ClaveLocal
from ...nucleo.ssh import analizar_destino
from .. import estilo
from ..widgets import botones_es, ConsolaAnsi, copiar, rellenar, tabla
from .base import PaginaBase

TIPOS = [("Ed25519 (recomendado)", "ed25519"), ("RSA 4096", "rsa"), ("ECDSA", "ecdsa")]


class DialogoGenerarClave(QDialog):
    """Pide nombre, tipo, comentario y frase de paso de una clave nueva."""

    def __init__(self, nombre_sugerido: str, padre: Optional[QWidget] = None):
        super().__init__(padre)
        self.setWindowTitle("Generar clave SSH")
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        self.ruta = QLineEdit("~/.ssh/" + nombre_sugerido)
        self.tipo = QComboBox()
        for t, v in TIPOS:
            self.tipo.addItem(t, v)
        self.comentario = QLineEdit()
        self.frase = QLineEdit()
        self.frase.setEchoMode(QLineEdit.EchoMode.Password)
        self.frase2 = QLineEdit()
        self.frase2.setEchoMode(QLineEdit.EchoMode.Password)
        self.aviso = QLabel("Con frase de paso la clave queda cifrada en disco (muy recomendable). "
                            "Déjala vacía solo para automatizaciones.")
        self.aviso.setWordWrap(True)
        self.aviso.setProperty("rol", "subtitulo")
        form.addRow("Fichero:", self.ruta)
        form.addRow("Tipo:", self.tipo)
        form.addRow("Comentario:", self.comentario)
        form.addRow("Frase de paso:", self.frase)
        form.addRow("Repetir frase:", self.frase2)
        form.addRow(self.aviso)
        botones = botones_es(QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel))
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        form.addRow(botones)

    def _aceptar(self) -> None:
        if self.frase.text() != self.frase2.text():
            self.aviso.setText("Las dos frases no coinciden.")
            estilo.poner_rol(self.aviso, "error")
            return
        if not self.ruta.text().strip():
            return
        self.accept()


class PaginaClaves(PaginaBase):
    titulo = "Claves SSH"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._claves: list = []

        g1 = QGroupBox("Claves de este equipo (~/.ssh)")
        c1 = QVBoxLayout(g1)
        self.tabla = tabla(["Tipo", "Bits", "Frase", "Huella SHA256", "Comentario", "Fichero"])
        c1.addWidget(self.tabla)
        f1 = QHBoxLayout()
        self.b_actualizar = QPushButton("Actualizar")
        self.b_generar = QPushButton("Generar nueva…")
        self.b_agente = QPushButton("Cargar en ssh-agent")
        self.b_copiar = QPushButton("Copiar pública")
        self.b_usar = QPushButton("Usar en este servidor")
        for b in (self.b_actualizar, self.b_generar, self.b_agente, self.b_copiar, self.b_usar):
            f1.addWidget(b)
        f1.addStretch(1)
        c1.addLayout(f1)
        self.agente = QLabel("ssh-agent: —")
        self.agente.setProperty("rol", "subtitulo")
        self.agente.setWordWrap(True)
        c1.addWidget(self.agente)
        self.raiz.addWidget(g1, 2)

        g2 = QGroupBox("En el servidor (usa la clave seleccionada arriba)")
        c2 = QHBoxLayout(g2)
        self.b_comprobar = QPushButton("Comprobar acceso solo con clave")
        self.b_instalar = QPushButton("Instalar clave")
        self.b_revocar = QPushButton("Revocar clave…")
        self.b_auditar = QPushButton("Auditar authorized_keys")
        self.b_huella = QPushButton("Olvidar huella del servidor…")
        for b in (self.b_comprobar, self.b_instalar, self.b_revocar, self.b_auditar, self.b_huella):
            c2.addWidget(b)
        c2.addStretch(1)
        self.raiz.addWidget(g2)
        self.salida = ConsolaAnsi()
        self.raiz.addWidget(self.salida, 2)
        self.raiz.addWidget(self.barra)

        self.b_actualizar.clicked.connect(self.actualizar)
        self.b_generar.clicked.connect(self.generar)
        self.b_agente.clicked.connect(self.cargar_agente)
        self.b_copiar.clicked.connect(self.copiar_publica)
        self.b_usar.clicked.connect(self.usar_en_perfil)
        self.b_comprobar.clicked.connect(self.comprobar)
        self.b_instalar.clicked.connect(self.instalar)
        self.b_revocar.clicked.connect(self.revocar)
        self.b_auditar.clicked.connect(self.auditar)
        self.b_huella.clicked.connect(self.olvidar_huella)
        self.tabla.itemSelectionChanged.connect(self._seleccion)
        self.perfil_cambiado()
        self.actualizar()

    # ------------------------------------------------------------------ utilidades
    def _clave(self) -> Optional[ClaveLocal]:
        filas = self.tabla.selectionModel().selectedRows()
        return self._claves[filas[0].row()] if filas and filas[0].row() < len(self._claves) else None

    def _seleccion(self) -> None:
        c = self._clave()
        for b in (self.b_agente, self.b_copiar, self.b_usar):
            b.setEnabled(c is not None)
        self._servidor_habilitado()

    def _servidor_habilitado(self) -> None:
        hay = self.perfil is not None
        c = self._clave()
        self.b_comprobar.setEnabled(hay)
        self.b_auditar.setEnabled(hay)
        self.b_huella.setEnabled(hay)
        self.b_instalar.setEnabled(hay and (c is not None or True))     # sin selección usa la clave del perfil / por defecto
        self.b_revocar.setEnabled(hay and c is not None)

    def perfil_cambiado(self) -> None:
        self.salida.clear()
        self.barra.poner("")
        self._seleccion()

    def _publica(self) -> tuple:
        """(línea pública, ruta) de la clave seleccionada o, si no hay, la del perfil / predeterminada."""
        c = self._clave()
        if c is not None:
            return claves.leer_publica(c.ruta_publica), c.ruta_publica
        return claves.buscar_publica(self.perfil.identidad if self.perfil else "")

    def _identidad(self) -> str:
        c = self._clave()
        return c.ruta_privada if c is not None else (self.perfil.identidad if self.perfil else "")

    # ------------------------------------------------------------------ claves locales
    def actualizar(self) -> None:
        ajustes = self.ctx.ajustes

        def trabajo(t):
            return claves.listar_claves_locales(ajustes), claves.listar_agente()

        def listo(res):
            self._claves, agente = res
            filas = [(c.tipo, c.bits or "", {True: "sí", False: "no", None: "?"}[c.protegida] if c.tiene_privada else "(sin privada)",
                      c.huella, c.comentario, c.ruta_privada) for c in self._claves]
            rellenar(self.tabla, filas)
            self.agente.setText("ssh-agent: %s" % ("; ".join("%s %s" % (h[:22] + "…", com) for h, com in agente) if agente
                                                    else "sin claves cargadas (o no hay agente)"))
            self._seleccion()

        self.correr("Leyendo ~/.ssh…", trabajo, listo, deshabilitar=[self.b_actualizar])

    def generar(self) -> None:
        sugerido = "id_ed25519_" + "".join(ch for ch in (self.perfil.etiqueta() if self.perfil else "panel") if ch.isalnum()).lower()
        dlg = DialogoGenerarClave(sugerido, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ruta, tipo, frase, comentario = dlg.ruta.text().strip(), dlg.tipo.currentData(), dlg.frase.text(), dlg.comentario.text().strip()
        ajustes, askpass = self.ctx.ajustes, self.ctx.askpass

        def listo(r):
            if r.ok:
                self.barra.poner("Clave creada: %s" % ruta, "ok")
                self.actualizar()
            else:
                self.salida.anadir(r.error, True)
                self.barra.poner((r.error.strip().splitlines() or ["Error"])[0], "error")

        self.correr("Generando clave…", lambda t: claves.generar_clave(ajustes, askpass, ruta, tipo, frase, comentario),
                    listo, deshabilitar=[self.b_generar])

    def cargar_agente(self) -> None:
        c = self._clave()
        if c is None:
            return
        ajustes, askpass, inter = self.ctx.ajustes, self.ctx.askpass, self.ctx.interaccion

        def frase(prompt: str) -> Optional[str]:
            r = inter.pedir_secreto("Frase de la clave", "Escribe la frase de paso de %s." % c.ruta_privada)
            return r[0] if r else None

        def listo(r):
            self.barra.poner("Clave cargada en el agente." if r.ok else (r.error.strip().splitlines() or ["Error"])[0],
                             "ok" if r.ok else "error")
            self.actualizar()

        self.correr("Cargando en ssh-agent…", lambda t: claves.agregar_al_agente(ajustes, askpass, c.ruta_privada, frase),
                    listo, deshabilitar=[self.b_agente])

    def copiar_publica(self) -> None:
        linea, _ = self._publica()
        if linea:
            copiar(linea)
            self.barra.poner("Clave pública copiada.", "ok")

    def usar_en_perfil(self) -> None:
        c = self._clave()
        if c is None or not self.hay_perfil():
            return
        from ...nucleo.modelos import AUTH_CLAVE
        self.perfil.autenticacion = AUTH_CLAVE
        self.perfil.identidad = c.ruta_privada
        self.ctx.almacen.actualizar(self.perfil)
        self.ctx.perfiles_cambiados.emit()
        self.barra.poner("El servidor «%s» ahora se autentica con %s." % (self.perfil.etiqueta(), c.ruta_privada), "ok")

    # ------------------------------------------------------------------ en el servidor
    def comprobar(self) -> None:
        if not self.hay_perfil():
            return
        con, identidad = self.ctx.conexion(self.perfil), self._identidad()

        def listo(r):
            self.salida.clear()
            if r["ok"]:
                k = r.get("clave") or {}
                self.salida.anadir("✔ Acceso con clave correcto como %s en %s." % (r["usuario"], r["host"]))
                if k:
                    self.salida.anadir("   Clave aceptada: %s (%s)" % (k.get("huella", "?"), k.get("descripcion", "")))
                self.barra.poner("El servidor acepta tu clave: ya no hace falta la contraseña.", "ok")
            else:
                self.salida.anadir("✖ " + claves.EXPLICACION_MOTIVO.get(r["motivo"], "Fallo."), True)
                if r["error"]:
                    self.salida.anadir(r["error"], True)
                self.barra.poner("El acceso solo con clave no funciona (%s)." % r["motivo"], "error")

        self.correr("Comprobando acceso solo con clave…", lambda t: claves.comprobar_acceso_clave(con, identidad, t.cancelador),
                    listo, deshabilitar=[self.b_comprobar])

    def instalar(self) -> None:
        if not self.hay_perfil():
            return
        linea, ruta = self._publica()
        if not linea:
            self.error("No hay clave pública (%s). Genera una con «Generar nueva…»." % ruta)
            return
        if not self.confirmar("Instalar clave", "Se añadirá la clave de %s a ~/.ssh/authorized_keys de %s." % (ruta, self.perfil.etiqueta())):
            return
        con = self.ctx.conexion(self.perfil)

        def listo(r):
            if r["ok"]:
                self.salida.anadir("Clave %s en %s" % ("ya estaba" if r["resultado"] == "already" else "añadida", r["fichero"]))
                self.barra.poner("Clave instalada. Prueba «Comprobar acceso solo con clave».", "ok")
            else:
                self.salida.anadir(r["error"], True)
                self.barra.poner(r["error"].splitlines()[0] if r["error"] else "Error", "error")

        self.correr("Instalando clave…", lambda t: claves.instalar_clave(con, linea, t.cancelador), listo,
                    deshabilitar=[self.b_instalar])

    def revocar(self) -> None:
        c = self._clave()
        if c is None or not self.hay_perfil():
            return
        linea = claves.leer_publica(c.ruta_publica)
        if not linea:
            return
        if not self.confirmar("Revocar clave", "Se quitará la clave %s de authorized_keys de %s (con copia previa).\n"
                              "Si es la única forma de entrar, perderás el acceso." % (c.huella, self.perfil.etiqueta()), forzar=True):
            return
        con = self.ctx.conexion(self.perfil)

        def listo(r):
            if not r["ok"]:
                self.barra.poner(r["error"], "error")
                return
            mensaje = {"removed": "Quitada (%d línea/s). Copia: %s" % (r.get("cantidad", 0), r.get("copia")),
                       "absent": "La clave no estaba en authorized_keys.", "missing": "El servidor no tiene authorized_keys."}
            self.salida.anadir(mensaje.get(r["resultado"], str(r)))
            self.barra.poner("Hecho.", "ok")

        self.correr("Revocando clave…", lambda t: claves.revocar_clave(con, linea, t.cancelador), listo,
                    deshabilitar=[self.b_revocar])

    def auditar(self) -> None:
        if not self.hay_perfil():
            return
        con, recursos, idioma = self.ctx.conexion(self.perfil), self.ctx.recursos(), self.ctx.ajustes.idioma_informe

        def listo(r):
            self.salida.clear()
            if r["ok"]:
                self.salida.anadir(r["texto"])
                errores = sum(1 for d in r["datos"].get("diagnostics", []) if d.get("level") == "err")
                self.barra.poner("Auditoría terminada (%d error/es)." % errores, "ok" if not errores else "aviso")
            else:
                self.salida.anadir(r["error"], True)
                self.barra.poner("No se pudo auditar.", "error")

        self.correr("Auditando authorized_keys…", lambda t: colector.auditar_claves(con, recursos, idioma, t.cancelador),
                    listo, deshabilitar=[self.b_auditar])

    def olvidar_huella(self) -> None:
        if not self.hay_perfil():
            return
        d = analizar_destino(self.perfil.destino)
        if d is None:
            return
        puerto = d.puerto or self.perfil.puerto
        if not self.confirmar("Olvidar huella", "Se quitará «%s» de ~/.ssh/known_hosts.\nHazlo solo si sabes por qué cambió "
                              "la huella (reinstalación, nueva IP…)." % d.host, forzar=True):
            return
        r = claves.olvidar_huella(d.host, puerto)
        self.salida.anadir((r.salida + r.error).strip() or "Hecho.")
        self.barra.poner("Huella olvidada: la próxima conexión pedirá confirmación." if r.ok else "ssh-keygen devolvió un error.",
                         "ok" if r.ok else "error")

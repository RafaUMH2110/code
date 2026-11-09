"""Ventana «Acerca de»: qué es la aplicación, versión, fecha de la última modificación y entorno.

Toda la información sale de ``nucleo/acerca.py``; aquí solo se maqueta y se añade lo propio de Qt.
"""

from __future__ import annotations

from typing import Optional

import PySide6
from PySide6.QtCore import Qt, qVersion
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from .. import AUTOR, LEYENDA_IA, NOMBRE_APP, URL_REPOSITORIO, __version__, rutas
from ..nucleo import acerca
from . import estilo
from .widgets import botones_es, copiar


class DialogoAcerca(QDialog):
    def __init__(self, ssh_path: str = "", padre: Optional[QWidget] = None):
        super().__init__(padre)
        self.setWindowTitle("Acerca de %s" % NOMBRE_APP)
        self.setMinimumWidth(560)
        self._extra = [("Qt / PySide6", "%s / %s" % (qVersion(), PySide6.__version__))]
        self._ssh_path = ssh_path
        capa = QVBoxLayout(self)
        capa.setSpacing(12)

        # --- cabecera: icono + nombre + versión + fecha de la última modificación
        cabecera = QHBoxLayout()
        icono = QLabel()
        ruta_icono = rutas.dir_recursos().parent / "icono.png"
        if ruta_icono.is_file():
            icono.setPixmap(QPixmap(str(ruta_icono)).scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                                                           Qt.TransformationMode.SmoothTransformation))
        icono.setAlignment(Qt.AlignmentFlag.AlignTop)
        cabecera.addWidget(icono)
        textos = QVBoxLayout()
        titulo = QLabel(NOMBRE_APP)
        estilo.poner_rol(titulo, "titulo")
        version = QLabel("Versión %s" % __version__)
        self.etiqueta_fecha = QLabel("Última modificación: <b>%s</b>" % acerca.fecha_modificacion_legible())
        self.etiqueta_fecha.setTextFormat(Qt.TextFormat.RichText)
        descripcion = QLabel("Administración gráfica de servidores TeleMet / Apache por SSH. Sustituye a "
                             "<code>instalar-todo.sh</code>, <code>telemet-collector-info.py</code> y "
                             "<code>telemet-collector-info-ssh.py</code>.")
        descripcion.setWordWrap(True)
        descripcion.setTextFormat(Qt.TextFormat.RichText)
        for w in (titulo, version, self.etiqueta_fecha, descripcion):
            textos.addWidget(w)
        textos.addStretch(1)
        cabecera.addLayout(textos, 1)
        capa.addLayout(cabecera)

        # --- tabla de datos del entorno (texto seleccionable para copiarlo con el ratón)
        rejilla = QGridLayout()
        rejilla.setHorizontalSpacing(14)
        rejilla.setVerticalSpacing(4)
        filas = [f for f in acerca.informacion(ssh_path) if f[0] not in ("Versión", "Última modificación")]
        filas.insert(1, self._extra[0])
        for i, (etiqueta, valor) in enumerate(filas):
            e = QLabel(etiqueta + ":")
            estilo.poner_rol(e, "subtitulo")
            e.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            v = QLabel(valor)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.setWordWrap(True)
            rejilla.addWidget(e, i, 0)
            rejilla.addWidget(v, i, 1)
        rejilla.setColumnStretch(1, 1)
        capa.addLayout(rejilla)

        # --- autoría y enlace
        autor = QLabel()
        # El azul de enlace por defecto no se lee sobre fondo oscuro: el color va en el propio <a>.
        autor.setTextFormat(Qt.TextFormat.RichText)
        autor.setText("%s<br><i>%s</i><br><a href=\"%s\" style=\"color:%s\">Código fuente en GitHub</a>" % (AUTOR, LEYENDA_IA, URL_REPOSITORIO, estilo.color("enlace")))
        autor.setOpenExternalLinks(True)
        autor.setWordWrap(True)
        capa.addWidget(autor)

        # --- botones
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copiar_btn = QPushButton("Copiar información")
        copiar_btn.setToolTip("Copia versión, fecha y entorno (sin ningún dato secreto) para pegarlos en un correo")
        botones.addButton(copiar_btn, QDialogButtonBox.ButtonRole.ActionRole)
        copiar_btn.clicked.connect(lambda: copiar(self.texto_informacion()))
        botones.rejected.connect(self.reject)
        capa.addWidget(botones_es(botones))

    def texto_informacion(self) -> str:
        return acerca.texto_para_copiar(self._extra, self._ssh_path)

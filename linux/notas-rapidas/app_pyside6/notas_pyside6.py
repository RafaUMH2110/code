#!/usr/bin/env python3
"""Notas Rápidas con PySide6 (Qt for Python) para Linux (Debian, Ubuntu y Linux Mint).

Se puede ejecutar de varias formas:
  * Como script:       python3 notas_pyside6.py   (con PySide6 instalado)
  * Instalada (.deb):  sudo apt install ./notas-rapidas-pyside6_1.0.0_all.deb
  * Binario:           ./construir_app.sh  (PyInstaller)

Conceptos que ilustra:
  - QApplication, QMainWindow y el bucle de eventos de Qt
  - QAction con atajos estándar (QKeySequence.StandardKey) y menú Ayuda
  - Indicador de documento modificado (setWindowModified) y confirmación al cerrar
  - Icono de ventana y nombre de fichero .desktop (setDesktopFileName) para el dock
  - Rutas XDG: configuración en ~/.config y registro en ~/.local/state
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QAction, QFont, QFontDatabase, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
)

APP_NAME = "Notas Rápidas"
APP_ID = "notas-rapidas-pyside6"
VERSION = "1.0.0"
def _xdg(variable: str, por_defecto: str) -> Path:
    """Carpetas de usuario según la especificación XDG (con valores por defecto)."""
    return Path(os.environ.get(variable) or Path.home() / por_defecto)


SUPPORT_DIR = _xdg("XDG_CONFIG_HOME", ".config") / APP_ID      # configuración
LOG_DIR = _xdg("XDG_STATE_HOME", ".local/state") / APP_ID      # registros

CONFIG_FILE = SUPPORT_DIR / "config.json"
LOG_FILE = LOG_DIR / "app.log"
DEFAULT_CONFIG = {"width": 820, "height": 560, "font_size": 14, "last_file": None}

log = logging.getLogger(APP_ID)


def resource_path(relative: str) -> Path:
    """Recursos empaquetados: sys._MEIPASS con PyInstaller; junto al .py en cualquier otro caso."""
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return Path(base) / relative


def configurar_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8",
    )

    def hook(tipo, valor, tb):
        log.critical("Excepción no controlada", exc_info=(tipo, valor, tb))
        sys.__excepthook__(tipo, valor, tb)

    sys.excepthook = hook
    log.info("Arranque %s v%s (Python %s)", APP_NAME, VERSION, sys.version.split()[0])


def cargar_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    try:
        config.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError):
        log.exception("Config ilegible; se usan valores por defecto")
    return config


def guardar_config(config: dict) -> None:
    try:
        SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError:
        log.exception("No se pudo guardar la configuración")


class Ventana(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = cargar_config()
        self.archivo: Path | None = None

        self.resize(QSize(self.config["width"], self.config["height"]))
        self.setMinimumSize(420, 280)

        self.texto = QPlainTextEdit()
        fuente = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fuente.setPointSize(self.config["font_size"])
        self.texto.setFont(fuente)
        self.texto.setTabStopDistance(4 * self.texto.fontMetrics().horizontalAdvance(" "))
        self.setCentralWidget(self.texto)

        self.estado = QLabel()
        self.statusBar().addWidget(self.estado, 1)

        self._crear_acciones_y_menus()

        self.texto.textChanged.connect(self._actualizar_estado)
        self.texto.document().modificationChanged.connect(self._actualizar_titulo)

        ultimo = self.config.get("last_file")
        if ultimo and Path(ultimo).is_file():
            self.cargar(Path(ultimo))
        self._actualizar_titulo()
        self._actualizar_estado()

    # ---- menús ------------------------------------------------------------
    def _accion(self, texto, atajo, funcion, rol=None) -> QAction:
        accion = QAction(texto, self)
        if atajo is not None:
            accion.setShortcut(QKeySequence(atajo))   # StandardKey -> Cmd en macOS
        if rol is not None:
            accion.setMenuRole(rol)
        accion.triggered.connect(funcion)
        return accion

    def _crear_acciones_y_menus(self) -> None:
        SK = QKeySequence.StandardKey
        barra = self.menuBar()

        m_archivo = barra.addMenu("Archivo")
        m_archivo.addAction(self._accion("Nuevo", SK.New, self.nuevo))
        m_archivo.addAction(self._accion("Abrir…", SK.Open, self.abrir))
        m_archivo.addSeparator()
        m_archivo.addAction(self._accion("Guardar", SK.Save, self.guardar))
        m_archivo.addAction(self._accion("Guardar como…", SK.SaveAs, self.guardar_como))
        m_archivo.addSeparator()
        m_archivo.addAction(self._accion(
            "Salir", QKeySequence("Ctrl+Q"), self.close, QAction.MenuRole.QuitRole))

        m_edicion = barra.addMenu("Edición")
        m_edicion.addAction(self._accion("Deshacer", SK.Undo, self.texto.undo))
        m_edicion.addAction(self._accion("Rehacer", SK.Redo, self.texto.redo))
        m_edicion.addSeparator()
        m_edicion.addAction(self._accion("Cortar", SK.Cut, self.texto.cut))
        m_edicion.addAction(self._accion("Copiar", SK.Copy, self.texto.copy))
        m_edicion.addAction(self._accion("Pegar", SK.Paste, self.texto.paste))
        m_edicion.addAction(self._accion("Seleccionar todo", SK.SelectAll, self.texto.selectAll))

        m_ver = barra.addMenu("Ver")
        m_ver.addAction(self._accion("Aumentar letra", SK.ZoomIn, lambda: self.zoom(+1)))
        m_ver.addAction(self._accion("Reducir letra", SK.ZoomOut, lambda: self.zoom(-1)))

        m_ayuda = barra.addMenu("Ayuda")
        m_ayuda.addAction(self._accion(
            "Acerca de…", None, self.acerca_de, QAction.MenuRole.AboutRole))

    # ---- archivo ------------------------------------------------------------
    def nuevo(self) -> None:
        if not self._confirmar_cambios():
            return
        self.texto.clear()
        self.texto.document().setModified(False)
        self.archivo = None
        self._actualizar_titulo()

    def abrir(self) -> None:
        if not self._confirmar_cambios():
            return
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Abrir", "", "Texto (*.txt *.md);;Todos los archivos (*)")
        if ruta:
            self.cargar(Path(ruta))

    def cargar(self, ruta: Path) -> None:
        try:
            contenido = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log.exception("No se pudo abrir %s", ruta)
            QMessageBox.critical(self, APP_NAME, f"No se pudo abrir el archivo:\n{exc}")
            return
        self.texto.setPlainText(contenido)
        self.texto.document().setModified(False)
        self.texto.document().clearUndoRedoStacks()
        self.archivo = ruta
        self._actualizar_titulo()

    def guardar(self) -> bool:
        return self._escribir(self.archivo) if self.archivo else self.guardar_como()

    def guardar_como(self) -> bool:
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar como", "nota.txt", "Texto (*.txt);;Markdown (*.md)")
        return self._escribir(Path(ruta)) if ruta else False

    def _escribir(self, ruta: Path) -> bool:
        try:
            ruta.write_text(self.texto.toPlainText(), encoding="utf-8")
        except OSError as exc:
            log.exception("No se pudo guardar %s", ruta)
            QMessageBox.critical(self, APP_NAME, f"No se pudo guardar:\n{exc}")
            return False
        self.archivo = ruta
        self.texto.document().setModified(False)
        self._actualizar_titulo()
        return True

    def _confirmar_cambios(self) -> bool:
        """True si se puede continuar (guardado, descartado o sin cambios)."""
        if not self.texto.document().isModified():
            return True
        caja = QMessageBox(self)
        caja.setIcon(QMessageBox.Icon.Warning)
        caja.setText("Hay cambios sin guardar.")
        caja.setInformativeText("¿Quieres guardarlos antes de continuar?")
        caja.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        caja.setDefaultButton(QMessageBox.StandardButton.Save)
        boton = caja.exec()
        if boton == QMessageBox.StandardButton.Save:
            return self.guardar()
        return boton == QMessageBox.StandardButton.Discard

    # ---- varios ---------------------------------------------------------------
    def zoom(self, delta: int) -> None:
        fuente = self.texto.font()
        fuente.setPointSize(max(8, min(48, fuente.pointSize() + delta)))
        self.texto.setFont(fuente)

    def _actualizar_titulo(self, *_args) -> None:
        nombre = self.archivo.name if self.archivo else "Sin título"
        self.setWindowTitle(f"{nombre}[*] — {APP_NAME}")   # [*] lo sustituye Qt si está modificado
        self.setWindowModified(self.texto.document().isModified())

    def _actualizar_estado(self) -> None:
        contenido = self.texto.toPlainText()
        self.estado.setText(f"{len(contenido.split())} palabras · {len(contenido)} caracteres")

    def acerca_de(self) -> None:
        QMessageBox.about(
            self, f"Acerca de {APP_NAME}",
            f"<b>{APP_NAME}</b> v{VERSION}<br>Ejemplo de app de escritorio con PySide6.")

    def closeEvent(self, evento) -> None:  # noqa: N802 (nombre impuesto por Qt)
        if not self._confirmar_cambios():
            evento.ignore()
            return
        self.config.update(
            width=self.width(), height=self.height(),
            font_size=self.texto.font().pointSize(),
            last_file=str(self.archivo) if self.archivo else None,
        )
        guardar_config(self.config)
        log.info("Cierre normal")
        evento.accept()


class Aplicacion(QApplication):
    """Recibe ficheros que el sistema envía a la app (QFileOpenEvent: solo macOS).

    En Windows y Linux los ficheros llegan como argumento de la línea de comandos (ver main).
    """

    def __init__(self, argv) -> None:
        super().__init__(argv)
        self.ventana: Ventana | None = None
        self._pendiente: Path | None = None

    def event(self, evento) -> bool:  # noqa: N802
        if evento.type() == QEvent.Type.FileOpen:
            ruta = Path(evento.file())
            if self.ventana is not None:
                self.ventana.cargar(ruta)
            else:
                self._pendiente = ruta        # llegó antes de crear la ventana
            return True
        return super().event(evento)


def main() -> None:
    configurar_logging()
    app = Aplicacion(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("")
    # El nombre del .desktop asocia la ventana con su icono y su entrada de menú (Wayland y X11)
    app.setDesktopFileName("notas-rapidas-pyside6")
    icono = resource_path("icono_256.png")
    if icono.is_file():
        app.setWindowIcon(QIcon(str(icono)))
    ventana = Ventana()
    app.ventana = ventana
    ventana.show()

    argumentos = [a for a in sys.argv[1:] if not a.startswith("-")]
    candidato = app._pendiente or (Path(argumentos[0]) if argumentos else None)
    if candidato and candidato.is_file():
        ventana.cargar(candidato)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

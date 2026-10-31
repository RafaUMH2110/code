#!/usr/bin/env python3
"""Notas Rápidas con PyObjC (AppKit directo) para macOS.

Solo funciona en macOS. Se puede ejecutar de dos formas:
  * Como script:  python notas_pyobjc.py
  * Como .app:    ./construir_app.sh  (py2app)  ->  dist/Notas Rápidas PyObjC.app

Conceptos que ilustra:
  - NSApplication, un NSObject como delegado y el bucle de eventos de Cocoa
  - Menú principal construido a mano, con la cadena de respondedores (undo:, copy:, paste:…)
  - NSWindow + NSScrollView + NSTextView (con deshacer integrado)
  - NSOpenPanel / NSSavePanel / NSAlert (diálogos nativos)
  - Documento modificado (setDocumentEdited_), restauración automática del marco
  - Abrir ficheros desde Finder (application:openFile:)
  - Configuración en ~/Library/Application Support y registro en ~/Library/Logs
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSAlertSecondButtonReturn,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSFont,
    NSMenu,
    NSMenuItem,
    NSOpenPanel,
    NSSavePanel,
    NSScrollView,
    NSTextField,
    NSTextView,
    NSViewHeightSizable,
    NSViewMaxYMargin,
    NSViewWidthSizable,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSMakeRect, NSObject
from PyObjCTools import AppHelper

APP_NAME = "Notas Rápidas"
APP_ID = "NotasRapidasPyObjC"
VERSION = "1.0.0"

SUPPORT_DIR = Path.home() / "Library" / "Application Support" / APP_ID
LOG_DIR = Path.home() / "Library" / "Logs" / APP_ID
CONFIG_FILE = SUPPORT_DIR / "config.json"
LOG_FILE = LOG_DIR / "app.log"
DEFAULT_CONFIG = {"font_size": 14, "last_file": None}
ALTO_ESTADO = 22

# Modificadores de teclas para los atajos del menú (valores de NSEventModifierFlags)
CMD = 1 << 20
SHIFT = 1 << 17

log = logging.getLogger(APP_ID)


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


def _item(menu: NSMenu, titulo: str, accion: str | None, tecla: str = "",
          modificadores: int = CMD, destino=None) -> NSMenuItem:
    """Añade una opción al menú. `accion` es el nombre del selector ('undo:', 'nuevo:'…).

    Con destino=None la acción viaja por la cadena de respondedores (ventana, vista de texto…).
    """
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(titulo, accion, tecla)
    if tecla:
        item.setKeyEquivalentModifierMask_(modificadores)
    if destino is not None:
        item.setTarget_(destino)
    menu.addItem_(item)
    return item


def _submenu(barra: NSMenu, titulo: str) -> NSMenu:
    """Crea un menú de primer nivel (Archivo, Edición…) y lo cuelga de la barra."""
    contenedor = NSMenuItem.alloc().init()
    menu = NSMenu.alloc().initWithTitle_(titulo)
    contenedor.setSubmenu_(menu)
    barra.addItem_(contenedor)
    return menu


class Delegado(NSObject):
    """Delegado de la aplicación, de la ventana y de la vista de texto."""

    # En PyObjC no se usa __init__: se inicializa con init() y se prepara aparte.
    def preparar(self) -> "Delegado":
        self.config = cargar_config()
        self.archivo = None            # Path | None
        self.sucio = False
        self.pendiente = None          # fichero que Finder pidió abrir antes de crear la ventana
        self.ventana = None
        self.texto = None
        self.estado = None
        self.tam_fuente = int(self.config["font_size"])
        return self

    # ---- ciclo de vida de la aplicación -----------------------------------
    def applicationDidFinishLaunching_(self, _notificacion):
        self._crear_menu()
        self._crear_ventana()

        ultimo = self.config.get("last_file")
        argumentos = [a for a in sys.argv[1:] if not a.startswith("-")]
        candidato = self.pendiente or (argumentos[0] if argumentos else ultimo)
        if candidato and Path(candidato).is_file():
            self._cargar(Path(candidato))
        self._refrescar()

        self.ventana.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def applicationShouldTerminateAfterLastWindowClosed_(self, _app):
        return True

    def applicationShouldTerminate_(self, _app):
        # Cmd+Q: 1 = NSTerminateNow, 0 = NSTerminateCancel
        return 1 if self._confirmar_cambios() else 0

    def applicationWillTerminate_(self, _notificacion):
        self.config.update(font_size=self.tam_fuente,
                           last_file=str(self.archivo) if self.archivo else None)
        guardar_config(self.config)
        log.info("Cierre normal")

    def application_openFile_(self, _app, nombre):
        """Finder abre la app con un fichero («Abrir con…», arrastrar al icono)."""
        if self.ventana is None:
            self.pendiente = nombre
            return True
        if self._confirmar_cambios():
            self._cargar(Path(nombre))
        return True

    # ---- ventana y vista de texto ------------------------------------------------
    def windowShouldClose_(self, _ventana):
        return bool(self._confirmar_cambios())

    def textDidChange_(self, _notificacion):
        self.sucio = True
        self._refrescar()

    # ---- construcción de la interfaz -----------------------------------------------
    @objc.python_method
    def _crear_menu(self) -> None:
        barra = NSMenu.alloc().init()

        app_menu = _submenu(barra, APP_NAME)
        _item(app_menu, f"Acerca de {APP_NAME}", "acercaDe:", destino=self)
        app_menu.addItem_(NSMenuItem.separatorItem())
        _item(app_menu, f"Ocultar {APP_NAME}", "hide:", "h")
        app_menu.addItem_(NSMenuItem.separatorItem())
        _item(app_menu, f"Salir de {APP_NAME}", "terminate:", "q")

        archivo = _submenu(barra, "Archivo")
        _item(archivo, "Nuevo", "nuevo:", "n", destino=self)
        _item(archivo, "Abrir…", "abrir:", "o", destino=self)
        archivo.addItem_(NSMenuItem.separatorItem())
        _item(archivo, "Guardar", "guardar:", "s", destino=self)
        _item(archivo, "Guardar como…", "guardarComo:", "s", CMD | SHIFT, destino=self)

        edicion = _submenu(barra, "Edición")
        _item(edicion, "Deshacer", "undo:", "z")           # los maneja NSTextView
        _item(edicion, "Rehacer", "redo:", "z", CMD | SHIFT)
        edicion.addItem_(NSMenuItem.separatorItem())
        _item(edicion, "Cortar", "cut:", "x")
        _item(edicion, "Copiar", "copy:", "c")
        _item(edicion, "Pegar", "paste:", "v")
        _item(edicion, "Seleccionar todo", "selectAll:", "a")

        ver = _submenu(barra, "Ver")
        _item(ver, "Aumentar letra", "masLetra:", "+", destino=self)
        _item(ver, "Reducir letra", "menosLetra:", "-", destino=self)

        ventana_menu = _submenu(barra, "Ventana")
        _item(ventana_menu, "Minimizar", "performMiniaturize:", "m")

        app = NSApplication.sharedApplication()
        app.setMainMenu_(barra)
        app.setWindowsMenu_(ventana_menu)

    @objc.python_method
    def _crear_ventana(self) -> None:
        mascara = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
                   | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        self.ventana = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 820, 560), mascara, NSBackingStoreBuffered, False)
        self.ventana.setReleasedWhenClosed_(False)
        self.ventana.setMinSize_((420, 280))
        self.ventana.setDelegate_(self)
        self.ventana.center()
        # Cocoa recuerda posición y tamaño entre ejecuciones con este nombre
        self.ventana.setFrameAutosaveName_(APP_ID)

        vista = self.ventana.contentView()
        ancho, alto = vista.bounds().size.width, vista.bounds().size.height

        # Barra de estado (abajo)
        self.estado = NSTextField.labelWithString_("")
        self.estado.setFrame_(NSMakeRect(8, 0, ancho - 16, ALTO_ESTADO))
        self.estado.setAutoresizingMask_(NSViewWidthSizable | NSViewMaxYMargin)
        vista.addSubview_(self.estado)

        # Área de texto con desplazamiento
        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, ALTO_ESTADO, ancho, alto - ALTO_ESTADO))
        scroll.setHasVerticalScroller_(True)
        scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        tamano = scroll.contentSize()

        self.texto = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, tamano.width, tamano.height))
        self.texto.setMinSize_((0, tamano.height))
        self.texto.setMaxSize_((1e7, 1e7))
        self.texto.setVerticallyResizable_(True)
        self.texto.setHorizontallyResizable_(False)
        self.texto.setAutoresizingMask_(NSViewWidthSizable)
        self.texto.textContainer().setWidthTracksTextView_(True)
        self.texto.setAllowsUndo_(True)
        self.texto.setRichText_(False)
        self.texto.setAutomaticQuoteSubstitutionEnabled_(False)
        self.texto.setTextContainerInset_((8, 8))
        self.texto.setDelegate_(self)
        self._aplicar_fuente()
        scroll.setDocumentView_(self.texto)
        vista.addSubview_(scroll)
        self.ventana.makeFirstResponder_(self.texto)

    # ---- acciones de menú (selectores: nombre con «_» = «:» en Objective-C) -------
    def nuevo_(self, _remitente):
        if not self._confirmar_cambios():
            return
        self.texto.setString_("")
        self.texto.undoManager().removeAllActions()
        self.archivo = None
        self.sucio = False
        self._refrescar()

    def abrir_(self, _remitente):
        if not self._confirmar_cambios():
            return
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        try:
            panel.setAllowedFileTypes_(["txt", "md"])   # obsoleto en macOS 12+, pero funciona
        except Exception:  # noqa: BLE001
            pass
        if panel.runModal() == 1:                        # 1 = NSModalResponseOK
            self._cargar(Path(panel.URL().path()))

    def guardar_(self, _remitente):
        self._guardar()

    def guardarComo_(self, _remitente):
        self._guardar_como()

    def masLetra_(self, _remitente):
        self._zoom(+1)

    def menosLetra_(self, _remitente):
        self._zoom(-1)

    def acercaDe_(self, _remitente):
        NSApplication.sharedApplication().orderFrontStandardAboutPanelWithOptions_({
            "ApplicationName": APP_NAME,
            "ApplicationVersion": VERSION,
            "Version": "",
        })

    # ---- lógica (métodos ocultos a Objective-C con python_method) -----------------
    @objc.python_method
    def _cargar(self, ruta: Path) -> None:
        try:
            contenido = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log.exception("No se pudo abrir %s", ruta)
            self._alerta("No se pudo abrir el archivo", str(exc))
            return
        self.texto.setString_(contenido)
        self.texto.undoManager().removeAllActions()
        self.archivo = ruta
        self.sucio = False
        self._refrescar()

    @objc.python_method
    def _guardar(self) -> bool:
        return self._escribir(self.archivo) if self.archivo else self._guardar_como()

    @objc.python_method
    def _guardar_como(self) -> bool:
        panel = NSSavePanel.savePanel()
        panel.setNameFieldStringValue_("nota.txt")
        if panel.runModal() != 1:
            return False
        return self._escribir(Path(panel.URL().path()))

    @objc.python_method
    def _escribir(self, ruta: Path) -> bool:
        try:
            ruta.write_text(str(self.texto.string()), encoding="utf-8")
        except OSError as exc:
            log.exception("No se pudo guardar %s", ruta)
            self._alerta("No se pudo guardar", str(exc))
            return False
        self.archivo = ruta
        self.sucio = False
        self._refrescar()
        return True

    @objc.python_method
    def _confirmar_cambios(self) -> bool:
        """True si se puede continuar (guardado, descartado o sin cambios)."""
        if not self.sucio:
            return True
        alerta = NSAlert.alloc().init()
        alerta.setMessageText_("Hay cambios sin guardar")
        alerta.setInformativeText_("¿Quieres guardarlos antes de continuar?")
        alerta.addButtonWithTitle_("Guardar")        # 1000
        alerta.addButtonWithTitle_("No guardar")     # 1001
        alerta.addButtonWithTitle_("Cancelar")       # 1002
        respuesta = alerta.runModal()
        if respuesta == NSAlertFirstButtonReturn:
            return self._guardar()
        if respuesta == NSAlertSecondButtonReturn:     # «No guardar»: descartar los cambios
            self.sucio = False
            return True
        return False

    @objc.python_method
    def _alerta(self, titulo: str, detalle: str) -> None:
        alerta = NSAlert.alloc().init()
        alerta.setMessageText_(titulo)
        alerta.setInformativeText_(detalle)
        alerta.runModal()

    @objc.python_method
    def _aplicar_fuente(self) -> None:
        self.texto.setFont_(NSFont.userFixedPitchFontOfSize_(self.tam_fuente))

    @objc.python_method
    def _zoom(self, delta: int) -> None:
        self.tam_fuente = max(8, min(48, self.tam_fuente + delta))
        self._aplicar_fuente()

    @objc.python_method
    def _refrescar(self) -> None:
        nombre = self.archivo.name if self.archivo else "Sin título"
        self.ventana.setTitle_(f"{nombre} — {APP_NAME}")
        self.ventana.setDocumentEdited_(self.sucio)       # punto de «modificado» en el botón rojo
        contenido = str(self.texto.string())
        self.estado.setStringValue_(
            f"{len(contenido.split())} palabras · {len(contenido)} caracteres")


def main() -> None:
    configurar_logging()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegado = Delegado.alloc().init().preparar()
    app.setDelegate_(delegado)         # la variable mantiene viva la referencia al delegado
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()

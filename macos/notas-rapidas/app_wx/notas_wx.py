#!/usr/bin/env python3
"""Notas Rápidas con wxPython (Phoenix) para macOS.

Se puede ejecutar de dos formas:
  * Como script:  python notas_wx.py
  * Como .app:    ./construir_app.sh  (py2app)  ->  dist/Notas Rápidas Wx.app

Conceptos que ilustra:
  - wx.App, wx.Frame y el bucle de eventos (MainLoop)
  - Menús con identificadores estándar (wx.ID_ABOUT, wx.ID_EXIT): wxWidgets los mueve
    solo al menú de la aplicación en macOS
  - Aceleradores «\\tCtrl+S»: en macOS «Ctrl» significa la tecla Cmd
  - Indicador de documento modificado (OSXSetModified) y confirmación al cerrar
  - Abrir ficheros desde Finder (MacOpenFiles)
  - Configuración en ~/Library/Application Support y registro en ~/Library/Logs
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import wx
import wx.adv

APP_NAME = "Notas Rápidas"
APP_ID = "NotasRapidasWx"
VERSION = "1.0.0"
IS_MAC = sys.platform == "darwin"

if IS_MAC:
    SUPPORT_DIR = Path.home() / "Library" / "Application Support" / APP_ID
    LOG_DIR = Path.home() / "Library" / "Logs" / APP_ID
else:  # solo para poder probar el script fuera de macOS
    SUPPORT_DIR = Path.home() / ".config" / APP_ID
    LOG_DIR = Path.home() / ".cache" / APP_ID

CONFIG_FILE = SUPPORT_DIR / "config.json"
LOG_FILE = LOG_DIR / "app.log"
DEFAULT_CONFIG = {"width": 820, "height": 560, "font_size": 14, "last_file": None}

# Identificadores propios para las acciones que no tienen uno estándar
ID_ZOOM_MAS = wx.ID_HIGHEST + 1
ID_ZOOM_MENOS = wx.ID_HIGHEST + 2

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


class Marco(wx.Frame):
    def __init__(self) -> None:
        self.config = cargar_config()
        super().__init__(None, title=APP_NAME,
                         size=(self.config["width"], self.config["height"]))
        self.SetMinSize((420, 280))
        self.archivo: Path | None = None
        self.tam_fuente: int = int(self.config["font_size"])

        self.texto = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.BORDER_NONE)
        self._aplicar_fuente()
        self.CreateStatusBar()

        self._crear_menus()
        self.texto.Bind(wx.EVT_TEXT, self._al_cambiar_texto)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)
        self.Centre()

        ultimo = self.config.get("last_file")
        if ultimo and Path(ultimo).is_file():
            self.cargar(Path(ultimo))
        self._refrescar()

    # ---- menús ------------------------------------------------------------
    def _crear_menus(self) -> None:
        archivo = wx.Menu()
        archivo.Append(wx.ID_NEW, "Nuevo\tCtrl+N")
        archivo.Append(wx.ID_OPEN, "Abrir…\tCtrl+O")
        archivo.AppendSeparator()
        archivo.Append(wx.ID_SAVE, "Guardar\tCtrl+S")
        archivo.Append(wx.ID_SAVEAS, "Guardar como…\tCtrl+Shift+S")
        archivo.AppendSeparator()
        archivo.Append(wx.ID_EXIT, "Salir\tCtrl+Q")      # en macOS pasa al menú de la app

        edicion = wx.Menu()
        edicion.Append(wx.ID_UNDO, "Deshacer\tCtrl+Z")
        edicion.Append(wx.ID_REDO, "Rehacer\tCtrl+Shift+Z")
        edicion.AppendSeparator()
        edicion.Append(wx.ID_CUT, "Cortar\tCtrl+X")
        edicion.Append(wx.ID_COPY, "Copiar\tCtrl+C")
        edicion.Append(wx.ID_PASTE, "Pegar\tCtrl+V")
        edicion.Append(wx.ID_SELECTALL, "Seleccionar todo\tCtrl+A")

        ver = wx.Menu()
        ver.Append(ID_ZOOM_MAS, "Aumentar letra\tCtrl++")
        ver.Append(ID_ZOOM_MENOS, "Reducir letra\tCtrl+-")

        ayuda = wx.Menu()
        ayuda.Append(wx.ID_ABOUT, "Acerca de…")           # en macOS pasa al menú de la app

        barra = wx.MenuBar()
        barra.Append(archivo, "Archivo")
        barra.Append(edicion, "Edición")
        barra.Append(ver, "Ver")
        barra.Append(ayuda, "Ayuda")
        self.SetMenuBar(barra)

        enlaces = {
            wx.ID_NEW: self.nuevo, wx.ID_OPEN: self.abrir,
            wx.ID_SAVE: self.guardar, wx.ID_SAVEAS: self.guardar_como,
            wx.ID_EXIT: lambda _e: self.Close(),
            wx.ID_UNDO: lambda _e: self.texto.Undo(), wx.ID_REDO: lambda _e: self.texto.Redo(),
            wx.ID_CUT: lambda _e: self.texto.Cut(), wx.ID_COPY: lambda _e: self.texto.Copy(),
            wx.ID_PASTE: lambda _e: self.texto.Paste(),
            wx.ID_SELECTALL: lambda _e: self.texto.SelectAll(),
            ID_ZOOM_MAS: lambda _e: self.zoom(+1), ID_ZOOM_MENOS: lambda _e: self.zoom(-1),
            wx.ID_ABOUT: self.acerca_de,
        }
        for ident, funcion in enlaces.items():
            self.Bind(wx.EVT_MENU, funcion, id=ident)

    # ---- archivo ------------------------------------------------------------
    def nuevo(self, _evento=None) -> None:
        if not self._confirmar_cambios():
            return
        self.texto.ChangeValue("")
        self.texto.DiscardEdits()
        self.archivo = None
        self._refrescar()

    def abrir(self, _evento=None) -> None:
        if not self._confirmar_cambios():
            return
        with wx.FileDialog(self, "Abrir", wildcard="Texto (*.txt;*.md)|*.txt;*.md|Todos|*",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK:
                self.cargar(Path(dialogo.GetPath()))

    def cargar(self, ruta: Path) -> None:
        try:
            contenido = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log.exception("No se pudo abrir %s", ruta)
            wx.MessageBox(f"No se pudo abrir el archivo:\n{exc}", APP_NAME, wx.ICON_ERROR, self)
            return
        self.texto.ChangeValue(contenido)      # ChangeValue no dispara EVT_TEXT
        self.texto.DiscardEdits()
        self.archivo = ruta
        self._refrescar()

    def guardar(self, _evento=None) -> bool:
        return self._escribir(self.archivo) if self.archivo else self.guardar_como()

    def guardar_como(self, _evento=None) -> bool:
        with wx.FileDialog(self, "Guardar como", defaultFile="nota.txt",
                           wildcard="Texto (*.txt)|*.txt|Markdown (*.md)|*.md",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return False
            return self._escribir(Path(dialogo.GetPath()))

    def _escribir(self, ruta: Path) -> bool:
        try:
            ruta.write_text(self.texto.GetValue(), encoding="utf-8")
        except OSError as exc:
            log.exception("No se pudo guardar %s", ruta)
            wx.MessageBox(f"No se pudo guardar:\n{exc}", APP_NAME, wx.ICON_ERROR, self)
            return False
        self.archivo = ruta
        self.texto.DiscardEdits()
        self._refrescar()
        return True

    def _confirmar_cambios(self) -> bool:
        """True si se puede continuar (guardado, descartado o sin cambios)."""
        if not self.texto.IsModified():
            return True
        resp = wx.MessageBox("Hay cambios sin guardar. ¿Quieres guardarlos?", APP_NAME,
                             wx.YES_NO | wx.CANCEL | wx.ICON_WARNING, self)
        if resp == wx.CANCEL:
            return False
        return self.guardar() if resp == wx.YES else True

    # ---- varios ---------------------------------------------------------------
    def _aplicar_fuente(self) -> None:
        fuente = wx.Font(self.tam_fuente, wx.FONTFAMILY_TELETYPE,
                         wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.texto.SetFont(fuente)

    def zoom(self, delta: int) -> None:
        self.tam_fuente = max(8, min(48, self.tam_fuente + delta))
        self._aplicar_fuente()

    def _al_cambiar_texto(self, _evento) -> None:
        self._refrescar()

    def _refrescar(self) -> None:
        modificado = self.texto.IsModified()
        nombre = self.archivo.name if self.archivo else "Sin título"
        self.SetTitle(f"{'• ' if modificado else ''}{nombre} — {APP_NAME}")
        if hasattr(self, "OSXSetModified"):       # punto de «modificado» en macOS
            self.OSXSetModified(modificado)
        contenido = self.texto.GetValue()
        self.SetStatusText(f"{len(contenido.split())} palabras · {len(contenido)} caracteres")

    def acerca_de(self, _evento=None) -> None:
        info = wx.adv.AboutDialogInfo()
        info.SetName(APP_NAME)
        info.SetVersion(VERSION)
        info.SetDescription("Ejemplo de app de escritorio con wxPython.")
        wx.adv.AboutBox(info)

    def _al_cerrar(self, evento: wx.CloseEvent) -> None:
        if evento.CanVeto() and not self._confirmar_cambios():
            evento.Veto()
            return
        ancho, alto = self.GetSize()
        self.config.update(
            width=ancho, height=alto, font_size=self.tam_fuente,
            last_file=str(self.archivo) if self.archivo else None,
        )
        guardar_config(self.config)
        log.info("Cierre normal")
        evento.Skip()      # continúa el cierre normal de la ventana


class Aplicacion(wx.App):
    def OnInit(self) -> bool:  # noqa: N802 (nombre impuesto por wxPython)
        self.SetAppName(APP_NAME)
        self.marco = Marco()
        self.marco.Show()
        argumentos = [a for a in sys.argv[1:] if not a.startswith("-")]
        if argumentos and Path(argumentos[0]).is_file():
            self.marco.cargar(Path(argumentos[0]))
        return True

    def MacOpenFiles(self, nombres) -> None:  # noqa: N802
        """Finder abre la app con ficheros («Abrir con…», arrastrar al icono)."""
        if nombres and self.marco._confirmar_cambios():
            self.marco.cargar(Path(nombres[0]))


def main() -> None:
    configurar_logging()
    app = Aplicacion(False)
    app.MainLoop()


if __name__ == "__main__":
    main()

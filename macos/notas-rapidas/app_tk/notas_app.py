#!/usr/bin/env python3
"""Notas Rápidas: ejemplo de aplicación de escritorio para macOS con Tkinter.

Se puede ejecutar de dos formas:
  * Como script:      python3 notas_app.py
  * Como app (.app):  empaquetada con py2app (ver setup.py / construir_app.sh)

Conceptos que ilustra:
  - Bucle de eventos de Tkinter y estructura de una clase de aplicación
  - Integración con el menú nativo de macOS (Acerca de, Cmd+Q, abrir desde Finder)
  - Atajos con la tecla Cmd
  - Configuración persistente en ~/Library/Application Support
  - Registro (log) en ~/Library/Logs
  - Localización de recursos dentro del bundle .app
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from tkinter import font as tkfont

# --------------------------------------------------------------------------
# Constantes y rutas
# --------------------------------------------------------------------------
APP_NAME = "Notas Rápidas"
APP_ID = "NotasRapidas"          # nombre de carpeta (sin espacios ni acentos)
VERSION = "1.0.0"

IS_MAC = sys.platform == "darwin"
MOD = "Command" if IS_MAC else "Control"   # tecla modificadora de los atajos

SUPPORT_DIR = Path.home() / "Library" / "Application Support" / APP_ID
LOG_DIR = Path.home() / "Library" / "Logs" / APP_ID
if not IS_MAC:  # para poder probar el script en Linux sin ensuciar rutas macOS
    SUPPORT_DIR = Path.home() / ".config" / APP_ID
    LOG_DIR = Path.home() / ".cache" / APP_ID

CONFIG_FILE = SUPPORT_DIR / "config.json"
LOG_FILE = LOG_DIR / "app.log"

DEFAULT_CONFIG = {
    "geometry": "820x560+120+120",
    "font_size": 14,
    "last_file": None,
}

log = logging.getLogger(APP_ID)


def resource_path(relative: str) -> Path:
    """Ruta a un recurso empaquetado.

    Dentro de un .app creado con py2app, los recursos viven en
    Contents/Resources y py2app define la variable RESOURCEPATH.
    Al ejecutar como script, se busca junto al fichero .py.
    """
    base = os.environ.get("RESOURCEPATH") or Path(__file__).resolve().parent
    return Path(base) / relative


def configurar_logging() -> None:
    """Un .app no tiene terminal: sin fichero de log no sabrías qué falla."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    def hook(tipo, valor, tb):
        log.critical("Excepción no controlada", exc_info=(tipo, valor, tb))

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


# --------------------------------------------------------------------------
# Aplicación
# --------------------------------------------------------------------------
class NotasApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.config = cargar_config()
        self.archivo: Path | None = None

        root.geometry(self.config["geometry"])
        root.minsize(420, 280)

        self.fuente = tkfont.Font(
            family="Menlo" if IS_MAC else "Courier", size=self.config["font_size"]
        )

        self._crear_menus()
        self._crear_widgets()
        self._crear_atajos()
        self._integrar_macos()

        root.protocol("WM_DELETE_WINDOW", self.salir)
        root.report_callback_exception = self._excepcion_tk

        # Reabrir el último fichero si existe
        ultimo = self.config.get("last_file")
        if ultimo and Path(ultimo).is_file():
            self._cargar(Path(ultimo))
        self._refrescar()

    # ---- construcción de la interfaz ------------------------------------
    def _crear_menus(self) -> None:
        barra = tk.Menu(self.root)

        archivo = tk.Menu(barra, tearoff=False)
        archivo.add_command(label="Nuevo", accelerator=f"{MOD}-N", command=self.nuevo)
        archivo.add_command(label="Abrir…", accelerator=f"{MOD}-O", command=self.abrir)
        archivo.add_separator()
        archivo.add_command(label="Guardar", accelerator=f"{MOD}-S", command=self.guardar)
        archivo.add_command(label="Guardar como…", command=self.guardar_como)
        barra.add_cascade(label="Archivo", menu=archivo)

        edicion = tk.Menu(barra, tearoff=False)
        edicion.add_command(label="Deshacer", accelerator=f"{MOD}-Z",
                            command=lambda: self.texto.event_generate("<<Undo>>"))
        edicion.add_command(label="Rehacer", accelerator=f"{MOD}-Shift-Z",
                            command=lambda: self.texto.event_generate("<<Redo>>"))
        edicion.add_separator()
        edicion.add_command(label="Cortar", accelerator=f"{MOD}-X",
                            command=lambda: self.texto.event_generate("<<Cut>>"))
        edicion.add_command(label="Copiar", accelerator=f"{MOD}-C",
                            command=lambda: self.texto.event_generate("<<Copy>>"))
        edicion.add_command(label="Pegar", accelerator=f"{MOD}-V",
                            command=lambda: self.texto.event_generate("<<Paste>>"))
        barra.add_cascade(label="Edición", menu=edicion)

        ver = tk.Menu(barra, tearoff=False)
        ver.add_command(label="Aumentar letra", accelerator=f"{MOD}-+",
                        command=lambda: self.zoom(+1))
        ver.add_command(label="Reducir letra", accelerator=f"{MOD}--",
                        command=lambda: self.zoom(-1))
        barra.add_cascade(label="Ver", menu=ver)

        self.root.config(menu=barra)

    def _crear_widgets(self) -> None:
        marco = tk.Frame(self.root)
        marco.pack(fill="both", expand=True)

        scroll = tk.Scrollbar(marco)
        scroll.pack(side="right", fill="y")

        self.texto = tk.Text(
            marco, wrap="word", undo=True, font=self.fuente,
            yscrollcommand=scroll.set, padx=10, pady=8, borderwidth=0,
        )
        self.texto.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.texto.yview)

        self.estado = tk.Label(self.root, anchor="w", padx=8)
        self.estado.pack(fill="x", side="bottom")

        self.texto.bind("<<Modified>>", lambda _e: self._refrescar())
        self.texto.bind("<KeyRelease>", lambda _e: self._refrescar())
        self.texto.focus_set()

    def _crear_atajos(self) -> None:
        r = self.root
        r.bind(f"<{MOD}-n>", lambda _e: self.nuevo())
        r.bind(f"<{MOD}-o>", lambda _e: self.abrir())
        r.bind(f"<{MOD}-s>", lambda _e: self.guardar())
        r.bind(f"<{MOD}-plus>", lambda _e: self.zoom(+1))
        r.bind(f"<{MOD}-equal>", lambda _e: self.zoom(+1))
        r.bind(f"<{MOD}-minus>", lambda _e: self.zoom(-1))

    def _integrar_macos(self) -> None:
        """Comandos Tcl especiales que Tk enlaza con el menú de aplicación."""
        self.root.createcommand("tkAboutDialog", self.acerca_de)          # «Acerca de…»
        self.root.createcommand("::tk::mac::Quit", self.salir)            # Cmd+Q
        self.root.createcommand("::tk::mac::OpenDocument", self._abrir_desde_finder)

    # ---- acciones de archivo --------------------------------------------
    def nuevo(self) -> None:
        if not self._confirmar_cambios():
            return
        self.texto.delete("1.0", "end")
        self.texto.edit_reset()
        self.texto.edit_modified(False)
        self.archivo = None
        self._refrescar()

    def abrir(self) -> None:
        if not self._confirmar_cambios():
            return
        ruta = filedialog.askopenfilename(
            title="Abrir",
            filetypes=[("Texto", "*.txt *.md"), ("Todos los archivos", "*.*")],
        )
        if ruta:
            self._cargar(Path(ruta))

    def _abrir_desde_finder(self, *rutas: str) -> None:
        """Se invoca al arrastrar un fichero sobre el icono o abrirlo con la app."""
        if rutas and self._confirmar_cambios():
            self._cargar(Path(rutas[0]))

    def _cargar(self, ruta: Path) -> None:
        try:
            contenido = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log.exception("No se pudo abrir %s", ruta)
            messagebox.showerror(APP_NAME, f"No se pudo abrir el archivo:\n{exc}")
            return
        self.texto.delete("1.0", "end")
        self.texto.insert("1.0", contenido)
        self.texto.edit_reset()
        self.texto.edit_modified(False)
        self.archivo = ruta
        self._refrescar()

    def guardar(self) -> bool:
        return self._escribir(self.archivo) if self.archivo else self.guardar_como()

    def guardar_como(self) -> bool:
        ruta = filedialog.asksaveasfilename(
            title="Guardar como", defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Markdown", "*.md")],
        )
        return self._escribir(Path(ruta)) if ruta else False

    def _escribir(self, ruta: Path) -> bool:
        try:
            ruta.write_text(self.texto.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as exc:
            log.exception("No se pudo guardar %s", ruta)
            messagebox.showerror(APP_NAME, f"No se pudo guardar:\n{exc}")
            return False
        self.archivo = ruta
        self.texto.edit_modified(False)
        self._refrescar()
        return True

    def _confirmar_cambios(self) -> bool:
        """True si se puede continuar (guardado, descartado o sin cambios)."""
        if not self.texto.edit_modified():
            return True
        resp = messagebox.askyesnocancel(
            APP_NAME, "Hay cambios sin guardar. ¿Quieres guardarlos?"
        )
        if resp is None:
            return False
        return self.guardar() if resp else True

    # ---- varios ----------------------------------------------------------
    def zoom(self, delta: int) -> None:
        tamano = max(8, min(48, self.fuente.cget("size") + delta))
        self.fuente.configure(size=tamano)

    def _refrescar(self) -> None:
        modificado = self.texto.edit_modified()
        nombre = self.archivo.name if self.archivo else "Sin título"
        self.root.title(f"{'• ' if modificado else ''}{nombre} — {APP_NAME}")
        contenido = self.texto.get("1.0", "end-1c")
        palabras = len(contenido.split())
        self.estado.config(
            text=f"{palabras} palabras · {len(contenido)} caracteres"
        )

    def acerca_de(self) -> None:
        messagebox.showinfo(
            f"Acerca de {APP_NAME}",
            f"{APP_NAME} v{VERSION}\nEjemplo de app de escritorio en Python.",
        )

    def _excepcion_tk(self, tipo, valor, tb) -> None:
        log.critical("Excepción en callback de Tk", exc_info=(tipo, valor, tb))
        messagebox.showerror(APP_NAME, f"Error inesperado:\n{valor}")

    def salir(self) -> None:
        if not self._confirmar_cambios():
            return
        self.config.update(
            geometry=self.root.geometry(),
            font_size=self.fuente.cget("size"),
            last_file=str(self.archivo) if self.archivo else None,
        )
        guardar_config(self.config)
        log.info("Cierre normal")
        self.root.destroy()


def main() -> None:
    configurar_logging()
    root = tk.Tk()
    root.title(APP_NAME)
    app = NotasApp(root)

    # Fichero pasado por línea de comandos (ignorando -psn_… de macOS antiguo)
    args = [a for a in sys.argv[1:] if not a.startswith("-psn")]
    if args and Path(args[0]).is_file():
        app._cargar(Path(args[0]))

    root.mainloop()


if __name__ == "__main__":
    main()

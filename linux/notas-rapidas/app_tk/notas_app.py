#!/usr/bin/env python3
"""Notas Rápidas: ejemplo de aplicación de escritorio para Linux con Tkinter.

Pensada para Debian, Ubuntu y Linux Mint. Se puede ejecutar de varias formas:
  * Como script:          python3 notas_app.py
  * Instalada (.deb):     sudo apt install ./notas-rapidas_1.0.0_all.deb
  * Binario PyInstaller:  ./construir_app.sh  ->  dist/notas-rapidas/notas-rapidas

Conceptos que ilustra:
  - Bucle de eventos de Tkinter y estructura de una clase de aplicación
  - Atajos con Ctrl y menú de la aplicación
  - Rutas XDG: configuración en ~/.config, registro en ~/.local/state
  - Icono de ventana (iconphoto) y clase WM_CLASS para agrupar en el dock
  - Localización de recursos tanto en script como dentro de PyInstaller
  - Abrir un fichero pasado como argumento («Abrir con…»)
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
APP_ID = "notas-rapidas"         # nombre de carpeta y de paquete (minúsculas y guiones)
WM_CLASS = "NotasRapidas"        # debe coincidir con StartupWMClass del fichero .desktop
VERSION = "1.0.0"
MOD = "Control"


def _xdg(variable: str, por_defecto: str) -> Path:
    """Carpetas de usuario según la especificación XDG (con valores por defecto)."""
    return Path(os.environ.get(variable) or Path.home() / por_defecto)


SUPPORT_DIR = _xdg("XDG_CONFIG_HOME", ".config") / APP_ID        # configuración
LOG_DIR = _xdg("XDG_STATE_HOME", ".local/state") / APP_ID        # registros
CONFIG_FILE = SUPPORT_DIR / "config.json"
LOG_FILE = LOG_DIR / "app.log"

DEFAULT_CONFIG = {
    "geometry": "820x560+120+120",
    "font_size": 12,
    "last_file": None,
}

log = logging.getLogger(APP_ID)


def resource_path(relative: str) -> Path:
    """Ruta a un recurso empaquetado.

    Con PyInstaller, los recursos están en sys._MEIPASS. Como script (o instalada
    por el .deb en /opt/notas-rapidas) se busca junto al fichero .py.
    """
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return Path(base) / relative


def configurar_logging() -> None:
    """Una app lanzada desde el menú no tiene terminal: sin log no sabrías qué falla."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
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
        self._poner_icono()

        # Fuente monoespaciada del sistema (DejaVu Sans Mono en Debian/Ubuntu/Mint)
        familia = tkfont.nametofont("TkFixedFont").actual("family")
        self.fuente = tkfont.Font(family=familia, size=self.config["font_size"])

        self._crear_menus()
        self._crear_widgets()
        self._crear_atajos()

        root.protocol("WM_DELETE_WINDOW", self.salir)
        root.report_callback_exception = self._excepcion_tk

        # Reabrir el último fichero si existe
        ultimo = self.config.get("last_file")
        if ultimo and Path(ultimo).is_file():
            self._cargar(Path(ultimo))
        self._refrescar()

    # ---- construcción de la interfaz ------------------------------------
    def _poner_icono(self) -> None:
        """Icono de la ventana (el del menú lo da el fichero .desktop)."""
        png = resource_path("icono.png")
        if png.is_file():
            try:
                self._icono = tk.PhotoImage(file=str(png))   # guardar referencia
                self.root.iconphoto(True, self._icono)
            except tk.TclError:
                log.warning("No se pudo cargar el icono %s", png)

    def _crear_menus(self) -> None:
        barra = tk.Menu(self.root)

        archivo = tk.Menu(barra, tearoff=False)
        archivo.add_command(label="Nuevo", accelerator="Ctrl+N", command=self.nuevo)
        archivo.add_command(label="Abrir…", accelerator="Ctrl+O", command=self.abrir)
        archivo.add_separator()
        archivo.add_command(label="Guardar", accelerator="Ctrl+S", command=self.guardar)
        archivo.add_command(label="Guardar como…", command=self.guardar_como)
        archivo.add_separator()
        archivo.add_command(label="Salir", accelerator="Ctrl+Q", command=self.salir)
        barra.add_cascade(label="Archivo", menu=archivo)

        edicion = tk.Menu(barra, tearoff=False)
        edicion.add_command(label="Deshacer", accelerator="Ctrl+Z",
                            command=lambda: self.texto.event_generate("<<Undo>>"))
        edicion.add_command(label="Rehacer", accelerator="Ctrl+Y",
                            command=lambda: self.texto.event_generate("<<Redo>>"))
        edicion.add_separator()
        edicion.add_command(label="Cortar", accelerator="Ctrl+X",
                            command=lambda: self.texto.event_generate("<<Cut>>"))
        edicion.add_command(label="Copiar", accelerator="Ctrl+C",
                            command=lambda: self.texto.event_generate("<<Copy>>"))
        edicion.add_command(label="Pegar", accelerator="Ctrl+V",
                            command=lambda: self.texto.event_generate("<<Paste>>"))
        barra.add_cascade(label="Edición", menu=edicion)

        ver = tk.Menu(barra, tearoff=False)
        ver.add_command(label="Aumentar letra", accelerator="Ctrl++",
                        command=lambda: self.zoom(+1))
        ver.add_command(label="Reducir letra", accelerator="Ctrl+-",
                        command=lambda: self.zoom(-1))
        barra.add_cascade(label="Ver", menu=ver)

        ayuda = tk.Menu(barra, tearoff=False)
        ayuda.add_command(label="Acerca de…", command=self.acerca_de)
        barra.add_cascade(label="Ayuda", menu=ayuda)

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
        # En Tk/X11 el «rehacer» estándar es Ctrl+Shift+Z; añadimos también Ctrl+Y
        self.texto.bind("<Control-y>", self._rehacer)
        self.texto.focus_set()

    def _rehacer(self, _e=None) -> str:
        self.texto.event_generate("<<Redo>>")
        return "break"

    def _crear_atajos(self) -> None:
        r = self.root
        r.bind(f"<{MOD}-n>", lambda _e: self.nuevo())
        r.bind(f"<{MOD}-o>", lambda _e: self.abrir())
        r.bind(f"<{MOD}-s>", lambda _e: self.guardar())
        r.bind(f"<{MOD}-q>", lambda _e: self.salir())
        r.bind(f"<{MOD}-plus>", lambda _e: self.zoom(+1))
        r.bind(f"<{MOD}-equal>", lambda _e: self.zoom(+1))
        r.bind(f"<{MOD}-minus>", lambda _e: self.zoom(-1))

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
            filetypes=[("Texto", "*.txt *.md"), ("Todos los archivos", "*")],
        )
        if ruta:
            self._cargar(Path(ruta))

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
    # Necesario si algún día usas multiprocessing dentro de un binario PyInstaller
    import multiprocessing
    multiprocessing.freeze_support()

    configurar_logging()
    # className fija WM_CLASS: el dock/escritorio lo usa para asociar la ventana al .desktop
    root = tk.Tk(className=WM_CLASS)
    root.title(APP_NAME)
    app = NotasApp(root)

    # «Abrir con…» o `notas-rapidas fichero.txt`: llega como argumento
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        app._cargar(Path(sys.argv[1]))

    root.mainloop()


if __name__ == "__main__":
    main()

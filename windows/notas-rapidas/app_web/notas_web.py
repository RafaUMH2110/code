#!/usr/bin/env python3
"""Notas Rápidas (variante pywebview) para Windows.

Interfaz en HTML/CSS/JS (carpeta ui/) dentro de una ventana nativa que usa
Microsoft Edge WebView2. Python actúa de «backend»: ficheros, configuración y diálogos.

Ejecución:
  pip install pywebview
  py notas_web.py            # normal
  py notas_web.py --debug    # con inspector web (clic derecho > Inspeccionar)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import webview

APP_NAME = "Notas Rápidas"
APP_ID = "NotasRapidasWeb"
VERSION = "1.0.0"
IS_WIN = sys.platform == "win32"


def _carpeta(variable: str, por_defecto: str) -> Path:
    return Path(os.environ.get(variable) or Path.home() / por_defecto)


if IS_WIN:
    SUPPORT_DIR = _carpeta("APPDATA", "AppData/Roaming") / APP_ID
    LOG_DIR = _carpeta("LOCALAPPDATA", "AppData/Local") / APP_ID / "Logs"
else:  # solo para poder probar el script fuera de Windows
    SUPPORT_DIR = Path.home() / ".config" / APP_ID
    LOG_DIR = Path.home() / ".cache" / APP_ID

CONFIG_FILE = SUPPORT_DIR / "config.json"
LOG_FILE = LOG_DIR / "app.log"
DEFAULT_CONFIG = {"width": 900, "height": 620, "font_size": 16, "last_file": None}

# pywebview >= 5 usa webview.FileDialog.*; las versiones antiguas, webview.OPEN_DIALOG
_FD = getattr(webview, "FileDialog", None)
DIALOGO_ABRIR = getattr(_FD, "OPEN", None) or getattr(webview, "OPEN_DIALOG", None)
DIALOGO_GUARDAR = getattr(_FD, "SAVE", None) or getattr(webview, "SAVE_DIALOG", None)

log = logging.getLogger(APP_ID)


def resource_path(relative: str) -> Path:
    """Con PyInstaller los recursos están en sys._MEIPASS."""
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return Path(base) / relative


def configurar_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8",
    )
    sys.excepthook = lambda t, v, tb: log.critical("Excepción", exc_info=(t, v, tb))
    log.info("Arranque %s v%s", APP_NAME, VERSION)


def _primera_ruta(resultado) -> Path | None:
    """Los diálogos devuelven None, una cadena o una tupla según versión/modo."""
    if not resultado:
        return None
    return Path(resultado if isinstance(resultado, str) else resultado[0])


class Api:
    """Métodos públicos = funciones invocables desde JS (pywebview.api.*).

    IMPORTANTE: pywebview inspecciona los atributos públicos del objeto.
    Todo lo que no deba exponerse (ventana, estado interno) lleva guion bajo.
    """

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._config = dict(DEFAULT_CONFIG)
        try:
            self._config.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError):
            log.exception("Config ilegible; se usan valores por defecto")

    # ---- configuración ---------------------------------------------------
    def iniciar(self) -> dict:
        """Lo llama JS al arrancar: config y, si procede, el fichero a abrir."""
        datos = {"config": self._config, "version": VERSION, "archivo": None}
        # «Abrir con…» pasa la ruta como argumento; si no, se reabre el último fichero
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        candidato = args[0] if args and Path(args[0]).is_file() else self._config.get("last_file")
        if candidato and Path(candidato).is_file():
            datos["archivo"] = self._leer(Path(candidato))
        return datos

    def guardar_ajustes(self, font_size: int) -> None:
        self._config["font_size"] = int(font_size)

    # ---- ficheros --------------------------------------------------------
    def abrir(self) -> dict | None:
        ruta = _primera_ruta(self._window.create_file_dialog(
            DIALOGO_ABRIR, file_types=("Texto (*.txt;*.md)", "Todos (*.*)")))
        return self._leer(ruta) if ruta else None

    def guardar(self, contenido: str, ruta: str | None) -> dict | None:
        if not ruta:
            return self.guardar_como(contenido)
        return self._escribir(Path(ruta), contenido)

    def guardar_como(self, contenido: str) -> dict | None:
        ruta = _primera_ruta(self._window.create_file_dialog(
            DIALOGO_GUARDAR, save_filename="nota.txt"))
        return self._escribir(ruta, contenido) if ruta else None

    def poner_titulo(self, titulo: str) -> None:
        self._window.set_title(titulo)

    # ---- internos (no expuestos: nombres con guion bajo) -----------------
    def _leer(self, ruta: Path) -> dict | None:
        try:
            texto = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log.exception("No se pudo abrir %s", ruta)
            return {"error": f"No se pudo abrir el archivo: {exc}"}
        self._config["last_file"] = str(ruta)
        return {"ruta": str(ruta), "nombre": ruta.name, "contenido": texto}

    def _escribir(self, ruta: Path, contenido: str) -> dict:
        try:
            ruta.write_text(contenido, encoding="utf-8")
        except OSError as exc:
            log.exception("No se pudo guardar %s", ruta)
            return {"error": f"No se pudo guardar: {exc}"}
        self._config["last_file"] = str(ruta)
        return {"ruta": str(ruta), "nombre": ruta.name}

    def _al_cerrar(self):
        """Evento 'closing': devolver False cancela el cierre."""
        try:
            sucio = bool(self._window.evaluate_js("window.hayCambios()"))
        except Exception:  # noqa: BLE001
            sucio = False
        if sucio and not self._window.create_confirmation_dialog(
                APP_NAME, "Hay cambios sin guardar. ¿Cerrar igualmente?"):
            return False
        try:
            self._config.update(width=self._window.width, height=self._window.height)
            SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(self._config, indent=2), encoding="utf-8")
        except OSError:
            log.exception("No se pudo guardar la configuración")
        log.info("Cierre normal")
        return None


def main() -> None:
    import multiprocessing
    multiprocessing.freeze_support()

    configurar_logging()
    api = Api()
    ventana = webview.create_window(
        APP_NAME,
        url=str(resource_path("ui/index.html")),
        js_api=api,
        width=api._config["width"],
        height=api._config["height"],
        min_size=(420, 300),
    )
    api._window = ventana
    ventana.events.closing += api._al_cerrar
    # En Windows el motor por defecto es Edge WebView2 (gui="edgechromium")
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()

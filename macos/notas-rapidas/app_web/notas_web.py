#!/usr/bin/env python3
"""Notas Rápidas (variante pywebview).

Interfaz en HTML/CSS/JS (carpeta ui/) dentro de una ventana nativa de macOS
(WKWebView). Python actúa de «backend»: ficheros, configuración y diálogos.

Ejecución:
  pip install pywebview
  python3 notas_web.py            # normal
  python3 notas_web.py --debug    # con inspector web (clic derecho > Inspeccionar)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path

import webview

APP_NAME = "Notas Rápidas"
APP_ID = "NotasRapidasWeb"
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
DEFAULT_CONFIG = {"width": 900, "height": 620, "font_size": 16, "last_file": None}

# pywebview >= 5 usa webview.FileDialog.*; las versiones antiguas, webview.OPEN_DIALOG
_FD = getattr(webview, "FileDialog", None)
DIALOGO_ABRIR = getattr(_FD, "OPEN", None) or getattr(webview, "OPEN_DIALOG", None)
DIALOGO_GUARDAR = getattr(_FD, "SAVE", None) or getattr(webview, "SAVE_DIALOG", None)

log = logging.getLogger(APP_ID)


def resource_path(relative: str) -> Path:
    """Dentro del .app (py2app) los recursos están en RESOURCEPATH."""
    base = os.environ.get("RESOURCEPATH") or Path(__file__).resolve().parent
    return Path(base) / relative


def configurar_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
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
        self._sucio = False               # ¿hay cambios sin guardar? (lo actualiza JS)
        self._preguntando = False         # diálogo de cierre abierto
        self._cierre_confirmado = False   # el usuario aceptó cerrar sin guardar
        self._config = dict(DEFAULT_CONFIG)
        try:
            self._config.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError):
            log.exception("Config ilegible; se usan valores por defecto")

    # ---- configuración ---------------------------------------------------
    def iniciar(self) -> dict:
        """Lo llama JS al arrancar: config y, si procede, el último fichero."""
        datos = {"config": self._config, "version": VERSION, "archivo": None}
        ultimo = self._config.get("last_file")
        if ultimo and Path(ultimo).is_file():
            datos["archivo"] = self._leer(Path(ultimo))
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

    def marcar_cambios(self, sucio: bool) -> None:
        """JS avisa aquí cada vez que cambia el estado «hay cambios sin guardar».

        El cierre de la ventana consulta este valor en lugar de llamar a evaluate_js,
        que se bloquea si se invoca desde el evento 'closing' (sobre todo en macOS).
        """
        self._sucio = bool(sucio)

    def _tamano(self, ancho: int, alto: int) -> None:
        """Evento 'resized': guarda el tamaño sin consultar a la ventana al cerrar."""
        self._config.update(width=int(ancho), height=int(alto))

    def _guardar_config(self) -> None:
        try:
            SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(self._config, indent=2), encoding="utf-8")
        except OSError:
            log.exception("No se pudo guardar la configuración")

    def _al_cerrar(self):
        """Evento 'closing': devolver False cancela el cierre.

        No se hacen llamadas bloqueantes aquí (evaluate_js, diálogos, width/height):
        si hay cambios sin guardar se cancela el cierre, se pregunta desde otro hilo
        y, si el usuario confirma, se cierra la ventana con destroy().
        """
        if self._sucio and not self._cierre_confirmado:
            if not self._preguntando:
                self._preguntando = True
                threading.Thread(target=self._confirmar_cierre, daemon=True).start()
            return False
        self._guardar_config()
        log.info("Cierre normal")
        return None

    def _confirmar_cierre(self) -> None:
        try:
            ok = self._window.create_confirmation_dialog(
                APP_NAME, "Hay cambios sin guardar. ¿Cerrar igualmente?")
        except Exception:  # noqa: BLE001
            log.exception("Fallo al mostrar el diálogo de cierre")
            ok = False
        self._preguntando = False
        if ok:
            self._cierre_confirmado = True
            self._window.destroy()


def main() -> None:
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
    ventana.events.resized += api._tamano
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()

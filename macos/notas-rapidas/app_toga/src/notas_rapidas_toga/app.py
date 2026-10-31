"""Notas Rápidas con Toga (BeeWare) para macOS.

Se puede ejecutar de tres formas:
  * Desarrollo:  briefcase dev
  * Directa:     cd src && python -m notas_rapidas_toga
  * Como .app:   ./construir_app.sh  (Briefcase)  ->  build/notas-rapidas-toga/macos/app/…

Conceptos que ilustra:
  - toga.App: método startup(), ventana principal, widgets y layout con Pack
  - Comandos (toga.Command) con atajos «MOD_1» (Cmd en macOS) y grupos de menú estándar
  - Diálogos asíncronos (await ventana.dialog(...))
  - Rutas estándar del sistema por aplicación (app.paths.config / app.paths.logs)
  - Confirmación al cerrar sin bloquear el bucle de eventos (on_close / on_exit)

Está escrita para Toga 0.5 (ver pyproject.toml). Los widgets y el menú son nativos de cada
sistema: el mismo código funciona en Windows, Linux, iOS y Android cambiando el backend.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

APP_NAME = "Notas Rápidas"
APP_ID = "com.ejemplo.notas-rapidas-toga"      # identificador del bundle (cámbialo por el tuyo)
VERSION = "1.0.0"
DEFAULT_CONFIG = {"width": 820, "height": 560, "font_size": 14, "last_file": None}

log = logging.getLogger("notas_rapidas_toga")


class NotasRapidas(toga.App):
    # ---- arranque -----------------------------------------------------------
    def startup(self) -> None:
        self._configurar_rutas_y_log()
        self.config = self._cargar_config()
        self.archivo: Path | None = None
        self._sucio = False            # ¿hay cambios sin guardar?
        self._cargando = False         # evita marcar «modificado» al cargar un fichero
        self._cierre_ok = False        # el usuario ya confirmó cerrar sin guardar
        self._preguntando = False
        self.tam_fuente = int(self.config["font_size"])

        self.texto = toga.MultilineTextInput(
            on_change=self._al_cambiar_texto,
            placeholder="Escribe aquí…",
            style=Pack(flex=1, font_family="monospace", font_size=self.tam_fuente),
        )
        self.estado = toga.Label("", style=Pack(margin=(4, 10)))
        caja = toga.Box(children=[self.texto, self.estado], style=Pack(direction=COLUMN))

        self.main_window = toga.MainWindow(
            title=APP_NAME, size=(self.config["width"], self.config["height"]))
        self.main_window.content = caja
        self._crear_comandos()

        # Dos puertas de salida: cerrar la ventana y Cmd+Q. Ambas comparten la misma lógica.
        self.main_window.on_close = self._al_cerrar_ventana
        self.on_exit = self._al_salir

        ultimo = self.config.get("last_file")
        argumentos = [a for a in sys.argv[1:] if not a.startswith("-")]
        candidato = argumentos[0] if argumentos and Path(argumentos[0]).is_file() else ultimo
        if candidato and Path(candidato).is_file():
            self._cargar(Path(candidato))
        self._refrescar()
        self.main_window.show()

    def _configurar_rutas_y_log(self) -> None:
        """app.paths da las carpetas estándar de cada sistema para esta app."""
        self._dir_config = Path(self.paths.config)
        self._dir_config.mkdir(parents=True, exist_ok=True)
        dir_logs = Path(self.paths.logs)
        dir_logs.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=dir_logs / "app.log", level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
        log.info("Arranque %s v%s (Python %s)", APP_NAME, VERSION, sys.version.split()[0])

    def _cargar_config(self) -> dict:
        config = dict(DEFAULT_CONFIG)
        try:
            config.update(json.loads((self._dir_config / "config.json").read_text(encoding="utf-8")))
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError):
            log.exception("Config ilegible; se usan valores por defecto")
        return config

    def _guardar_config(self) -> None:
        try:
            ancho, alto = self.main_window.size
            self.config.update(
                width=int(ancho), height=int(alto), font_size=self.tam_fuente,
                last_file=str(self.archivo) if self.archivo else None)
            (self._dir_config / "config.json").write_text(
                json.dumps(self.config, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001 - guardar preferencias nunca debe impedir salir
            log.exception("No se pudo guardar la configuración")

    # ---- comandos y menús ------------------------------------------------------
    def _crear_comandos(self) -> None:
        MOD = toga.Key.MOD_1                          # Cmd en macOS, Ctrl en el resto
        self.commands.add(
            toga.Command(self.nuevo, text="Nuevo", shortcut=MOD + "n",
                         group=toga.Group.FILE, section=0, order=0),
            toga.Command(self.abrir, text="Abrir…", shortcut=MOD + "o",
                         group=toga.Group.FILE, section=0, order=1),
            toga.Command(self.guardar, text="Guardar", shortcut=MOD + "s",
                         group=toga.Group.FILE, section=1, order=0),
            toga.Command(self.guardar_como, text="Guardar como…",
                         shortcut=MOD + toga.Key.SHIFT + "s",
                         group=toga.Group.FILE, section=1, order=1),
            toga.Command(self.mas_letra, text="Aumentar letra", shortcut=MOD + "=",
                         group=toga.Group.VIEW, section=0, order=0),
            toga.Command(self.menos_letra, text="Reducir letra", shortcut=MOD + "-",
                         group=toga.Group.VIEW, section=0, order=1),
        )
        # «Acerca de» y «Salir» los aporta Toga. Si tu versión no incluye los comandos de edición
        # (deshacer, copiar, pegar), añádelos aquí como toga.Command con group=toga.Group.EDIT.

    # ---- acciones (Toga las invoca como handler(command, **kwargs)) -------------
    async def nuevo(self, command=None, **kwargs) -> None:
        if not await self._confirmar_cambios():
            return
        self._poner_texto("")
        self.archivo = None
        self._sucio = False
        self._refrescar()

    async def abrir(self, command=None, **kwargs) -> None:
        if not await self._confirmar_cambios():
            return
        ruta = await self.main_window.dialog(
            toga.OpenFileDialog("Abrir", file_types=["txt", "md"]))
        if ruta:
            self._cargar(Path(ruta))

    async def guardar(self, command=None, **kwargs) -> bool:
        if self.archivo:
            return await self._escribir(self.archivo)
        return await self.guardar_como()

    async def guardar_como(self, command=None, **kwargs) -> bool:
        ruta = await self.main_window.dialog(
            toga.SaveFileDialog("Guardar como", suggested_filename="nota.txt",
                                file_types=["txt", "md"]))
        return await self._escribir(Path(ruta)) if ruta else False

    def mas_letra(self, command=None, **kwargs) -> None:
        self._zoom(+1)

    def menos_letra(self, command=None, **kwargs) -> None:
        self._zoom(-1)

    # ---- lógica ---------------------------------------------------------------------
    def _poner_texto(self, contenido: str) -> None:
        self._cargando = True
        try:
            self.texto.value = contenido
        finally:
            self._cargando = False

    def _cargar(self, ruta: Path) -> None:
        try:
            contenido = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log.exception("No se pudo abrir %s", ruta)
            self.loop.create_task(self.main_window.dialog(
                toga.ErrorDialog("No se pudo abrir", str(exc))))
            return
        self._poner_texto(contenido)
        self.archivo = ruta
        self._sucio = False
        self._refrescar()

    async def _escribir(self, ruta: Path) -> bool:
        try:
            ruta.write_text(self.texto.value, encoding="utf-8")
        except OSError as exc:
            log.exception("No se pudo guardar %s", ruta)
            await self.main_window.dialog(toga.ErrorDialog("No se pudo guardar", str(exc)))
            return False
        self.archivo = ruta
        self._sucio = False
        self._refrescar()
        return True

    async def _confirmar_cambios(self) -> bool:
        """True si se puede continuar (sin cambios, o el usuario acepta descartarlos)."""
        if not self._sucio:
            return True
        # Toga no ofrece un diálogo de tres botones: se pregunta primero si guardar.
        if await self.main_window.dialog(toga.QuestionDialog(
                APP_NAME, "Hay cambios sin guardar. ¿Quieres guardarlos?")):
            return await self.guardar()
        return await self.main_window.dialog(toga.ConfirmDialog(
            APP_NAME, "Se perderán los cambios. ¿Continuar sin guardar?"))

    def _zoom(self, delta: int) -> None:
        self.tam_fuente = max(8, min(48, self.tam_fuente + delta))
        self.texto.style.font_size = self.tam_fuente

    def _al_cambiar_texto(self, widget, **kwargs) -> None:
        if not self._cargando:
            self._sucio = True
        self._refrescar()

    def _refrescar(self) -> None:
        nombre = self.archivo.name if self.archivo else "Sin título"
        self.main_window.title = f"{'• ' if self._sucio else ''}{nombre} — {APP_NAME}"
        contenido = self.texto.value or ""
        self.estado.text = f"{len(contenido.split())} palabras · {len(contenido)} caracteres"

    # ---- salir sin bloquear el bucle de eventos --------------------------------------
    def _al_cerrar_ventana(self, window, **kwargs) -> bool:
        return self._puede_salir()

    def _al_salir(self, app, **kwargs) -> bool:
        return self._puede_salir()

    def _puede_salir(self) -> bool:
        """Los handlers de cierre son síncronos y devuelven bool. Si hay cambios, se cancela el
        cierre, se pregunta con un diálogo asíncrono y, si el usuario acepta, se sale con exit()."""
        if not self._sucio or self._cierre_ok:
            self._guardar_config()
            log.info("Cierre normal")
            return True
        if not self._preguntando:
            self._preguntando = True
            self.loop.create_task(self._preguntar_salida())
        return False

    async def _preguntar_salida(self) -> None:
        try:
            if await self._confirmar_cambios():
                self._cierre_ok = True
                self._guardar_config()
                log.info("Cierre normal")
                self.exit()
        finally:
            self._preguntando = False


def main() -> NotasRapidas:
    try:
        # Con Briefcase, el nombre y el identificador salen de pyproject.toml
        return NotasRapidas()
    except RuntimeError:
        # Ejecución directa sin metadatos del paquete
        return NotasRapidas(formal_name=f"{APP_NAME} Toga", app_id=APP_ID, version=VERSION)

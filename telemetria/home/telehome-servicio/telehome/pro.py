"""TeleHome Pro: transiciones y temporizadores de las luces, escenas y grupos.

Todo lo que ocurre «con el tiempo» vive en **un solo hilo** (`Automatismos`) que duerme hasta el próximo
suceso y no hace nada mientras no haya ninguno: sin transiciones ni temporizadores no gasta CPU.

* **Transición** (`fade`): llevar el brillo, el blanco o el color de una luz de un valor a otro en N segundos.
  Se hace en pasos. Cada paso es una orden a la bombilla y, por la nube, una llamada a Tuya, así que hay un
  mínimo entre pasos (`PASO_NUBE` / `PASO_LOCAL`) y un máximo de pasos (`MAX_PASOS`): una transición de un
  minuto cuesta unas 15 llamadas, no 60. Una orden manual sobre esa luz cancela la transición.
* **Temporizador**: apagar (o encender) un dispositivo dentro de N minutos, opcionalmente con una transición
  (solo en luces). Se guarda en el fichero de configuración, así que **un reinicio no lo pierde**: al arrancar,
  los que vencieron mientras el servicio estaba parado se ejecutan si hace poco (`GRACIA_ARRANQUE`) y se
  descartan si hace mucho.

El cálculo de los pasos (`pasos_*`) es puro y se prueba sin hilo ni red.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import luces

log = logging.getLogger("telehome")

MAX_FADE = 3600          # s
MAX_PASOS = 20           # pasos de una transición, por larga que sea
PASO_NUBE = 4.0          # s mínimos entre dos pasos de una luz por la nube (cada uno es una llamada a Tuya)
PASO_LOCAL = 1.5         # s mínimos entre dos pasos de una luz en la red local
MAX_TEMPORIZADOR = 1440  # min (24 h)
ESPERA_MAX = 30.0        # s; cuánto duerme el hilo como máximo si no hay nada pendiente
GRACIA_ARRANQUE = 900.0  # s; un temporizador que venció mientras el servicio estaba parado se ejecuta si fue hace menos

Paso = Tuple[float, str, Any]      # (segundos desde el inicio, orden, valor)


def _n_pasos(segundos: float, paso_min: float) -> int:
    return max(1, min(MAX_PASOS, int(segundos // paso_min)))


def _lineal(a: float, b: float, i: int, n: int) -> float:
    return a + (b - a) * i / n


def pasos_nivel(actual: Optional[float], encendida: bool, destino: int, segundos: float, paso_min: float) -> List[Paso]:
    """Transición de brillo. Bajar a 0 es bajar hasta 1 % y apagar al final; subir desde apagada empieza en 1 %."""
    out: List[Paso] = []
    n = _n_pasos(segundos, paso_min)
    inicio = float(actual) if (encendida and actual is not None) else 1.0
    if not encendida and destino > 0:
        out.append((0.0, "level", 1))
    meta = max(1, destino)
    ultimo: Optional[int] = out[0][2] if out else None
    for i in range(1, n + 1):
        v = int(round(_lineal(inicio, meta, i, n)))
        if v != ultimo:
            out.append((segundos * i / n, "level", v))
            ultimo = v
    if destino == 0:
        out.append((float(segundos), "switch", False))
    return out


def pasos_temp(actual: Optional[float], necesita_modo: bool, destino: int, segundos: float, paso_min: float) -> List[Paso]:
    """Transición del blanco. Si la luz no está en modo blanco (o está apagada), el primer paso la pone."""
    out: List[Paso] = []
    n = _n_pasos(segundos, paso_min)
    inicio = float(actual) if actual is not None else 30.0
    if necesita_modo:
        out.append((0.0, "temp", int(round(inicio))))
    ultimo = out[0][2] if out else None
    for i in range(1, n + 1):
        v = int(round(_lineal(inicio, destino, i, n)))
        if v != ultimo:
            out.append((segundos * i / n, "temp", v))
            ultimo = v
    return out


def _tono_corto(a: float, b: float, t: float) -> float:
    d = ((b - a + 180) % 360) - 180
    return (a + d * t) % 360


def pasos_color(actual: Optional[Dict[str, int]], necesita_modo: bool, destino: Tuple[int, int, int], nivel_actual: Optional[float],
                segundos: float, paso_min: float) -> List[Paso]:
    """Transición de color en HSV, por el camino corto del tono. Desde blanco empieza en el mismo tono, sin color."""
    h1, s1, v1 = destino
    if actual is None or necesita_modo:
        h0, s0, v0 = h1, 0, int(nivel_actual or 50)
    else:
        h0, s0, v0 = actual["h"], actual["s"], actual["v"]
    out: List[Paso] = []
    n = _n_pasos(segundos, paso_min)
    ultimo = None
    if necesita_modo or actual is None:
        ini = {"h": int(h0), "s": int(s0), "v": max(1, int(v0))}
        out.append((0.0, "color", ini))
        ultimo = (ini["h"], ini["s"], ini["v"])
    for i in range(1, n + 1):
        t = i / n
        c = (int(round(_tono_corto(h0, h1, t))) % 360, int(round(_lineal(s0, s1, i, n))), max(1, int(round(_lineal(v0, v1, i, n)))))
        if c != ultimo:
            out.append((segundos * t, "color", {"h": c[0], "s": c[1], "v": c[2]}))
            ultimo = c
    return out


class Automatismos:
    """Hilo único con las transiciones y los temporizadores en curso."""

    def __init__(self, monitor, reloj: Callable[[], float] = time.time):
        self.monitor = monitor
        self.reloj = reloj
        self._cv = threading.Condition()
        self._fades: Dict[str, Dict[str, Any]] = {}
        self._timers: Dict[str, Dict[str, Any]] = {}
        self._hilo: Optional[threading.Thread] = None
        self._cerrar = False

    # ---- ciclo de vida: el hilo nace con la primera tarea y muere con el servicio ----
    def _asegurar_hilo(self) -> None:
        if self._hilo is None or not self._hilo.is_alive():
            self._hilo = threading.Thread(target=self._bucle, name="telehome-pro", daemon=True)
            self._hilo.start()

    def stop(self) -> None:
        with self._cv:
            self._cerrar = True
            self._cv.notify_all()

    def _bucle(self) -> None:
        while True:
            with self._cv:
                if self._cerrar:
                    return
                prox = self._proximo()
                if prox is None:
                    self._cv.wait(ESPERA_MAX)
                    continue
                espera = prox - self.reloj()
                if espera > 0:
                    self._cv.wait(min(espera, ESPERA_MAX))
                    continue
            try:
                self.tick()
            except Exception:
                log.exception("Error en las transiciones y temporizadores")

    def _proximo(self) -> Optional[float]:
        horas = [j["pasos"][0][0] + j["t0"] for j in self._fades.values() if j["pasos"]]
        horas += [t["at"] for t in self._timers.values()]
        return min(horas) if horas else None

    # ---- tareas ----
    def _paso_min(self, dev_id: str) -> float:
        dev = self.monitor.config.get(dev_id) or {}
        return PASO_NUBE if dev.get("mode") == "nube" else PASO_LOCAL

    def cancelar(self, dev_id: str) -> bool:
        """Cancela la transición de una luz (una orden manual lo hace). El temporizador se respeta."""
        with self._cv:
            return self._fades.pop(dev_id, None) is not None

    def cancelar_temporizador(self, dev_id: str) -> bool:
        with self._cv:
            habia = self._timers.pop(dev_id, None) is not None
        try:
            quitado = self.monitor.config.clear_timer(dev_id)
        except Exception:
            log.exception("No se pudo borrar el temporizador de %s", dev_id)
            quitado = False
        return habia or quitado

    def fade(self, dev_id: str, action: str, value: Any, segundos: float) -> None:
        """Programa una transición y ejecuta ya su primer paso si lo tiene a tiempo 0."""
        if action not in ("level", "temp", "color"):
            raise ValueError("Solo se puede hacer una transición con brillo, blanco o color")
        if not 0 < segundos <= MAX_FADE:
            raise ValueError("La transición debe durar entre 1 y %d segundos" % MAX_FADE)
        cur = self.monitor.light_state(dev_id)
        paso_min = self._paso_min(dev_id)
        on = bool(cur.get("on"))
        if action == "level":
            pc = luces._entero(value, "level")
            lo, hi = luces.limites(self.monitor.config.get(dev_id))
            destino = 0 if pc == 0 else int(luces.clamp(pc, lo, max(lo, hi)))
            pasos = pasos_nivel(self._brillo_visible(cur), on, destino, segundos, paso_min)
        elif action == "temp":
            destino = luces._entero(value, "temp")
            necesita = (not on) or cur.get("mode") != "white"
            pasos = pasos_temp(cur.get("temp"), necesita, destino, segundos, paso_min)
        else:
            h, s_, v_ = luces.parse_color_arg(value)
            lo, hi = luces.limites(self.monitor.config.get(dev_id))
            v_ = int(luces.clamp(v_, lo, max(lo, hi)))
            necesita = (not on) or cur.get("mode") != "colour"
            pasos = pasos_color(cur.get("color"), necesita, (h, s_, v_), self._brillo_visible(cur), segundos, paso_min)
        if not pasos:
            return
        job = {"dev": dev_id, "action": action, "t0": self.reloj(), "pasos": pasos, "dur": segundos}
        with self._cv:
            self._fades[dev_id] = job
            self._cv.notify_all()
        self._asegurar_hilo()
        self.tick()                                  # el primer paso, si es de tiempo 0, sale ya

    @staticmethod
    def _brillo_visible(cur: Dict[str, Any]) -> Optional[float]:
        return cur.get("level")

    def temporizador(self, dev_id: str, minutos: float, accion: str = "off", fade: int = 0) -> Dict[str, Any]:
        """Apaga o enciende un dispositivo dentro de N minutos. La transición solo se aplica a las luces."""
        if accion not in ("off", "on"):
            raise ValueError("La acción del temporizador debe ser «off» o «on»")
        if not 0 < minutos <= MAX_TEMPORIZADOR:
            raise ValueError("El temporizador debe estar entre 1 y %d minutos" % MAX_TEMPORIZADOR)
        if not 0 <= fade <= MAX_FADE:
            raise ValueError("La transición debe estar entre 0 y %d segundos" % MAX_FADE)
        dev = self.monitor.config.get(dev_id)
        if dev is None:
            raise KeyError(dev_id)
        if dev.get("type") != "luz":
            fade = 0                               # un enchufe solo se enciende y se apaga
        t = {"device": dev_id, "at": self.reloj() + minutos * 60, "action": accion, "fade": int(fade)}
        self._guardar(dev_id, t)
        self._asegurar_hilo()
        return dict(t)

    def _guardar(self, dev_id: str, t: Optional[Dict[str, Any]]) -> None:
        """Apunta (o quita) el temporizador en memoria y en el fichero, para que sobreviva a un reinicio."""
        with self._cv:
            if t is None:
                self._timers.pop(dev_id, None)
            else:
                self._timers[dev_id] = t
            self._cv.notify_all()
        try:
            if t is None:
                self.monitor.config.clear_timer(dev_id)
            else:
                self.monitor.config.set_timer(t)
        except Exception:                          # no guardar no debe tumbar el temporizador
            log.exception("No se pudo guardar el temporizador de %s", dev_id)

    def restaurar(self) -> int:
        """Vuelve a poner en marcha los temporizadores guardados. Devuelve cuántos quedan pendientes."""
        ahora = self.reloj()
        pendientes, vencidos = [], []
        for t in list(getattr(self.monitor.config, "timers", [])):
            if self.monitor.config.get(t["device"]) is None:
                continue                           # el dispositivo ya no existe
            (pendientes if t["at"] > ahora else vencidos).append(dict(t))
        with self._cv:
            self._timers = {t["device"]: t for t in pendientes}
        for t in vencidos:
            if ahora - t["at"] <= GRACIA_ARRANQUE:
                log.info("Temporizador de «%s» vencido durante la parada: se ejecuta ahora", t["device"])
                with self._cv:
                    self._timers[t["device"]] = {**t, "at": ahora}
            else:
                log.info("Temporizador de «%s» caducado hace mucho: se descarta", t["device"])
                try:
                    self.monitor.config.clear_timer(t["device"])
                except Exception:
                    log.exception("No se pudo borrar el temporizador caducado de %s", t["device"])
        with self._cv:
            n = len(self._timers)
        if n:
            self._asegurar_hilo()
            self.tick()
        return n

    # ---- ejecución ----
    def tick(self, ahora: Optional[float] = None) -> int:
        """Ejecuta lo que ya tocaba. Devuelve cuántas órdenes dio (para los tests)."""
        ahora = self.reloj() if ahora is None else ahora
        listos: List[Tuple[str, str, Any]] = []
        vencidos: List[Dict[str, Any]] = []
        with self._cv:
            for dev, j in list(self._fades.items()):
                while j["pasos"] and j["t0"] + j["pasos"][0][0] <= ahora:
                    _, orden, valor = j["pasos"].pop(0)
                    listos.append((dev, orden, valor))
                if not j["pasos"]:
                    self._fades.pop(dev, None)
            for dev, t in list(self._timers.items()):
                if t["at"] <= ahora:
                    vencidos.append(self._timers.pop(dev))
        n = 0
        for dev, orden, valor in listos:
            try:
                self.monitor.command(dev, orden, valor, manual=False)
                n += 1
            except Exception as exc:
                log.warning("Transición de «%s» interrumpida: %s", dev, exc)
                with self._cv:
                    self._fades.pop(dev, None)
        for t in vencidos:
            try:
                self.monitor.config.clear_timer(t["device"])
            except Exception:
                log.exception("No se pudo borrar el temporizador cumplido de %s", t["device"])
            try:
                if t["action"] == "off":
                    if t["fade"] > 0 and (self.monitor.config.get(t["device"]) or {}).get("type") == "luz":
                        self.monitor.command(t["device"], "level", 0, manual=False, fade=t["fade"])
                    else:
                        self.monitor.command(t["device"], "switch", False, manual=False)
                else:
                    self.monitor.command(t["device"], "switch", True, manual=False)
                n += 1
                log.info("Temporizador de «%s»: %s", t["device"], "apagada" if t["action"] == "off" else "encendida")
            except Exception as exc:
                log.warning("Temporizador de «%s» fallido: %s", t["device"], exc)
        return n

    # ---- para el estado de la API ----
    def listar(self) -> Dict[str, List[Dict[str, Any]]]:
        with self._cv:
            return {
                "timers": [{"device": t["device"], "at": t["at"], "action": t["action"], "fade": t["fade"]} for t in self._timers.values()],
                "fades": [{"device": j["dev"], "action": j["action"], "until": j["t0"] + j["dur"]} for j in self._fades.values()],
            }

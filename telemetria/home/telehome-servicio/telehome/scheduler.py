"""Programaciones: dispara órdenes a una hora fija, al amanecer o al anochecer.

Cada minuto comprueba qué programaciones tocaban y no se han ejecutado todavía. Reglas:

* **Momento.** `clock` usa la hora local del servidor; `sunrise` y `sunset` calculan el orto y el
  ocaso del día con el lugar de las opciones, y admiten un desplazamiento en minutos.
* **Días.** Lista de días de la semana en formato ISO (1 lunes … 7 domingo).
* **Puesta al día.** Si el servicio estuvo parado, solo se recupera lo de la última hora
  (`VENTANA`): al arrancar por la mañana no se dispara todo lo de la noche de golpe.
* **Condición.** Opcional, sobre una magnitud de la última lectura; con `for` se exige además que
  se haya mantenido durante ese tiempo, mirando el histórico.
* **Mando manual.** Con `skip_if_manual`, si alguien dio una orden a ese dispositivo desde la
  última vez que se disparó esta programación (o en las últimas 24 h), se salta.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from .config import Config
from .sun import LAT_POR_DEFECTO, LON_POR_DEFECTO, _eventos

log = logging.getLogger("telehome")

VENTANA = 3600.0        # s; cuánto se recupera tras una parada del servicio
PASO = 20.0             # s; cada cuánto se mira el reloj
SIN_DISPARO = 86400.0   # s; antigüedad que se supone cuando una programación no se ha disparado nunca

OPS = {
    "<":  lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">":  lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def _medianoche(t: float) -> float:
    d = datetime.fromtimestamp(t)
    return time.mktime((d.year, d.month, d.day, 0, 0, 0, 0, 0, -1))


def instante(sch: Dict[str, Any], dia: date, lat: float, lon: float) -> Optional[float]:
    """Cuándo toca esta programación ese día, o None si ese día no aplica.
    Sin días marcados vale cualquier día: es de un solo uso y se desactiva al ejecutarse."""
    if sch["days"] and dia.isoweekday() not in sch["days"]:
        return None
    when = sch["when"]
    if when["kind"] == "clock":
        hh, mm = when["time"].split(":")
        return time.mktime((dia.year, dia.month, dia.day, int(hh), int(mm), 0, 0, 0, -1))
    amanece, anochece = _eventos(dia, lat, lon)
    base = amanece if when["kind"] == "sunrise" else anochece
    if base is None:
        return None                       # ese día el Sol no sale o no se pone
    return base + when.get("offset", 0) * 60


def _cumple_ahora(cond: Dict[str, Any], lectura) -> Tuple[bool, str]:
    if lectura is None or not getattr(lectura, "online", False):
        return False, "sin lectura del dispositivo"
    valores = {"p": lectura.power_w, "v": lectura.voltage_v, "i": lectura.current_a}
    v = valores.get(cond["metric"])
    if v is None:
        return False, "el dispositivo no mide «%s»" % cond["metric"]
    if not OPS[cond["op"]](v, cond["value"]):
        return False, "no se cumple la condición (%s %s %g, vale %g)" % (cond["metric"], cond["op"], cond["value"], v)
    return True, ""


def _cumple_durante(cond: Dict[str, Any], store, dev_id: str, ahora: float) -> Tuple[bool, str]:
    """¿La condición se ha mantenido durante los últimos `for` segundos?"""
    durante = cond.get("for") or 0
    if durante <= 0:
        return True, ""
    puntos = store.history(dev_id, ahora - durante, ahora, 400)
    if not puntos:
        return False, "no hay histórico para comprobar la condición"
    clave = {"p": "p", "v": "v", "i": "i"}.get(cond["metric"])
    vistos = 0
    for p in puntos:
        v = p.get(clave)
        if v is None:
            continue
        vistos += 1
        if not OPS[cond["op"]](v, cond["value"]):
            return False, "la condición no se mantuvo durante %d s" % durante
    if not vistos:
        return False, "no hay histórico de «%s»" % cond["metric"]
    return True, ""


class Scheduler:
    """Hilo que dispara las programaciones. Se para con stop()."""

    def __init__(self, config: Config, monitor, store):
        self.config = config
        self.monitor = monitor
        self.store = store
        self._stop = threading.Event()
        self._hilo: Optional[threading.Thread] = None

    # ---- ciclo de vida ----
    def start(self) -> None:
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._bucle, name="telehome-scheduler", daemon=True)
            self._hilo.start()

    def stop(self) -> None:
        self._stop.set()
        if self._hilo is not None:
            self._hilo.join(timeout=3)
            self._hilo = None

    def _bucle(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("Error evaluando las programaciones")
            self._stop.wait(PASO)

    # ---- evaluación ----
    def pendientes(self, ahora: Optional[float] = None) -> List[Tuple[Dict[str, Any], float]]:
        """Programaciones que tocaban y aún no se han ejecutado, con el instante que les correspondía."""
        ahora = time.time() if ahora is None else ahora
        lat = float(self.config.options.get("lat", LAT_POR_DEFECTO))
        lon = float(self.config.options.get("lon", LON_POR_DEFECTO))
        out = []
        for sch in list(self.config.schedules):
            if not sch.get("enabled"):
                continue
            mejor = None
            for delta in (0, -86400):      # hoy y ayer, por si toca de madrugada o hubo parada
                dia = date.fromtimestamp(ahora + delta)
                t = instante(sch, dia, lat, lon)
                if t is None or t > ahora or ahora - t > VENTANA:
                    continue
                if t <= float(sch.get("last_fire") or 0):
                    continue
                if t <= float(sch.get("created") or 0):
                    continue              # un momento anterior a la propia programación no cuenta
                if mejor is None or t > mejor:
                    mejor = t
            if mejor is not None:
                out.append((sch, mejor))
        return out

    def tick(self, ahora: Optional[float] = None) -> List[Tuple[str, str]]:
        """Evalúa y ejecuta lo que toque. Devuelve [(id, resultado)] de lo evaluado."""
        ahora = time.time() if ahora is None else ahora
        hechos = []
        for sch, momento in self.pendientes(ahora):
            resultado = self._ejecutar(sch, momento, ahora)
            # «Una sola vez» es una sola evaluación: se gasta aunque se salte o falle,
            # para que no reaparezca al día siguiente sin que nadie lo haya pedido.
            una_vez = not sch["days"]
            if una_vez:
                resultado += " (una sola vez: queda desactivada)"
            self.config.mark_schedule(sch["id"], momento, resultado, desactivar=una_vez)
            hechos.append((sch["id"], resultado))
            log.info("Programación «%s»: %s", sch["name"], resultado)
        return hechos

    def ejecutar_ahora(self, sch: Dict[str, Any], ahora: Optional[float] = None) -> str:
        """Dispara una programación al margen de su hora (el botón «Probar» de la app)."""
        ahora = time.time() if ahora is None else ahora
        return self._ejecutar(sch, ahora, ahora)

    def _ejecutar(self, sch: Dict[str, Any], momento: float, ahora: float) -> str:
        dev_id = sch["device"]
        if self.config.get(dev_id) is None:
            return "saltada: el dispositivo ya no existe"

        if sch.get("skip_if_manual"):
            manual = self.monitor.last_manual.get(dev_id, 0)
            desde = float(sch.get("last_fire") or 0) or (ahora - SIN_DISPARO)
            if manual > desde:
                return "saltada: lo manejaste a mano después de la vez anterior"

        cond = sch.get("condition")
        if cond:
            ok, por_que = _cumple_ahora(cond, self.monitor.latest.get(dev_id))
            if not ok:
                return "saltada: " + por_que
            ok, por_que = _cumple_durante(cond, self.store, dev_id, ahora)
            if not ok:
                return "saltada: " + por_que

        try:
            self.monitor.command(dev_id, sch["action"], sch["value"], manual=False)
        except KeyError:
            return "error: el dispositivo no está disponible"
        except ValueError as exc:
            return "error: %s" % exc
        except Exception as exc:                      # fallo de red con el dispositivo
            return "error: %s" % exc
        return "ejecutada"

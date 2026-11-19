"""Sondeo periódico de los enchufes, almacenamiento y estado en memoria."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .config import MIN_POLL, Config
from .devices import PlugError, Reading, make_plug
from .store import Store

log = logging.getLogger("telemet-enchufes")


def local_midnight(now: Optional[float] = None) -> float:
    t = time.localtime(now if now is not None else time.time())
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


class Monitor:
    def __init__(self, config: Config, store: Store, simulate: bool = False):
        self.config = config
        self.store = store
        self.simulate = simulate
        self.latest: Dict[str, Reading] = {}
        self.plugs: Dict[str, Any] = {}
        self._snap: Dict[str, Dict[str, Any]] = {}
        self._stops: Dict[str, threading.Event] = {}
        self._energy: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._closing = threading.Event()

    # ---- Ciclo de vida -------------------------------------------------
    def start(self) -> None:
        self.sync()
        threading.Thread(target=self._pruner, name="poda", daemon=True).start()

    def stop(self) -> None:
        self._closing.set()
        with self._lock:
            for ev in self._stops.values():
                ev.set()

    def sync(self) -> None:
        """Alinea los hilos de sondeo con la configuración actual."""
        with self._lock:
            wanted = {d["id"]: dict(d) for d in self.config.devices}
            for dev_id in list(self._snap):
                if dev_id not in wanted or wanted[dev_id] != self._snap[dev_id]:
                    self._stops.pop(dev_id).set()
                    self._snap.pop(dev_id)
                    self.plugs.pop(dev_id, None)
                    if dev_id not in wanted:
                        self.latest.pop(dev_id, None)
                        self._energy.pop(dev_id, None)
            for dev_id, dev in wanted.items():
                if dev_id not in self._snap:
                    self._spawn(dev)

    def _spawn(self, dev: Dict[str, Any]) -> None:
        plug = make_plug(dev, self.simulate)
        stop = threading.Event()
        self.plugs[dev["id"]] = plug
        self._snap[dev["id"]] = dict(dev)
        self._stops[dev["id"]] = stop
        now = time.time()
        self._energy[dev["id"]] = {
            "day": time.strftime("%Y-%m-%d", time.localtime(now)),
            "kwh": self.store.energy_kwh(dev["id"], local_midnight(now), now),
            "last": None,
        }
        threading.Thread(target=self._loop, args=(dev["id"], plug, stop),
                         name="sondeo-" + dev["id"], daemon=True).start()

    # ---- Sondeo ----------------------------------------------------------
    def _interval(self) -> int:
        return max(MIN_POLL, int(self.config.options.get("poll_interval", 10)))

    def _read(self, dev_id: str, plug) -> Reading:
        try:
            return plug.read()
        except PlugError as exc:
            return Reading(ts=time.time(), online=False, error=str(exc))
        except Exception as exc:  # no dejar morir el hilo por un error inesperado
            log.exception("Error inesperado leyendo %s", dev_id)
            return Reading(ts=time.time(), online=False, error="Error interno: %s" % exc)

    def _record(self, dev_id: str, r: Reading, stop: Optional[threading.Event]) -> None:
        if stop is not None and stop.is_set():
            return  # enchufe eliminado/reconfigurado mientras se leía
        with self._lock:
            self.latest[dev_id] = r
            self._account(dev_id, r)
        self.store.add(dev_id, r.ts, r.online, r.on, r.power_w, r.voltage_v, r.current_a)

    def _account(self, dev_id: str, r: Reading) -> None:
        acc = self._energy.get(dev_id)
        if acc is None:
            return
        day = time.strftime("%Y-%m-%d", time.localtime(r.ts))
        if acc["day"] != day:
            acc.update(day=day, kwh=0.0, last=None)
        if not r.online or r.power_w is None:
            acc["last"] = None
            return
        if acc["last"] is not None:
            t0, p0 = acc["last"]
            dt = r.ts - t0
            if 0 < dt <= max(120, 6 * self._interval()):
                acc["kwh"] += (p0 + r.power_w) / 2.0 * dt / 3_600_000.0
        acc["last"] = (r.ts, r.power_w)

    def _loop(self, dev_id: str, plug, stop: threading.Event) -> None:
        fails = 0
        while not stop.is_set() and not self._closing.is_set():
            r = self._read(dev_id, plug)
            self._record(dev_id, r, stop)
            fails = 0 if r.online else fails + 1
            wait = self._interval() if r.online else min(self._interval() * (2 ** min(fails, 3)), 60)
            stop.wait(wait)

    def _pruner(self) -> None:
        while not self._closing.wait(3600):
            try:
                n = self.store.prune(int(self.config.options.get("retention_days", 30)))
                if n:
                    log.info("Poda: %d lecturas antiguas eliminadas", n)
            except Exception:
                log.exception("Error podando la base de datos")

    # ---- Órdenes -----------------------------------------------------------
    def set_power(self, dev_id: str, on: bool) -> Reading:
        plug = self.plugs.get(dev_id)
        if plug is None:
            raise KeyError(dev_id)
        plug.set_power(on)
        r = self._read(dev_id, plug)
        self._record(dev_id, r, self._stops.get(dev_id))
        return r

    # ---- Estado --------------------------------------------------------------
    def state(self) -> List[Dict[str, Any]]:
        out = []
        with self._lock:
            for dev in self.config.devices:
                r = self.latest.get(dev["id"])
                acc = self._energy.get(dev["id"])
                out.append({
                    "id": dev["id"],
                    "reading": None if r is None else {
                        "ts": r.ts, "online": r.online, "on": r.on, "power_w": r.power_w,
                        "voltage_v": r.voltage_v, "current_a": r.current_a, "error": r.error},
                    "energy_today_kwh": None if acc is None else round(acc["kwh"], 4),
                })
        return out

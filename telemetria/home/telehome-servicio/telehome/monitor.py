"""Sondeo periódico de los enchufes, almacenamiento y estado en memoria."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Dict, List, Optional

from .config import MIN_CLOUD_POLL, MIN_POLL, Config
from . import luces
from .pro import Automatismos
from .devices import PlugError, Reading, TipoIncorrecto, make_plug
from .store import Store

log = logging.getLogger("telehome")

MIN_REFRESH = 5.0       # s entre dos refrescos forzados (cada uno cuesta una llamada a la nube de Tuya)
REFRESH_TIMEOUT = 20.0  # s que se espera a que contesten los dispositivos antes de devolver lo que haya


def local_midnight(now: Optional[float] = None) -> float:
    t = time.localtime(now if now is not None else time.time())
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


class Monitor:
    def __init__(self, config: Config, store: Store, simulate: bool = False, hub=None):
        self.config = config
        self.store = store
        self.simulate = simulate
        self.hub = hub
        self.latest: Dict[str, Reading] = {}
        # Última orden dada a mano por una persona, por dispositivo: las programaciones
        # con «skip_if_manual» la consultan para no pisar lo que acabas de hacer.
        self.last_manual: Dict[str, float] = {}
        self.plugs: Dict[str, Any] = {}
        self._snap: Dict[str, Dict[str, Any]] = {}
        self._stops: Dict[str, threading.Event] = {}
        self._energy: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._closing = threading.Event()
        self._refresh_lock = threading.Lock()
        self._refresh_ts = 0.0
        self.auto = Automatismos(self)      # transiciones y temporizadores (el hilo nace con la primera tarea)

    # ---- Ciclo de vida -------------------------------------------------
    def start(self) -> None:
        self.sync()
        try:
            n = self.auto.restaurar()          # temporizadores que quedaron pendientes antes de parar
            if n:
                log.info("%d temporizador(es) recuperados", n)
        except Exception:
            log.exception("No se pudieron recuperar los temporizadores")
        threading.Thread(target=self._pruner, name="poda", daemon=True).start()

    def stop(self) -> None:
        self._closing.set()
        self.auto.stop()
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
        mode = dev.get("mode", "local")
        plug = make_plug(dev, self.simulate, self.hub, lambda: self._interval(mode) * 0.9)
        stop = threading.Event()
        self.plugs[dev["id"]] = plug
        self._snap[dev["id"]] = dict(dev)
        self._stops[dev["id"]] = stop
        now = time.time()
        self._energy[dev["id"]] = {
            "day": time.strftime("%Y-%m-%d", time.localtime(now)),
            # mismo hueco máximo que en _account: con lecturas por nube (cada 60-300 s) un máximo fijo de
            # 120 s dejaba la energía de hoy casi a cero tras cada reinicio
            "kwh": self.store.energy_kwh(dev["id"], local_midnight(now), now, max(120.0, 6.0 * self._interval(mode))),
            "last": None,
        }
        threading.Thread(target=self._loop, args=(dev["id"], plug, stop, mode),
                         name="sondeo-" + dev["id"], daemon=True).start()

    # ---- Sondeo ----------------------------------------------------------
    def _interval(self, mode: str = "local") -> int:
        if mode == "nube":
            return max(MIN_CLOUD_POLL, int(self.config.options.get("cloud_poll_interval", 300)))
        return max(MIN_POLL, int(self.config.options.get("poll_interval", 10)))

    def interval_for(self, dev_id: str) -> int:
        dev = self.config.get(dev_id)
        return self._interval(dev.get("mode", "local") if dev else "local")

    def _read(self, dev_id: str, plug) -> Reading:
        try:
            return plug.read()
        except TipoIncorrecto as exc:
            self._retipar(dev_id, exc.tipo)
            return Reading(ts=time.time(), online=False, error=str(exc))
        except PlugError as exc:
            return Reading(ts=time.time(), online=False, error=str(exc))
        except Exception as exc:  # no dejar morir el hilo por un error inesperado
            log.exception("Error inesperado leyendo %s", dev_id)
            return Reading(ts=time.time(), online=False, error="Error interno: %s" % exc)

    def _retipar(self, dev_id: str, tipo: str) -> None:
        """Cambia el tipo de un dispositivo que contesta como otro (típico: una bombilla importada como enchufe)."""
        try:
            self.config.retype_device(dev_id, tipo)
        except (KeyError, ValueError):
            return
        log.info("«%s» responde como «%s»: se cambia su tipo y se reinicia su sondeo", dev_id, tipo)
        self.sync()

    def _record(self, dev_id: str, r: Reading, stop: Optional[threading.Event]) -> None:
        if stop is not None and stop.is_set():
            return  # enchufe eliminado/reconfigurado mientras se leía
        with self._lock:
            self.latest[dev_id] = r
            self._account(dev_id, r)
        self.store.add(dev_id, r.ts, r.online, r.on, r.power_w, r.voltage_v, r.current_a, level=r.level)

    def _account(self, dev_id: str, r: Reading) -> None:  # energía de hoy (trapecios)
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
            if 0 < dt <= max(120, 6 * self.interval_for(dev_id)):
                acc["kwh"] += (p0 + r.power_w) / 2.0 * dt / 3_600_000.0
        acc["last"] = (r.ts, r.power_w)

    def _loop(self, dev_id: str, plug, stop: threading.Event, mode: str = "local") -> None:
        fails = 0
        while not stop.is_set() and not self._closing.is_set():
            r = self._read(dev_id, plug)
            self._record(dev_id, r, stop)
            fails = 0 if r.online else fails + 1
            iv = self._interval(mode)
            wait = iv if r.online else min(iv * (2 ** min(fails, 3)), max(60, iv))
            stop.wait(wait)

    def _pruner(self) -> None:
        while not self._closing.wait(3600):
            try:
                n = self.store.prune(int(self.config.options.get("retention_days", 30)))
                if n:
                    log.info("Poda: %d lecturas antiguas eliminadas", n)
            except Exception:
                log.exception("Error podando la base de datos")

    def refresh(self) -> Dict[str, Any]:
        """Lee ya todos los dispositivos, sin esperar al siguiente ciclo de sondeo.

        Sirve cuando alguien los ha cambiado con otra app: por la nube la lectura es cada
        300 s por omisión y hasta entonces no se vería. Se deja pasar un mínimo entre dos
        refrescos para no gastar el cupo de llamadas de Tuya si se pulsa varias veces.
        """
        with self._refresh_lock:
            espera = MIN_REFRESH - (time.time() - self._refresh_ts)
            if espera > 0:
                return {"refrescado": False, "espera": round(espera, 1)}
            self._refresh_ts = time.time()
        if self.hub is not None:
            self.hub.invalidate()      # la primera lectura por nube la rellena y las demás la aprovechan
        with self._lock:
            tareas = [(d, p, self._stops.get(d)) for d, p in self.plugs.items()]
        if not tareas:
            return {"refrescado": True, "dispositivos": 0, "pendientes": 0}
        ex = ThreadPoolExecutor(max_workers=min(8, len(tareas)), thread_name_prefix="refresco")
        try:
            futuros = [ex.submit(lambda d=d, p=p, st=st: self._record(d, self._read(d, p), st)) for d, p, st in tareas]
            _, pendientes = wait(futuros, timeout=REFRESH_TIMEOUT)
        finally:
            ex.shutdown(wait=False)
        if pendientes:
            log.warning("Refresco: %d dispositivo(s) no contestaron en %.0f s", len(pendientes), REFRESH_TIMEOUT)
        return {"refrescado": True, "dispositivos": len(tareas), "pendientes": len(pendientes)}

    # ---- Órdenes -----------------------------------------------------------
    def set_power(self, dev_id: str, on: bool, manual: bool = True) -> Reading:
        plug = self.plugs.get(dev_id)
        if plug is None:
            raise KeyError(dev_id)
        plug.set_power(on)
        if manual:
            self.last_manual[dev_id] = time.time()
        r = self._read(dev_id, plug)
        self._record(dev_id, r, self._stops.get(dev_id))
        return r

    # Órdenes que admite cada tipo de dispositivo (protocolo genérico TeleHome).
    ACTIONS: Dict[str, tuple] = {"enchufe": ("switch",), "luz": luces.LIGHT_ACTIONS}

    def actions_for(self, dev_id: str) -> tuple:
        dev = self.config.get(dev_id)
        if dev is None:
            raise KeyError(dev_id)
        return self.ACTIONS.get(dev.get("type", "enchufe"), ())

    def light_state(self, dev_id: str) -> Dict[str, Any]:
        """Último estado conocido de una luz: {on, level, temp, mode, color}."""
        r = self.latest.get(dev_id)
        e = dict(r.extra or {}) if r is not None else {}
        e["on"] = None if r is None else r.on
        return e

    def command(self, dev_id: str, action: str, value: Any, manual: bool = True, fade: int = 0) -> Reading:
        """Orden genérica. Un enchufe solo admite «switch»; una luz, también brillo, temperatura, color y modo.
        Con `fade` (segundos) el brillo, el blanco o el color cambian poco a poco (solo en luces)."""
        if action not in self.actions_for(dev_id):
            raise ValueError("Orden «%s» no admitida por este dispositivo" % action)
        if manual:
            self.auto.cancelar(dev_id)      # una orden a mano manda sobre una transición en curso
        if fade:
            if self.config.get(dev_id).get("type") != "luz" or action not in ("level", "temp", "color"):
                raise ValueError("Solo se puede hacer una transición con el brillo, el blanco o el color de una luz")
            luces.plan(action, value)        # valida el valor antes de empezar
            self.auto.fade(dev_id, action, value, fade)
            if manual:
                self.last_manual[dev_id] = time.time()
            return self.latest.get(dev_id) or self._read(dev_id, self.plugs[dev_id])
        if action == "switch" or self.config.get(dev_id).get("type") != "luz":
            if not isinstance(value, bool):
                raise ValueError("«value» debe ser true o false")
            return self.set_power(dev_id, value, manual=manual)
        plug = self.plugs.get(dev_id)
        if plug is None:
            raise KeyError(dev_id)
        luces.plan(action, value)          # valida el valor antes de tocar nada
        plug.apply(action, value)
        if manual:
            self.last_manual[dev_id] = time.time()
        r = self._read(dev_id, plug)
        self._record(dev_id, r, self._stops.get(dev_id))
        return r

    def apply_scene(self, scene: Dict[str, Any], manual: bool = True, fade: int = 0) -> List[Dict[str, Any]]:
        """Deja cada dispositivo de la escena como dice. Una orden por dispositivo, en paralelo.
        Con `fade` (segundos) las luces llegan a su brillo poco a poco: el color o el blanco se ponen ya,
        el brillo arranca donde esté la luz (1 % si estaba apagada) y sube o baja durante la transición."""
        def uno(item: Dict[str, Any]) -> Dict[str, Any]:
            dev_id = item["device"]
            res = {"device": dev_id, "ok": False}
            dev = self.config.get(dev_id)
            plug = self.plugs.get(dev_id)
            if dev is None or plug is None:
                res["error"] = "el dispositivo ya no existe"
                return res
            try:
                self.auto.cancelar(dev_id)
                if dev.get("type") != "luz":
                    plug.set_power(bool(item.get("on", True)))
                elif fade > 0:
                    self._escena_con_fade(dev_id, dev, plug, item, fade)
                else:
                    plug.apply_steps(luces.plan_estado(item, dev))
                if manual:
                    self.last_manual[dev_id] = time.time()
                self._record(dev_id, self._read(dev_id, plug), self._stops.get(dev_id))
                res["ok"] = True
            except (PlugError, ValueError) as exc:
                res["error"] = str(exc)
            except Exception as exc:
                log.exception("Error aplicando la escena a %s", dev_id)
                res["error"] = "Error interno: %s" % exc
            return res
        items = list(scene.get("items", []))
        if len(items) <= 1:
            return [uno(i) for i in items]
        with ThreadPoolExecutor(max_workers=min(4, len(items)), thread_name_prefix="escena") as ex:
            return list(ex.map(uno, items))

    def _escena_con_fade(self, dev_id: str, dev: Dict[str, Any], plug, item: Dict[str, Any], fade: int) -> None:
        """Una luz dentro de una escena con transición: estado nuevo ya, brillo poco a poco."""
        cur = self.light_state(dev_id)
        if not item.get("on", True):                       # apagar poco a poco: bajar el brillo hasta apagarse
            if cur.get("on"):
                self.auto.fade(dev_id, "level", 0, fade)
            else:
                plug.set_power(False)
            return
        destino = item.get("level")
        arranque = int(cur.get("level") or 1) if cur.get("on") else 1
        plug.apply_steps(luces.plan_estado({**item, "level": arranque}, dev))
        if destino is not None and int(destino) != arranque:
            self.auto.fade(dev_id, "level", int(destino), fade)

    def group_command(self, group: Dict[str, Any], action: str, value: Any, manual: bool = True, fade: int = 0) -> List[Dict[str, Any]]:
        """Una orden a todos los miembros de un grupo. Los que no la admiten (un enchufe con «level») se saltan."""
        def uno(dev_id: str) -> Dict[str, Any]:
            res = {"device": dev_id, "ok": False}
            try:
                if action not in self.actions_for(dev_id):
                    res["skipped"] = True
                    return res
                self.command(dev_id, action, value, manual=manual, fade=fade if self._admite_fade(dev_id, action) else 0)
                res["ok"] = True
            except KeyError:
                res["error"] = "el dispositivo ya no existe"
            except (PlugError, ValueError) as exc:
                res["error"] = str(exc)
            except Exception as exc:
                log.exception("Error en la orden de grupo a %s", dev_id)
                res["error"] = "Error interno: %s" % exc
            return res
        ids = list(group.get("devices", []))
        if len(ids) <= 1:
            return [uno(i) for i in ids]
        with ThreadPoolExecutor(max_workers=min(4, len(ids)), thread_name_prefix="grupo") as ex:
            return list(ex.map(uno, ids))

    def _admite_fade(self, dev_id: str, action: str) -> bool:
        dev = self.config.get(dev_id) or {}
        return dev.get("type") == "luz" and action in ("level", "temp", "color")

    def raw(self, dev_id: str) -> Dict[str, Any]:
        """Lo que devuelve el dispositivo sin interpretar (códigos de la nube o DPS locales). En la nube cuesta una llamada."""
        plug = self.plugs.get(dev_id)
        if plug is None:
            raise KeyError(dev_id)
        dev = self.config.get(dev_id) or {}
        datos = plug.probe()
        return {"id": dev_id, "mode": dev.get("mode"), "type": dev.get("type"),
                "claves": "códigos de Tuya" if dev.get("mode") == "nube" else "DPS", "datos": datos}

    @staticmethod
    def _public_reading(r: Reading, luz: bool) -> Dict[str, Any]:
        if luz:
            e = r.extra or {}
            return {"ts": r.ts, "online": r.online, "on": r.on, "error": r.error,
                    "state": {"on": r.on, "br": e.get("level"), "temp": e.get("temp"), "mode": e.get("mode"),
                              "color": e.get("color"), "hex": e.get("hex")},
                    "values": {"br": r.level}}
        return {"ts": r.ts, "online": r.online, "on": r.on, "power_w": r.power_w,
                "voltage_v": r.voltage_v, "current_a": r.current_a, "error": r.error,
                "state": {"on": r.on},
                "values": {"p": r.power_w, "v": r.voltage_v, "i": r.current_a}}

    # ---- Estado --------------------------------------------------------------
    def state(self) -> List[Dict[str, Any]]:
        out = []
        with self._lock:
            for dev in self.config.devices:
                r = self.latest.get(dev["id"])
                acc = self._energy.get(dev["id"])
                kwh = None if acc is None else round(acc["kwh"], 4)
                luz = dev.get("type") == "luz"
                out.append({
                    "id": dev["id"],
                    # «state» y «values» son el modelo genérico de TeleHome; los campos
                    # planos (on, power_w...) se conservan para las apps anteriores.
                    "reading": None if r is None else self._public_reading(r, luz),
                    **({"caps": (r.extra or {}).get("caps", {}) if r else {}} if luz else {}),
                    "energy_today_kwh": kwh,
                    "accum": {"energy_today_kwh": kwh},
                })
        return out

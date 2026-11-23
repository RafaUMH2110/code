"""Acceso a los enchufes: Tuya local (TinyTuya) y un simulador para pruebas."""

from __future__ import annotations

import hashlib
import math
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


class PlugError(Exception):
    """Fallo de comunicación con un enchufe.

    El mensaje está escrito para quien usa la app; «detalle» guarda el texto
    técnico (excepción de red, respuesta cruda) para quien tenga que diagnosticar.
    """

    def __init__(self, mensaje: str, detalle: str = ""):
        super().__init__(mensaje)
        self.detalle = detalle


@dataclass
class Reading:
    ts: float
    online: bool
    on: Optional[bool] = None
    power_w: Optional[float] = None
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    error: Optional[str] = None


_ERR_HINTS = {
    "901": "No se puede conectar con el enchufe",
    "902": "El enchufe no responde (tiempo de espera agotado)",
    "904": "Respuesta no válida del enchufe",
    "905": "Enchufe no alcanzable en la red local",
    "908": "Datos de conexión incompletos",
    "914": "Local Key o versión de protocolo incorrectas",
    "917": "Local Key o versión de protocolo incorrectas",
}


def _scaled(dps: Dict[str, Any], dp: Any, scale: float) -> Optional[float]:
    raw = dps.get(str(dp))
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return round(float(raw) / scale, 3)
    except (TypeError, ValueError):
        return None


def parse_dps(dps: Dict[str, Any], dev: Dict[str, Any], ts: Optional[float] = None) -> Reading:
    """Convierte los DPS crudos de Tuya a unidades físicas según la configuración."""
    sw = dps.get(str(dev["dp_switch"]))
    return Reading(
        ts=ts if ts is not None else time.time(),
        online=True,
        on=bool(sw) if sw is not None else None,
        power_w=_scaled(dps, dev["dp_power"], dev["scale_power"]),
        voltage_v=_scaled(dps, dev["dp_voltage"], dev["scale_voltage"]),
        current_a=_scaled(dps, dev["dp_current"], dev["scale_current"]),
    )


def parse_cloud_status(status: Dict[str, Any], dev: Dict[str, Any], online: Optional[bool] = True,
                       ts: Optional[float] = None) -> Reading:
    """Igual que parse_dps, pero con los códigos de la nube (switch_1, cur_power...)."""
    sw = status.get(dev["code_switch"])
    return Reading(
        ts=ts if ts is not None else time.time(),
        online=online is not False,
        on=bool(sw) if sw is not None else None,
        power_w=_scaled(status, dev["code_power"], dev["scale_power"]),
        voltage_v=_scaled(status, dev["code_voltage"], dev["scale_voltage"]),
        current_a=_scaled(status, dev["code_current"], dev["scale_current"]),
    )


# Fallos de red hablando con un enchufe de la red local: el texto de la
# librería («[Errno 113] No route to host») no le dice nada a quien usa la app.
_FALLOS_LAN = (
    (("timed out", "timeout"), "El enchufe no contestó a tiempo: comprueba que está enchufado y con cobertura Wi-Fi."),
    (("no route to host", "network is unreachable", "host is unreachable", "unreachable"),
     "No se llega al enchufe: ¿está encendido y en la misma red que el servidor?"),
    (("connection refused",), "El enchufe rechazó la conexión: suele pasar si otra app lo tiene ocupado."),
    (("connection reset", "broken pipe", "connection aborted"), "El enchufe cortó la conexión antes de responder."),
    (("name or service not known", "getaddrinfo", "failed to resolve"),
     "No se pudo averiguar la dirección del enchufe: revisa su IP en los ajustes del enchufe."),
    (("invalid key", "decrypt", "payload"), "La Local Key no parece correcta: vuelve a copiarla desde la nube de Tuya."),
)


def _error_lan(exc: BaseException) -> PlugError:
    detalle = "%s: %s" % (type(exc).__name__, exc)
    if len(detalle) > 400:
        detalle = detalle[:400] + "…"
    texto = detalle.lower()
    for claves, msg in _FALLOS_LAN:
        if any(k in texto for k in claves):
            return PlugError(msg, detalle)
    return PlugError("No se pudo hablar con el enchufe en la red local; el detalle técnico dice qué ha fallado.", detalle)


def _error_text(resp: Dict[str, Any]) -> str:
    code = str(resp.get("Err", ""))
    base = _ERR_HINTS.get(code) or str(resp.get("Error") or "Error desconocido")
    return "%s (Err %s)" % (base, code) if code else base


class TuyaPlug:
    """Enchufe Tuya por LAN. Una única conexión TCP a la vez (cerrojo)."""

    def __init__(self, dev: Dict[str, Any]):
        self.dev = dev
        self.lock = threading.Lock()
        self._ip: Optional[str] = None if dev["ip"] == "Auto" else dev["ip"]

    def _resolve_ip(self) -> str:
        if self._ip:
            return self._ip
        import tinytuya  # import perezoso: el simulador no lo necesita

        found = tinytuya.find_device(self.dev["dev_id"])
        if not found.get("ip"):
            raise PlugError("No se encuentra el enchufe en la red (¿encendido y en la misma LAN?)")
        self._ip = found["ip"]
        return self._ip

    def _client(self):
        import tinytuya

        d = tinytuya.OutletDevice(
            self.dev["dev_id"], address=self._resolve_ip(), local_key=self.dev["local_key"],
            version=float(self.dev["version"]), connection_timeout=4,
            connection_retry_limit=1, connection_retry_delay=1,
        )
        d.set_socketPersistent(False)
        return d

    def _fail(self, resp: Dict[str, Any]) -> PlugError:
        if self.dev["ip"] == "Auto":
            self._ip = None  # puede haber cambiado de IP: se resuelve de nuevo
        return PlugError(_error_text(resp))

    def read(self) -> Reading:
        with self.lock:
            try:
                resp = self._client().status()
            except PlugError:
                raise
            except Exception as exc:  # errores de red/biblioteca
                raise _error_lan(exc)
            if not isinstance(resp, dict) or "dps" not in resp:
                raise self._fail(resp if isinstance(resp, dict) else {})
            return parse_dps(resp["dps"], self.dev)

    def set_power(self, on: bool) -> None:
        with self.lock:
            try:
                resp = self._client().set_status(bool(on), switch=self.dev["dp_switch"])
            except PlugError:
                raise
            except Exception as exc:
                raise _error_lan(exc)
            if isinstance(resp, dict) and (resp.get("Error") or resp.get("Err")):
                raise self._fail(resp)

    def probe(self) -> Dict[str, Any]:
        """DPS crudos (para localizar el mapa de datos de un modelo nuevo)."""
        with self.lock:
            resp = self._client().status()
        if not isinstance(resp, dict) or "dps" not in resp:
            raise self._fail(resp if isinstance(resp, dict) else {})
        return resp["dps"]


class CloudPlug:
    """Enchufe leído a través de la nube de Tuya (caché compartida en CloudHub)."""

    def __init__(self, dev: Dict[str, Any], hub, max_age):
        self.dev = dev
        self.hub = hub
        self._max_age = max_age  # función: segundos de validez de la caché

    def read(self) -> Reading:
        from .cloud import CloudError

        try:
            online, status = self.hub.status(self.dev["dev_id"], self._max_age())
        except CloudError as exc:
            raise PlugError(str(exc), exc.detalle)
        if online is False:
            raise PlugError("El enchufe aparece desconectado en la nube de Tuya")
        return parse_cloud_status(status, self.dev, online)

    def set_power(self, on: bool) -> None:
        from .cloud import CloudError

        try:
            self.hub.command(self.dev["dev_id"], self.dev["code_switch"], bool(on))
        except CloudError as exc:
            raise PlugError(str(exc), exc.detalle)

    def probe(self) -> Dict[str, Any]:
        from .cloud import CloudError

        try:
            return self.hub.status(self.dev["dev_id"], 0)[1]
        except CloudError as exc:
            raise PlugError(str(exc), exc.detalle)


class SimPlug:
    """Enchufe simulado: consumo plausible, conmutable y con fallo forzable."""

    def __init__(self, dev: Dict[str, Any]):
        self.dev = dev
        self.lock = threading.Lock()
        seed = int(hashlib.sha1(dev["dev_id"].encode()).hexdigest()[:8], 16)
        self._rnd = random.Random(seed)
        self.base_w = 20 + (seed % 180)
        self.on = True
        self.offline = False

    def read(self) -> Reading:
        with self.lock:
            if self.offline:
                raise PlugError("Enchufe no alcanzable en la red local (simulado)")
            now = time.time()
            if self.on:
                p = self.base_w * (1 + 0.15 * math.sin(now / 40.0)) + self._rnd.uniform(-1.5, 1.5)
            else:
                p = 0.0
            v = 230 + self._rnd.uniform(-1.5, 1.5)
            return Reading(ts=now, online=True, on=self.on, power_w=round(max(p, 0), 1),
                           voltage_v=round(v, 1), current_a=round(max(p, 0) / v, 3))

    def set_power(self, on: bool) -> None:
        with self.lock:
            if self.offline:
                raise PlugError("Enchufe no alcanzable en la red local (simulado)")
            self.on = bool(on)

    def probe(self) -> Dict[str, Any]:
        return {"1": self.on, "18": 0, "19": 0, "20": 2300}


def make_plug(dev: Dict[str, Any], simulate: bool = False, hub=None, max_age=None):
    if simulate:
        return SimPlug(dev)
    if dev.get("mode") == "nube":
        return CloudPlug(dev, hub, max_age or (lambda: 60))
    return TuyaPlug(dev)


def scan_network(duration: int = 12) -> list:
    """Busca enchufes Tuya por difusión UDP. Devuelve [{ip, dev_id, version}]."""
    import tinytuya

    try:
        found = tinytuya.deviceScan(verbose=False, scantime=duration, color=False, poll=False, byID=True)
    except TypeError:  # versiones antiguas de TinyTuya
        found = tinytuya.deviceScan(verbose=False, color=False, poll=False, byID=True)
    out = []
    for gw_id, info in (found or {}).items():
        out.append({"dev_id": gw_id, "ip": info.get("ip"), "version": str(info.get("version") or "")})
    return sorted(out, key=lambda r: r["ip"] or "")

"""Acceso a la nube de Tuya (IoT Core) para el modo nube.

Una única lectura por ciclo para todos los enchufes en modo nube (consulta por
lotes con caché compartida), de modo que el consumo de llamadas a la API no
crece con el número de enchufes.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("telehome-enchufes")

REGIONS = {
    "eu": "Europa central",
    "eu-w": "Europa occidental",
    "us": "EE. UU. oeste",
    "us-e": "EE. UU. este",
    "in": "India",
    "sg": "Singapur",
    "cn": "China",
}


class CloudError(Exception):
    """Fallo de la nube de Tuya (mensaje apto para el usuario)."""


def _msg(resp: Any) -> str:
    if isinstance(resp, dict):
        for k in ("msg", "Payload", "Error"):
            if resp.get(k):
                return str(resp[k])
        if resp.get("code"):
            return "código %s" % resp["code"]
    return "respuesta no válida"


# Ayuda para los errores de permisos más frecuentes de Tuya (lo que hay que
# cambiar en iot.tuya.com). Se busca por código y por texto del mensaje.
_AYUDA_PERMISOS = (
    (("28841105", "not authorized to call this api"),
     "El proyecto de Tuya no está autorizado a usar IoT Core. En iot.tuya.com → Cloud → Cloud Services, si en la "
     "fila de «IoT Core» la columna «Authorized Projects» está vacía, pulsa «View Details» → «Authorized Projects» → "
     "«Add Authorization», marca tu proyecto y pulsa «Confirm Authorization» (o, dentro del proyecto: «Service API» → "
     "«Go to Authorize» → «IoT Core»). Comprueba también que no ha caducado («Extend Trial Period») y que en "
     "«Devices» cada enchufe tiene «Device Permission» = «Controllable»."),
    (("28841106", "api is not subscribed"),
     "La API no está suscrita: en iot.tuya.com → tu proyecto → «Service API» → «Go to Authorize» suscribe "
     "«IoT Core» y «Authorization»."),
    (("1106", "permission deny"),
     "Sin permiso sobre el dispositivo: en iot.tuya.com → tu proyecto → «Devices», pulsa «Change» en la columna "
     "«Device Permission» del enchufe y elige «Controllable» (con «Read» solo se puede leer)."),
)


def _ayuda(texto: str) -> str:
    t = texto.lower()
    for claves, ayuda in _AYUDA_PERMISOS:
        if any(k in t for k in claves):
            return ayuda
    return ""


def _msg_codigo(resp: Any) -> str:
    """Mensaje de Tuya con su código, p. ej. «No permissions… (código 28841105)»."""
    m = _msg(resp)
    if isinstance(resp, dict) and resp.get("code") and str(resp["code"]) not in m:
        m += " (código %s)" % resp["code"]
    return m


def _ok(resp: Any) -> bool:
    return isinstance(resp, dict) and bool(resp.get("success")) and "Error" not in resp


def _status_map(items: Any) -> Dict[str, Any]:
    if isinstance(items, dict):
        return dict(items)
    out: Dict[str, Any] = {}
    for it in items or []:
        if isinstance(it, dict) and "code" in it:
            out[str(it["code"])] = it.get("value")
    return out


def _items(result: Any) -> List[Dict[str, Any]]:
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict):
        for k in ("devices", "list"):
            if isinstance(result.get(k), list):
                return [r for r in result[k] if isinstance(r, dict)]
    return []


def _online(item: Dict[str, Any]) -> Optional[bool]:
    for k in ("online", "is_online"):
        if k in item:
            return bool(item[k])
    return None


def default_client_factory(region: str, key: str, secret: str):
    import tinytuya

    try:
        c = tinytuya.Cloud(apiRegion=region, apiKey=key, apiSecret=secret, configFile="/nonexistent-telehome")
    except TypeError as exc:
        raise CloudError("Credenciales de la nube incompletas: %s" % exc)
    if not getattr(c, "token", None):
        raise CloudError("No se pudo iniciar sesión en la nube de Tuya: %s" % _msg(getattr(c, "error", None)))
    return c


class CloudHub:
    """Cliente compartido de la nube de Tuya con caché de estado por lotes."""

    def __init__(self, get_options: Callable[[], Dict[str, Any]], get_ids: Callable[[], List[str]],
                 client_factory: Callable[[str, str, str], Any] = default_client_factory):
        self._opts = get_options
        self._ids = get_ids
        self._factory = client_factory
        self._lock = threading.RLock()
        self._client = None
        self._cache: Dict[str, Tuple[Optional[bool], Dict[str, Any]]] = {}
        self._cache_ts = 0.0
        self._err: Optional[str] = None
        self._err_ts = 0.0
        self._strategy: Optional[str] = None
        self._cmd_strategy: Optional[str] = None
        self.calls = 0  # llamadas a la API desde el arranque (orientativo)

    # ---- sesión ---------------------------------------------------------
    def configured(self) -> bool:
        o = self._opts()
        return bool(o.get("cloud_api_key") and o.get("cloud_api_secret"))

    def reset(self) -> None:
        with self._lock:
            self._client = None
            self._cache, self._cache_ts = {}, 0.0
            self._err, self._err_ts = None, 0.0
            self._strategy = None
            self._cmd_strategy = None

    def _get_client(self):
        if self._client is None:
            if not self.configured():
                raise CloudError("Configura primero las credenciales de la nube de Tuya (Ajustes → Nube)")
            o = self._opts()
            self.calls += 1  # obtención del token
            self._client = self._factory(o.get("cloud_region", "eu"), o["cloud_api_key"], o["cloud_api_secret"])
        return self._client

    def _req(self, url: str, query: Optional[Dict[str, Any]] = None, post: Any = None, action: Optional[str] = None):
        c = self._get_client()
        self.calls += 1
        resp = c.cloudrequest(url, action=action, post=post, query=query)
        if isinstance(resp, dict) and str(resp.get("code")) in ("1010", "1011"):  # token caducado/no válido
            self._client = None
            c = self._get_client()
            self.calls += 1
            resp = c.cloudrequest(url, action=action, post=post, query=query)
        return resp

    # ---- lectura por lotes ---------------------------------------------
    def _fetch_devices_v1(self, ids: List[str]):
        r = self._req("/v1.0/devices", query={"device_ids": ",".join(ids)})
        if not _ok(r):
            raise CloudError(_msg_codigo(r))
        out = {}
        for it in _items(r.get("result")):
            did = it.get("id") or it.get("device_id")
            if did and "status" in it:
                out[did] = (_online(it), _status_map(it.get("status")))
        if not out:
            raise CloudError("sin datos de estado")
        return out

    def _fetch_iot03(self, ids: List[str]):
        q = {"device_ids": ",".join(ids)}
        r = self._req("/v1.0/iot-03/devices/status", query=q)
        if not _ok(r):
            raise CloudError(_msg_codigo(r))
        out = {}
        for it in _items(r.get("result")):
            did = it.get("id") or it.get("device_id")
            if did:
                out[did] = (None, _status_map(it.get("status")))
        if not out:
            raise CloudError("sin datos de estado")
        info = self._req("/v1.0/iot-03/devices", query=q)
        if _ok(info):
            for it in _items(info.get("result")):
                did = it.get("id")
                if did in out:
                    out[did] = (_online(it), out[did][1])
        return out

    def _fetch_each(self, ids: List[str]):
        c = self._get_client()
        out = {}
        for did in ids:
            self.calls += 2
            st = c.getstatus(did)
            if not _ok(st):
                raise CloudError(_msg(st))
            cs = c.getconnectstatus(did)
            online = cs.get("result") if isinstance(cs, dict) and isinstance(cs.get("result"), bool) else None
            out[did] = (online, _status_map(st.get("result")))
        return out

    def _fetch(self, ids: List[str]):
        strategies = [("v1", self._fetch_devices_v1), ("iot03", self._fetch_iot03), ("each", self._fetch_each)]
        if self._strategy:
            strategies.sort(key=lambda s: s[0] != self._strategy)
        last = None
        for name, fn in strategies:
            try:
                data = fn(ids)
                if self._strategy != name:
                    log.info("Nube de Tuya: lectura por el método «%s»", name)
                self._strategy = name
                return data
            except CloudError as exc:
                last = exc
                log.debug("Método de nube %s falló: %s", name, exc)
        ayuda = _ayuda(str(last))
        raise CloudError("Error de la nube de Tuya: %s" % last + (". " + ayuda if ayuda else ""))

    def status(self, dev_id: str, max_age: float) -> Tuple[Optional[bool], Dict[str, Any]]:
        with self._lock:
            now = time.time()
            if dev_id in self._cache and now - self._cache_ts < max_age:
                return self._cache[dev_id]
            if self._err and now - self._err_ts < max_age:
                raise CloudError(self._err)
            ids = list(dict.fromkeys(self._ids() + [dev_id]))
            try:
                self._cache = self._fetch(ids)
                self._cache_ts, self._err = now, None
            except CloudError as exc:
                self._err, self._err_ts = str(exc), now
                raise
            except Exception as exc:  # red, JSON...
                self._client = None
                self._err, self._err_ts = "Error de comunicación con la nube: %s" % exc, now
                raise CloudError(self._err)
            if dev_id not in self._cache:
                raise CloudError("La nube no devuelve datos de este Device ID (¿cuenta enlazada correcta?)")
            return self._cache[dev_id]

    # ---- órdenes y utilidades -------------------------------------------
    # Formas de enviar una orden, de la más habitual a la menos: cada proyecto de
    # Tuya tiene autorizadas unas u otras según cuándo se creó y qué servicios
    # tiene suscritos. Se recuerda la que funciona.
    _CMD_STRATEGIES = (
        ("iot03", "/v1.0/iot-03/devices/%s/commands", lambda code, value: {"commands": [{"code": code, "value": value}]}),
        ("v1", "/v1.0/devices/%s/commands", lambda code, value: {"commands": [{"code": code, "value": value}]}),
        ("shadow", "/v2.0/cloud/thing/%s/shadow/properties/issue", lambda code, value: {"properties": json.dumps({code: value})}),
    )

    def command(self, dev_id: str, code: str, value: Any) -> None:
        with self._lock:
            estrategias = list(self._CMD_STRATEGIES)
            if self._cmd_strategy:
                estrategias.sort(key=lambda e: e[0] != self._cmd_strategy)
            fallos = []
            for nombre, url, cuerpo in estrategias:
                try:
                    r = self._req(url % dev_id, post=cuerpo(code, value), action="POST")
                except CloudError:
                    raise
                except Exception as exc:
                    self._client = None
                    raise CloudError("Error de comunicación con la nube: %s" % exc)
                if _ok(r):
                    if self._cmd_strategy != nombre:
                        log.info("Nube de Tuya: órdenes por el método «%s»", nombre)
                    self._cmd_strategy = nombre
                    break
                fallos.append(_msg_codigo(r))
                log.debug("Orden por el método %s rechazada: %s", nombre, fallos[-1])
            else:
                # Se muestra el primer error (el del método principal) y, si es
                # de permisos, qué cambiar en la consola de Tuya.
                texto = "La nube rechazó la orden: %s" % fallos[0]
                ayuda = _ayuda(" ".join(fallos))
                raise CloudError(texto + (". " + ayuda if ayuda else ""))
            if dev_id in self._cache:  # actualización optimista: evita otra llamada
                online, st = self._cache[dev_id]
                st = dict(st)
                st[code] = value
                self._cache[dev_id] = (online, st)

    def list_devices(self) -> List[Dict[str, Any]]:
        with self._lock:
            c = self._get_client()
            self.calls += 2
            try:
                devs = c.getdevices()
            except Exception as exc:
                self._client = None
                raise CloudError("Error de comunicación con la nube: %s" % exc)
            if isinstance(devs, dict):
                raise CloudError("No se pudo obtener la lista de dispositivos: %s" % _msg(devs))
            out = []
            for d in devs or []:
                if isinstance(d, dict) and d.get("id"):
                    out.append({"dev_id": d["id"], "name": d.get("name") or d["id"], "key": d.get("key", ""),
                                "category": d.get("category", ""), "product_name": d.get("product_name", ""),
                                "online": d.get("online")})
            return out


class SimCloudHub:
    """Sustituto para --simulate: lista de dispositivos de ejemplo."""

    calls = 0

    def configured(self) -> bool:
        return True

    def reset(self) -> None:
        pass

    def list_devices(self) -> List[Dict[str, Any]]:
        return [{"dev_id": "simnube%05d" % i, "name": "Enchufe nube %d" % i, "key": "0123456789abcdef",
                 "category": "cz", "product_name": "Enchufe Wi-Fi con medidor", "online": True} for i in range(1, 4)]

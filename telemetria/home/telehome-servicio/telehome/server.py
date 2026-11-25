"""Servidor HTTP local: API JSON + interfaz web de un solo HTML."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from . import APP_NAME, __version__
from .cloud import REGIONS, CloudError
from .config import (DEVICE_TYPES, MAX_DEVICES, MAX_GROUPS, MAX_SCENES, MAX_SCHEDULES, Config, ConfigError,
                     public_device, verify_password)
from .devices import PlugError, scan_network
from .monitor import Monitor
from .pro import MAX_FADE
from .store import Store

log = logging.getLogger("telehome")

# Funciones que ofrece este servicio además de lo básico; las apps Pro miran esta lista.
FEATURES = ["luces", "escenas", "grupos", "transiciones", "temporizadores", "parametros-luz"]
STATIC_INDEX = Path(__file__).with_name("static") / "index.html"
MAX_BODY = 1_000_000
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
ADMIN_TTL = 12 * 3600          # s; duración de una sesión (administrador o usuario de confianza)
ADMIN_MAX_SESSIONS = 50
# Niveles de acceso, de menos a más: solo lectura, usuario de confianza (manda órdenes) y administrador.
NIVELES = ("none", "user", "admin")
# Lo que ve quien no es administrador: sin direcciones, identificadores ni mapas de datos de los dispositivos.
_CONFIG_FIELDS = ("dev_id", "ip", "version", "has_key")
_CONFIG_PREFIXES = ("dp_", "code_", "scale_")
_VIEW_OPTIONS = ("poll_interval", "cloud_poll_interval", "retention_days")


class AppContext:
    def __init__(self, config: Config, store: Store, monitor: Monitor, simulate: bool,
                 loopback_only: bool = True, extra_hosts: Optional[List[str]] = None, hub=None,
                 extra_origins: Optional[List[str]] = None, scheduler=None):
        self.config = config
        self.store = store
        self.monitor = monitor
        self.hub = hub if hub is not None else monitor.hub
        self.simulate = simulate
        self.loopback_only = loopback_only
        self.extra_hosts = {h.lower() for h in (extra_hosts or [])}
        self.allowed_hosts = LOOPBACK_HOSTS | self.extra_hosts
        # orígenes web externos autorizados a usar la API desde el navegador (CORS), p. ej. https://usuario.github.io
        self.extra_origins = {o.strip().rstrip("/").lower() for o in (extra_origins or []) if o.strip()}
        self.scheduler = scheduler
        self.scan_lock = threading.Lock()
        self.admin_tokens: Dict[str, Tuple[float, str, str]] = {}   # token -> (caduca, huella de las contraseñas, nivel)
        self.admin_lock = threading.Lock()


def _host_only(header: str) -> str:
    header = header.strip().lower()
    if header.startswith("["):
        return header[1:].split("]")[0]
    return header.split(":")[0]


class Handler(BaseHTTPRequestHandler):
    server_version = "TeleHome/" + __version__
    ctx: AppContext  # lo fija make_server

    # ---- modo Administrador ---------------------------------------------------
    def _admin_hash(self) -> str:
        return self.ctx.config.options.get("admin_password_hash") or ""

    def _user_hash(self) -> str:
        return self.ctx.config.options.get("user_password_hash") or ""

    @staticmethod
    def _fingerprint(stored: str) -> str:
        return hashlib.sha256(stored.encode("utf-8")).hexdigest()[:16]

    def _huella(self) -> str:
        """Cambiar cualquiera de las dos contraseñas invalida las sesiones abiertas."""
        return self._fingerprint(self._admin_hash() + "|" + self._user_hash())

    def _level(self) -> str:
        """Nivel de esta petición: «admin», «user» o «none».
        Sin ninguna contraseña puesta el servicio está abierto, como siempre."""
        if not self._admin_hash() and not self._user_hash():
            return "admin"
        tok = self.headers.get("X-TeleHome-Admin", "")
        if not tok:
            return "none"
        with self.ctx.admin_lock:
            ent = self.ctx.admin_tokens.get(tok)
        if not ent or ent[0] <= time.time() or ent[1] != self._huella():
            return "none"
        return ent[2]

    def _is_admin(self) -> bool:
        return self._level() == "admin"

    def _puede_mandar(self) -> bool:
        return self._level() in ("user", "admin")

    def _new_admin_token(self, nivel: str = "admin") -> str:
        tok = secrets.token_urlsafe(32)
        now = time.time()
        with self.ctx.admin_lock:
            toks = {t: e for t, e in self.ctx.admin_tokens.items() if e[0] > now}
            while len(toks) >= ADMIN_MAX_SESSIONS:                 # se descartan las más antiguas
                toks.pop(min(toks, key=lambda t: toks[t][0]))
            toks[tok] = (now + ADMIN_TTL, self._huella(), nivel)
            self.ctx.admin_tokens = toks
        return tok

    # ---- utilidades -------------------------------------------------------
    def log_message(self, fmt, *args):  # silencia el log por petición
        log.debug("%s - %s", self.address_string(), fmt % args)

    def _origin_ok(self) -> Optional[str]:
        """Devuelve el Origin de la petición si está en --allow-origin."""
        origin = (self.headers.get("Origin") or "").strip()
        if origin and origin.rstrip("/").lower() in self.ctx.extra_origins:
            return origin
        return None

    def _cors(self) -> None:
        origin = self._origin_ok()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")

    def _send(self, status: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self._cors()
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, obj: Any) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ConfigError("Petición demasiado grande")
        if n == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            raise ConfigError("JSON no válido")
        if not isinstance(data, (dict, list)):
            raise ConfigError("Se esperaba un objeto JSON")
        return data

    def _authorized(self) -> bool:
        stored = self.ctx.config.options.get("password_hash")
        if not stored:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                _, _, pw = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
            except (ValueError, UnicodeDecodeError):
                pw = None
            if pw is not None and verify_password(pw, stored):
                return True
        time.sleep(0.5)  # frena los intentos por fuerza bruta
        return False

    def _guard(self, method: str) -> Optional[str]:
        host = _host_only(self.headers.get("Host", ""))
        if self.ctx.loopback_only and host not in self.ctx.allowed_hosts:
            return "Host no permitido"  # protección frente a DNS rebinding
        if method != "GET":
            if self.headers.get("X-TeleHome") != "1":
                return "Falta la cabecera X-TeleHome"
            origin = self.headers.get("Origin")
            if origin:
                o = urlsplit(origin)
                same = o.netloc.lower() == self.headers.get("Host", "").lower()
                if not same and not self._origin_ok() and (o.hostname or "").lower() not in self.ctx.extra_hosts:
                    return "Origen no permitido"
        return None

    def _reto(self) -> Dict[str, str]:
        """Cabecera que hace que el navegador abra su diálogo de contraseña.

        Solo se envía cuando es una navegación (la página, que no sabe pedirla ella misma). Las
        peticiones de las apps (fetch/XHR, ``Sec-Fetch-Dest: empty``) reciben 401 a secas: así el
        navegador no lanza su diálogo y la app usa su propio campo de contraseña. Sin la cabecera
        ``Sec-Fetch-Dest`` (navegadores antiguos, curl) se mantiene el comportamiento de siempre.
        """
        destino = (self.headers.get("Sec-Fetch-Dest") or "").strip().lower()
        if destino in ("", "document", "iframe", "frame", "embed", "object"):
            return {"WWW-Authenticate": 'Basic realm="TeleHome", charset="UTF-8"'}
        return {}

    # ---- despacho -----------------------------------------------------------
    def _dispatch(self, method: str) -> None:
        try:
            denied = self._guard(method)
            if denied:
                return self._json(403, {"error": denied})
            if self.ctx.config.maybe_reload():  # cambios hechos desde la línea de órdenes
                if self.ctx.hub is not None:
                    self.ctx.hub.reset()
                self.ctx.monitor.sync()
            if not self._authorized():
                body = json.dumps({"error": "Se requiere contraseña"}).encode("utf-8")
                return self._send(401, body, "application/json; charset=utf-8", self._reto())
            url = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            for m, rx, fn in ROUTES:
                match = rx.match(url.path)
                if m == method and match:
                    if method != "GET" and fn not in SIN_SESION and fn not in SOLO_LEE:
                        if fn in SOLO_MANDO:
                            if not self._puede_mandar():
                                return self._json(403, {"error": "Hace falta la contraseña de usuario o de administrador",
                                                        "admin_required": True, "nivel_necesario": "user"})
                        elif not self._is_admin():
                            return self._json(403, {"error": "Se requiere el modo Administrador",
                                                    "admin_required": True, "nivel_necesario": "admin"})
                    return fn(self, query, *match.groups())
            self._json(404, {"error": "No encontrado"})
        except ConfigError as exc:
            self._json(400, {"error": str(exc)})
        except KeyError:
            self._json(404, {"error": "Enchufe no encontrado"})
        except (PlugError, CloudError) as exc:
            # El detalle técnico va aparte: la interfaz lo enseña solo si se pide.
            detalle = getattr(exc, "detalle", "")
            if detalle:
                log.warning("%s | %s", exc, detalle)
            self._json(502, {"error": str(exc), "detalle": detalle} if detalle else {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            log.exception("Error en %s %s", method, self.path)
            self._json(500, {"error": "Error interno"})

    def do_OPTIONS(self):
        """Preflight CORS: solo se responde a los orígenes autorizados con --allow-origin."""
        host = _host_only(self.headers.get("Host", ""))
        origin = self._origin_ok()
        if not origin or (self.ctx.loopback_only and host not in self.ctx.allowed_hosts):
            return self._json(403, {"error": "Origen no permitido"})
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-TeleHome, X-TeleHome-Admin, Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


# ---- rutas ----------------------------------------------------------------------

def _range(h: Handler, q: Dict[str, str]) -> Tuple[float, float]:
    try:
        span = int(q.get("range", 86400))
    except ValueError:
        raise ConfigError("range debe ser un número de segundos")
    keep = int(h.ctx.config.options["retention_days"]) * 86400
    span = max(60, min(span, keep))
    t1 = time.time()
    return t1 - span, t1


def _wanted(q: Dict[str, str], default: str = "all") -> str:
    """Identificador pedido: «dev» es el nombre genérico; «plug», el de las apps anteriores."""
    return q.get("dev") or q.get("plug") or default


def r_index(h: Handler, q):
    h._send(200, STATIC_INDEX.read_bytes(), "text/html; charset=utf-8",
            {"Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                        "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                        "connect-src 'self'; frame-ancestors 'none'"})


def r_health(h: Handler, q):
    # «app» no cambia, para que las apps anteriores sigan reconociendo el servicio;
    # «api» y «types» le dicen a la app genérica TeleHome que puede hablarle directamente.
    h._json(200, {"app": APP_NAME, "version": __version__, "ok": True,
                  "api": "telehome", "types": list(DEVICE_TYPES), "features": FEATURES,
                  "admin_required": bool(h._admin_hash()), "user_required": bool(h._user_hash())})


def r_state(h: Handler, q):
    c = h.ctx
    by_id = {s["id"]: s for s in c.monitor.state()}
    devices = []
    for dev in c.config.devices:
        item = public_device(dev)
        item.update({k: v for k, v in by_id.get(dev["id"], {}).items() if k != "id"})
        devices.append(item)
    hub = c.hub
    por_dia = c.store.api_calls_by_day(31)
    mes = time.strftime("%Y-%m")
    llamadas = {"configured": bool(hub and hub.configured()), "calls": getattr(hub, "calls", 0),
                "today": por_dia[-1]["n"], "yesterday": por_dia[-2]["n"],
                "month": sum(d["n"] for d in por_dia if d["day"].startswith(mes)),
                "last30": sum(d["n"] for d in por_dia[-30:]), "by_day": por_dia}
    nivel = h._level()
    admin = nivel == "admin"
    options = c.config.public_options()
    if not admin:    # modo solo lectura: se ve lo que miden los dispositivos, no cómo están configurados
        devices = [{k: v for k, v in d.items() if k not in _CONFIG_FIELDS and not k.startswith(_CONFIG_PREFIXES)} for d in devices]
        options = {k: options[k] for k in _VIEW_OPTIONS if k in options}
        llamadas = {"configured": False, "calls": 0, "today": 0, "yesterday": 0, "month": 0, "last30": 0, "by_day": []}
    h._json(200, {"app": APP_NAME, "version": __version__, "simulate": c.simulate,
                  "max_devices": MAX_DEVICES, "server_time": time.time(),
                  "api": "telehome", "types": list(DEVICE_TYPES), "features": FEATURES,
                  "admin": {"required": bool(h._admin_hash()), "active": admin},
                  "sesion": {"nivel": nivel, "admin_required": bool(h._admin_hash()), "user_required": bool(h._user_hash()),
                             "puede_mandar": nivel in ("user", "admin")},
                  "schedules": [dict(x) for x in c.config.schedules] if admin else [],
                  "max_schedules": MAX_SCHEDULES,
                  "scenes": [dict(x) for x in c.config.scenes], "groups": [dict(x) for x in c.config.groups],
                  "max_scenes": MAX_SCENES, "max_groups": MAX_GROUPS,
                  **c.monitor.auto.listar(),
                  "options": options, "regions": REGIONS,
                  "cloud": llamadas,
                  "devices": devices})


def r_power(h: Handler, q, dev_id):
    body = h._body()
    if not isinstance(body, dict) or not isinstance(body.get("on"), bool):
        raise ConfigError("Se esperaba {\"on\": true|false}")
    r = h.ctx.monitor.set_power(dev_id, body["on"])
    h._json(200, {"id": dev_id, "on": r.on, "online": r.online, "error": r.error})


def r_command(h: Handler, q, dev_id):
    """Orden genérica de TeleHome: {"action": "switch", "value": true|false}. Una luz admite además
    "level" (0-100), "temp" (0 cálida - 100 fría), "color" ("#rrggbb" o {"h","s","v"}) y "mode" ("white"|"colour")."""
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    try:
        r = h.ctx.monitor.command(dev_id, str(body.get("action") or ""), body.get("value"), fade=_fade(body))
    except ValueError as exc:
        raise ConfigError(str(exc))
    pub = h.ctx.monitor._public_reading(r, h.ctx.config.get(dev_id).get("type") == "luz")
    h._json(200, {"id": dev_id, "online": r.online, "error": r.error,
                  "state": pub["state"], "on": r.on})


def _fade(body: Dict[str, Any]) -> int:
    """Segundos de transición pedidos en una orden (0 = inmediata)."""
    try:
        f = int(body.get("fade") or 0)
    except (TypeError, ValueError):
        raise ConfigError("«fade» debe ser un número de segundos")
    if not 0 <= f <= MAX_FADE:
        raise ConfigError("«fade» debe estar entre 0 y %d segundos" % MAX_FADE)
    return f


def _obj(h: Handler) -> Dict[str, Any]:
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    return body


def r_scene_add(h: Handler, q):
    h._json(201, h.ctx.config.add_scene(_obj(h)))


def r_scene_upd(h: Handler, q, scene_id):
    h._json(200, h.ctx.config.update_scene(scene_id, _obj(h)))


def r_scene_del(h: Handler, q, scene_id):
    h.ctx.config.delete_scene(scene_id)
    h._json(200, {"deleted": scene_id})


def r_scene_apply(h: Handler, q, scene_id):
    """Aplica una escena: deja cada dispositivo como dice. Devuelve el resultado de cada uno."""
    sc = h.ctx.config.get_scene(scene_id)
    if sc is None:
        raise KeyError(scene_id)
    res = h.ctx.monitor.apply_scene(sc)
    h._json(200, {"id": scene_id, "ok": all(r["ok"] for r in res), "resultados": res})


def r_group_add(h: Handler, q):
    h._json(201, h.ctx.config.add_group(_obj(h)))


def r_group_upd(h: Handler, q, group_id):
    h._json(200, h.ctx.config.update_group(group_id, _obj(h)))


def r_group_del(h: Handler, q, group_id):
    h.ctx.config.delete_group(group_id)
    h._json(200, {"deleted": group_id})


def r_group_command(h: Handler, q, group_id):
    """Una orden a todo el grupo; los miembros que no la admiten se saltan."""
    g = h.ctx.config.get_group(group_id)
    if g is None:
        raise KeyError(group_id)
    body = _obj(h)
    accion = str(body.get("action") or "")
    if not accion:
        raise ConfigError("Falta «action»")
    res = h.ctx.monitor.group_command(g, accion, body.get("value"), fade=_fade(body))
    if res and all(r.get("skipped") for r in res):
        raise ConfigError("Ningún dispositivo del grupo admite la orden «%s»" % accion)
    h._json(200, {"id": group_id, "ok": all(r["ok"] or r.get("skipped") for r in res), "resultados": res})


def r_timer_set(h: Handler, q, dev_id):
    """Temporizador de una luz: {"minutes": 30, "action": "off"|"on", "fade": 0}."""
    body = _obj(h)
    try:
        t = h.ctx.monitor.auto.temporizador(dev_id, float(body.get("minutes") or 0), str(body.get("action") or "off"), _fade(body))
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc))
    h._json(200, t)


def r_timer_del(h: Handler, q, dev_id):
    h._json(200, {"cancelado": h.ctx.monitor.auto.cancelar_temporizador(dev_id)})


def r_raw(h: Handler, q, dev_id):
    """Datos sin interpretar del dispositivo, para ajustar códigos y escalas. Solo administradores."""
    if not h._is_admin():
        return h._json(403, {"error": "Se requiere el modo Administrador", "admin_required": True, "nivel_necesario": "admin"})
    h._json(200, h.ctx.monitor.raw(dev_id))


def r_refresh(h: Handler, q):
    """Lee ya los dispositivos (no espera al ciclo de sondeo). Lo puede pedir quien pueda ver el estado."""
    h._json(200, h.ctx.monitor.refresh())


def r_history(h: Handler, q):
    t0, t1 = _range(h, q)
    pts = max(50, min(int(q.get("points", 400)), 2000))
    wanted = _wanted(q)
    ids = [d["id"] for d in h.ctx.config.devices]
    if wanted != "all":
        if wanted not in ids:
            raise KeyError(wanted)
        ids = [wanted]
    h._json(200, {"from": t0, "to": t1,
                  "series": {i: h.ctx.store.history(i, t0, t1, pts) for i in ids}})


def r_summary(h: Handler, q):
    t0, t1 = _range(h, q)
    mon = h.ctx.monitor
    rows = {d["id"]: h.ctx.store.summary(d["id"], t0, t1, max(120.0, 6.0 * mon.interval_for(d["id"])))
            for d in h.ctx.config.devices}
    # «devices» es el nombre genérico; «plugs» se mantiene para las apps anteriores.
    h._json(200, {"from": t0, "to": t1, "devices": rows, "plugs": rows})


def r_csv(h: Handler, q):
    t0, t1 = _range(h, q)
    plug = _wanted(q, "")
    if h.ctx.config.get(plug) is None:
        raise KeyError(plug)
    luz = h.ctx.config.get(plug).get("type") == "luz"
    data = "".join(h.ctx.store.export_csv(plug, t0, t1, luz=luz)).encode("utf-8")
    fname = "telehome-%s-%s.csv" % (plug, time.strftime("%Y%m%d-%H%M"))
    h._send(200, data, "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="%s"' % fname})


def _changed(h: Handler) -> None:
    h.ctx.monitor.sync()


def r_dev_add(h: Handler, q):
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    dev = h.ctx.config.add_device(body)
    _changed(h)
    h._json(201, public_device(dev))


def r_dev_upd(h: Handler, q, dev_id):
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    dev = h.ctx.config.update_device(dev_id, body)
    _changed(h)
    h._json(200, public_device(dev))


def r_dev_del(h: Handler, q, dev_id):
    h.ctx.config.delete_device(dev_id)
    if q.get("keep_history") != "1":
        h.ctx.store.delete_plug(dev_id)
    _changed(h)
    h._json(200, {"deleted": dev_id})


def r_import(h: Handler, q):
    body = h._body()
    rows = body.get("devices") if isinstance(body, dict) else body
    mode = body.get("mode", "local") if isinstance(body, dict) else "local"
    if not isinstance(rows, list):
        raise ConfigError("Se esperaba una lista de dispositivos (devices.json de TinyTuya)")
    if mode not in ("local", "nube"):
        raise ConfigError("Modo no válido")
    report = h.ctx.config.import_devices(rows, mode, str(body.get("type") or "").lower() or None
                                         if isinstance(body, dict) else None)
    _changed(h)
    h._json(200, report)


def r_config_export(h: Handler, q):
    """Descarga toda la configuración (dispositivos, credenciales de Tuya y ajustes, sin la contraseña del servicio).
    Va por POST para que exija la cabecera X-TeleHome y no pueda pedirla otra web."""
    body = h._body()
    ruta = body.get("ruta") if isinstance(body, dict) else None      # la pone la interfaz: es por donde se llega al servicio
    data = json.dumps(h.ctx.config.export_config(ruta), ensure_ascii=False, indent=2).encode("utf-8")
    fname = "telehome-config-%s.json" % time.strftime("%Y%m%d")
    h._send(200, data, "application/json; charset=utf-8",
            {"Content-Disposition": 'attachment; filename="%s"' % fname})


def r_config_import(h: Handler, q):
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    data = body.get("config") if isinstance(body.get("config"), dict) else body
    modo = str(body.get("modo") or "reemplazar").strip().lower()
    if modo not in ("reemplazar", "añadir"):
        raise ConfigError("Modo no válido (reemplazar o añadir)")
    report = h.ctx.config.import_config(data, replace=(modo == "reemplazar"))
    if report.get("cloud_cambiada") and h.ctx.hub is not None:
        h.ctx.hub.reset()
    _changed(h)
    h._json(200, report)


def _entrar(h: Handler, pw: str, solo_admin: bool = False) -> Optional[str]:
    """Nivel que abre esta contraseña, o None si no abre ninguno."""
    adm, usr = h._admin_hash(), h._user_hash()
    if adm and verify_password(pw, adm):
        return "admin"
    if not solo_admin and usr and verify_password(pw, usr):
        return "user"
    return None


def r_login(h: Handler, q):
    """Abre sesión con la contraseña de administrador o la de usuario de confianza.
    Devuelve el nivel y un token que la app manda en X-TeleHome-Admin."""
    body = h._body()
    pw = str(body.get("password") or "") if isinstance(body, dict) else ""
    if not h._admin_hash() and not h._user_hash():
        return h._json(200, {"nivel": "admin", "required": False, "active": True})
    nivel = _entrar(h, pw)
    if nivel is None:
        time.sleep(0.5)  # frena los intentos por fuerza bruta
        return h._json(403, {"error": "Contraseña incorrecta"})
    h._json(200, {"nivel": nivel, "required": True, "active": nivel == "admin",
                  "token": h._new_admin_token(nivel), "expires_in": ADMIN_TTL})


def r_admin_login(h: Handler, q):
    """Igual que r_login pero solo acepta la contraseña de administrador (lo usan las apps anteriores)."""
    body = h._body()
    pw = str(body.get("password") or "") if isinstance(body, dict) else ""
    if not h._admin_hash():
        return h._json(200, {"nivel": "admin", "required": False, "active": True})
    if _entrar(h, pw, solo_admin=True) is None:
        time.sleep(0.5)
        return h._json(403, {"error": "Contraseña de administrador incorrecta"})
    h._json(200, {"nivel": "admin", "required": True, "active": True,
                  "token": h._new_admin_token("admin"), "expires_in": ADMIN_TTL})


def r_logout(h: Handler, q):
    tok = h.headers.get("X-TeleHome-Admin", "")
    with h.ctx.admin_lock:
        h.ctx.admin_tokens.pop(tok, None)
    abierto = not h._admin_hash() and not h._user_hash()
    h._json(200, {"nivel": "admin" if abierto else "none", "required": bool(h._admin_hash()), "active": abierto})


def r_user_password(h: Handler, q):
    """Pone, cambia o quita la contraseña del usuario de confianza (solo un administrador)."""
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    h.ctx.config.set_user_password(None if body.get("quitar") else str(body.get("password") or ""))
    nuevo = h._new_admin_token("admin")        # cambiar contraseñas cierra las sesiones; el administrador conserva la suya
    with h.ctx.admin_lock:
        h.ctx.admin_tokens = {t: e for t, e in h.ctx.admin_tokens.items() if t == nuevo}
    h._json(200, {"user_required": bool(h._user_hash()), "token": nuevo, "expires_in": ADMIN_TTL})


def r_admin_password(h: Handler, q):
    """Pone, cambia o quita la contraseña de administrador (solo un administrador puede). Cierra todas las sesiones."""
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    if body.get("quitar"):
        h.ctx.config.set_admin_password(None)
        with h.ctx.admin_lock:
            h.ctx.admin_tokens = {}
        return h._json(200, {"required": False, "active": True})
    pw = str(body.get("password") or "")
    h.ctx.config.set_admin_password(pw)
    with h.ctx.admin_lock:
        h.ctx.admin_tokens = {}
    h._json(200, {"required": True, "active": True, "token": h._new_admin_token(), "expires_in": ADMIN_TTL})


def r_password(h: Handler, q):
    """Cambia o quita la contraseña del servicio (solo un administrador). La actual no se puede mostrar:
    se guarda con PBKDF2 y no hay forma de recuperarla."""
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    if body.get("quitar"):
        h.ctx.config.set_password(None)
    else:
        h.ctx.config.set_password(str(body.get("password") or ""))
    h._json(200, h.ctx.config.public_options())


def _sched_body(h: Handler) -> Dict[str, Any]:
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    return body


def r_sched_add(h: Handler, q):
    sch = h.ctx.config.add_schedule(_sched_body(h))
    h._json(201, sch)


def r_sched_upd(h: Handler, q, sched_id):
    h._json(200, h.ctx.config.update_schedule(sched_id, _sched_body(h)))


def r_sched_del(h: Handler, q, sched_id):
    h.ctx.config.delete_schedule(sched_id)
    h._json(200, {"deleted": sched_id})


def r_sched_run(h: Handler, q, sched_id):
    """Dispara una programación ahora mismo, para probarla sin esperar a su hora."""
    sch = h.ctx.config.get_schedule(sched_id)
    if sch is None:
        raise KeyError(sched_id)
    motor = h.ctx.scheduler
    if motor is None:                 # servidor levantado sin hilo de programaciones: vale uno de usar y tirar
        from .scheduler import Scheduler
        motor = Scheduler(h.ctx.config, h.ctx.monitor, h.ctx.store)
    ahora = time.time()
    resultado = motor.ejecutar_ahora(sch, ahora)
    h._json(200, {"id": sched_id, "resultado": resultado})


def r_place(h: Handler, q):
    """Lugar para calcular el amanecer y el anochecer."""
    body = _sched_body(h)
    h._json(200, h.ctx.config.set_place(body.get("lat"), body.get("lon")))


def r_sun(h: Handler, q):
    """Amanecer y anochecer de hoy, para que la app los enseñe junto a las programaciones."""
    from .sun import LAT_POR_DEFECTO, LON_POR_DEFECTO, _eventos
    from datetime import date as _date
    lat = float(h.ctx.config.options.get("lat", LAT_POR_DEFECTO))
    lon = float(h.ctx.config.options.get("lon", LON_POR_DEFECTO))
    amanece, anochece = _eventos(_date.today(), lat, lon)
    h._json(200, {"lat": lat, "lon": lon, "sunrise": amanece, "sunset": anochece})


def r_options(h: Handler, q):
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    h._json(200, h.ctx.config.set_options(body))


def r_cloud_set(h: Handler, q):
    body = h._body()
    if not isinstance(body, dict):
        raise ConfigError("Se esperaba un objeto JSON")
    opts = h.ctx.config.set_cloud(body)
    if h.ctx.hub is not None:
        h.ctx.hub.reset()
    h._json(200, opts)


def _cloud_list(h: Handler):
    if h.ctx.hub is None:
        raise ConfigError("Modo nube no disponible")
    devs = h.ctx.hub.list_devices()
    known = {d["dev_id"] for d in h.ctx.config.devices}
    for d in devs:
        d["configured"] = d["dev_id"] in known
        d.pop("key", None)  # la Local Key no sale por la API
    return devs


def r_cloud_test(h: Handler, q):
    devs = _cloud_list(h)
    h._json(200, {"ok": True, "devices": len(devs)})


def r_cloud_devices(h: Handler, q):
    h._json(200, {"found": _cloud_list(h)})


def r_cloud_import(h: Handler, q):
    """Añade en modo nube los Device ID indicados (guardando también su Local Key)."""
    body = h._body()
    ids = body.get("dev_ids") if isinstance(body, dict) else None
    if not isinstance(ids, list) or not ids:
        raise ConfigError("Se esperaba {\"dev_ids\": [...]}")
    # Sin «type», cada dispositivo toma el tipo de su categoría en Tuya (bombillas y tiras → luz).
    dtype = str((body.get("type") if isinstance(body, dict) else None) or "").strip().lower() or None
    if dtype is not None and dtype not in DEVICE_TYPES:
        raise ConfigError("Tipo de dispositivo no admitido por este servicio (%s)" % ", ".join(DEVICE_TYPES))
    wanted = {str(i) for i in ids}
    rows = [d for d in h.ctx.hub.list_devices() if d["dev_id"] in wanted]
    report = h.ctx.config.import_devices(rows, "nube", dtype)
    _changed(h)
    h._json(200, report)


def r_discover(h: Handler, q):
    c = h.ctx
    if not c.scan_lock.acquire(blocking=False):
        return h._json(409, {"error": "Ya hay una búsqueda en curso"})
    try:
        if c.simulate:
            found = [{"dev_id": "sim%07d" % (i + 90), "ip": "192.168.1.%d" % (100 + i), "version": "3.3"} for i in range(2)]
        else:
            try:
                found = scan_network()
            except ImportError:
                raise ConfigError("Falta TinyTuya (pip install tinytuya)")
        known = {d["dev_id"] for d in c.config.devices}
        for f in found:
            f["configured"] = f["dev_id"] in known
        h._json(200, {"found": found})
    finally:
        c.scan_lock.release()


def _r(pattern: str) -> "re.Pattern":
    return re.compile("^" + pattern + "$")


ROUTES: List[Tuple[str, "re.Pattern", Callable]] = [
    ("GET", _r(r"/"), r_index),
    ("GET", _r(r"/api/health"), r_health),
    ("GET", _r(r"/api/state"), r_state),
    ("POST", _r(r"/api/refresh"), r_refresh),
    ("GET", _r(r"/api/history"), r_history),
    ("GET", _r(r"/api/summary"), r_summary),
    ("GET", _r(r"/api/export\.csv"), r_csv),
    ("POST", _r(r"/api/plugs/([a-z0-9-]+)/power"), r_power),      # compatibilidad
    ("POST", _r(r"/api/devices/([a-z0-9-]+)/command"), r_command),
    ("POST", _r(r"/api/devices/([a-z0-9-]+)/timer"), r_timer_set),
    ("DELETE", _r(r"/api/devices/([a-z0-9-]+)/timer"), r_timer_del),
    ("GET", _r(r"/api/devices/([a-z0-9-]+)/raw"), r_raw),
    ("POST", _r(r"/api/scenes"), r_scene_add),
    ("PUT", _r(r"/api/scenes/([a-z0-9-]+)"), r_scene_upd),
    ("DELETE", _r(r"/api/scenes/([a-z0-9-]+)"), r_scene_del),
    ("POST", _r(r"/api/scenes/([a-z0-9-]+)/apply"), r_scene_apply),
    ("POST", _r(r"/api/groups"), r_group_add),
    ("PUT", _r(r"/api/groups/([a-z0-9-]+)"), r_group_upd),
    ("DELETE", _r(r"/api/groups/([a-z0-9-]+)"), r_group_del),
    ("POST", _r(r"/api/groups/([a-z0-9-]+)/command"), r_group_command),
    ("POST", _r(r"/api/devices"), r_dev_add),
    ("POST", _r(r"/api/devices/import"), r_import),
    ("PUT", _r(r"/api/devices/([a-z0-9-]+)"), r_dev_upd),
    ("DELETE", _r(r"/api/devices/([a-z0-9-]+)"), r_dev_del),
    ("POST", _r(r"/api/login"), r_login),
    ("POST", _r(r"/api/logout"), r_logout),
    ("POST", _r(r"/api/admin/login"), r_admin_login),      # compatibilidad con las apps anteriores
    ("POST", _r(r"/api/admin/logout"), r_logout),
    ("PUT", _r(r"/api/admin/password"), r_admin_password),
    ("PUT", _r(r"/api/user-password"), r_user_password),
    ("POST", _r(r"/api/config/export"), r_config_export),
    ("POST", _r(r"/api/config/import"), r_config_import),
    ("GET", _r(r"/api/sun"), r_sun),
    ("POST", _r(r"/api/schedules"), r_sched_add),
    ("PUT", _r(r"/api/schedules/([a-z0-9-]+)"), r_sched_upd),
    ("DELETE", _r(r"/api/schedules/([a-z0-9-]+)"), r_sched_del),
    ("POST", _r(r"/api/schedules/([a-z0-9-]+)/run"), r_sched_run),
    ("PUT", _r(r"/api/place"), r_place),
    ("PUT", _r(r"/api/options"), r_options),
    ("PUT", _r(r"/api/password"), r_password),
    ("PUT", _r(r"/api/cloud"), r_cloud_set),
    ("POST", _r(r"/api/cloud/test"), r_cloud_test),
    ("POST", _r(r"/api/cloud/devices"), r_cloud_devices),
    ("POST", _r(r"/api/cloud/import"), r_cloud_import),
    ("POST", _r(r"/api/discover"), r_discover),
]


# Abrir y cerrar sesión no exige sesión; mandar órdenes basta con la de usuario; todo lo demás, administrador.
SIN_SESION = {r_login, r_logout, r_admin_login}
# Solo lee: no cambia nada, así que no exige ni usuario ni administrador (basta con poder ver el estado).
SOLO_LEE = {r_refresh}
SOLO_MANDO = {r_power, r_command, r_scene_apply, r_group_command, r_timer_set, r_timer_del}


def make_server(ctx: AppContext, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"ctx": ctx})
    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer.daemon_threads = True
    return ThreadingHTTPServer((host, port), handler)

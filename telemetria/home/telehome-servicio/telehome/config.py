"""Configuración persistente (JSON) con validación y límite de enchufes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import unicodedata
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import luces

MAX_DEVICES = 7
MIN_POLL = 5            # s; los medidores de energía Tuya no admiten sondeos locales más rápidos
MIN_CLOUD_POLL = 60     # s; la cuenta gratuita de Tuya tiene un cupo de llamadas muy limitado
MAX_POLL = 3600
VERSIONS = ("3.1", "3.2", "3.3", "3.4", "3.5")
MODES = ("local", "nube")
# Tipos de dispositivo que sabe leer este servicio. La app genérica TeleHome los
# consulta en api/health y api/state y deshabilita en el alta los que no estén.
DEVICE_TYPES = ("enchufe", "luz")
CLOUD_REGIONS = ("eu", "eu-w", "us", "us-e", "in", "sg", "cn")

# ---- Programaciones -------------------------------------------------------
MAX_SCHEDULES = 32
MAX_SCENES = 24
MAX_GROUPS = 8
MAX_FADE = 3600                                   # s; transición más larga que se admite
SCHEDULE_ACTIONS = ("switch", "level", "temp", "color", "mode", "position", "stop", "scene")
FADE_ACTIONS = ("level", "temp", "color")         # las órdenes que admiten transición
WHEN_KINDS = ("clock", "sunrise", "sunset")      # hora fija, amanecer o anochecer
CONDITION_OPS = ("<", "<=", ">", ">=")
MAX_OFFSET = 720                                  # min; desplazamiento sobre el amanecer o el anochecer
MAX_CONDITION_FOR = 86400                         # s; cuánto puede exigirse que la condición se mantenga
_HORA_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

OPTION_DEFAULTS: Dict[str, Any] = {
    "poll_interval": 10,
    "cloud_poll_interval": 300,
    "retention_days": 30,
    "cloud_region": "eu",
    "cloud_api_key": "",
    "cloud_api_secret": "",
    "password_hash": "",
    "admin_password_hash": "",   # modo Administrador: sin él, cualquiera que llegue al servicio puede cambiarlo todo
    "user_password_hash": "",    # usuario de confianza: puede mandar órdenes, pero no cambiar nada
    # Lugar, para calcular el amanecer y el anochecer de las programaciones
    "lat": 38.2699,
    "lon": -0.7126,
}
SECRET_OPTIONS = ("cloud_api_secret", "password_hash", "admin_password_hash", "user_password_hash")

# Exportación de la configuración para compartirla con otro usuario. Lleva las credenciales
# de la nube de Tuya y la Local Key de cada enchufe; NUNCA la contraseña del servicio.
EXPORT_FORMAT = "telehome-config"
EXPORT_VERSION = 1
EXPORT_OPTIONS = ("poll_interval", "cloud_poll_interval", "retention_days", "cloud_region",
                  "cloud_api_key", "cloud_api_secret", "lat", "lon")
_ID_RE = re.compile(r"^[a-z0-9-]{1,40}$")
_RUTA_RE = re.compile(r"^(/[^\s\"<>]{0,200}|https?://[^\s\"<>]{1,200})$")


def clean_ruta(ruta: Any) -> str:
    """Ruta del servicio TeleHome (/rafa/telehome/ o una URL completa). Cadena vacía si no es válida."""
    ruta = str(ruta or "").strip()
    return ruta if _RUTA_RE.match(ruta) else ""

# Valores típicos de un enchufe Tuya con medidor. En modo local se usan los
# números de DPS; en modo nube, los códigos estándar de Tuya.
DEVICE_DEFAULTS: Dict[str, Any] = {
    "type": "enchufe",
    "room": "",
    "mode": "local",
    "ip": "Auto",
    "version": "3.3",
    "dp_switch": 1,
    "dp_power": 19,
    "dp_voltage": 20,
    "dp_current": 18,
    "code_switch": "switch_1",
    "code_power": "cur_power",
    "code_voltage": "cur_voltage",
    "code_current": "cur_current",
    "scale_power": 10.0,      # potencia = valor / 10  (W)
    "scale_voltage": 10.0,    # tensión  = valor / 10  (V)
    "scale_current": 1000.0,  # corriente = valor / 1000 (A, el dato viene en mA)
}

# Campos propios de cada tipo (el resto son comunes). Al cambiar de tipo, los del tipo anterior se descartan.
TYPE_FIELDS = {
    "enchufe": ("dp_switch", "dp_power", "dp_voltage", "dp_current", "code_switch", "code_power", "code_voltage",
                "code_current", "scale_power", "scale_voltage", "scale_current"),
    "luz": luces.LIGHT_FIELDS,
}
COMMON_FIELDS = ("id", "slot", "type", "mode", "name", "room", "dev_id", "local_key", "ip", "version")
TYPE_DEFAULTS = {
    "enchufe": {k: DEVICE_DEFAULTS[k] for k in TYPE_FIELDS["enchufe"]},
    "luz": dict(luces.LIGHT_DEFAULTS),
}
NOMBRE_TIPO = {"enchufe": "enchufe", "luz": "luz"}

_DEV_ID_RE = re.compile(r"^[A-Za-z0-9]{8,40}$")
_CODE_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_PBKDF2_ITER = 200_000


class ConfigError(ValueError):
    """Error de validación con mensaje apto para mostrar al usuario."""


def data_dir(override: Optional[str] = None) -> Path:
    if override:
        return Path(override).expanduser()
    env = os.environ.get("TELEHOME_DIR")
    if env:
        return Path(env).expanduser()
    if sys.platform == "darwin":
        nuevo = Path.home() / "Library" / "Application Support" / "telehome"
        viejo = Path.home() / "Library" / "Application Support" / "telehome-enchufes"
    else:
        nuevo = Path.home() / ".telehome"
        viejo = Path.home() / ".telehome-enchufes"
    # instalaciones anteriores: si solo existe la carpeta con el nombre antiguo, se sigue usando (no se pierden datos)
    return viejo if viejo.exists() and not nuevo.exists() else nuevo


def _slug(text: str) -> str:
    """Identificador a partir del nombre. Las tildes y la eñe se reducen a su letra base,
    para que «Habitación» dé «habitacion» y no «habitaci-n»."""
    base = unicodedata.normalize("NFKD", text.lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return s[:24] or "enchufe"


def _num(raw: Dict[str, Any], key: str, lo: float, hi: float, as_int: bool = False):
    value = raw.get(key, DEVICE_DEFAULTS.get(key, luces.LIGHT_DEFAULTS.get(key)))
    try:
        value = int(value) if as_int else float(value)
    except (TypeError, ValueError):
        raise ConfigError("«%s» debe ser un número" % key)
    if not lo <= value <= hi:
        raise ConfigError("«%s» debe estar entre %s y %s" % (key, lo, hi))
    return value


def _code(raw: Dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or DEVICE_DEFAULTS.get(key) or luces.LIGHT_DEFAULTS.get(key) or "").strip()
    if not _CODE_RE.match(value):
        raise ConfigError("«%s» debe ser un código Tuya (minúsculas, números y _)" % key)
    return value


def normalize_device(raw: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Valida un dispositivo. Si `existing` se indica, los campos ausentes se heredan."""
    base = dict(existing) if existing else {}
    nuevo_tipo = str(raw.get("type") or "").strip().lower()
    if base and nuevo_tipo and nuevo_tipo != base.get("type", "enchufe"):
        # cambio de tipo: se conservan los datos de la cuenta y el dispositivo, no los códigos del tipo anterior
        base = {k: v for k, v in base.items() if k in COMMON_FIELDS}
    dtype = str(raw.get("type") or base.get("type") or "enchufe").strip().lower()
    if dtype not in DEVICE_TYPES:
        raise ConfigError("Tipo de dispositivo no admitido por este servicio (%s)" % ", ".join(DEVICE_TYPES))
    merged = {**DEVICE_DEFAULTS, **TYPE_DEFAULTS[dtype], **base, **{k: v for k, v in raw.items() if v is not None}}
    merged["type"] = dtype
    quien = NOMBRE_TIPO[dtype]

    mode = str(merged.get("mode") or "local").strip().lower()
    if mode not in MODES:
        raise ConfigError("Modo no válido (local o nube)")

    name = str(merged.get("name", "")).strip()
    if not name:
        raise ConfigError("El nombre del %s es obligatorio" % quien)
    if len(name) > 40:
        raise ConfigError("El nombre no puede superar 40 caracteres")

    room = re.sub(r"\s+", " ", str(merged.get("room") or "")).strip()
    if len(room) > 24:
        raise ConfigError("La estancia no puede superar 24 caracteres")

    dev_id = str(merged.get("dev_id", "")).strip()
    if not _DEV_ID_RE.match(dev_id):
        raise ConfigError("Device ID no válido (8-40 caracteres alfanuméricos)")

    key = str(raw.get("local_key") or base.get("local_key") or "").strip()
    if mode == "local" and not key:
        raise ConfigError("Falta la Local Key del %s (necesaria en modo local)" % quien)
    if len(key) > 64:
        raise ConfigError("Local Key demasiado larga")

    ip = str(merged.get("ip") or "Auto").strip()
    if ip.lower() == "auto":
        ip = "Auto"
    else:
        try:
            ip = str(ipaddress.IPv4Address(ip))
        except ValueError:
            raise ConfigError("La IP debe ser una dirección IPv4 válida o «Auto»")

    version = str(merged.get("version"))
    if version not in VERSIONS:
        raise ConfigError("Versión de protocolo no válida (%s)" % ", ".join(VERSIONS))

    out = {
        "id": base.get("id") or raw.get("id") or "",
        "slot": base.get("slot", raw.get("slot")),  # color fijo del dispositivo (0-6)
        "type": dtype,
        "mode": mode,
        "name": name,
        "room": room,
        "dev_id": dev_id,
        "local_key": key,
        "ip": ip,
        "version": version,
    }
    for campo in TYPE_FIELDS[dtype]:
        if campo.startswith("dp_"):
            out[campo] = _num(merged, campo, 1, 255, True)
        elif campo.startswith("code_"):
            out[campo] = _code(merged, campo)
        elif campo in ("level_min", "level_max"):
            out[campo] = _num(merged, campo, 1, 100, True)
        elif campo in ("kelvin_min", "kelvin_max"):
            out[campo] = _num(merged, campo, 1000, 12000, True)
        else:
            out[campo] = _num(merged, campo, 0.001, 1e6)
    if dtype == "luz":
        if out["level_min"] > out["level_max"]:
            raise ConfigError("El brillo mínimo no puede ser mayor que el máximo")
        if out["kelvin_min"] >= out["kelvin_max"]:
            raise ConfigError("El blanco cálido (K) debe ser menor que el frío")
    return out


def normalize_schedule(raw: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Valida una programación. Si `existing` se indica, los campos ausentes se heredan."""
    base = dict(existing) if existing else {}
    m = {**base, **{k: v for k, v in raw.items() if v is not None}}

    nombre = str(m.get("name", "")).strip()
    if not nombre:
        raise ConfigError("El nombre de la programación es obligatorio")
    if len(nombre) > 40:
        raise ConfigError("El nombre no puede superar 40 caracteres")

    device = str(m.get("device", "") or "").strip()
    action = str(m.get("action", "")).strip().lower()
    if action not in SCHEDULE_ACTIONS:
        raise ConfigError("Orden no válida (%s)" % ", ".join(SCHEDULE_ACTIONS))
    if action == "scene":
        device = ""                                   # una escena lleva sus propios dispositivos
    elif not device:
        raise ConfigError("Falta el dispositivo de la programación")
    elif device.startswith("grupo:") and not _ID_RE.match(device[6:]):
        raise ConfigError("Grupo no válido")

    value = m.get("value")
    if action == "scene":
        value = str(value or "").strip()
        if not _ID_RE.match(value):
            raise ConfigError("«scene» necesita el identificador de una escena")
    elif action == "switch":
        if not isinstance(value, bool):
            raise ConfigError("«switch» necesita un valor true o false")
    elif action in ("level", "position", "temp"):
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ConfigError("«%s» necesita un porcentaje de 0 a 100" % action)
        if not 0 <= value <= 100:
            raise ConfigError("«%s» necesita un porcentaje de 0 a 100" % action)
    elif action == "color":
        try:
            h, s_, v_ = luces.parse_color_arg(value)
        except ValueError as exc:
            raise ConfigError(str(exc))
        value = luces.hsv_to_hex(h, s_, v_)       # se guarda como «#rrggbb»
    elif action == "mode":
        if value not in luces.MODES:
            raise ConfigError("«mode» debe ser «white» (blanco) o «colour» (color)")
    else:
        value = None

    cuando = m.get("when") or {}
    if not isinstance(cuando, dict):
        raise ConfigError("«when» debe ser un objeto")
    kind = str(cuando.get("kind", "clock")).strip().lower()
    if kind not in WHEN_KINDS:
        raise ConfigError("Momento no válido (%s)" % ", ".join(WHEN_KINDS))
    when: Dict[str, Any] = {"kind": kind}
    if kind == "clock":
        hora = str(cuando.get("time", "")).strip()
        if not _HORA_RE.match(hora):
            raise ConfigError("La hora debe tener la forma HH:MM (00:00 a 23:59)")
        when["time"] = hora
    else:
        try:
            off = int(cuando.get("offset", 0) or 0)
        except (TypeError, ValueError):
            raise ConfigError("El desplazamiento debe ser un número de minutos")
        if not -MAX_OFFSET <= off <= MAX_OFFSET:
            raise ConfigError("El desplazamiento debe estar entre -%d y %d minutos" % (MAX_OFFSET, MAX_OFFSET))
        when["offset"] = off

    # Sin días marcados se ejecuta una sola vez, la próxima vez que llegue ese momento.
    dias = m.get("days", [])
    if not isinstance(dias, list):
        raise ConfigError("Los días deben ser una lista")
    try:
        dias = sorted({int(d) for d in dias})
    except (TypeError, ValueError):
        raise ConfigError("Los días deben ser números del 1 (lunes) al 7 (domingo)")
    if any(d < 1 or d > 7 for d in dias):
        raise ConfigError("Los días deben ser números del 1 (lunes) al 7 (domingo)")

    cond = m.get("condition")
    condition = None
    if cond:
        if not isinstance(cond, dict):
            raise ConfigError("«condition» debe ser un objeto")
        metric = str(cond.get("metric", "")).strip().lower()
        if not re.match(r"^[a-z_]{1,12}$", metric):
            raise ConfigError("La magnitud de la condición no es válida")
        op = str(cond.get("op", "")).strip()
        if op not in CONDITION_OPS:
            raise ConfigError("El operador de la condición debe ser %s" % ", ".join(CONDITION_OPS))
        try:
            umbral = float(cond.get("value"))
        except (TypeError, ValueError):
            raise ConfigError("El valor de la condición debe ser un número")
        try:
            durante = int(cond.get("for", 0) or 0)
        except (TypeError, ValueError):
            raise ConfigError("«for» debe ser un número de segundos")
        if not 0 <= durante <= MAX_CONDITION_FOR:
            raise ConfigError("«for» debe estar entre 0 y %d segundos" % MAX_CONDITION_FOR)
        condition = {"metric": metric, "op": op, "value": umbral, "for": durante}

    if (action == "scene" or device.startswith("grupo:")) and condition:
        raise ConfigError("Las escenas y los grupos no admiten condición")

    try:
        fade = int(m.get("fade", 0) or 0)
    except (TypeError, ValueError):
        raise ConfigError("«fade» debe ser un número de segundos")
    if not 0 <= fade <= MAX_FADE:
        raise ConfigError("«fade» debe estar entre 0 y %d segundos" % MAX_FADE)
    if fade and action not in FADE_ACTIONS:
        raise ConfigError("Solo se puede hacer una transición con brillo, blanco o color")

    creado = base.get("created", raw.get("created"))
    return {
        "id": base.get("id") or raw.get("id") or "",
        "name": nombre,
        "enabled": bool(m.get("enabled", True)),
        "device": device,
        "action": action,
        "value": value,
        "when": when,
        "days": dias,
        "condition": condition,
        "skip_if_manual": bool(m.get("skip_if_manual", False)),
        **({"fade": fade} if fade else {}),
        "last_fire": float(base.get("last_fire") or 0),
        "last_result": base.get("last_result") or "",
        # Cuándo se creó. Nunca se dispara un momento anterior a esto, para que crear a las 07:30
        # una programación de las 07:00 no la ejecute en el acto.
        "created": float(creado) if creado is not None else time.time(),
        "once": not dias,
    }


def _clean_ids(raw: Any, que: str, maximo: int = MAX_DEVICES) -> List[str]:
    if not isinstance(raw, list):
        raise ConfigError("«%s» debe ser una lista" % que)
    out: List[str] = []
    for x in raw:
        x = str(x or "").strip()
        if not _ID_RE.match(x):
            raise ConfigError("Identificador de dispositivo no válido en «%s»" % que)
        if x not in out:
            out.append(x)
    if len(out) > maximo:
        raise ConfigError("Demasiados dispositivos (máximo %d)" % maximo)
    return out


def normalize_group(raw: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Grupo: un nombre y una lista de dispositivos que se manejan juntos."""
    m = {**(existing or {}), **{k: v for k, v in raw.items() if v is not None}}
    nombre = re.sub(r"\s+", " ", str(m.get("name", ""))).strip()
    if not nombre:
        raise ConfigError("El nombre del grupo es obligatorio")
    if len(nombre) > 40:
        raise ConfigError("El nombre no puede superar 40 caracteres")
    devices = _clean_ids(m.get("devices", []), "devices")
    if len(devices) < 1:
        raise ConfigError("Un grupo necesita al menos un dispositivo")
    return {"id": (existing or {}).get("id") or raw.get("id") or "", "name": nombre, "devices": devices}


def normalize_scene(raw: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Escena: para cada dispositivo, cómo debe quedar. Un elemento es
    {"device", "on", "mode", "level", "temp", "color"}; en un enchufe solo cuenta «on»."""
    m = {**(existing or {}), **{k: v for k, v in raw.items() if v is not None}}
    nombre = re.sub(r"\s+", " ", str(m.get("name", ""))).strip()
    if not nombre:
        raise ConfigError("El nombre de la escena es obligatorio")
    if len(nombre) > 40:
        raise ConfigError("El nombre no puede superar 40 caracteres")
    items = m.get("items", [])
    if not isinstance(items, list) or not items:
        raise ConfigError("Una escena necesita al menos un dispositivo")
    if len(items) > MAX_DEVICES:
        raise ConfigError("Demasiados dispositivos (máximo %d)" % MAX_DEVICES)
    out, vistos = [], set()
    for it in items:
        if not isinstance(it, dict):
            raise ConfigError("Cada elemento de la escena debe ser un objeto")
        dev = str(it.get("device", "")).strip()
        if not _ID_RE.match(dev):
            raise ConfigError("Falta el dispositivo de un elemento de la escena")
        if dev in vistos:
            raise ConfigError("Un dispositivo aparece dos veces en la escena")
        vistos.add(dev)
        on = it.get("on", True)
        if not isinstance(on, bool):
            raise ConfigError("«on» debe ser true o false")
        el: Dict[str, Any] = {"device": dev, "on": on}
        if on:
            try:
                pasos = luces.plan_estado({k: it.get(k) for k in ("mode", "level", "temp", "color") if it.get(k) is not None})
            except ValueError as exc:
                raise ConfigError(str(exc))
            for k, v in pasos:
                if k == "mode":
                    el["mode"] = v
                elif k == "level":
                    el["level"] = v
                elif k == "temp":
                    el["temp"] = v
                elif k == "color":
                    el["color"] = luces.hsv_to_hex(v[0], v[1], 100)
                    el["level"] = v[2]            # en modo color el brillo es el valor del color
        out.append(el)
    return {"id": (existing or {}).get("id") or raw.get("id") or "", "name": nombre, "items": out}


def public_device(dev: Dict[str, Any]) -> Dict[str, Any]:
    """Vista del enchufe sin la Local Key (nunca sale por la API)."""
    out = {k: v for k, v in dev.items() if k != "local_key"}
    out["has_key"] = bool(dev.get("local_key"))
    return out


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
    return "pbkdf2_sha256$%d$%s$%s" % (_PBKDF2_ITER, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt, dk = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


class Config:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.options: Dict[str, Any] = dict(OPTION_DEFAULTS)
        self.devices: List[Dict[str, Any]] = []
        self.schedules: List[Dict[str, Any]] = []
        self.scenes: List[Dict[str, Any]] = []
        self.groups: List[Dict[str, Any]] = []
        self._mtime: Optional[float] = None
        self.load()

    # ---- E/S -----------------------------------------------------------
    def _stat(self) -> Optional[float]:
        try:
            return self.path.stat().st_mtime_ns
        except OSError:
            return None

    def load(self) -> None:
        with self.lock:
            if not self.path.exists():
                return
            try:
                data = json.loads(self.path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                raise ConfigError("No se puede leer %s: %s" % (self.path, exc))
            self.options = {**OPTION_DEFAULTS, **data.get("options", {})}
            self.devices = []
            self.schedules = []
            self.scenes = []
            self.groups = []
            for raw in data.get("schedules", [])[:MAX_SCHEDULES]:
                try:
                    sch = normalize_schedule(raw)
                except ConfigError:
                    continue                      # una programación rota no impide arrancar
                sch["id"] = raw.get("id") or self._new_sched_id(sch["name"])
                self.schedules.append(sch)
            for raw in data.get("devices", [])[:MAX_DEVICES]:
                dev = normalize_device(raw)
                dev["id"] = raw.get("id") or self._new_id(dev["name"])
                dev["slot"] = self._free_slot(dev.get("slot"))
                self.devices.append(dev)
            for clave, norm, lista, tope in (("scenes", normalize_scene, self.scenes, MAX_SCENES),
                                             ("groups", normalize_group, self.groups, MAX_GROUPS)):
                for raw in data.get(clave, [])[:tope]:
                    try:
                        el = norm(raw)
                    except ConfigError:
                        continue                  # una escena o un grupo roto no impide arrancar
                    el["id"] = raw.get("id") if _ID_RE.match(str(raw.get("id") or "")) else self._new_pro_id(el["name"], lista)
                    lista.append(el)
            self._mtime = self._stat()

    def maybe_reload(self) -> bool:
        """Recarga si otro proceso (la línea de órdenes) ha cambiado el fichero."""
        with self.lock:
            m = self._stat()
            if m is None or m == self._mtime:
                return False
            try:
                self.load()
            except ConfigError:
                self._mtime = m  # fichero roto: se conserva lo que hay en memoria
                return False
            return True

    def save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps({"options": self.options, "devices": self.devices, "schedules": self.schedules,
                                  "scenes": self.scenes, "groups": self.groups},
                                 ensure_ascii=False, indent=2)
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".cfg-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            self._mtime = self._stat()

    # ---- Enchufes ------------------------------------------------------
    def _new_id(self, name: str) -> str:
        used = {d["id"] for d in self.devices}
        base = _slug(name)
        cand, n = base, 2
        while cand in used:
            cand = "%s-%d" % (base, n)
            n += 1
        return cand

    def _free_slot(self, wanted: Optional[int] = None) -> int:
        """Color estable: el enchufe conserva su hueco aunque se borren otros."""
        used = {d.get("slot") for d in self.devices}
        if isinstance(wanted, int) and 0 <= wanted < MAX_DEVICES and wanted not in used:
            return wanted
        return next(i for i in range(MAX_DEVICES + 1) if i not in used)

    def get(self, dev_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return next((d for d in self.devices if d["id"] == dev_id), None)

    def cloud_ids(self) -> List[str]:
        with self.lock:
            return [d["dev_id"] for d in self.devices if d["mode"] == "nube"]

    def add_device(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if len(self.devices) >= MAX_DEVICES:
                raise ConfigError("Máximo %d enchufes: elimina uno antes de añadir otro" % MAX_DEVICES)
            dev = normalize_device(raw)
            if any(d["dev_id"] == dev["dev_id"] for d in self.devices):
                raise ConfigError("Ese Device ID ya está configurado")
            dev["id"] = self._new_id(dev["name"])
            dev["slot"] = self._free_slot()
            self.devices.append(dev)
            self.save()
            return dev

    def update_device(self, dev_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            cur = self.get(dev_id)
            if cur is None:
                raise KeyError(dev_id)
            new = normalize_device({k: v for k, v in raw.items() if k not in ("id", "has_key", "slot")}, cur)
            if any(d["dev_id"] == new["dev_id"] and d["id"] != dev_id for d in self.devices):
                raise ConfigError("Ese Device ID ya está configurado")
            new["id"] = dev_id
            self.devices[self.devices.index(cur)] = new
            self.save()
            return new

    def delete_device(self, dev_id: str) -> None:
        with self.lock:
            cur = self.get(dev_id)
            if cur is None:
                raise KeyError(dev_id)
            self.devices.remove(cur)
            self._purge_device(dev_id)
            self.save()

    def retype_device(self, dev_id: str, tipo: str) -> Dict[str, Any]:
        """Cambia el tipo de un dispositivo (p. ej. enchufe → luz) con los códigos por omisión del nuevo tipo."""
        with self.lock:
            cur = self.get(dev_id)
            if cur is None:
                raise KeyError(dev_id)
            if cur.get("type") == tipo:
                return cur
            new = normalize_device({"type": tipo}, cur)
            new["id"] = dev_id
            self.devices[self.devices.index(cur)] = new
            self.save()
            return new

    def import_devices(self, rows: List[Dict[str, Any]], mode: str = "local", dtype: Optional[str] = None) -> Dict[str, Any]:
        """Importa el devices.json de TinyTuya o la lista de la nube (id/dev_id, key, name, ip, version).

        El tipo sale de la categoría de Tuya (bombillas y tiras → luz, lo demás → enchufe) salvo que se indique."""
        added, skipped = [], []
        for row in rows:
            if not isinstance(row, dict):
                continue
            tipo = dtype or ("luz" if str(row.get("category") or "") in luces.LIGHT_CATEGORIES else "enchufe")
            name = row.get("name") or row.get("id") or row.get("dev_id") or NOMBRE_TIPO[tipo].capitalize()
            raw = {
                "type": tipo,
                "mode": mode,
                "name": str(name)[:40],
                "dev_id": row.get("id") or row.get("dev_id"),
                "local_key": row.get("key") or row.get("local_key"),
                "ip": row.get("ip") if mode == "local" and row.get("ip") else "Auto",
                "version": str(row.get("version") or "3.3"),
            }
            if raw["version"] not in VERSIONS:
                raw["version"] = "3.3"
            try:
                added.append(self.add_device(raw)["name"])
            except ConfigError as exc:
                skipped.append({"name": str(name), "motivo": str(exc)})
        return {"añadidos": added, "omitidos": skipped}

    # ---- Programaciones ------------------------------------------------
    def _new_sched_id(self, name: str) -> str:
        usados = {s["id"] for s in self.schedules}
        base, n, cand = _slug(name) or "prog", 2, _slug(name) or "prog"
        while cand in usados:
            cand, n = "%s-%d" % (base, n), n + 1
        return cand

    def _new_pro_id(self, name: str, lista: List[Dict[str, Any]]) -> str:
        usados = {x["id"] for x in lista}
        base = _slug(name) or "x"
        n, cand = 2, base
        while cand in usados:
            cand, n = "%s-%d" % (base, n), n + 1
        return cand

    def _check_device(self, dev_id: str) -> None:
        if dev_id.startswith("grupo:"):
            if not any(g["id"] == dev_id[6:] for g in self.groups):
                raise ConfigError("No hay ningún grupo con el identificador «%s»" % dev_id[6:])
            return
        if not any(d["id"] == dev_id for d in self.devices):
            raise ConfigError("No hay ningún dispositivo con el identificador «%s»" % dev_id)

    def _check_members(self, ids: List[str]) -> None:
        for dev_id in ids:
            if not any(d["id"] == dev_id for d in self.devices):
                raise ConfigError("No hay ningún dispositivo con el identificador «%s»" % dev_id)

    def get_scene(self, scene_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return next((x for x in self.scenes if x["id"] == scene_id), None)

    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return next((x for x in self.groups if x["id"] == group_id), None)

    def add_scene(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if len(self.scenes) >= MAX_SCENES:
                raise ConfigError("Máximo %d escenas" % MAX_SCENES)
            sc = normalize_scene(raw)
            self._check_members([i["device"] for i in sc["items"]])
            sc["id"] = self._new_pro_id(sc["name"], self.scenes)
            self.scenes.append(sc)
            self.save()
            return sc

    def update_scene(self, scene_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            cur = self.get_scene(scene_id)
            if cur is None:
                raise KeyError(scene_id)
            nuevo = normalize_scene({k: v for k, v in raw.items() if k != "id"}, cur)
            self._check_members([i["device"] for i in nuevo["items"]])
            nuevo["id"] = scene_id
            self.scenes[self.scenes.index(cur)] = nuevo
            self.save()
            return nuevo

    def delete_scene(self, scene_id: str) -> None:
        with self.lock:
            cur = self.get_scene(scene_id)
            if cur is None:
                raise KeyError(scene_id)
            self.scenes.remove(cur)
            self.save()

    def add_group(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if len(self.groups) >= MAX_GROUPS:
                raise ConfigError("Máximo %d grupos" % MAX_GROUPS)
            g = normalize_group(raw)
            self._check_members(g["devices"])
            g["id"] = self._new_pro_id(g["name"], self.groups)
            self.groups.append(g)
            self.save()
            return g

    def update_group(self, group_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            cur = self.get_group(group_id)
            if cur is None:
                raise KeyError(group_id)
            nuevo = normalize_group({k: v for k, v in raw.items() if k != "id"}, cur)
            self._check_members(nuevo["devices"])
            nuevo["id"] = group_id
            self.groups[self.groups.index(cur)] = nuevo
            self.save()
            return nuevo

    def delete_group(self, group_id: str) -> None:
        with self.lock:
            cur = self.get_group(group_id)
            if cur is None:
                raise KeyError(group_id)
            self.groups.remove(cur)
            self.save()

    def _purge_device(self, dev_id: str) -> None:
        """Quita un dispositivo borrado de las escenas y los grupos (y las que se quedan vacías)."""
        for sc in list(self.scenes):
            sc["items"] = [i for i in sc["items"] if i["device"] != dev_id]
            if not sc["items"]:
                self.scenes.remove(sc)
        for g in list(self.groups):
            g["devices"] = [d for d in g["devices"] if d != dev_id]
            if not g["devices"]:
                self.groups.remove(g)

    def _check_target(self, sch: Dict[str, Any]) -> None:
        if sch["action"] == "scene":
            if self.get_scene(sch["value"]) is None:
                raise ConfigError("No hay ninguna escena con el identificador «%s»" % sch["value"])
        else:
            self._check_device(sch["device"])

    def get_schedule(self, sched_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return next((s for s in self.schedules if s["id"] == sched_id), None)

    def add_schedule(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if len(self.schedules) >= MAX_SCHEDULES:
                raise ConfigError("Máximo %d programaciones" % MAX_SCHEDULES)
            sch = normalize_schedule(raw)
            self._check_target(sch)
            sch["id"] = self._new_sched_id(sch["name"])
            self.schedules.append(sch)
            self.save()
            return sch

    def update_schedule(self, sched_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            cur = next((s for s in self.schedules if s["id"] == sched_id), None)
            if cur is None:
                raise KeyError(sched_id)
            nuevo = normalize_schedule({k: v for k, v in raw.items() if k != "id"}, cur)
            self._check_target(nuevo)
            nuevo["id"] = sched_id
            self.schedules[self.schedules.index(cur)] = nuevo
            self.save()
            return nuevo

    def delete_schedule(self, sched_id: str) -> None:
        with self.lock:
            cur = next((s for s in self.schedules if s["id"] == sched_id), None)
            if cur is None:
                raise KeyError(sched_id)
            self.schedules.remove(cur)
            self.save()

    def mark_schedule(self, sched_id: str, cuando: float, resultado: str, desactivar: bool = False) -> None:
        """Anota que una programación se ha evaluado, para no repetirla y poder mostrar qué pasó."""
        with self.lock:
            cur = next((s for s in self.schedules if s["id"] == sched_id), None)
            if cur is None:
                return
            cur["last_fire"] = cuando
            cur["last_result"] = resultado[:120]
            if desactivar:
                cur["enabled"] = False
            self.save()

    def set_place(self, lat: Any, lon: Any) -> Dict[str, Any]:
        """Lugar para calcular el amanecer y el anochecer."""
        with self.lock:
            try:
                la, lo = float(lat), float(lon)
            except (TypeError, ValueError):
                raise ConfigError("La latitud y la longitud deben ser números")
            if not -90 <= la <= 90 or not -180 <= lo <= 180:
                raise ConfigError("Latitud entre -90 y 90, longitud entre -180 y 180")
            self.options = {**self.options, "lat": la, "lon": lo}
            self.save()
            return self.public_options()

    # ---- Exportar / importar toda la configuración ---------------------
    def export_config(self, ruta: Optional[str] = None) -> Dict[str, Any]:
        """Configuración completa y portable: dispositivos (con su Local Key), credenciales de Tuya y ajustes.
        Excluye la contraseña del servicio (password_hash). `ruta` es dónde se llega a este servicio
        (p. ej. /rafa/telehome/): el servicio no la conoce (va detrás de un proxy), así que la pone quien exporta."""
        if ruta not in (None, "") and not clean_ruta(ruta):
            raise ConfigError("La ruta del servicio no es válida (usa /ruta/ o http(s)://servidor/ruta/)")
        with self.lock:
            return {
                "format": EXPORT_FORMAT,
                "version": EXPORT_VERSION,
                "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "aviso": "Este fichero contiene credenciales de Tuya y las Local Key de tus dispositivos: compártelo solo con quien debas.",
                **({"servicio": {"ruta": clean_ruta(ruta)}} if ruta else {}),
                "options": {k: self.options.get(k, OPTION_DEFAULTS[k]) for k in EXPORT_OPTIONS},
                "devices": [dict(d) for d in self.devices],
                "schedules": [{k: v for k, v in s.items() if k not in ("last_fire", "last_result", "created")}
                              for s in self.schedules],
                "scenes": [dict(x) for x in self.scenes],
                "groups": [dict(x) for x in self.groups],
            }

    def _clean_export_options(self, raw: Any) -> Dict[str, Any]:
        """Valida las opciones de un fichero exportado sin tocar nada (lanza ConfigError si algo no vale)."""
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ConfigError("«options» debe ser un objeto")
        out: Dict[str, Any] = {}
        if "poll_interval" in raw:
            out["poll_interval"] = self._int_opt(raw, "poll_interval", MIN_POLL, MAX_POLL, "Intervalo local (s)")
        if "cloud_poll_interval" in raw:
            out["cloud_poll_interval"] = self._int_opt(raw, "cloud_poll_interval", MIN_CLOUD_POLL, MAX_POLL, "Intervalo de la nube (s)")
        if "retention_days" in raw:
            out["retention_days"] = self._int_opt(raw, "retention_days", 1, 3650, "Retención (días)")
        for clave in ("lat", "lon"):
            if clave in raw:
                try:
                    v = float(raw[clave])
                except (TypeError, ValueError):
                    raise ConfigError("«%s» debe ser un número" % clave)
                tope = 90 if clave == "lat" else 180
                if not -tope <= v <= tope:
                    raise ConfigError("«%s» fuera de rango" % clave)
                out[clave] = v
        if "cloud_region" in raw:
            region = str(raw["cloud_region"] or "").strip()
            if region not in CLOUD_REGIONS:
                raise ConfigError("Región de la nube no válida (%s)" % ", ".join(CLOUD_REGIONS))
            out["cloud_region"] = region
        key = str(raw.get("cloud_api_key") or "").strip()
        secret = str(raw.get("cloud_api_secret") or "").strip()
        for label, v in (("Access ID", key), ("Access Secret", secret)):
            if v and not re.match(r"^[A-Za-z0-9]{8,64}$", v):
                raise ConfigError("%s del fichero no es válido" % label)
        if key and secret:                 # las credenciales vacías no borran las que ya tiene quien importa
            out["cloud_api_key"], out["cloud_api_secret"] = key, secret
        return out

    def import_config(self, data: Any, replace: bool = True) -> Dict[str, Any]:
        """Aplica un fichero producido por export_config.
        replace=True: los dispositivos pasan a ser los del fichero (se conserva el id de los que ya existían);
        replace=False: se añaden solo los que no estén. La contraseña del servicio no se toca nunca."""
        if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
            raise ConfigError("No es un fichero de configuración de TeleHome (falta «format»: «%s»)" % EXPORT_FORMAT)
        try:
            version = int(data.get("version", 0))
        except (TypeError, ValueError):
            version = 0
        if version < 1 or version > EXPORT_VERSION:
            raise ConfigError("Versión del fichero no admitida (%s): actualiza TeleHome" % data.get("version"))
        raw_devs = data.get("devices", [])
        if not isinstance(raw_devs, list):
            raise ConfigError("«devices» debe ser una lista")
        with self.lock:
            opts = self._clean_export_options(data.get("options"))     # si falla, no se ha tocado nada
            report: Dict[str, Any] = {"añadidos": [], "actualizados": [], "omitidos": [], "opciones": sorted(opts)}
            current = list(self.devices)
            idmap: Dict[str, str] = {}            # id que traía el fichero -> id que ha quedado
            by_devid = {d["dev_id"]: d for d in current}
            result: List[Dict[str, Any]] = [] if replace else list(current)
            seen = {d["dev_id"] for d in result}
            for raw in raw_devs:
                name = str((raw or {}).get("name") or "Enchufe")[:40] if isinstance(raw, dict) else "Enchufe"
                try:
                    if not isinstance(raw, dict):
                        raise ConfigError("Entrada no válida")
                    dev = normalize_device({k: v for k, v in raw.items() if k not in ("id", "slot", "has_key")})
                except ConfigError as exc:
                    report["omitidos"].append({"name": name, "motivo": str(exc)})
                    continue
                if dev["dev_id"] in seen:
                    report["omitidos"].append({"name": name, "motivo": "Ese Device ID ya está configurado"})
                    continue
                if len(result) >= MAX_DEVICES:
                    report["omitidos"].append({"name": name, "motivo": "Máximo %d enchufes" % MAX_DEVICES})
                    continue
                prev = by_devid.get(dev["dev_id"])
                used_ids = {d["id"] for d in result}
                wanted = (prev or {}).get("id") or (raw.get("id") if isinstance(raw.get("id"), str) else "")
                if wanted and _ID_RE.match(wanted) and wanted not in used_ids:
                    dev["id"] = wanted
                else:
                    base, n, cand = _slug(dev["name"]), 2, _slug(dev["name"])
                    while cand in used_ids:
                        cand, n = "%s-%d" % (base, n), n + 1
                    dev["id"] = cand
                taken = {d.get("slot") for d in result}
                want_slot = (prev or {}).get("slot", raw.get("slot"))
                dev["slot"] = want_slot if isinstance(want_slot, int) and 0 <= want_slot < MAX_DEVICES and want_slot not in taken \
                    else next(i for i in range(MAX_DEVICES + 1) if i not in taken)
                result.append(dev)
                seen.add(dev["dev_id"])
                if isinstance(raw.get("id"), str):
                    idmap[raw["id"]] = dev["id"]
                report["actualizados" if prev else "añadidos"].append(dev["name"])
            self.options = {**self.options, **opts}
            self.devices = result
            # Programaciones: solo las que apunten a un dispositivo que haya quedado
            ids = {d["id"] for d in self.devices}
            nuevas, usados = [], set()
            for raw in (data.get("schedules") or []):
                if len(nuevas) >= MAX_SCHEDULES:
                    break
                try:
                    sch = normalize_schedule(raw if isinstance(raw, dict) else {})
                except ConfigError as exc:
                    report["omitidos"].append({"name": str((raw or {}).get("name", "programación"))[:40], "motivo": str(exc)})
                    continue
                if sch["device"] and not sch["device"].startswith("grupo:"):
                    sch["device"] = idmap.get(sch["device"], sch["device"])
                if sch["device"] and not sch["device"].startswith("grupo:") and sch["device"] not in ids:
                    report["omitidos"].append({"name": sch["name"], "motivo": "Su dispositivo no está en el fichero"})
                    continue
                base, n, cand = _slug(sch["name"]) or "prog", 2, _slug(sch["name"]) or "prog"
                while cand in usados:
                    cand, n = "%s-%d" % (base, n), n + 1
                sch["id"], _ = cand, usados.add(cand)
                nuevas.append(sch)
            if replace or nuevas:
                self.schedules = nuevas if replace else self.schedules + nuevas[:MAX_SCHEDULES - len(self.schedules)]
            report["programaciones"] = len(nuevas)
            # Escenas y grupos (TeleHome Pro): solo con los dispositivos que han quedado
            for clave, norm, tope, lista_nombre in (("scenes", normalize_scene, MAX_SCENES, "escenas"),
                                                    ("groups", normalize_group, MAX_GROUPS, "grupos")):
                nuevos: List[Dict[str, Any]] = []
                raw_lista = data.get(clave) or []
                if not isinstance(raw_lista, list):
                    raw_lista = []
                for raw in raw_lista[:tope]:
                    try:
                        el = norm(raw if isinstance(raw, dict) else {})
                    except ConfigError as exc:
                        report["omitidos"].append({"name": str((raw or {}).get("name", lista_nombre))[:40], "motivo": str(exc)})
                        continue
                    if clave == "scenes":
                        el["items"] = [{**i, "device": idmap.get(i["device"], i["device"])} for i in el["items"]]
                        el["items"] = [i for i in el["items"] if i["device"] in ids]
                        vacio = not el["items"]
                    else:
                        el["devices"] = [idmap.get(d, d) for d in el["devices"] if idmap.get(d, d) in ids]
                        vacio = not el["devices"]
                    if vacio:
                        report["omitidos"].append({"name": el["name"], "motivo": "Sus dispositivos no están en el fichero"})
                        continue
                    base = self.scenes if clave == "scenes" else self.groups
                    el["id"] = self._new_pro_id(el["name"], nuevos if replace else base + nuevos)
                    nuevos.append(el)
                if clave == "scenes":
                    self.scenes = nuevos if replace else self.scenes + nuevos[:max(0, MAX_SCENES - len(self.scenes))]
                else:
                    self.groups = nuevos if replace else self.groups + nuevos[:max(0, MAX_GROUPS - len(self.groups))]
                report[lista_nombre] = len(nuevos)
            self.save()
            report["cloud_cambiada"] = "cloud_api_key" in opts
            srv = data.get("servicio")
            report["servicio"] = {"ruta": clean_ruta(srv.get("ruta"))} if isinstance(srv, dict) and clean_ruta(srv.get("ruta")) else None
            report["total"] = len(self.devices)
            return report

    # ---- Opciones ------------------------------------------------------
    def public_options(self) -> Dict[str, Any]:
        with self.lock:
            out = {k: v for k, v in self.options.items() if k not in SECRET_OPTIONS}
            out["cloud_secret_set"] = bool(self.options.get("cloud_api_secret"))
            out["password_set"] = bool(self.options.get("password_hash"))
            out["admin_set"] = bool(self.options.get("admin_password_hash"))
            out["user_set"] = bool(self.options.get("user_password_hash"))
            return out

    def _int_opt(self, raw, key, lo, hi, label) -> int:
        try:
            v = int(raw[key])
        except (TypeError, ValueError):
            raise ConfigError("%s debe ser un número entero" % label)
        if not lo <= v <= hi:
            raise ConfigError("%s entre %d y %d" % (label, lo, hi))
        return v

    def set_options(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            opts = dict(self.options)
            if "poll_interval" in raw:
                opts["poll_interval"] = self._int_opt(raw, "poll_interval", MIN_POLL, MAX_POLL, "Intervalo local (s)")
            if "cloud_poll_interval" in raw:
                opts["cloud_poll_interval"] = self._int_opt(raw, "cloud_poll_interval", MIN_CLOUD_POLL, MAX_POLL,
                                                            "Intervalo de la nube (s)")
            if "retention_days" in raw:
                opts["retention_days"] = self._int_opt(raw, "retention_days", 1, 3650, "Retención (días)")
            self.options = opts
            self.save()
            return self.public_options()

    def set_cloud(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            opts = dict(self.options)
            region = str(raw.get("region", opts["cloud_region"])).strip()
            if region not in CLOUD_REGIONS:
                raise ConfigError("Región de la nube no válida (%s)" % ", ".join(CLOUD_REGIONS))
            key = str(raw.get("api_key", opts["cloud_api_key"]) or "").strip()
            secret = str(raw.get("api_secret") or "").strip() or opts["cloud_api_secret"]
            if raw.get("clear"):
                key, secret = "", ""
            for label, v in (("Access ID", key), ("Access Secret", secret)):
                if v and not re.match(r"^[A-Za-z0-9]{8,64}$", v):
                    raise ConfigError("%s no válido" % label)
            opts.update(cloud_region=region, cloud_api_key=key, cloud_api_secret=secret)
            self.options = opts
            self.save()
            return self.public_options()

    def set_user_password(self, password: Optional[str]) -> None:
        """Contraseña del usuario de confianza: puede encender y apagar, pero no cambiar la configuración."""
        with self.lock:
            if password is not None and len(password) < 8:
                raise ConfigError("La contraseña de usuario debe tener al menos 8 caracteres")
            self.options = {**self.options, "user_password_hash": hash_password(password) if password else ""}
            self.save()

    def set_admin_password(self, password: Optional[str]) -> None:
        """Contraseña del modo Administrador (distinta de la del servicio). Vacía = sin modo Administrador."""
        with self.lock:
            if password is not None and len(password) < 8:
                raise ConfigError("La contraseña de administrador debe tener al menos 8 caracteres")
            self.options = {**self.options, "admin_password_hash": hash_password(password) if password else ""}
            self.save()

    def set_password(self, password: Optional[str]) -> None:
        with self.lock:
            if password is not None and len(password) < 8:
                raise ConfigError("La contraseña debe tener al menos 8 caracteres")
            self.options = {**self.options, "password_hash": hash_password(password) if password else ""}
            self.save()

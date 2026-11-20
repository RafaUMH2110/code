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
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_DEVICES = 7
MIN_POLL = 5            # s; los medidores de energía Tuya no admiten sondeos locales más rápidos
MIN_CLOUD_POLL = 60     # s; la cuenta gratuita de Tuya tiene un cupo de llamadas muy limitado
MAX_POLL = 3600
VERSIONS = ("3.1", "3.2", "3.3", "3.4", "3.5")
MODES = ("local", "nube")
# Tipos de dispositivo que sabe leer este servicio. La app genérica TeleHome los
# consulta en api/health y api/state y deshabilita en el alta los que no estén.
DEVICE_TYPES = ("enchufe",)
CLOUD_REGIONS = ("eu", "eu-w", "us", "us-e", "in", "sg", "cn")

OPTION_DEFAULTS: Dict[str, Any] = {
    "poll_interval": 10,
    "cloud_poll_interval": 300,
    "retention_days": 30,
    "cloud_region": "eu",
    "cloud_api_key": "",
    "cloud_api_secret": "",
    "password_hash": "",
}
SECRET_OPTIONS = ("cloud_api_secret", "password_hash")

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

_DEV_ID_RE = re.compile(r"^[A-Za-z0-9]{8,40}$")
_CODE_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_PBKDF2_ITER = 200_000


class ConfigError(ValueError):
    """Error de validación con mensaje apto para mostrar al usuario."""


def data_dir(override: Optional[str] = None) -> Path:
    if override:
        return Path(override).expanduser()
    env = os.environ.get("TELEHOME_ENCHUFES_DIR")
    if env:
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "telehome-enchufes"
    return Path.home() / ".telehome-enchufes"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:24] or "enchufe"


def _num(raw: Dict[str, Any], key: str, lo: float, hi: float, as_int: bool = False):
    value = raw.get(key, DEVICE_DEFAULTS[key])
    try:
        value = int(value) if as_int else float(value)
    except (TypeError, ValueError):
        raise ConfigError("«%s» debe ser un número" % key)
    if not lo <= value <= hi:
        raise ConfigError("«%s» debe estar entre %s y %s" % (key, lo, hi))
    return value


def _code(raw: Dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or DEVICE_DEFAULTS[key]).strip()
    if not _CODE_RE.match(value):
        raise ConfigError("«%s» debe ser un código Tuya (minúsculas, números y _)" % key)
    return value


def normalize_device(raw: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Valida un enchufe. Si `existing` se indica, los campos ausentes se heredan."""
    base = dict(existing) if existing else {}
    merged = {**DEVICE_DEFAULTS, **base, **{k: v for k, v in raw.items() if v is not None}}

    dtype = str(merged.get("type") or "enchufe").strip().lower()
    if dtype not in DEVICE_TYPES:
        raise ConfigError("Tipo de dispositivo no admitido por este servicio (%s)" % ", ".join(DEVICE_TYPES))

    mode = str(merged.get("mode") or "local").strip().lower()
    if mode not in MODES:
        raise ConfigError("Modo no válido (local o nube)")

    name = str(merged.get("name", "")).strip()
    if not name:
        raise ConfigError("El nombre del enchufe es obligatorio")
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
        raise ConfigError("Falta la Local Key del enchufe (necesaria en modo local)")
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

    return {
        "id": base.get("id") or raw.get("id") or "",
        "slot": base.get("slot", raw.get("slot")),  # color fijo del enchufe (0-6)
        "type": dtype,
        "mode": mode,
        "name": name,
        "room": room,
        "dev_id": dev_id,
        "local_key": key,
        "ip": ip,
        "version": version,
        "dp_switch": _num(merged, "dp_switch", 1, 255, True),
        "dp_power": _num(merged, "dp_power", 1, 255, True),
        "dp_voltage": _num(merged, "dp_voltage", 1, 255, True),
        "dp_current": _num(merged, "dp_current", 1, 255, True),
        "code_switch": _code(merged, "code_switch"),
        "code_power": _code(merged, "code_power"),
        "code_voltage": _code(merged, "code_voltage"),
        "code_current": _code(merged, "code_current"),
        "scale_power": _num(merged, "scale_power", 0.001, 1e6),
        "scale_voltage": _num(merged, "scale_voltage", 0.001, 1e6),
        "scale_current": _num(merged, "scale_current", 0.001, 1e6),
    }


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
            for raw in data.get("devices", [])[:MAX_DEVICES]:
                dev = normalize_device(raw)
                dev["id"] = raw.get("id") or self._new_id(dev["name"])
                dev["slot"] = self._free_slot(dev.get("slot"))
                self.devices.append(dev)
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
            payload = json.dumps({"options": self.options, "devices": self.devices},
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
            self.save()

    def import_devices(self, rows: List[Dict[str, Any]], mode: str = "local") -> Dict[str, Any]:
        """Importa el devices.json de TinyTuya o la lista de la nube (id/dev_id, key, name, ip, version)."""
        added, skipped = [], []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get("name") or row.get("id") or row.get("dev_id") or "Enchufe"
            raw = {
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

    # ---- Opciones ------------------------------------------------------
    def public_options(self) -> Dict[str, Any]:
        with self.lock:
            out = {k: v for k, v in self.options.items() if k not in SECRET_OPTIONS}
            out["cloud_secret_set"] = bool(self.options.get("cloud_api_secret"))
            out["password_set"] = bool(self.options.get("password_hash"))
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

    def set_password(self, password: Optional[str]) -> None:
        with self.lock:
            if password is not None and len(password) < 8:
                raise ConfigError("La contraseña debe tener al menos 8 caracteres")
            self.options = {**self.options, "password_hash": hash_password(password) if password else ""}
            self.save()

"""Configuración persistente (JSON) con validación y límite de enchufes."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_DEVICES = 7
MIN_POLL = 5          # s; los medidores de energía Tuya no admiten sondeos más rápidos
MAX_POLL = 3600
VERSIONS = ("3.1", "3.2", "3.3", "3.4", "3.5")

OPTION_DEFAULTS: Dict[str, Any] = {"poll_interval": 10, "retention_days": 30}

# Valores típicos de un enchufe Tuya con medidor (se pueden ajustar por enchufe
# con `probar`, que muestra los DPS reales del dispositivo).
DEVICE_DEFAULTS: Dict[str, Any] = {
    "ip": "Auto",
    "version": "3.3",
    "dp_switch": 1,
    "dp_power": 19,
    "dp_voltage": 20,
    "dp_current": 18,
    "scale_power": 10.0,      # potencia = valor / 10  (W)
    "scale_voltage": 10.0,    # tensión  = valor / 10  (V)
    "scale_current": 1000.0,  # corriente = valor / 1000 (A, el DPS viene en mA)
}

_DEV_ID_RE = re.compile(r"^[A-Za-z0-9]{8,40}$")


class ConfigError(ValueError):
    """Error de validación con mensaje apto para mostrar al usuario."""


def data_dir(override: Optional[str] = None) -> Path:
    if override:
        return Path(override).expanduser()
    env = os.environ.get("TELEMET_ENCHUFES_DIR")
    if env:
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "telemet-enchufes"
    return Path.home() / ".telemet-enchufes"


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


def normalize_device(raw: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Valida un enchufe. Si `existing` se indica, los campos ausentes se heredan."""
    base = dict(existing) if existing else {}
    merged = {**DEVICE_DEFAULTS, **base, **{k: v for k, v in raw.items() if v is not None}}

    name = str(merged.get("name", "")).strip()
    if not name:
        raise ConfigError("El nombre del enchufe es obligatorio")
    if len(name) > 40:
        raise ConfigError("El nombre no puede superar 40 caracteres")

    dev_id = str(merged.get("dev_id", "")).strip()
    if not _DEV_ID_RE.match(dev_id):
        raise ConfigError("Device ID no válido (8-40 caracteres alfanuméricos)")

    key = str(raw.get("local_key") or base.get("local_key") or "").strip()
    if not key:
        raise ConfigError("Falta la Local Key del enchufe")
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

    dev = {
        "id": base.get("id") or raw.get("id") or "",
        "slot": base.get("slot", raw.get("slot")),  # color fijo del enchufe (0-6)
        "name": name,
        "dev_id": dev_id,
        "local_key": key,
        "ip": ip,
        "version": version,
        "dp_switch": _num(merged, "dp_switch", 1, 255, True),
        "dp_power": _num(merged, "dp_power", 1, 255, True),
        "dp_voltage": _num(merged, "dp_voltage", 1, 255, True),
        "dp_current": _num(merged, "dp_current", 1, 255, True),
        "scale_power": _num(merged, "scale_power", 0.001, 1e6),
        "scale_voltage": _num(merged, "scale_voltage", 0.001, 1e6),
        "scale_current": _num(merged, "scale_current", 0.001, 1e6),
    }
    return dev


def public_device(dev: Dict[str, Any]) -> Dict[str, Any]:
    """Vista del enchufe sin la Local Key (nunca sale por la API)."""
    out = {k: v for k, v in dev.items() if k != "local_key"}
    out["has_key"] = bool(dev.get("local_key"))
    return out


class Config:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.options: Dict[str, Any] = dict(OPTION_DEFAULTS)
        self.devices: List[Dict[str, Any]] = []
        self.load()

    # ---- E/S -----------------------------------------------------------
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
            new = normalize_device({k: v for k, v in raw.items() if k not in ("id", "has_key")}, cur)
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

    def import_devices(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Importa el devices.json del asistente de TinyTuya (campos id, key, name, ip, version)."""
        added, skipped = [], []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get("name") or row.get("id") or "Enchufe"
            raw = {
                "name": str(name)[:40],
                "dev_id": row.get("id") or row.get("dev_id"),
                "local_key": row.get("key") or row.get("local_key"),
                "ip": row.get("ip") or "Auto",
                "version": str(row.get("version") or "3.3"),
            }
            try:
                added.append(self.add_device(raw)["name"])
            except ConfigError as exc:
                skipped.append({"name": str(name), "motivo": str(exc)})
        return {"añadidos": added, "omitidos": skipped}

    # ---- Opciones ------------------------------------------------------
    def set_options(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            opts = dict(self.options)
            if "poll_interval" in raw:
                try:
                    v = int(raw["poll_interval"])
                except (TypeError, ValueError):
                    raise ConfigError("El intervalo debe ser un número entero de segundos")
                if not MIN_POLL <= v <= MAX_POLL:
                    raise ConfigError("Intervalo entre %d y %d s" % (MIN_POLL, MAX_POLL))
                opts["poll_interval"] = v
            if "retention_days" in raw:
                try:
                    v = int(raw["retention_days"])
                except (TypeError, ValueError):
                    raise ConfigError("La retención debe ser un número entero de días")
                if not 1 <= v <= 3650:
                    raise ConfigError("Retención entre 1 y 3650 días")
                opts["retention_days"] = v
            self.options = opts
            self.save()
            return opts

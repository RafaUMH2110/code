"""Luces Tuya: lectura y órdenes (encendido, brillo, blanco cálido/frío, color y modo).

Una bombilla Tuya expone cinco datos. La nube los llama por **código** y el protocolo local por **DPS**:

| Dato        | Código nube (v2)   | DPS | Valor crudo                                     |
|-------------|--------------------|-----|-------------------------------------------------|
| Encendido   | `switch_led`       | 20  | true / false                                    |
| Modo        | `work_mode`        | 21  | `white`, `colour`, `scene`, `music`             |
| Brillo      | `bright_value_v2`  | 22  | 10-1000 (en modo blanco)                        |
| Temperatura | `temp_value_v2`    | 23  | 0-1000 (0 cálida, 1000 fría)                    |
| Color       | `colour_data_v2`   | 24  | `{"h":0-360,"s":0-1000,"v":0-1000}` (nube) o    |
|             |                    |     | `HHHHSSSSVVVV` en hexadecimal (local)           |

Hacia fuera TeleHome habla siempre en unidades de persona: brillo y temperatura de 0 a 100, color como
tono 0-360 y saturación y valor 0-100. Las escalas (`scale_level`, `scale_temp`, `scale_color`) convierten.

Este módulo no hace red: solo convierte y decide qué órdenes hacen falta, de modo que se prueba sin bombilla.
"""

from __future__ import annotations

import colorsys
import json
import re
from typing import Any, Dict, List, Optional, Tuple

# Categorías de la nube de Tuya que son luces (bombillas, tiras, plafones, guirnaldas…).
LIGHT_CATEGORIES = frozenset({"dj", "dd", "xdd", "fwd", "dc", "tgq"})
# Si un dispositivo dado de alta como enchufe devuelve alguno de estos códigos, en realidad es una luz.
LIGHT_CODES = ("switch_led", "bright_value_v2", "bright_value", "temp_value_v2", "temp_value",
               "colour_data_v2", "colour_data")

LIGHT_ACTIONS = ("switch", "level", "temp", "color", "mode")
MODES_BASE = ("white", "colour")            # los que manejan todas las apps
MODES = MODES_BASE + ("scene", "music")     # TeleHome Pro también puede pasar a la escena o la música que tenga la bombilla

# Códigos y DPS por omisión de una bombilla Tuya con la API v2.
LIGHT_DEFAULTS: Dict[str, Any] = {
    "dp_switch": 20, "dp_mode": 21, "dp_level": 22, "dp_temp": 23, "dp_color": 24,
    "code_switch": "switch_led", "code_mode": "work_mode", "code_level": "bright_value_v2",
    "code_temp": "temp_value_v2", "code_color": "colour_data_v2",
    "scale_level": 10.0,   # brillo (%) = valor / 10
    "scale_temp": 10.0,    # temperatura (0-100) = valor / 10
    "scale_color": 10.0,   # saturación y valor (%) = dato / 10
    # Parámetros de la bombilla (TeleHome Pro). No se mandan a Tuya: los aplica TeleHome.
    "level_min": 1,        # % mínimo de brillo al que se deja bajar (algunas bombillas parpadean por debajo)
    "level_max": 100,      # % máximo de brillo (para no deslumbrar ni gastar de más)
    "kelvin_min": 2700,    # K del blanco más cálido (temp 0); solo para enseñar kelvin en las apps
    "kelvin_max": 6500,    # K del blanco más frío (temp 100)
}
LIGHT_FIELDS = tuple(LIGHT_DEFAULTS)

# Bombillas de la API antigua (v1): brillo 25-255, temperatura 0-255, saturación y valor 0-255.
LIGHT_V1 = {"code_level": "bright_value", "code_temp": "temp_value", "code_color": "colour_data",
            "scale_level": 2.55, "scale_temp": 2.55, "scale_color": 2.55}


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def es_luz_por_codigos(status: Dict[str, Any]) -> bool:
    return any(k in status for k in LIGHT_CODES)


def defaults_para(status: Dict[str, Any]) -> Dict[str, Any]:
    """Códigos que corresponden a este dispositivo según lo que devuelve la nube (v2 por omisión, v1 si es antigua)."""
    out = dict(LIGHT_DEFAULTS)
    if "bright_value_v2" not in status and "bright_value" in status:
        out.update(LIGHT_V1)
    return out


def adaptar(dev: Dict[str, Any], status: Dict[str, Any]) -> Dict[str, Any]:
    """Configuración efectiva de una luz: si la nube devuelve los códigos de la API antigua (v1) y el dispositivo
    sigue con los de la v2, se usan los v1 sin tocar lo guardado. Si no, el dispositivo tal cual."""
    cambios = {}
    for campo, v1 in (("code_level", "bright_value"), ("code_temp", "temp_value"), ("code_color", "colour_data")):
        v2 = LIGHT_DEFAULTS[campo]
        if dev.get(campo) == v2 and v2 not in status and v1 in status:
            cambios[campo] = v1
            cambios[campo.replace("code_", "scale_")] = LIGHT_V1[campo.replace("code_", "scale_")]
    return {**dev, **cambios} if cambios else dev


# ---- color ----------------------------------------------------------------
def hsv_to_hex(h: float, s: float, v: float) -> str:
    """«#rrggbb» de un color (tono 0-360, saturación y valor 0-100)."""
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, clamp(s, 0, 100) / 100.0, clamp(v, 0, 100) / 100.0)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def hex_to_hsv(texto: str) -> Tuple[int, int, int]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(texto).strip())
    if not m:
        raise ValueError("El color debe ser #rrggbb o {\"h\":0-360,\"s\":0-100,\"v\":0-100}")
    n = int(m.group(1), 16)
    h, s, v = colorsys.rgb_to_hsv((n >> 16 & 255) / 255.0, (n >> 8 & 255) / 255.0, (n & 255) / 255.0)
    return int(round(h * 360)) % 360, int(round(s * 100)), int(round(v * 100))


def parse_color_arg(value: Any) -> Tuple[int, int, int]:
    """Color de una orden: «#rrggbb» o {"h","s","v"} (0-360, 0-100, 0-100). Devuelve (h, s, v) enteros."""
    if isinstance(value, str):
        h, s, v = hex_to_hsv(value)
    elif isinstance(value, dict):
        try:
            h, s, v = float(value["h"]), float(value["s"]), float(value["v"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("El color necesita h (0-360), s (0-100) y v (0-100), o un texto #rrggbb")
    else:
        raise ValueError("El color debe ser #rrggbb o {\"h\":0-360,\"s\":0-100,\"v\":0-100}")
    if not (0 <= h <= 360 and 0 <= s <= 100 and 0 <= v <= 100):
        raise ValueError("Color fuera de rango: h 0-360, s 0-100, v 0-100")
    return int(round(h)) % 360, int(round(s)), max(1, int(round(v)))   # la bombilla no admite menos del 1 % de valor


# ---- lectura ---------------------------------------------------------------
def _num(x: Any) -> Optional[float]:
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _final(on: Optional[bool], mode: Optional[str], bright: Optional[float], temp: Optional[float],
           color: Optional[Dict[str, int]], caps: Dict[str, bool]) -> Dict[str, Any]:
    """Estado en unidades de persona. El brillo que se enseña es el del modo actual: en modo color
    es el «valor» del color, porque la bombilla ignora el brillo blanco mientras está en color."""
    level = color["v"] if (mode == "colour" and color) else bright
    return {"on": on, "mode": mode, "level": None if level is None else round(level, 1),
            "temp": None if temp is None else round(temp, 1), "color": color,
            "hex": None if not color else hsv_to_hex(color["h"], color["s"], color["v"]), "caps": caps}


def read_cloud(status: Dict[str, Any], dev: Dict[str, Any]) -> Dict[str, Any]:
    sw = status.get(dev["code_switch"])
    mode = status.get(dev["code_mode"])
    bright = _num(status.get(dev["code_level"]))
    temp = _num(status.get(dev["code_temp"]))
    raw = status.get(dev["code_color"])
    color = None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if isinstance(raw, dict) and all(_num(raw.get(k)) is not None for k in "hsv"):
        sc = float(dev["scale_color"])
        color = {"h": int(round(float(raw["h"]))) % 360,
                 "s": int(round(clamp(float(raw["s"]) / sc, 0, 100))), "v": int(round(clamp(float(raw["v"]) / sc, 0, 100)))}
    caps = {"mode": dev["code_mode"] in status, "level": dev["code_level"] in status,
            "temp": dev["code_temp"] in status, "color": dev["code_color"] in status}
    return _final(None if sw is None else bool(sw), mode if isinstance(mode, str) else None,
                  None if bright is None else clamp(bright / float(dev["scale_level"]), 0, 100),
                  None if temp is None else clamp(temp / float(dev["scale_temp"]), 0, 100), color, caps)


def parse_local_color(texto: Any) -> Optional[Dict[str, int]]:
    """Dato de color del protocolo local: 12 dígitos HHHHSSSSVVVV (0-360, 0-1000, 0-1000) o 14 RRGGBBHHHHSSVV (v1)."""
    if not isinstance(texto, str) or not re.fullmatch(r"[0-9a-fA-F]+", texto):
        return None
    try:
        if len(texto) == 12:
            h, s, v = int(texto[0:4], 16), int(texto[4:8], 16) / 10.0, int(texto[8:12], 16) / 10.0
        elif len(texto) == 14:
            h, s, v = int(texto[6:10], 16), int(texto[10:12], 16) / 2.55, int(texto[12:14], 16) / 2.55
        else:
            return None
    except ValueError:
        return None
    return {"h": h % 360, "s": int(round(clamp(s, 0, 100))), "v": int(round(clamp(v, 0, 100)))}


def read_local(dps: Dict[str, Any], dev: Dict[str, Any]) -> Dict[str, Any]:
    g = lambda k: dps.get(str(dev[k]))
    sw, mode = g("dp_switch"), g("dp_mode")
    bright, temp = _num(g("dp_level")), _num(g("dp_temp"))
    caps = {"mode": g("dp_mode") is not None, "level": g("dp_level") is not None,
            "temp": g("dp_temp") is not None, "color": g("dp_color") is not None}
    return _final(None if sw is None else bool(sw), mode if isinstance(mode, str) else None,
                  None if bright is None else clamp(bright / float(dev["scale_level"]), 0, 100),
                  None if temp is None else clamp(temp / float(dev["scale_temp"]), 0, 100),
                  parse_local_color(g("dp_color")), caps)


# ---- órdenes ---------------------------------------------------------------
Paso = Tuple[str, Any]


def _entero(valor: Any, que: str, lo: int = 0, hi: int = 100) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError("«%s» necesita un número de %d a %d" % (que, lo, hi))
    if not lo <= valor <= hi:
        raise ValueError("«%s» necesita un número de %d a %d" % (que, lo, hi))
    return int(round(valor))


def limites(dev: Optional[Dict[str, Any]]) -> Tuple[int, int]:
    """(mínimo, máximo) de brillo en % que admite esta bombilla."""
    if not dev:
        return 1, 100
    lo = int(dev.get("level_min") or 1)
    hi = int(dev.get("level_max") or 100)
    return max(1, min(lo, 100)), max(1, min(hi, 100))


def _lim(pc: int, dev: Optional[Dict[str, Any]]) -> int:
    lo, hi = limites(dev)
    return int(clamp(pc, lo, max(lo, hi)))


def plan(action: str, value: Any, cur: Optional[Dict[str, Any]] = None, dev: Optional[Dict[str, Any]] = None) -> List[Paso]:
    """Pasos lógicos que hacen falta para una orden, según el estado actual de la bombilla.

    Pasos: ("switch", bool), ("mode", "white"|"colour"), ("level", 1-100), ("temp", 0-100), ("color", (h, s, v)).
    Poner brillo, temperatura o color la enciende: quien lo pide quiere ver el resultado.
    """
    cur = cur or {}
    if action == "switch":
        if not isinstance(value, bool):
            raise ValueError("«value» debe ser true o false")
        return [("switch", value)]
    if action == "level":
        pc = _entero(value, "level")
        if pc == 0:
            return [("switch", False)]
        pc = _lim(pc, dev)
        color = cur.get("color")
        if cur.get("mode") == "colour" and color:
            return [("switch", True), ("color", (color["h"], color["s"], pc))]
        return [("switch", True), ("level", pc)]
    if action == "temp":
        return [("switch", True), ("mode", "white"), ("temp", _entero(value, "temp"))]
    if action == "color":
        h, s_, v_ = parse_color_arg(value)
        return [("switch", True), ("mode", "colour"), ("color", (h, s_, _lim(v_, dev)))]
    if action == "mode":
        if value not in MODES:
            raise ValueError("«mode» debe ser «white» (blanco), «colour» (color), «scene» o «music»")
        return [("mode", value)]
    raise ValueError("Orden «%s» no admitida por una luz" % action)


def _raw(pc: float, scale: float, minimo: int = 1) -> int:
    return max(minimo, int(round(pc * scale)))


def cloud_commands(dev: Dict[str, Any], pasos: List[Paso]) -> List[Tuple[str, Any]]:
    out: List[Tuple[str, Any]] = []
    for clave, v in pasos:
        if clave == "switch":
            out.append((dev["code_switch"], bool(v)))
        elif clave == "mode":
            out.append((dev["code_mode"], v))
        elif clave == "level":
            out.append((dev["code_level"], _raw(v, float(dev["scale_level"]))))
        elif clave == "temp":
            out.append((dev["code_temp"], _raw(v, float(dev["scale_temp"]), 0)))
        elif clave == "color":
            h, s, val = v
            sc = float(dev["scale_color"])
            out.append((dev["code_color"], json.dumps({"h": int(h), "s": _raw(s, sc, 0), "v": _raw(val, sc)},
                                                      separators=(",", ":"))))
    return out


def local_color(h: int, s: int, v: int, largo_actual: int = 12) -> str:
    """Dato de color del protocolo local, en el mismo formato que usa la bombilla (por el largo del dato actual)."""
    if largo_actual == 14:    # v1: RRGGBB + HHHH + SS + VV
        rgb = hsv_to_hex(h, 100, 100).lstrip("#")
        return "%s%04x%02x%02x" % (rgb, int(h), int(round(s * 2.55)), int(round(v * 2.55)))
    return "%04x%04x%04x" % (int(h), int(round(s * 10)), int(round(v * 10)))


def local_dps(dev: Dict[str, Any], pasos: List[Paso], largo_color: int = 12) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for clave, v in pasos:
        if clave == "switch":
            out[str(dev["dp_switch"])] = bool(v)
        elif clave == "mode":
            out[str(dev["dp_mode"])] = v
        elif clave == "level":
            out[str(dev["dp_level"])] = _raw(v, float(dev["scale_level"]))
        elif clave == "temp":
            out[str(dev["dp_temp"])] = _raw(v, float(dev["scale_temp"]), 0)
        elif clave == "color":
            out[str(dev["dp_color"])] = local_color(v[0], v[1], v[2], largo_color)
    return out


def plan_estado(item: Dict[str, Any], dev: Optional[Dict[str, Any]] = None) -> List[Paso]:
    """Pasos para dejar una luz en el estado de una escena: {"on", "mode", "level", "temp", "color"}.

    Todo va en una sola orden: encender, modo y el valor que toque. En modo color el brillo es el «valor»
    del color. Si falta algún dato, se deja como está."""
    if item.get("on") is False:
        return [("switch", False)]
    modo = item.get("mode")
    if modo is not None and modo not in MODES:
        raise ValueError("«mode» debe ser «white», «colour», «scene» o «music»")
    pasos: List[Paso] = [("switch", True)]
    nivel = item.get("level")
    if nivel is not None:
        nivel = _lim(_entero(nivel, "level", 1, 100), dev)
    if modo == "colour" or (modo is None and item.get("color") is not None):
        h, s_, v_ = parse_color_arg(item["color"]) if item.get("color") is not None else (0, 100, 100)
        pasos += [("mode", "colour"), ("color", (h, s_, nivel if nivel is not None else _lim(v_, dev)))]
        return pasos
    if modo is not None:
        pasos.append(("mode", modo))
    if modo in (None, "white"):
        if nivel is not None:
            pasos.append(("level", nivel))
        if item.get("temp") is not None:
            pasos.append(("temp", _entero(item["temp"], "temp")))
    return pasos

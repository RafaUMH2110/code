"""Amanecer y anochecer para una fecha y un lugar, sin dependencias.

Algoritmo del NOAA (Solar Calculator), con la precisión de sobra para encender una luz:
el error frente a las efemérides oficiales es de pocos minutos salvo muy cerca de los polos.
"""

from __future__ import annotations

import math
import time
from datetime import date
from typing import Optional, Tuple

# Elche (Universidad Miguel Hernández): por donde se empieza si nadie dice otra cosa.
LAT_POR_DEFECTO = 38.2699
LON_POR_DEFECTO = -0.7126
# Ángulo del centro del Sol bajo el horizonte en el orto y el ocaso (incluye refracción).
CENIT_ORTO = 90.833


def _dia_juliano(d: date) -> float:
    a = (14 - d.month) // 12
    y = d.year + 4800 - a
    m = d.month + 12 * a - 3
    jdn = d.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jdn - 0.5


def _eventos(d: date, lat: float, lon: float) -> Tuple[Optional[float], Optional[float]]:
    """(amanecer, anochecer) como épocas UTC en segundos, o None si ese día no hay (sol de medianoche)."""
    siglos = (_dia_juliano(d) - 2451545.0) / 36525.0
    # Geometría solar
    media = (280.46646 + siglos * (36000.76983 + siglos * 0.0003032)) % 360
    anomalia = 357.52911 + siglos * (35999.05029 - 0.0001537 * siglos)
    excentricidad = 0.016708634 - siglos * (0.000042037 + 0.0000001267 * siglos)
    ra = math.radians(anomalia)
    centro = (math.sin(ra) * (1.914602 - siglos * (0.004817 + 0.000014 * siglos))
              + math.sin(2 * ra) * (0.019993 - 0.000101 * siglos)
              + math.sin(3 * ra) * 0.000289)
    longitud = media + centro
    omega = 125.04 - 1934.136 * siglos
    aparente = longitud - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    oblicuidad = (23 + (26 + ((21.448 - siglos * (46.815 + siglos * (0.00059 - siglos * 0.001813)))) / 60) / 60)
    oblic_corr = oblicuidad + 0.00256 * math.cos(math.radians(omega))
    declinacion = math.degrees(math.asin(math.sin(math.radians(oblic_corr)) * math.sin(math.radians(aparente))))

    # Ecuación del tiempo (minutos)
    y = math.tan(math.radians(oblic_corr / 2)) ** 2
    rm = math.radians(media)
    et = 4 * math.degrees(
        y * math.sin(2 * rm) - 2 * excentricidad * math.sin(ra)
        + 4 * excentricidad * y * math.sin(ra) * math.cos(2 * rm)
        - 0.5 * y * y * math.sin(4 * rm) - 1.25 * excentricidad * excentricidad * math.sin(2 * ra))

    # Ángulo horario del orto
    rlat, rdec = math.radians(lat), math.radians(declinacion)
    cos_h = (math.cos(math.radians(CENIT_ORTO)) / (math.cos(rlat) * math.cos(rdec)) - math.tan(rlat) * math.tan(rdec))
    if not -1.0 <= cos_h <= 1.0:
        return None, None                      # el Sol no sale o no se pone ese día
    h = math.degrees(math.acos(cos_h))

    mediodia = 720 - 4 * lon - et               # minutos UTC del mediodía solar
    medianoche = time.mktime((d.year, d.month, d.day, 0, 0, 0, 0, 0, 0)) - time.timezone
    return medianoche + (mediodia - 4 * h) * 60, medianoche + (mediodia + 4 * h) * 60


def amanecer(d: date, lat: float = LAT_POR_DEFECTO, lon: float = LON_POR_DEFECTO) -> Optional[float]:
    return _eventos(d, lat, lon)[0]


def anochecer(d: date, lat: float = LAT_POR_DEFECTO, lon: float = LON_POR_DEFECTO) -> Optional[float]:
    return _eventos(d, lat, lon)[1]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
telehome-enchufes-pruebas.py
===========================

Herramienta de **pruebas preliminares** para enchufes Wi-Fi Tuya con medidor de
consumo (Energeeks EG-EW008MC / pack EG-EW009MC) desde la línea de órdenes o
desde Visual Studio Code.

Permite, sin la interfaz web de TeleHome Enchufes:

* consultar el estado (encendido, potencia, tensión, corriente);
* encender, apagar y conmutar uno o varios enchufes;
* vigilar las lecturas cada N segundos (opcionalmente a un CSV);
* ver los datos crudos que devuelve el enchufe (DPS o códigos de la nube);
* buscar enchufes en la red local y listar los de la cuenta de la nube.

Cada enchufe funciona en uno de tres **modos**:

``local``
    Habla con el enchufe por la red local (TCP 6668) con TinyTuya. Requiere
    estar en la misma red y conocer su *Local Key*.
``nube``
    Usa la API de Tuya IoT (TinyTuya ``Cloud``). Funciona desde cualquier
    sitio; requiere un proyecto en iot.tuya.com con la cuenta de Smart Life
    enlazada y su *Access ID* / *Access Secret*.
``simulado``
    Enchufe ficticio (no necesita nada) para probar la herramienta.
    La opción ``--simular`` fuerza este modo en todos los enchufes.

Configuración
-------------
Los parámetros se toman, por este orden de prioridad (el último gana):

1. Las **variables del código**: sección «1. CONFIGURACIÓN EDITABLE», justo
   debajo de este texto.
2. El **fichero JSON** (por defecto ``config-pruebas.json`` junto al script, o
   el indicado con ``--config``). Sus secciones ``nube`` y ``opciones`` se
   fusionan campo a campo con las del código; la lista ``enchufes``, si
   aparece, **sustituye** a la del código. ``--sin-json`` lo ignora.
3. Las **opciones de la línea de órdenes** (``--simular``, ``--intervalo``...).

El *Access Secret* puede dejarse vacío y pasarse en la variable de entorno
``TUYA_ACCESS_SECRET`` para no escribirlo en ningún fichero.

Uso rápido
----------
::

    python telehome-enchufes-pruebas.py --simular estado
    python telehome-enchufes-pruebas.py estado                 # todos los enchufes
    python telehome-enchufes-pruebas.py encender Nevera
    python telehome-enchufes-pruebas.py apagar 2               # por posición (1-7)
    python telehome-enchufes-pruebas.py vigilar todos --intervalo 30 --veces 10 --csv lecturas.csv
    python telehome-enchufes-pruebas.py nube-dispositivos --guardar
    python telehome-enchufes-pruebas.py --json estado          # salida para otros programas

``python telehome-enchufes-pruebas.py -h`` y ``<orden> -h`` muestran la ayuda.

Códigos de salida
-----------------
0 correcto · 1 algún enchufe falló · 2 error de configuración o de uso ·
3 falta la biblioteca TinyTuya · 130 interrumpido con Ctrl+C.

Requisitos: Python 3.9+ y, salvo en modo simulado, ``pip install tinytuya``.

Rafa · Departamento de Ingeniería de Sistemas y Automática ·
Universidad Miguel Hernández de Elche · r.puerto@umh.es
Generado con IA · Revisado por el autor
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import random
import re
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# ════════════════════════════════════════════════════════════════════════════
# 1. CONFIGURACIÓN EDITABLE
# ----------------------------------------------------------------------------
# Puedes configurar la herramienta editando estas variables (cómodo en VS Code)
# o con un fichero JSON (ver config-pruebas.example.json). Si existen ambos, el
# JSON tiene prioridad. No subas a git un fichero con claves reales.
# ════════════════════════════════════════════════════════════════════════════

#: Fichero JSON que se lee si existe (ruta relativa a la carpeta del script).
RUTA_JSON = "config-pruebas.json"

#: Credenciales del proyecto de la nube de Tuya (solo para enchufes en modo nube).
#: region: eu (Europa central, la habitual en España), eu-w, us, us-e, in, sg, cn.
NUBE: Dict[str, Any] = {
    "region": "eu",
    "access_id": "",       # Access ID / Client ID (pestaña Overview del proyecto)
    "access_secret": "",   # Access Secret; vacío → se lee de TUYA_ACCESS_SECRET
}

#: Enchufes (máximo 7). Campos obligatorios: nombre, modo y dev_id.
#: Modo local: además local_key, y opcionalmente ip ("Auto" la busca) y version.
#: "protegido": True impide apagarlo sin --forzar (p. ej. el que alimenta el router).
ENCHUFES: List[Dict[str, Any]] = [
    # {"nombre": "Nevera", "modo": "nube", "dev_id": "bf0123456789abcdefxyz"},
    # {"nombre": "Router", "modo": "nube", "dev_id": "bf9876543210fedcbaxyz", "protegido": True},
    # {"nombre": "Lámpara", "modo": "local", "dev_id": "bf1111111111111111abc",
    #  "local_key": "0123456789abcdef", "ip": "192.168.1.40", "version": "3.3"},
]

#: Opciones generales.
OPCIONES: Dict[str, Any] = {
    "intervalo_vigilancia": 10,   # s entre lecturas en «vigilar» (mín. 5 local, 60 nube)
    "tiempo_espera": 5,           # s de espera de cada conexión local
    "tiempo_busqueda": 12,        # s de escucha en «buscar»
}


# ════════════════════════════════════════════════════════════════════════════
# 2. CONSTANTES
# ════════════════════════════════════════════════════════════════════════════

VERSION = "1.0.0"
MAX_ENCHUFES = 7
MODOS = ("local", "nube", "simulado")
VERSIONES_PROTOCOLO = ("3.1", "3.2", "3.3", "3.4", "3.5")
REGIONES = {"eu": "Europa central", "eu-w": "Europa occidental", "us": "EE. UU. oeste",
            "us-e": "EE. UU. este", "in": "India", "sg": "Singapur", "cn": "China"}
INTERVALO_MINIMO = {"local": 5, "nube": 60, "simulado": 1}

# Mapa de datos por defecto de un enchufe Tuya con medidor. En modo local se
# usan números de DPS; en modo nube, los códigos estándar de Tuya. Cualquiera
# de ellos se puede cambiar por enchufe en la configuración (claves dp_* / codigo_*).
DATOS_POR_DEFECTO: Dict[str, Any] = {
    "dp_interruptor": 1, "dp_potencia": 19, "dp_tension": 20, "dp_corriente": 18,
    "codigo_interruptor": "switch_1", "codigo_potencia": "cur_power",
    "codigo_tension": "cur_voltage", "codigo_corriente": "cur_current",
    # Divisores para pasar el valor crudo a unidades: W, V y A (la corriente llega en mA).
    "escala_potencia": 10.0, "escala_tension": 10.0, "escala_corriente": 1000.0,
}

# Códigos de salida del programa.
SALIDA_OK, SALIDA_FALLO, SALIDA_CONFIG, SALIDA_DEPENDENCIA, SALIDA_INTERRUMPIDO = 0, 1, 2, 3, 130

# Errores del protocolo local de TinyTuya traducidos a algo comprensible.
ERRORES_LOCALES = {
    "901": "No se puede conectar con el enchufe",
    "902": "El enchufe no responde (tiempo de espera agotado)",
    "904": "Respuesta no válida del enchufe",
    "905": "Enchufe no alcanzable en la red local",
    "914": "Local Key o versión de protocolo incorrectas",
    "917": "Local Key o versión de protocolo incorrectas",
}

log = logging.getLogger("telehome-enchufes-pruebas")


# ════════════════════════════════════════════════════════════════════════════
# 3. MODELO DE DATOS
# ════════════════════════════════════════════════════════════════════════════

class ErrorConfig(Exception):
    """Configuración no válida. El mensaje se muestra tal cual al usuario."""


class ErrorEnchufe(Exception):
    """Fallo al comunicar con un enchufe. El mensaje se muestra tal cual."""


class FaltaDependencia(Exception):
    """No está instalada una biblioteca necesaria (TinyTuya)."""


@dataclass(frozen=True)
class ConfigNube:
    """Credenciales del proyecto en la nube de Tuya."""

    region: str = "eu"
    access_id: str = ""
    access_secret: str = ""

    @property
    def completa(self) -> bool:
        return bool(self.access_id and self.access_secret)


@dataclass(frozen=True)
class Enchufe:
    """Un enchufe configurado. Los campos dp_*/codigo_*/escala_* traducen los datos crudos."""

    nombre: str
    modo: str
    dev_id: str
    local_key: str = ""
    ip: str = "Auto"
    version: str = "3.3"
    protegido: bool = False
    dp_interruptor: int = 1
    dp_potencia: int = 19
    dp_tension: int = 20
    dp_corriente: int = 18
    codigo_interruptor: str = "switch_1"
    codigo_potencia: str = "cur_power"
    codigo_tension: str = "cur_voltage"
    codigo_corriente: str = "cur_current"
    escala_potencia: float = 10.0
    escala_tension: float = 10.0
    escala_corriente: float = 1000.0

    def clave(self, magnitud: str) -> str:
        """Clave del dato crudo de una magnitud (interruptor, potencia...) según el modo."""
        if self.modo == "nube":
            return getattr(self, "codigo_" + magnitud)
        return str(getattr(self, "dp_" + magnitud))


#: Enchufes de demostración que usa --simular cuando no hay ninguno configurado.
ENCHUFES_DEMO = tuple(Enchufe(nombre=n, modo="simulado", dev_id="demo%07d" % i)
                      for i, n in enumerate(("Nevera", "Lavadora", "Router"), 1))


@dataclass(frozen=True)
class Opciones:
    intervalo_vigilancia: float = 10
    tiempo_espera: float = 5
    tiempo_busqueda: int = 12


@dataclass(frozen=True)
class Configuracion:
    """Configuración efectiva tras fusionar código, JSON y línea de órdenes."""

    nube: ConfigNube
    enchufes: Tuple[Enchufe, ...]
    opciones: Opciones
    origen: Dict[str, str] = field(default_factory=dict)  # sección → «código» / «JSON …»
    ruta_json: Optional[Path] = None


@dataclass
class Lectura:
    """Resultado de leer un enchufe, ya en unidades físicas."""

    enchufe: str
    modo: str
    en_linea: bool
    encendido: Optional[bool] = None
    potencia_w: Optional[float] = None
    tension_v: Optional[float] = None
    corriente_a: Optional[float] = None
    error: Optional[str] = None
    hora: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))


# ════════════════════════════════════════════════════════════════════════════
# 4. CARGA Y VALIDACIÓN DE LA CONFIGURACIÓN
# ════════════════════════════════════════════════════════════════════════════

_ID_VALIDO = re.compile(r"^[A-Za-z0-9]{8,40}$")
_CODIGO_VALIDO = re.compile(r"^[a-z0-9_]{1,40}$")


def _leer_json(ruta: Path) -> Dict[str, Any]:
    """Lee el JSON de configuración (admite BOM de Windows) y comprueba su forma."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ErrorConfig("No se puede leer %s: %s" % (ruta, exc.strerror))
    except ValueError as exc:
        raise ErrorConfig("JSON no válido en %s: %s" % (ruta, exc))
    if not isinstance(datos, dict):
        raise ErrorConfig("%s debe contener un objeto JSON {…}" % ruta)
    for seccion, tipo in (("nube", dict), ("opciones", dict), ("enchufes", list)):
        if seccion in datos and not isinstance(datos[seccion], tipo):
            raise ErrorConfig("En %s, «%s» debe ser %s" % (ruta, seccion, "una lista" if tipo is list else "un objeto"))
    return datos


def _validar_enchufe(crudo: Dict[str, Any], posicion: int) -> Enchufe:
    """Convierte un diccionario de configuración en un Enchufe validado."""
    donde = "enchufe %d" % posicion
    if not isinstance(crudo, dict):
        raise ErrorConfig("El %s debe ser un objeto {…}" % donde)
    desconocidas = set(crudo) - set(Enchufe.__dataclass_fields__) - {"comentario"}
    if desconocidas:
        raise ErrorConfig("Campos desconocidos en el %s: %s" % (donde, ", ".join(sorted(desconocidas))))

    datos = {**DATOS_POR_DEFECTO, **crudo}
    nombre = str(datos.get("nombre", "")).strip()
    if not nombre:
        raise ErrorConfig("Falta «nombre» en el %s" % donde)
    donde = "enchufe «%s»" % nombre

    modo = str(datos.get("modo", "")).strip().lower()
    if modo not in MODOS:
        raise ErrorConfig("Modo no válido en el %s (usa: %s)" % (donde, ", ".join(MODOS)))
    dev_id = str(datos.get("dev_id", "")).strip()
    if not _ID_VALIDO.match(dev_id):
        raise ErrorConfig("Device ID no válido en el %s (8-40 caracteres alfanuméricos)" % donde)
    if modo == "local" and not str(datos.get("local_key", "")).strip():
        raise ErrorConfig("El %s está en modo local y le falta «local_key»" % donde)
    version = str(datos.get("version", "3.3"))
    if version not in VERSIONES_PROTOCOLO:
        raise ErrorConfig("Versión de protocolo no válida en el %s (%s)" % (donde, ", ".join(VERSIONES_PROTOCOLO)))

    try:
        numeros = {k: int(datos[k]) for k in ("dp_interruptor", "dp_potencia", "dp_tension", "dp_corriente")}
        escalas = {k: float(datos[k]) for k in ("escala_potencia", "escala_tension", "escala_corriente")}
    except (TypeError, ValueError):
        raise ErrorConfig("Los campos dp_* y escala_* del %s deben ser números" % donde)
    if any(e <= 0 for e in escalas.values()):
        raise ErrorConfig("Las escalas del %s deben ser mayores que cero" % donde)
    codigos = {k: str(datos[k]) for k in ("codigo_interruptor", "codigo_potencia", "codigo_tension", "codigo_corriente")}
    if not all(_CODIGO_VALIDO.match(c) for c in codigos.values()):
        raise ErrorConfig("Los códigos de la nube del %s solo admiten minúsculas, números y _" % donde)

    return Enchufe(nombre=nombre, modo=modo, dev_id=dev_id, local_key=str(datos.get("local_key", "")).strip(),
                   ip=str(datos.get("ip") or "Auto").strip(), version=version,
                   protegido=bool(datos.get("protegido", False)), **numeros, **codigos, **escalas)


def cargar_configuracion(ruta_json: Optional[Path] = None, usar_json: bool = True) -> Configuracion:
    """Fusiona variables del código y JSON (el JSON gana) y valida el resultado.

    :param ruta_json: fichero JSON; por defecto RUTA_JSON junto al script.
    :param usar_json: False para ignorar el JSON y usar solo las variables del código.
    """
    nube, enchufes, opciones = dict(NUBE), list(ENCHUFES), dict(OPCIONES)
    origen = {"nube": "código", "enchufes": "código", "opciones": "código"}

    ruta = Path(ruta_json) if ruta_json else Path(__file__).resolve().with_name(RUTA_JSON)
    explicita = ruta_json is not None
    if usar_json and ruta.exists():
        datos = _leer_json(ruta)
        etiqueta = "JSON (%s)" % ruta.name
        if "nube" in datos:
            nube.update(datos["nube"])
            origen["nube"] = etiqueta
        if "opciones" in datos:
            opciones.update(datos["opciones"])
            origen["opciones"] = etiqueta
        if "enchufes" in datos:
            enchufes = datos["enchufes"]  # la lista sustituye a la del código
            origen["enchufes"] = etiqueta
    elif usar_json and explicita:
        raise ErrorConfig("No existe el fichero de configuración %s" % ruta)

    # --- Nube ---------------------------------------------------------------
    region = str(nube.get("region", "eu")).strip()
    if region not in REGIONES:
        raise ErrorConfig("Región de la nube no válida: %s (usa: %s)" % (region, ", ".join(REGIONES)))
    secreto = str(nube.get("access_secret") or os.environ.get("TUYA_ACCESS_SECRET", "")).strip()
    cfg_nube = ConfigNube(region=region, access_id=str(nube.get("access_id", "")).strip(), access_secret=secreto)

    # --- Enchufes ---------------------------------------------------------------
    if len(enchufes) > MAX_ENCHUFES:
        raise ErrorConfig("Hay %d enchufes configurados; el máximo es %d" % (len(enchufes), MAX_ENCHUFES))
    lista = tuple(_validar_enchufe(e, i) for i, e in enumerate(enchufes, 1))
    for campo in ("nombre", "dev_id"):
        valores = [getattr(e, campo).lower() for e in lista]
        repetidos = {v for v in valores if valores.count(v) > 1}
        if repetidos:
            raise ErrorConfig("«%s» repetido en varios enchufes: %s" % (campo, ", ".join(sorted(repetidos))))

    # --- Opciones -----------------------------------------------------------------
    try:
        cfg_opciones = Opciones(intervalo_vigilancia=float(opciones["intervalo_vigilancia"]),
                                tiempo_espera=float(opciones["tiempo_espera"]),
                                tiempo_busqueda=int(opciones["tiempo_busqueda"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorConfig("Opción no válida: %s" % exc)

    return Configuracion(nube=cfg_nube, enchufes=lista, opciones=cfg_opciones, origen=origen,
                         ruta_json=ruta if (usar_json and ruta.exists()) else None)


def resolver_enchufes(cfg: Configuracion, referencias: Sequence[str]) -> List[Enchufe]:
    """Traduce referencias (nombre, posición 1-7, Device ID o «todos») a enchufes."""
    if not cfg.enchufes:
        raise ErrorConfig("No hay enchufes configurados (edita ENCHUFES o el JSON, o usa --simular)")
    if not referencias or any(r.lower() == "todos" for r in referencias):
        return list(cfg.enchufes)
    elegidos: List[Enchufe] = []
    for ref in referencias:
        encontrado = None
        if ref.isdigit() and 1 <= int(ref) <= len(cfg.enchufes):
            encontrado = cfg.enchufes[int(ref) - 1]
        else:
            encontrado = next((e for e in cfg.enchufes if ref.lower() in (e.nombre.lower(), e.dev_id.lower())), None)
        if encontrado is None:
            nombres = ", ".join("%d=%s" % (i, e.nombre) for i, e in enumerate(cfg.enchufes, 1))
            raise ErrorConfig("Enchufe desconocido: «%s». Disponibles: %s" % (ref, nombres))
        if encontrado not in elegidos:
            elegidos.append(encontrado)
    return elegidos


def guardar_json(ruta: Path, datos: Dict[str, Any]) -> None:
    """Escribe el JSON de configuración con permisos 600 (contiene claves)."""
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(ruta, 0o600)
    except OSError:  # p. ej. en Windows
        pass


# ════════════════════════════════════════════════════════════════════════════
# 5. CONECTORES: cómo se habla con cada tipo de enchufe
# ----------------------------------------------------------------------------
# Todos implementan la misma interfaz (Conector), de modo que las órdenes no
# necesitan saber si el enchufe es local, de la nube o simulado.
# ════════════════════════════════════════════════════════════════════════════

def _tinytuya():
    """Importa TinyTuya solo cuando hace falta (el modo simulado no la necesita)."""
    try:
        import tinytuya  # noqa: WPS433 (import perezoso deliberado)
    except ImportError:
        raise FaltaDependencia("Falta TinyTuya. Instálala con:  pip install tinytuya")
    return tinytuya


def _escalar(datos: Dict[str, Any], clave: str, divisor: float) -> Optional[float]:
    """Valor crudo → unidades físicas; None si no existe o no es numérico."""
    valor = datos.get(clave)
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return round(float(valor) / divisor, 3)
    except (TypeError, ValueError):
        return None


def interpretar(enchufe: Enchufe, datos: Dict[str, Any], en_linea: bool = True) -> Lectura:
    """Convierte los datos crudos (DPS o códigos de la nube) en una Lectura."""
    interruptor = datos.get(enchufe.clave("interruptor"))
    return Lectura(
        enchufe=enchufe.nombre, modo=enchufe.modo, en_linea=en_linea,
        encendido=None if interruptor is None else bool(interruptor),
        potencia_w=_escalar(datos, enchufe.clave("potencia"), enchufe.escala_potencia),
        tension_v=_escalar(datos, enchufe.clave("tension"), enchufe.escala_tension),
        corriente_a=_escalar(datos, enchufe.clave("corriente"), enchufe.escala_corriente),
    )


class Conector(ABC):
    """Interfaz común de acceso a un enchufe."""

    def __init__(self, enchufe: Enchufe):
        self.enchufe = enchufe

    @abstractmethod
    def datos_crudos(self) -> Dict[str, Any]:
        """Diccionario {clave: valor} tal como lo devuelve el enchufe o la nube."""

    @abstractmethod
    def conmutar(self, encender: bool) -> None:
        """Enciende (True) o apaga (False) el enchufe."""

    def leer(self) -> Lectura:
        """Lectura en unidades físicas. Nunca lanza: los fallos van en Lectura.error."""
        try:
            return interpretar(self.enchufe, self.datos_crudos())
        except ErrorEnchufe as exc:
            return Lectura(enchufe=self.enchufe.nombre, modo=self.enchufe.modo, en_linea=False, error=str(exc))


class ConectorLocal(Conector):
    """Protocolo local de Tuya (TCP 6668) mediante tinytuya.OutletDevice."""

    def __init__(self, enchufe: Enchufe, tiempo_espera: float = 5):
        super().__init__(enchufe)
        self.tiempo_espera = tiempo_espera
        self._dispositivo = None

    def _ip(self) -> str:
        if self.enchufe.ip.lower() != "auto":
            return self.enchufe.ip
        log.debug("Buscando la IP de %s por difusión UDP…", self.enchufe.nombre)
        encontrado = _tinytuya().find_device(self.enchufe.dev_id)
        if not encontrado.get("ip"):
            raise ErrorEnchufe("No se encuentra el enchufe en la red local (¿misma red? ¿encendido?)")
        return encontrado["ip"]

    def _cliente(self):
        if self._dispositivo is None:
            tt = _tinytuya()
            self._dispositivo = tt.OutletDevice(
                self.enchufe.dev_id, address=self._ip(), local_key=self.enchufe.local_key,
                version=float(self.enchufe.version), connection_timeout=self.tiempo_espera,
                connection_retry_limit=1, connection_retry_delay=1)
        return self._dispositivo

    @staticmethod
    def _comprobar(respuesta: Any) -> Dict[str, Any]:
        """Lanza ErrorEnchufe con un mensaje claro si TinyTuya devolvió un error."""
        if isinstance(respuesta, dict) and ("Err" in respuesta or "Error" in respuesta):
            codigo = str(respuesta.get("Err", ""))
            texto = ERRORES_LOCALES.get(codigo) or str(respuesta.get("Error") or "Error desconocido")
            raise ErrorEnchufe("%s (Err %s)" % (texto, codigo) if codigo else texto)
        if not isinstance(respuesta, dict):
            raise ErrorEnchufe("Respuesta no válida del enchufe")
        return respuesta

    def datos_crudos(self) -> Dict[str, Any]:
        respuesta = self._comprobar(self._cliente().status())
        if "dps" not in respuesta:
            raise ErrorEnchufe("El enchufe no devolvió datos (DPS)")
        return {str(k): v for k, v in respuesta["dps"].items()}

    def conmutar(self, encender: bool) -> None:
        self._comprobar(self._cliente().set_status(bool(encender), switch=self.enchufe.dp_interruptor) or {})


class SesionNube:
    """Sesión compartida con la API de Tuya: un único token para toda la ejecución."""

    def __init__(self, cfg: ConfigNube):
        self.cfg = cfg
        self._cliente = None
        self.llamadas = 0  # llamadas a la API en esta ejecución (el plan gratuito tiene cupo)

    def cliente(self):
        if self._cliente is None:
            if not self.cfg.completa:
                raise ErrorEnchufe("Faltan access_id/access_secret de la nube (NUBE en el código o «nube» en el JSON)")
            tt = _tinytuya()
            self.llamadas += 1
            cliente = tt.Cloud(apiRegion=self.cfg.region, apiKey=self.cfg.access_id,
                               apiSecret=self.cfg.access_secret, configFile=os.devnull)
            if not getattr(cliente, "token", None):
                raise ErrorEnchufe("No se pudo iniciar sesión en la nube de Tuya: %s"
                                   % _mensaje_nube(getattr(cliente, "error", None)))
            self._cliente = cliente
        return self._cliente

    def llamar(self, metodo: str, *args: Any) -> Dict[str, Any]:
        """Invoca un método de tinytuya.Cloud y comprueba la respuesta."""
        cliente = self.cliente()
        self.llamadas += 1
        respuesta = getattr(cliente, metodo)(*args)
        if isinstance(respuesta, list):  # getdevices() devuelve directamente una lista
            return {"result": respuesta}
        if not isinstance(respuesta, dict) or not respuesta.get("success", "Error" not in (respuesta or {})):
            raise ErrorEnchufe("La nube de Tuya respondió con error: %s" % _mensaje_nube(respuesta))
        return respuesta


def _mensaje_nube(respuesta: Any) -> str:
    if isinstance(respuesta, dict):
        for clave in ("msg", "Payload", "Error"):
            if respuesta.get(clave):
                return str(respuesta[clave])
    return "respuesta no válida"


class ConectorNube(Conector):
    """API de Tuya IoT (tinytuya.Cloud): estado, conexión y órdenes."""

    def __init__(self, enchufe: Enchufe, sesion: SesionNube):
        super().__init__(enchufe)
        self.sesion = sesion

    def datos_crudos(self) -> Dict[str, Any]:
        estado = self.sesion.llamar("getstatus", self.enchufe.dev_id)
        return {item["code"]: item.get("value") for item in estado.get("result") or [] if "code" in item}

    def en_linea(self) -> Optional[bool]:
        """Estado de conexión según la nube (None si no se puede saber)."""
        try:
            resultado = self.sesion.llamar("getconnectstatus", self.enchufe.dev_id).get("result")
        except ErrorEnchufe:
            return None
        return resultado if isinstance(resultado, bool) else None

    def leer(self) -> Lectura:
        lectura = super().leer()
        if lectura.en_linea and self.en_linea() is False:
            # La nube conserva el último estado conocido: hay que avisar de que no es actual.
            lectura.en_linea = False
            lectura.error = "Desconectado: la nube muestra el último estado conocido"
        return lectura

    def conmutar(self, encender: bool) -> None:
        orden = {"commands": [{"code": self.enchufe.codigo_interruptor, "value": bool(encender)}]}
        self.sesion.llamar("sendcommand", self.enchufe.dev_id, orden)


class ConectorSimulado(Conector):
    """Enchufe ficticio con consumo verosímil. Su estado on/off persiste entre ejecuciones."""

    FICHERO_ESTADO = Path(tempfile.gettempdir()) / "telehome-enchufes-pruebas-simulado.json"

    def _estados(self) -> Dict[str, bool]:
        try:
            return json.loads(self.FICHERO_ESTADO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def datos_crudos(self) -> Dict[str, Any]:
        encendido = self._estados().get(self.enchufe.dev_id, True)
        base = 20 + sum(map(ord, self.enchufe.dev_id)) % 180          # W, distinto por enchufe
        potencia = base * (1 + 0.15 * math.sin(time.time() / 40)) + random.uniform(-1.5, 1.5) if encendido else 0.0
        tension = 230 + random.uniform(-1.5, 1.5)
        corriente = potencia / tension
        e = self.enchufe
        return {  # mismos datos crudos que un enchufe real, con su mapa y escalas
            e.clave("interruptor"): encendido,
            e.clave("potencia"): round(potencia * e.escala_potencia),
            e.clave("tension"): round(tension * e.escala_tension),
            e.clave("corriente"): round(corriente * e.escala_corriente),
        }

    def conmutar(self, encender: bool) -> None:
        estados = self._estados()
        estados[self.enchufe.dev_id] = bool(encender)
        self.FICHERO_ESTADO.write_text(json.dumps(estados), encoding="utf-8")


def crear_conectores(cfg: Configuracion, enchufes: Iterable[Enchufe], simular: bool = False) -> List[Conector]:
    """Crea el conector adecuado para cada enchufe (con una sola sesión de nube)."""
    sesion = SesionNube(cfg.nube)
    conectores: List[Conector] = []
    for e in enchufes:
        if simular or e.modo == "simulado":
            conectores.append(ConectorSimulado(replace(e, modo="simulado") if simular else e))
        elif e.modo == "nube":
            conectores.append(ConectorNube(e, sesion))
        else:
            conectores.append(ConectorLocal(e, cfg.opciones.tiempo_espera))
    return conectores


def _sesion_de(conectores: Sequence[Conector]) -> Optional[SesionNube]:
    return next((c.sesion for c in conectores if isinstance(c, ConectorNube)), None)


# ════════════════════════════════════════════════════════════════════════════
# 6. PRESENTACIÓN
# ════════════════════════════════════════════════════════════════════════════

class Salida:
    """Muestra resultados como tabla legible o como JSON (opción --json)."""

    def __init__(self, como_json: bool = False):
        self.como_json = como_json

    def json(self, datos: Any) -> None:
        print(json.dumps(datos, ensure_ascii=False, indent=2, default=str))

    def lecturas(self, lecturas: Sequence[Lectura]) -> None:
        if self.como_json:
            return self.json([asdict(l) for l in lecturas])
        filas = [(l.enchufe, l.modo,
                  "sí" if l.en_linea else "NO",
                  "—" if l.encendido is None else ("ON" if l.encendido else "off"),
                  _num(l.potencia_w, 1), _num(l.tension_v, 1), _num(l.corriente_a, 3),
                  l.error or "") for l in lecturas]
        self.tabla(("Enchufe", "Modo", "En línea", "Estado", "Potencia W", "Tensión V", "Corriente A", "Observaciones"),
                   filas, derecha={4, 5, 6})

    def tabla(self, cabecera: Sequence[str], filas: Sequence[Sequence[Any]], derecha: Iterable[int] = ()) -> None:
        derecha = set(derecha)
        anchos = [max(len(str(x)) for x in col) for col in zip(cabecera, *filas)] if filas else [len(c) for c in cabecera]

        def linea(valores):
            celdas = [(str(v).rjust(a) if i in derecha else str(v).ljust(a)) for i, (v, a) in enumerate(zip(valores, anchos))]
            return "  ".join(celdas).rstrip()

        print(linea(cabecera))
        print("  ".join("─" * a for a in anchos))
        for fila in filas:
            print(linea(fila))

    def mensaje(self, texto: str) -> None:
        if not self.como_json:
            print(texto)


def _num(valor: Optional[float], decimales: int) -> str:
    return "—" if valor is None else ("%.*f" % (decimales, valor)).replace(".", ",")


def _ocultar(secreto: str) -> str:
    """Muestra solo el principio y el final de un secreto."""
    if not secreto:
        return "(vacío)"
    return secreto[:3] + "…" + secreto[-2:] if len(secreto) > 8 else "***"


# ════════════════════════════════════════════════════════════════════════════
# 7. ÓRDENES
# ----------------------------------------------------------------------------
# Cada orden recibe los argumentos ya analizados, la configuración y la salida,
# y devuelve un código de salida.
# ════════════════════════════════════════════════════════════════════════════

def orden_listar(args, cfg: Configuracion, out: Salida) -> int:
    """Lista los enchufes configurados (sin claves)."""
    if out.como_json:
        out.json([{**{k: v for k, v in asdict(e).items() if k != "local_key"}, "posicion": i}
                  for i, e in enumerate(cfg.enchufes, 1)])
        return SALIDA_OK
    if not cfg.enchufes:
        out.mensaje("No hay enchufes configurados. Edita ENCHUFES en el código o el JSON (o usa --simular).")
        return SALIDA_OK
    out.tabla(("#", "Nombre", "Modo", "Device ID", "IP / versión", "Protegido"),
              [(i, e.nombre, e.modo, e.dev_id, "%s · v%s" % (e.ip, e.version) if e.modo == "local" else "—",
                "sí" if e.protegido else "") for i, e in enumerate(cfg.enchufes, 1)])
    out.mensaje("\n%d/%d enchufes · configuración: %s" % (len(cfg.enchufes), MAX_ENCHUFES, cfg.origen["enchufes"]))
    return SALIDA_OK


def orden_config(args, cfg: Configuracion, out: Salida) -> int:
    """Muestra la configuración efectiva y de dónde sale cada parte (secretos ocultos)."""
    resumen = {
        "json": str(cfg.ruta_json) if cfg.ruta_json else None,
        "origen": cfg.origen,
        "nube": {"region": cfg.nube.region, "access_id": cfg.nube.access_id,
                 "access_secret": _ocultar(cfg.nube.access_secret)},
        "opciones": asdict(cfg.opciones),
        "enchufes": [{**asdict(e), "local_key": _ocultar(e.local_key)} for e in cfg.enchufes],
    }
    out.json(resumen)
    return SALIDA_OK


def orden_estado(args, cfg: Configuracion, out: Salida) -> int:
    """Lee y muestra el estado de los enchufes indicados (todos por defecto)."""
    conectores = crear_conectores(cfg, resolver_enchufes(cfg, args.enchufes), args.simular)
    lecturas = [c.leer() for c in conectores]
    out.lecturas(lecturas)
    _informar_llamadas(conectores, out)
    return SALIDA_OK if all(l.en_linea for l in lecturas) else SALIDA_FALLO


def _orden_conmutar(args, cfg: Configuracion, out: Salida, accion: str) -> int:
    """Lógica común de encender/apagar/conmutar, con protección y verificación."""
    enchufes = resolver_enchufes(cfg, args.enchufes)
    if accion != "encender" and not args.forzar:
        protegidos = [e.nombre for e in enchufes if e.protegido]
        if protegidos:
            raise ErrorConfig("Enchufe protegido: %s. Usa --forzar si de verdad quieres %s."
                              % (", ".join(protegidos), "apagarlo" if accion == "apagar" else "conmutarlo"))
    if "todos" in [r.lower() for r in args.enchufes] and accion != "encender" and not args.si:
        raise ErrorConfig("Para %s TODOS los enchufes añade --si" % accion)

    resultados, fallos = [], 0
    for conector in crear_conectores(cfg, enchufes, args.simular):
        try:
            if accion == "conmutar":
                actual = conector.leer()
                if actual.encendido is None:
                    raise ErrorEnchufe(actual.error or "No se conoce el estado actual")
                destino = not actual.encendido
            else:
                destino = accion == "encender"
            conector.conmutar(destino)
            time.sleep(args.espera)  # deja que el enchufe aplique la orden antes de verificar
            lectura = conector.leer()
            ok = lectura.encendido is destino
            if not ok and not lectura.error:
                lectura.error = "La orden se envió, pero el estado leído no coincide (la nube puede tardar)"
        except ErrorEnchufe as exc:
            lectura = Lectura(enchufe=conector.enchufe.nombre, modo=conector.enchufe.modo, en_linea=False, error=str(exc))
            ok = False
        fallos += not ok
        resultados.append(lectura)
    out.lecturas(resultados)
    return SALIDA_FALLO if fallos else SALIDA_OK


def orden_encender(args, cfg, out):
    return _orden_conmutar(args, cfg, out, "encender")


def orden_apagar(args, cfg, out):
    return _orden_conmutar(args, cfg, out, "apagar")


def orden_conmutar(args, cfg, out):
    return _orden_conmutar(args, cfg, out, "conmutar")


def orden_vigilar(args, cfg: Configuracion, out: Salida) -> int:
    """Lee periódicamente y muestra (y opcionalmente guarda en CSV) las lecturas."""
    conectores = crear_conectores(cfg, resolver_enchufes(cfg, args.enchufes), args.simular)
    intervalo = args.intervalo or cfg.opciones.intervalo_vigilancia
    minimo = max(INTERVALO_MINIMO["simulado" if args.simular else c.enchufe.modo] for c in conectores)
    if intervalo < minimo:
        out.mensaje("Aviso: intervalo ajustado a %g s (mínimo para estos enchufes)." % minimo)
        intervalo = minimo

    fichero = open(args.csv, "a", newline="", encoding="utf-8") if args.csv else None
    escritor = csv.writer(fichero) if fichero else None
    if escritor and fichero.tell() == 0:
        escritor.writerow(["hora", "enchufe", "modo", "en_linea", "encendido", "potencia_w", "tension_v", "corriente_a", "error"])
    out.mensaje("Vigilando %d enchufe(s) cada %g s%s. Ctrl+C para terminar.\n"
                % (len(conectores), intervalo, " → " + args.csv if args.csv else ""))
    try:
        n = 0
        while args.veces == 0 or n < args.veces:
            inicio = time.monotonic()
            for lectura in (c.leer() for c in conectores):
                if out.como_json:
                    print(json.dumps(asdict(lectura), ensure_ascii=False), flush=True)  # una línea por lectura
                else:
                    print("%s  %-20s %-4s %8s W %7s V %7s A  %s" % (
                        lectura.hora[11:], lectura.enchufe[:20],
                        "—" if lectura.encendido is None else ("ON" if lectura.encendido else "off"),
                        _num(lectura.potencia_w, 1), _num(lectura.tension_v, 1), _num(lectura.corriente_a, 3),
                        lectura.error or ""), flush=True)
                if escritor:
                    escritor.writerow([lectura.hora, lectura.enchufe, lectura.modo, lectura.en_linea, lectura.encendido,
                                       lectura.potencia_w, lectura.tension_v, lectura.corriente_a, lectura.error or ""])
                    fichero.flush()
            n += 1
            if args.veces == 0 or n < args.veces:
                time.sleep(max(0.0, intervalo - (time.monotonic() - inicio)))
    finally:
        if fichero:
            fichero.close()
        _informar_llamadas(conectores, out)
    return SALIDA_OK


def orden_dps(args, cfg: Configuracion, out: Salida) -> int:
    """Muestra los datos crudos del enchufe para ajustar el mapa dp_*/codigo_* y las escalas."""
    enchufe = resolver_enchufes(cfg, [args.enchufe])[0]
    conector = crear_conectores(cfg, [enchufe], args.simular)[0]
    try:
        crudos = conector.datos_crudos()
    except ErrorEnchufe as exc:
        raise ErrorEnchufe("%s: %s" % (enchufe.nombre, exc))
    if out.como_json:
        out.json(crudos)
        return SALIDA_OK
    nombres = {"interruptor": "interruptor", "potencia": "potencia", "tension": "tensión", "corriente": "corriente"}
    usados = {enchufe.clave(m): etiqueta for m, etiqueta in nombres.items()}
    out.tabla(("Clave", "Valor crudo", "Se usa como"),
              [(k, json.dumps(v, ensure_ascii=False), usados.get(str(k), "")) for k, v in crudos.items()])
    faltan = [m for k, m in usados.items() if k not in {str(x) for x in crudos}]
    if faltan:
        out.mensaje("\nAviso: no aparecen datos para %s; revisa el mapa (%s) de este enchufe."
                    % (", ".join(faltan), "codigo_*" if enchufe.modo == "nube" else "dp_*"))
    return SALIDA_OK


def orden_buscar(args, cfg: Configuracion, out: Salida) -> int:
    """Busca enchufes Tuya en la red local por difusión UDP (puertos 6666/6667)."""
    tt = _tinytuya()
    tiempo = args.tiempo or cfg.opciones.tiempo_busqueda
    out.mensaje("Escuchando %d s en la red local…" % tiempo)
    encontrados = tt.deviceScan(verbose=False, scantime=tiempo, color=False, poll=False, byID=True) or {}
    filas = [{"dev_id": k, "ip": v.get("ip"), "version": str(v.get("version", ""))} for k, v in encontrados.items()]
    if out.como_json:
        out.json(filas)
    elif filas:
        out.tabla(("Device ID", "IP", "Versión"), [(f["dev_id"], f["ip"], f["version"]) for f in filas])
    else:
        out.mensaje("No se ha encontrado ningún dispositivo Tuya en esta red.")
    return SALIDA_OK if filas else SALIDA_FALLO


def orden_nube_dispositivos(args, cfg: Configuracion, out: Salida) -> int:
    """Lista los dispositivos de la cuenta enlazada en la nube y, con --guardar, los añade al JSON."""
    sesion = SesionNube(cfg.nube)
    try:
        dispositivos = sesion.llamar("getdevices").get("result") or []
    except ErrorEnchufe as exc:
        raise ErrorEnchufe("No se pudo obtener la lista de la nube: %s" % exc)
    if out.como_json:
        out.json([{k: v for k, v in d.items() if k != "key"} for d in dispositivos])
    else:
        out.tabla(("Device ID", "Nombre", "Categoría", "Producto", "En línea"),
                  [(d.get("id"), d.get("name"), d.get("category", ""), d.get("product_name", ""),
                    "sí" if d.get("online") else "no") for d in dispositivos])
        out.mensaje("\n%d dispositivos en la cuenta (%d llamadas a la API)." % (len(dispositivos), sesion.llamadas))
    if args.guardar:
        _guardar_dispositivos_nube(cfg, dispositivos, args.todos, out)
    return SALIDA_OK


def _guardar_dispositivos_nube(cfg: Configuracion, dispositivos: List[Dict[str, Any]], todos: bool, out: Salida) -> None:
    """Añade (sin duplicar) los enchufes de la nube a la lista «enchufes» del JSON."""
    ruta = cfg.ruta_json or Path(__file__).resolve().with_name(RUTA_JSON)
    datos = _leer_json(ruta) if ruta.exists() else {"nube": {"region": cfg.nube.region, "access_id": cfg.nube.access_id}}
    actuales = datos.setdefault("enchufes", [asdict_sin_defectos(e) for e in cfg.enchufes])
    conocidos = {str(e.get("dev_id")) for e in actuales}
    nuevos = [d for d in dispositivos if d.get("id") not in conocidos and (todos or d.get("category") in ("cz", "pc"))]
    hueco = MAX_ENCHUFES - len(actuales)
    for d in nuevos[:max(hueco, 0)]:
        actuales.append({"nombre": str(d.get("name") or d["id"])[:40], "modo": "nube", "dev_id": d["id"],
                         "local_key": d.get("key", "")})  # la Local Key sirve para pasarlo luego a modo local
    guardar_json(ruta, datos)
    out.mensaje("Guardados %d enchufes nuevos en %s%s" % (min(len(nuevos), max(hueco, 0)), ruta,
                ("; %d no caben (máximo %d)" % (len(nuevos) - hueco, MAX_ENCHUFES)) if len(nuevos) > hueco else ""))


def asdict_sin_defectos(enchufe: Enchufe) -> Dict[str, Any]:
    """Enchufe → diccionario con solo los campos distintos de los valores por defecto."""
    defecto = Enchufe(nombre="", modo="", dev_id="")
    return {k: v for k, v in asdict(enchufe).items()
            if k in ("nombre", "modo", "dev_id") or v != getattr(defecto, k)}


def _informar_llamadas(conectores: Sequence[Conector], out: Salida) -> None:
    sesion = _sesion_de(conectores)
    if sesion and sesion.llamadas:
        out.mensaje("(llamadas a la API de la nube en esta ejecución: %d)" % sesion.llamadas)


# ════════════════════════════════════════════════════════════════════════════
# 8. LÍNEA DE ÓRDENES
# ════════════════════════════════════════════════════════════════════════════

def construir_parser() -> argparse.ArgumentParser:
    """Define las opciones generales y una subórden por cada acción."""
    p = argparse.ArgumentParser(
        prog="telehome-enchufes-pruebas",
        description="Pruebas preliminares de enchufes Tuya/Energeeks (local, nube o simulado).",
        epilog="Los enchufes se indican por nombre, posición (1-%d), Device ID o «todos»." % MAX_ENCHUFES)
    p.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    p.add_argument("-c", "--config", type=Path, help="fichero JSON de configuración (por defecto %s)" % RUTA_JSON)
    p.add_argument("--sin-json", action="store_true", help="usar solo las variables del código")
    p.add_argument("--simular", action="store_true", help="tratar todos los enchufes como simulados")
    p.add_argument("--json", action="store_true", help="salida en JSON")
    p.add_argument("-v", "--verbose", action="count", default=0, help="más detalle (-vv incluye TinyTuya)")
    sub = p.add_subparsers(dest="orden", metavar="ORDEN")

    def orden(nombre, funcion, ayuda):
        s = sub.add_parser(nombre, help=ayuda, description=ayuda)
        s.set_defaults(funcion=funcion)
        return s

    orden("listar", orden_listar, "lista los enchufes configurados")
    orden("config", orden_config, "muestra la configuración efectiva (secretos ocultos)")
    orden("estado", orden_estado, "estado, potencia, tensión y corriente").add_argument(
        "enchufes", nargs="*", metavar="ENCHUFE", help="por defecto, todos")

    for nombre, funcion, ayuda in (("encender", orden_encender, "enciende los enchufes indicados"),
                                   ("apagar", orden_apagar, "apaga los enchufes indicados"),
                                   ("conmutar", orden_conmutar, "invierte el estado de los enchufes indicados")):
        s = orden(nombre, funcion, ayuda)
        s.add_argument("enchufes", nargs="+", metavar="ENCHUFE")
        s.add_argument("--forzar", action="store_true", help="permite apagar enchufes protegidos")
        s.add_argument("--si", action="store_true", help="confirma una acción sobre «todos»")
        s.add_argument("--espera", type=float, default=2.0, help="s antes de verificar el estado (2)")

    s = orden("vigilar", orden_vigilar, "lecturas periódicas en pantalla (y CSV)")
    s.add_argument("enchufes", nargs="*", metavar="ENCHUFE", help="por defecto, todos")
    s.add_argument("-i", "--intervalo", type=float, help="segundos entre lecturas")
    s.add_argument("-n", "--veces", type=int, default=0, help="número de lecturas (0 = sin fin)")
    s.add_argument("--csv", help="añade las lecturas a este fichero CSV")

    orden("dps", orden_dps, "datos crudos de un enchufe (para ajustar el mapa)").add_argument("enchufe")
    orden("buscar", orden_buscar, "busca enchufes Tuya en la red local").add_argument(
        "--tiempo", type=int, help="segundos de escucha")
    s = orden("nube-dispositivos", orden_nube_dispositivos, "lista los dispositivos de la cuenta de la nube")
    s.add_argument("--guardar", action="store_true", help="añade los enchufes al JSON de configuración")
    s.add_argument("--todos", action="store_true", help="con --guardar, incluir también lo que no sean enchufes")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto de entrada: analiza argumentos, carga la configuración y ejecuta la orden."""
    parser = construir_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    if args.orden is None:
        parser.print_help()
        return SALIDA_CONFIG

    out = Salida(como_json=args.json)
    try:
        if args.verbose > 1:
            _tinytuya().set_debug(True)
        cfg = cargar_configuracion(args.config, usar_json=not args.sin_json)
        if args.simular and not cfg.enchufes:
            cfg = replace(cfg, enchufes=ENCHUFES_DEMO, origen={**cfg.origen, "enchufes": "demostración (--simular)"})
        return args.funcion(args, cfg, out)
    except ErrorConfig as exc:
        print("Error de configuración: %s" % exc, file=sys.stderr)
        return SALIDA_CONFIG
    except ErrorEnchufe as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return SALIDA_FALLO
    except FaltaDependencia as exc:
        print(exc, file=sys.stderr)
        return SALIDA_DEPENDENCIA
    except KeyboardInterrupt:
        print("\nInterrumpido.", file=sys.stderr)
        return SALIDA_INTERRUMPIDO


if __name__ == "__main__":
    sys.exit(main())

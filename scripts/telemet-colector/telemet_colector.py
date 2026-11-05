#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TeleMet Colector — lectura continua de la estación meteorológica y
histórico de 24 h (configurable) en el servidor Linux.

Qué hace
--------
1. Cada `intervalo_s` segundos consulta la API de Weather Underground
   (Earth Network) de tu estación personal (endpoint "current").
2. Guarda cada lectura en una base SQLite local (solo biblioteca estándar
   de Python: no hay que instalar nada con pip).
3. Con `modo = deslizante` (por defecto) va descartando las lecturas con más
   de `duracion_horas` (24 por defecto), de modo que siempre conserva las
   últimas 24 h (sirven para las gráficas de 12 h y de 24 h de la app). Las
   horas pueden cambiarse en config.ini, con la opción --horas o con la
   variable de entorno TELEMET_HORAS.
   Con `modo = reinicio`, cuando ha transcurrido `duracion_horas` desde el
   inicio del ciclo BORRA todos los datos y empieza un ciclo nuevo.
4. Tras cada lectura exporta el histórico a un fichero JSON estático dentro
   de la carpeta que sirve Apache, junto a la app TeleMet Historial. La
   app lo lee al abrirse y rellena con él los huecos de sus gráficas de
   evolución de 12 y 24 horas.

Todos los parámetros importantes están en `config.ini` (ver
`config.example.ini`) y los dos secretos pueden darse por variables de
entorno: TELEMET_STATION_ID y TELEMET_API_KEY.

Uso
---
    python3 telemet_colector.py                 # servicio continuo
    python3 telemet_colector.py -c /ruta/config.ini
    python3 telemet_colector.py --horas 48              # guarda 48 h en lugar de las 24 h por defecto
    python3 telemet_colector.py --una-vez       # una lectura, la guarda, exporta y sale
    python3 telemet_colector.py --probar        # una lectura, la muestra y sale (no guarda nada)
    python3 telemet_colector.py --estado        # resumen de lo guardado en la BD
"""

import argparse
import configparser
import json
import logging
import logging.handlers
import math
import os
import signal
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0"
FORMATO_JSON = 1  # versión del formato del JSON exportado (la app la comprueba)

log = logging.getLogger("telemet_colector")

# ----------------------------------------------------------------------
# VALORES POR DEFECTO (todos se pueden cambiar en config.ini)
# ----------------------------------------------------------------------
DEFECTOS = {
    "estacion": {
        "station_id": "",
        "api_key": "",
    },
    "lectura": {
        "url_base": "https://api.weather.com/v2/pws/observations/current",
        "intervalo_s": "300",      # segundos entre consultas
        "timeout_s": "15",         # tiempo límite de cada petición
        "backoff_base_s": "2",     # reintento tras un fallo: base * 2^n ...
        "backoff_max_s": "300",    # ... con este tope
    },
    "ciclo": {
        "duracion_horas": "24",   # horas de histórico (24 = gráficas de 12 h y de 24 h)
        # deslizante -> solo se borran las lecturas con más de `duracion_horas`
        # reinicio   -> al cumplirse las horas se borra TODO y se empieza de cero
        "modo": "deslizante",
    },
    "almacen": {
        "ruta_bd": "./datos/telemet.sqlite",
    },
    "salida": {
        "ruta_json": "/var/www/htdocs/rafa/telemethistorial/datos/historial.json",
        "decimales": "2",
    },
    "log": {
        "nivel": "INFO",
        "fichero": "",             # vacío = solo salida estándar (journald con systemd)
    },
}


# ----------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------
class Config:
    def __init__(self, ruta_ini, horas=None):
        cp = configparser.ConfigParser(interpolation=None)
        cp.read_dict(DEFECTOS)
        if ruta_ini:
            if not os.path.isfile(ruta_ini):
                raise SystemExit("No existe el fichero de configuración: %s" % ruta_ini)
            cp.read(ruta_ini, encoding="utf-8")
        self.base_dir = os.path.dirname(os.path.abspath(ruta_ini)) if ruta_ini else os.getcwd()

        # Los secretos pueden venir del entorno (tienen prioridad sobre el .ini).
        self.station_id = (os.environ.get("TELEMET_STATION_ID") or cp.get("estacion", "station_id")).strip()
        self.api_key = (os.environ.get("TELEMET_API_KEY") or cp.get("estacion", "api_key")).strip()

        self.url_base = cp.get("lectura", "url_base").strip()
        self.intervalo_s = max(5.0, cp.getfloat("lectura", "intervalo_s"))
        self.timeout_s = max(1.0, cp.getfloat("lectura", "timeout_s"))
        self.backoff_base_s = max(0.5, cp.getfloat("lectura", "backoff_base_s"))
        self.backoff_max_s = max(self.backoff_base_s, cp.getfloat("lectura", "backoff_max_s"))

        # Horas de histórico: --horas (línea de órdenes) > TELEMET_HORAS (entorno) > config.ini.
        valor_horas = horas if horas is not None else (os.environ.get("TELEMET_HORAS") or "").strip() or None
        try:
            self.duracion_h = float(valor_horas) if valor_horas is not None else cp.getfloat("ciclo", "duracion_horas")
        except ValueError:
            raise SystemExit("Las horas de histórico (--horas / TELEMET_HORAS / [ciclo] duracion_horas) deben ser un número.")
        if self.duracion_h <= 0:
            raise SystemExit("Las horas de histórico (duracion_horas) deben ser > 0")
        self.modo = cp.get("ciclo", "modo").strip().lower()
        if self.modo not in ("reinicio", "deslizante"):
            raise SystemExit("[ciclo] modo debe ser 'reinicio' o 'deslizante'")

        self.ruta_bd = self._ruta(cp.get("almacen", "ruta_bd"))
        self.ruta_json = self._ruta(cp.get("salida", "ruta_json"))
        self.decimales = max(0, cp.getint("salida", "decimales"))

        self.nivel_log = cp.get("log", "nivel").strip().upper()
        self.fichero_log = cp.get("log", "fichero").strip()
        if self.fichero_log:
            self.fichero_log = self._ruta(self.fichero_log)

    def _ruta(self, ruta):
        ruta = os.path.expanduser(ruta.strip())
        return ruta if os.path.isabs(ruta) else os.path.normpath(os.path.join(self.base_dir, ruta))

    @property
    def duracion_ms(self):
        return int(self.duracion_h * 3600 * 1000)


# ----------------------------------------------------------------------
# EXTRACCIÓN DE VALORES (misma lógica que extraerValores() de la app,
# para que lo guardado aquí sea idéntico a lo que guarda el navegador)
# ----------------------------------------------------------------------
def _first_defined(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


def _finito(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def indice_calor_c(t_c, rh):
    t_f = t_c * 9 / 5 + 32
    if t_f < 80 or rh is None or not _finito(rh):
        return t_c
    hi = (-42.379 + 2.04901523 * t_f + 10.14333127 * rh - 0.22475541 * t_f * rh
          - 0.00683783 * t_f * t_f - 0.05481717 * rh * rh + 0.00122874 * t_f * t_f * rh
          + 0.00085282 * t_f * rh * rh - 0.00000199 * t_f * t_f * rh * rh)
    if rh < 13 and 80 <= t_f <= 112:
        hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t_f - 95)) / 17)
    elif rh > 85 and 80 <= t_f <= 87:
        hi += ((rh - 85) / 10) * ((87 - t_f) / 5)
    return max((hi - 32) * 5 / 9, t_c)


def sensacion_frio_c(t_c, viento_kmh):
    if viento_kmh is None or not _finito(viento_kmh) or viento_kmh <= 4.8:
        return t_c
    v = viento_kmh ** 0.16
    sf = 13.12 + 0.6215 * t_c - 11.37 * v + 0.3965 * t_c * v
    return min(sf, t_c)


def sensacion_termica_c(t_c, rh, viento_kmh):
    if t_c is None or not _finito(t_c):
        return None
    if t_c >= 26.7:
        return indice_calor_c(t_c, rh)
    if t_c <= 10:
        return sensacion_frio_c(t_c, viento_kmh)
    return t_c


def extraer_valores(obs):
    metric = obs.get("metric") or {}
    temp_c = _first_defined(metric.get("temp"), metric.get("tempAvg"))
    hum = _first_defined(obs.get("humidity"), obs.get("humidityAvg"))
    viento = _first_defined(metric.get("windSpeed"), metric.get("windspeedAvg"))
    p_max, p_min = metric.get("pressureMax"), metric.get("pressureMin")
    if _finito(p_max) and _finito(p_min):
        presion_hist = (p_max + p_min) / 2
    else:
        presion_hist = _first_defined(p_max, p_min)
    return {
        "temp_c": temp_c,
        "heat_index_c": sensacion_termica_c(temp_c, hum, viento),
        "dewpoint_c": _first_defined(obs.get("dewpoint"), metric.get("dewpt"),
                                     metric.get("dewptAvg"), metric.get("dewpoint")),
        "humidity_pct": hum,
        "pressure_hpa": _first_defined(metric.get("pressure"), presion_hist),
        "wind_kmh": viento,
        "gust_kmh": _first_defined(metric.get("windGust"), metric.get("windgustAvg")),
        "wind_dir_deg": _first_defined(obs.get("winddir"), obs.get("windDir"), obs.get("winddirAvg")),
        "rainrate_mmh": metric.get("precipRate"),
        "rain_total_mm": metric.get("precipTotal"),
        "solarradiation_wm2": _first_defined(obs.get("solarRadiation"), obs.get("solarradiation"),
                                             obs.get("solarRadiationHigh")),
        "uv_index": _first_defined(obs.get("uv"), obs.get("uvHigh")),
        "quality_code": _first_defined(obs.get("qcStatus"), obs.get("qualityControlFlag"), "N/A"),
    }


# ----------------------------------------------------------------------
# ALMACÉN SQLITE
# ----------------------------------------------------------------------
class Almacen:
    def __init__(self, ruta):
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        self.db = sqlite3.connect(ruta, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS lecturas ("
                        "epoch_ms INTEGER PRIMARY KEY, vals TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        self.db.commit()

    def meta(self, clave, defecto=None):
        fila = self.db.execute("SELECT v FROM meta WHERE k=?", (clave,)).fetchone()
        return fila[0] if fila else defecto

    def set_meta(self, clave, valor):
        self.db.execute("INSERT INTO meta(k, v) VALUES(?, ?) "
                        "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (clave, str(valor)))
        self.db.commit()

    def anadir(self, epoch_ms, vals):
        """True si la lectura era nueva (la estación a veces repite la misma observación)."""
        cur = self.db.execute("INSERT OR IGNORE INTO lecturas(epoch_ms, vals) VALUES(?, ?)",
                              (int(epoch_ms), json.dumps(vals, separators=(",", ":"))))
        self.db.commit()
        return cur.rowcount > 0

    def borrar_todo(self):
        self.db.execute("DELETE FROM lecturas")
        self.db.commit()
        self.db.execute("VACUUM")

    def borrar_anteriores(self, limite_ms):
        cur = self.db.execute("DELETE FROM lecturas WHERE epoch_ms < ?", (int(limite_ms),))
        self.db.commit()
        return cur.rowcount

    def todas(self):
        return [(e, json.loads(v)) for e, v in
                self.db.execute("SELECT epoch_ms, vals FROM lecturas ORDER BY epoch_ms")]

    def resumen(self):
        n, mn, mx = self.db.execute("SELECT COUNT(*), MIN(epoch_ms), MAX(epoch_ms) FROM lecturas").fetchone()
        return n, mn, mx

    def cerrar(self):
        self.db.close()


# ----------------------------------------------------------------------
# EXPORTACIÓN A JSON (lo que lee la app)
# ----------------------------------------------------------------------
def _redondear(vals, decimales):
    out = {}
    for k, v in vals.items():
        out[k] = round(v, decimales) if isinstance(v, float) else v
    return out


def exportar_json(cfg, almacen, ciclo_inicio_ms):
    lecturas = [{"t": e, "v": _redondear(v, cfg.decimales)} for e, v in almacen.todas()]
    doc = {
        "formato": FORMATO_JSON,
        "stationId": cfg.station_id,
        "generadoMs": int(time.time() * 1000),
        "modo": cfg.modo,
        "duracionMs": cfg.duracion_ms,
        "cicloInicioMs": ciclo_inicio_ms,
        "cicloFinMs": ciclo_inicio_ms + cfg.duracion_ms if cfg.modo == "reinicio" else None,
        "intervaloS": cfg.intervalo_s,
        "lecturas": lecturas,
    }
    carpeta = os.path.dirname(cfg.ruta_json) or "."
    os.makedirs(carpeta, exist_ok=True)
    # Escritura atómica: Apache nunca sirve un JSON a medio escribir.
    fd, tmp = tempfile.mkstemp(prefix=".historial-", suffix=".tmp", dir=carpeta)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
        os.chmod(tmp, 0o644)  # legible por el usuario de Apache (www-data / apache)
        os.replace(tmp, cfg.ruta_json)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ----------------------------------------------------------------------
# PETICIÓN A LA API
# ----------------------------------------------------------------------
class ErrorFatal(Exception):
    """Error que no se arregla reintentando rápido (clave inválida, estación inexistente)."""


class ErrorTemporal(Exception):
    pass


def construir_url(cfg):
    params = {"stationId": cfg.station_id, "format": "json", "numericPrecision": "decimal",
              "units": "m", "apiKey": cfg.api_key}
    return cfg.url_base + "?" + urllib.parse.urlencode(params)


def consultar(cfg):
    """Devuelve (epoch_ms, vals) de la última observación, o None si la API no trae ninguna."""
    req = urllib.request.Request(construir_url(cfg), headers={"User-Agent": "telemet-colector/" + VERSION})
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp:
            cuerpo = resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ErrorFatal("HTTP %d: API Key inválida o sin permiso" % e.code)
        if e.code == 404:
            raise ErrorFatal("HTTP 404: Station ID no encontrado o endpoint obsoleto")
        raise ErrorTemporal("HTTP %d" % e.code)
    except (urllib.error.URLError, OSError) as e:
        raise ErrorTemporal("fallo de red: %s" % getattr(e, "reason", e))
    if not cuerpo:  # la API responde 204 sin cuerpo cuando no hay dato
        return None
    try:
        data = json.loads(cuerpo.decode("utf-8"))
    except ValueError:
        raise ErrorTemporal("respuesta no es JSON válido")
    obs_lista = data.get("observations") or []
    if not obs_lista:
        return None
    obs = obs_lista[0]
    epoch = obs.get("epoch")
    epoch_ms = int(epoch * 1000) if epoch else int(time.time() * 1000)
    return epoch_ms, extraer_valores(obs)


# ----------------------------------------------------------------------
# BUCLE PRINCIPAL
# ----------------------------------------------------------------------
class Colector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.almacen = Almacen(cfg.ruta_bd)
        self.parar = threading.Event()
        self.fallos_seguidos = 0
        self.ciclo_inicio_ms = self._cargar_ciclo()

    # -- ciclo de `duracion_horas` (24 h por defecto) ------------------
    def _cargar_ciclo(self):
        ahora = int(time.time() * 1000)
        estacion_bd = self.almacen.meta("station_id")
        if estacion_bd is not None and estacion_bd != self.cfg.station_id:
            log.warning("La BD era de la estación %s y ahora se usa %s: se borran los datos antiguos.",
                        estacion_bd, self.cfg.station_id)
            self.almacen.borrar_todo()
            self.almacen.set_meta("ciclo_inicio_ms", ahora)
        self.almacen.set_meta("station_id", self.cfg.station_id)
        inicio = self.almacen.meta("ciclo_inicio_ms")
        if inicio is None:
            inicio = ahora
            self.almacen.set_meta("ciclo_inicio_ms", inicio)
        return int(inicio)

    def aplicar_ciclo(self):
        """Aplica la regla de `duracion_horas`. Devuelve True si ha cambiado el contenido de la BD."""
        ahora = int(time.time() * 1000)
        if self.cfg.modo == "reinicio":
            if ahora - self.ciclo_inicio_ms >= self.cfg.duracion_ms:
                n = self.almacen.resumen()[0]
                self.almacen.borrar_todo()
                self.ciclo_inicio_ms = ahora
                self.almacen.set_meta("ciclo_inicio_ms", ahora)
                log.info("Ciclo de %.4g h cumplido: borradas %d lecturas y comienza un ciclo nuevo.",
                         self.cfg.duracion_h, n)
                return True
        else:
            borradas = self.almacen.borrar_anteriores(ahora - self.cfg.duracion_ms)
            if borradas:
                log.debug("Descartadas %d lecturas con más de %.4g h.", borradas, self.cfg.duracion_h)
                return True
        return False

    # -- una vuelta ------------------------------------------------------
    def una_vuelta(self):
        """Hace una consulta. Devuelve los segundos que hay que esperar hasta la siguiente."""
        cambio = self.aplicar_ciclo()
        try:
            res = consultar(self.cfg)
        except ErrorFatal as e:
            self.fallos_seguidos += 1
            log.error("%s. Se reintentará cada %.0f s; corrige config.ini si no es un fallo pasajero.",
                      e, self.cfg.backoff_max_s)
            self._exportar_si(cambio)
            return self.cfg.backoff_max_s
        except ErrorTemporal as e:
            self.fallos_seguidos += 1
            espera = min(self.cfg.backoff_base_s * (2 ** (self.fallos_seguidos - 1)), self.cfg.backoff_max_s)
            log.warning("Lectura fallida (%s); reintento n.º %d en %.0f s.", e, self.fallos_seguidos, espera)
            self._exportar_si(cambio)
            return espera

        self.fallos_seguidos = 0
        if res is None:
            log.info("La API no ha devuelto observaciones nuevas.")
            self._exportar_si(cambio)
            return self.cfg.intervalo_s
        epoch_ms, vals = res
        nueva = self.almacen.anadir(epoch_ms, vals)
        t = vals.get("temp_c")
        log.info("%s  T=%s °C  HR=%s %%  viento=%s km/h  %s",
                 time.strftime("%H:%M:%S", time.localtime(epoch_ms / 1000)),
                 t, vals.get("humidity_pct"), vals.get("wind_kmh"),
                 "guardada" if nueva else "(observación repetida, no se guarda)")
        self._exportar_si(cambio or nueva)
        return self.cfg.intervalo_s

    def _exportar_si(self, hace_falta):
        if not hace_falta:
            return
        try:
            exportar_json(self.cfg, self.almacen, self.ciclo_inicio_ms)
        except OSError as e:
            log.error("No se pudo escribir %s: %s (¿existe la carpeta y tiene permisos el usuario del servicio?)",
                      self.cfg.ruta_json, e)

    def ejecutar(self):
        log.info("TeleMet Colector %s · estación %s · cada %.0f s · ciclo %.4g h (%s)",
                 VERSION, self.cfg.station_id, self.cfg.intervalo_s, self.cfg.duracion_h, self.cfg.modo)
        log.info("BD: %s · JSON: %s", self.cfg.ruta_bd, self.cfg.ruta_json)
        # JSON inicial: así la app encuentra el fichero aunque la primera lectura tarde.
        self._exportar_si(True)
        while not self.parar.is_set():
            inicio = time.monotonic()
            try:
                espera = self.una_vuelta()
            except Exception:  # un fallo inesperado no debe tumbar el servicio
                log.exception("Error inesperado en la vuelta de lectura")
                self.fallos_seguidos += 1
                espera = min(self.cfg.backoff_base_s * (2 ** min(self.fallos_seguidos, 10)), self.cfg.backoff_max_s)
            # Intervalo a ritmo fijo: se descuenta lo que haya tardado la petición.
            restante = max(1.0, espera - (time.monotonic() - inicio))
            self.parar.wait(restante)
        self.almacen.cerrar()
        log.info("Detenido.")


# ----------------------------------------------------------------------
# ARRANQUE
# ----------------------------------------------------------------------
def configurar_log(cfg):
    log.setLevel(getattr(logging, cfg.nivel_log, logging.INFO))
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    manejadores = [logging.StreamHandler(sys.stdout)]
    if cfg.fichero_log:
        os.makedirs(os.path.dirname(cfg.fichero_log) or ".", exist_ok=True)
        manejadores.append(logging.handlers.RotatingFileHandler(cfg.fichero_log, maxBytes=1_000_000, backupCount=3,
                                                               encoding="utf-8"))
    for h in manejadores:
        h.setFormatter(fmt)
        log.addHandler(h)


def main(argv=None):
    ap = argparse.ArgumentParser(description="TeleMet Colector: histórico de la estación (24 h por defecto) en el servidor.")
    ap.add_argument("-c", "--config", default=None,
                    help="ruta de config.ini (por defecto, config.ini junto al script si existe)")
    ap.add_argument("--horas", type=float, default=None, metavar="H",
                    help="horas de histórico a guardar (sustituye a duracion_horas de config.ini y a TELEMET_HORAS; por defecto 24)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--una-vez", action="store_true", help="hace una lectura, la guarda, exporta el JSON y sale")
    g.add_argument("--probar", action="store_true", help="hace una lectura y la muestra, sin guardar nada")
    g.add_argument("--estado", action="store_true", help="muestra un resumen de lo guardado en la BD")
    args = ap.parse_args(argv)

    ruta_ini = args.config
    if ruta_ini is None:
        candidato = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
        ruta_ini = candidato if os.path.isfile(candidato) else None
    cfg = Config(ruta_ini, args.horas)
    configurar_log(cfg)

    if args.estado:
        a = Almacen(cfg.ruta_bd)
        n, mn, mx = a.resumen()
        f = lambda ms: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ms / 1000)) if ms else "—"
        print("BD:            %s" % cfg.ruta_bd)
        print("Estación:      %s" % a.meta("station_id", "—"))
        print("Lecturas:      %d  (de %s a %s)" % (n, f(mn), f(mx)))
        ini = a.meta("ciclo_inicio_ms")
        print("Ciclo desde:   %s" % (f(int(ini)) if ini else "—"))
        a.cerrar()
        return 0

    if not cfg.station_id or not cfg.api_key:
        raise SystemExit("Falta station_id y/o api_key (en config.ini o en TELEMET_STATION_ID / TELEMET_API_KEY).")

    if args.probar:
        try:
            res = consultar(cfg)
        except (ErrorFatal, ErrorTemporal) as e:
            print("ERROR: %s" % e)
            return 1
        if res is None:
            print("La API no ha devuelto observaciones.")
            return 1
        epoch_ms, vals = res
        print("Observación de %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch_ms / 1000)))
        print(json.dumps(vals, indent=2, ensure_ascii=False))
        return 0

    col = Colector(cfg)
    if args.una_vez:
        col.una_vuelta()
        col._exportar_si(True)
        col.almacen.cerrar()
        return 0

    def _parar(signum, _frame):
        log.info("Señal %d recibida: parando…", signum)
        col.parar.set()
    signal.signal(signal.SIGINT, _parar)
    signal.signal(signal.SIGTERM, _parar)
    col.ejecutar()
    return 0


if __name__ == "__main__":
    sys.exit(main())

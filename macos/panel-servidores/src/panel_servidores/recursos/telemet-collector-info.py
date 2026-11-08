#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
telemet-collector-info.py  ·  Shows ALL the parameters of TeleMet Collector

Standalone script (Python 3 standard library only, no dependency on the collector):
it reads config.ini with the same rules as telemet_collector.py and shows, in one
report, what the service is really going to use:

  · the config.ini file (path, owner, permissions, BOM)
  · stations: Station ID, API Key (masked), interval, database and JSON paths
  · reading, cycle, storage, output and log parameters
  · the state of each database (readings, first / last) and each JSON (age, size, owner)
  · the systemd service (state, user, ExecStart, ReadWritePaths, restarts)
  · a list of diagnostics (OK / warnings / errors)

  · (--authorized-keys / --keys-only) audit of the SSH keys that allow logging in to this server:
    ~/.ssh/authorized_keys (keys, fingerprints, permissions, owner) and the sshd settings that matter

It only READS: it never modifies anything and never calls the Weather Underground API.

Usage:
    sudo python3 telemet-collector-info.py                 # /opt/telemet-collector/config.ini
    sudo python3 telemet-collector-info.py -c /ruta/config.ini
    sudo python3 telemet-collector-info.py --show-key      # shows the API Key in full
    python3 telemet-collector-info.py --json               # machine-readable output
    python3 telemet-collector-info.py --lang en            # English (default: from $LANG)
    python3 telemet-collector-info.py --keys-only          # only the authorized_keys audit (no sudo needed)
    sudo python3 telemet-collector-info.py --authorized-keys   # full report + authorized_keys audit

config.ini is normally mode 600 and owned by 'telemet': run it with sudo.
"""

import argparse
import base64
import configparser
import glob
import grp
import hashlib
import json
import os
import pwd
import re
import sqlite3
import subprocess
import sys
import time

DEFAULT_CONFIG = "/opt/telemet-collector/config.ini"
DEFAULT_SERVICE = "telemet-collector"
OTHER_SERVICE = "telemet-colector"

# Same defaults as telemet_collector.py (the values that apply when config.ini omits them)
DEFAULTS = {
    "station": {"station_id": "", "api_key": ""},
    "reading": {"base_url": "https://api.weather.com/v2/pws/observations/current",
                "interval_s": "300", "timeout_s": "15", "backoff_base_s": "2", "backoff_max_s": "300"},
    "cycle": {"duration_hours": "24", "mode": "sliding"},
    "storage": {"db_path": "./data/telemet.sqlite"},
    "output": {"json_path": "/var/www/htdocs/rafa/telemethistory/data/history.json", "decimals": "2"},
    "log": {"level": "INFO", "file": ""},
}
PLACEHOLDERS = {"YOUR_STATION_ID", "YOUR_API_KEY", "TU_STATION_ID", "TU_API_KEY"}

# ----------------------------------------------------------------------------- texts
T = {
    "es": {
        "title": "TeleMet Collector · parámetros", "generated": "Generado",
        "file": "Fichero de configuración", "path": "Ruta", "exists": "Existe", "readable": "Legible",
        "owner": "Propietario", "mode": "Permisos", "size": "Tamaño", "modified": "Modificado", "bom": "BOM UTF-8",
        "yes": "sí", "no": "no", "bytes": "bytes",
        "stations": "Estaciones", "station": "Estación", "id": "Station ID", "key": "API Key", "src": "Origen",
        "interval": "Intervalo", "db": "Base de datos", "json": "JSON publicado", "calls": "llamadas/día",
        "reading": "Lectura (API)", "cycle": "Ciclo del histórico", "output": "Salida", "log": "Registro (log)",
        "service": "Servicio systemd", "unit": "Fichero de la unidad", "active": "Estado", "enabled": "Arranque automático",
        "user": "Usuario", "workdir": "Directorio de trabajo", "exec": "ExecStart", "rwpaths": "ReadWritePaths",
        "restarts": "Reinicios", "since": "Activo desde", "env_unit": "Variables de entorno (unidad)",
        "env_shell": "Variables TELEMET_* de ESTE shell (el servicio no las ve)",
        "paths": "Directorios y ficheros", "instdir": "Directorio de instalación", "state": "Estado",
        "readings": "lecturas", "from": "desde", "to": "hasta", "age": "antigüedad", "dir_missing": "carpeta inexistente",
        "diag": "Diagnóstico", "ok": "OK", "warn": "AVISO", "err": "ERROR",
        "hours_src": "Origen de las horas", "hours_ini": "config.ini", "hours_env": "variable TELEMET_HOURS",
        "src_ini": "config.ini", "src_env": "variable de entorno", "src_env_sec": "variable TELEMET_API_KEY_<ID>",
        "src_stations": "variable TELEMET_STATIONS", "none": "(ninguna)", "empty": "(vacío)",
        "ago": "hace", "na": "n/d", "unreadable": "no se puede leer", "noservice": "no instalado",
        "no_stations": "No hay ninguna estación configurada.",
        "e_noread": "No se puede leer %s (¿falta sudo? el fichero suele ser 600 y de 'telemet').",
        "e_nofile": "No existe el fichero de configuración: %s",
        "e_parse": "Error al interpretar config.ini: %s",
        "e_bom": "config.ini empieza por un BOM UTF-8: las versiones antiguas del colector fallan con MissingSectionHeaderError.",
        "w_bom": "config.ini tiene BOM UTF-8 (el colector actual lo tolera; para quitarlo: sudo sed -i '1s/^\\xEF\\xBB\\xBF//' %s).",
        "e_placeholder": "La estación '%s' sigue con los valores de la plantilla (station_id / api_key).",
        "e_nokey": "A la estación '%s' le falta el station_id o la api_key.",
        "w_perm": "config.ini tiene permisos %s: contiene la API Key, lo recomendable es 600.",
        "w_owner": "config.ini pertenece a %s y el servicio corre como %s: el servicio podría no poder leerlo.",
        "e_jsondir": "La carpeta del JSON no existe: %s",
        "e_jsonw": "El usuario %s no puede escribir en la carpeta del JSON: %s",
        "e_dbw": "El usuario %s no puede escribir en la carpeta de la base de datos: %s",
        "w_rw": "%s no está cubierto por ReadWritePaths de la unidad (ProtectSystem=strict lo hace de solo lectura).",
        "w_stale": "El JSON de %s tiene %s de antigüedad (intervalo: %s s): ¿está parado el colector?",
        "w_nojson": "Todavía no existe el JSON de la estación %s.",
        "w_inactive": "El servicio %s no está activo (estado: %s).",
        "w_restarts": "El servicio se ha reiniciado %s veces: revisa 'journalctl -u %s -e'.",
        "w_other": "Hay también un servicio %s (colector en español) instalado; si lee la misma estación, deja solo uno.",
        "w_calls": "Con %s s entre lecturas son %s llamadas/día a la API: comprueba el límite diario de tu API Key.",
        "w_station_mismatch": "La base de datos %s pertenece a la estación '%s', no a '%s'.",
        "k_title": "Claves SSH autorizadas (authorized_keys)", "k_user": "Usuario", "k_home": "Directorio personal",
        "k_sshdir": "Carpeta .ssh", "k_file": "Fichero de claves", "k_keys": "Claves autorizadas", "k_none": "(ninguna)",
        "k_sshd": "Servidor SSH (sshd)", "k_opts": "opciones", "k_missing": "no existe", "k_default": "por defecto",
        "k_nouser": "El usuario '%s' no existe.",
        "k_nodir": "No existe %s: no hay claves autorizadas (el acceso por clave no funcionará).",
        "k_nofile": "No existe %s (falta authorized_keys): el acceso por clave no funcionará.",
        "k_unread": "No se puede leer %s (%s).",
        "k_empty": "%s no contiene ninguna clave.",
        "k_perm": "%s tiene permisos %s: no debe ser escribible por grupo ni otros (con StrictModes sshd ignora las claves). Arreglo: chmod %s %s",
        "k_owner": "%s pertenece a %s y debería ser de %s (sshd ignorará las claves).",
        "k_home_w": "El directorio personal %s es escribible por grupo u otros (permisos %s): con StrictModes sshd rechaza las claves. Arreglo: chmod go-w %s",
        "k_pubauth": "sshd tiene PubkeyAuthentication desactivado: el acceso por clave no funcionará.",
        "k_weak": "Clave débil u obsoleta en la línea %d (%s): %s.",
        "k_custom": "sshd lee las claves de AuthorizedKeysFile = %s.",
        "k_pw_on": "sshd admite contraseña (PasswordAuthentication yes). Cuando compruebes que la clave funciona puedes ponerlo en 'no'.",
        "k_ok": "Acceso por clave correcto: %d clave(s) autorizada(s) y permisos válidos.",
        "info": "INFO",
        "i_all_ok": "Sin problemas detectados.", "i_sudo": "Ejecuta con sudo para ver la configuración completa.",
        "key_hint": "(usa --show-key para verla completa)",
    },
    "en": {
        "title": "TeleMet Collector · parameters", "generated": "Generated",
        "file": "Configuration file", "path": "Path", "exists": "Exists", "readable": "Readable",
        "owner": "Owner", "mode": "Permissions", "size": "Size", "modified": "Modified", "bom": "UTF-8 BOM",
        "yes": "yes", "no": "no", "bytes": "bytes",
        "stations": "Stations", "station": "Station", "id": "Station ID", "key": "API Key", "src": "Source",
        "interval": "Interval", "db": "Database", "json": "Published JSON", "calls": "calls/day",
        "reading": "Reading (API)", "cycle": "History cycle", "output": "Output", "log": "Log",
        "service": "systemd service", "unit": "Unit file", "active": "State", "enabled": "Start at boot",
        "user": "User", "workdir": "Working directory", "exec": "ExecStart", "rwpaths": "ReadWritePaths",
        "restarts": "Restarts", "since": "Active since", "env_unit": "Environment variables (unit)",
        "env_shell": "TELEMET_* variables of THIS shell (the service does not see them)",
        "paths": "Directories and files", "instdir": "Install directory", "state": "State",
        "readings": "readings", "from": "from", "to": "to", "age": "age", "dir_missing": "folder does not exist",
        "diag": "Diagnostics", "ok": "OK", "warn": "WARNING", "err": "ERROR",
        "hours_src": "Source of the hours", "hours_ini": "config.ini", "hours_env": "TELEMET_HOURS variable",
        "src_ini": "config.ini", "src_env": "environment variable", "src_env_sec": "TELEMET_API_KEY_<ID> variable",
        "src_stations": "TELEMET_STATIONS variable", "none": "(none)", "empty": "(empty)",
        "ago": "ago", "na": "n/a", "unreadable": "cannot be read", "noservice": "not installed",
        "no_stations": "No station is configured.",
        "e_noread": "Cannot read %s (missing sudo? the file is usually 600 and owned by 'telemet').",
        "e_nofile": "Configuration file not found: %s",
        "e_parse": "Error parsing config.ini: %s",
        "e_bom": "config.ini starts with a UTF-8 BOM: old collector versions fail with MissingSectionHeaderError.",
        "w_bom": "config.ini has a UTF-8 BOM (the current collector tolerates it; to remove it: sudo sed -i '1s/^\\xEF\\xBB\\xBF//' %s).",
        "e_placeholder": "Station '%s' still has the template values (station_id / api_key).",
        "e_nokey": "Station '%s' lacks its station_id or api_key.",
        "w_perm": "config.ini has permissions %s: it holds the API Key, 600 is recommended.",
        "w_owner": "config.ini belongs to %s and the service runs as %s: the service may not be able to read it.",
        "e_jsondir": "The JSON folder does not exist: %s",
        "e_jsonw": "User %s cannot write to the JSON folder: %s",
        "e_dbw": "User %s cannot write to the database folder: %s",
        "w_rw": "%s is not covered by the unit's ReadWritePaths (ProtectSystem=strict makes it read-only).",
        "w_stale": "The JSON of %s is %s old (interval: %s s): is the collector stopped?",
        "w_nojson": "The JSON of station %s does not exist yet.",
        "w_inactive": "The service %s is not active (state: %s).",
        "w_restarts": "The service has restarted %s times: check 'journalctl -u %s -e'.",
        "w_other": "A service %s (the Spanish collector) is also installed; if it reads the same station, keep only one.",
        "w_calls": "With %s s between readings that is %s API calls/day: check your API Key's daily limit.",
        "w_station_mismatch": "The database %s belongs to station '%s', not '%s'.",
        "k_title": "Authorized SSH keys (authorized_keys)", "k_user": "User", "k_home": "Home directory",
        "k_sshdir": ".ssh folder", "k_file": "Keys file", "k_keys": "Authorized keys", "k_none": "(none)",
        "k_sshd": "SSH server (sshd)", "k_opts": "options", "k_missing": "does not exist", "k_default": "default",
        "k_nouser": "User '%s' does not exist.",
        "k_nodir": "%s does not exist: there are no authorized keys (key login will not work).",
        "k_nofile": "%s does not exist (authorized_keys is missing): key login will not work.",
        "k_unread": "Cannot read %s (%s).",
        "k_empty": "%s contains no key.",
        "k_perm": "%s has permissions %s: it must not be writable by group or others (with StrictModes sshd ignores the keys). Fix: chmod %s %s",
        "k_owner": "%s belongs to %s and should belong to %s (sshd will ignore the keys).",
        "k_home_w": "The home directory %s is writable by group or others (permissions %s): with StrictModes sshd rejects the keys. Fix: chmod go-w %s",
        "k_pubauth": "sshd has PubkeyAuthentication disabled: key login will not work.",
        "k_weak": "Weak or obsolete key on line %d (%s): %s.",
        "k_custom": "sshd reads the keys from AuthorizedKeysFile = %s.",
        "k_pw_on": "sshd accepts passwords (PasswordAuthentication yes). Once you have checked that the key works you can set it to 'no'.",
        "k_ok": "Key login is fine: %d authorized key(s) and valid permissions.",
        "info": "INFO",
        "i_all_ok": "No problems found.", "i_sudo": "Run with sudo to see the full configuration.",
        "key_hint": "(use --show-key to see it in full)",
    },
}


def default_lang():
    return "es" if (os.environ.get("LANG") or os.environ.get("LC_ALL") or "es").lower().startswith("es") else "en"


# ----------------------------------------------------------------------------- helpers
def mask(key, full):
    if not key:
        return ""
    if full or key in PLACEHOLDERS:
        return key
    if len(key) <= 8:
        return key[:1] + "…" + " (%d)" % len(key)
    return "%s…%s (%d)" % (key[:4], key[-2:], len(key))


def safe(text):
    return re.sub(r"[^A-Za-z0-9._-]", "_", text)


def env_suffix(sid):
    return re.sub(r"[^A-Za-z0-9]", "_", sid).upper()


def owner_of(st):
    try:
        u = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        u = str(st.st_uid)
    try:
        g = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        g = str(st.st_gid)
    return "%s:%s" % (u, g)


def fmt_time(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def fmt_age(sec):
    sec = int(max(0, sec))
    if sec < 90:
        return "%d s" % sec
    if sec < 5400:
        return "%d min" % round(sec / 60)
    if sec < 172800:
        return "%.1f h" % (sec / 3600)
    return "%.1f d" % (sec / 86400)


def can_write(path, user):
    """True/False/None: could `user` write in the folder `path`? (None = unknown)."""
    try:
        pw = pwd.getpwnam(user)
        st = os.stat(path)
    except (KeyError, OSError):
        return None
    if pw.pw_uid == 0:
        return True
    if st.st_uid == pw.pw_uid:
        return bool(st.st_mode & 0o200)
    if st.st_gid in os.getgrouplist(user, pw.pw_gid):
        return bool(st.st_mode & 0o020)
    return bool(st.st_mode & 0o002)


def under(path, folders):
    path = os.path.realpath(path)
    for f in folders:
        f = os.path.realpath(f)
        if path == f or path.startswith(f.rstrip("/") + "/"):
            return True
    return False


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        return r.stdout.strip()
    except Exception:
        return None


# ----------------------------------------------------------------------------- unit file
def read_unit(name):
    info = {"file": None, "keys": {}, "rw": [], "env": {}}
    for d in ("/etc/systemd/system", "/lib/systemd/system", "/usr/lib/systemd/system"):
        p = os.path.join(d, name + ".service")
        if os.path.isfile(p):
            info["file"] = p
            break
    if not info["file"]:
        return info
    try:
        text = open(info["file"], encoding="utf-8", errors="replace").read()
    except OSError:
        return info
    sect = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("["):
            sect = line.strip("[]")
            continue
        if "=" not in line or sect != "Service":
            continue
        k, v = [x.strip() for x in line.split("=", 1)]
        if k == "ReadWritePaths":
            info["rw"] += [x.lstrip("-+") for x in v.split()]
        elif k == "Environment":
            for m in re.finditer(r'"?([A-Za-z_][A-Za-z0-9_]*)=([^"\s]*|"[^"]*")"?', v):
                info["env"][m.group(1)] = m.group(2).strip('"')
        elif k == "EnvironmentFile":
            path = v.lstrip("-")
            try:
                for ln in open(path, encoding="utf-8", errors="replace"):
                    ln = ln.strip()
                    if ln and ln[0] not in "#;" and "=" in ln:
                        kk, vv = ln.split("=", 1)
                        info["env"][kk.strip()] = vv.strip().strip('"\'')
            except OSError:
                pass
        else:
            info["keys"][k] = v
    return info


# ----------------------------------------------------------------------------- config
def load_config(path, env):
    """Same rules as telemet_collector.Config. Returns (dict, raw bytes info)."""
    cp = configparser.ConfigParser(interpolation=None)
    cp.read_dict(DEFAULTS)
    with open(path, "rb") as f:
        raw = f.read()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    cp.read_string(raw.decode("utf-8-sig"), source=path)
    base_dir = os.path.dirname(os.path.abspath(path))

    def P(p):
        p = os.path.expanduser(p.strip())
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(base_dir, p))

    raws = []
    sid_env, key_env = (env.get("TELEMET_STATION_ID") or "").strip(), (env.get("TELEMET_API_KEY") or "").strip()
    sid = sid_env or cp.get("station", "station_id").strip()
    key = key_env or cp.get("station", "api_key").strip()
    if sid or key:
        src_id = "env" if sid_env else "ini"
        src_key = "env" if key_env else "ini"
        raws.append({"id": sid, "key": key, "sec": "station", "src_id": src_id, "src_key": src_key})
    for sec in cp.sections():
        if sec.lower().startswith("station:"):
            sid = sec.split(":", 1)[1].strip()
            k_ini = cp.get(sec, "api_key", fallback="").strip()
            k_env = (env.get("TELEMET_API_KEY_" + env_suffix(sid)) or "").strip()
            raws.append({"id": sid, "key": k_ini or k_env, "sec": sec, "src_id": "ini",
                         "src_key": "ini" if k_ini else ("env_sec" if k_env else "ini")})
    for pair in (env.get("TELEMET_STATIONS") or "").replace(";", ",").split(","):
        pair = pair.strip()
        if pair and ":" in pair:
            sid, key = pair.split(":", 1)
            raws.append({"id": sid.strip(), "key": key.strip(), "sec": None, "src_id": "stations", "src_key": "stations"})

    interval = max(5.0, cp.getfloat("reading", "interval_s"))
    hours_env = (env.get("TELEMET_HOURS") or "").strip()
    hours = float(hours_env) if hours_env else cp.getfloat("cycle", "duration_hours")
    db_t, json_t = cp.get("storage", "db_path"), cp.get("output", "json_path")
    several = len(raws) > 1

    def spath(template, fid):
        if "{station_id}" in template:
            return P(template.replace("{station_id}", fid))
        p = P(template)
        if not several:
            return p
        b, e = os.path.splitext(p)
        return "%s_%s%s" % (b, fid, e)

    stations = []
    for r in raws:
        sec = r["sec"]
        def opt(n, d):
            return cp.get(sec, n, fallback=d).strip() if sec and cp.has_section(sec) else d
        fid = safe(r["id"].upper())
        stations.append({**r, "interval_s": max(5.0, float(opt("interval_s", str(interval)))),
                         "db_path": spath(opt("db_path", db_t), fid), "json_path": spath(opt("json_path", json_t), fid)})
    log_file = cp.get("log", "file").strip()
    return {
        "path": os.path.abspath(path), "base_dir": base_dir, "bom": has_bom,
        "stations": stations,
        "reading": {"base_url": cp.get("reading", "base_url").strip(), "interval_s": interval,
                    "timeout_s": cp.getfloat("reading", "timeout_s"),
                    "backoff_base_s": cp.getfloat("reading", "backoff_base_s"),
                    "backoff_max_s": cp.getfloat("reading", "backoff_max_s")},
        "cycle": {"duration_hours": hours, "mode": cp.get("cycle", "mode").strip().lower(),
                  "hours_src": "env" if hours_env else "ini"},
        "storage": {"db_path": P(db_t), "db_template": db_t},
        "output": {"json_path": P(json_t), "json_template": json_t, "decimals": cp.getint("output", "decimals")},
        "log": {"level": cp.get("log", "level").strip().upper(), "file": P(log_file) if log_file else ""},
    }


def inspect_db(path):
    r = {"path": path, "exists": os.path.isfile(path)}
    if not r["exists"]:
        return r
    st = os.stat(path)
    r.update(size=st.st_size, mtime=st.st_mtime, owner=owner_of(st))
    try:
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)
        n, mn, mx = con.execute("SELECT COUNT(*), MIN(epoch_ms), MAX(epoch_ms) FROM readings").fetchone()
        row = con.execute("SELECT v FROM meta WHERE k='station_id'").fetchone()
        con.close()
        r.update(readings=n, first=mn / 1000 if mn else None, last=mx / 1000 if mx else None,
                 db_station=row[0] if row else None)
    except Exception as e:
        r["error"] = str(e)
    return r


def inspect_json(path):
    r = {"path": path, "exists": os.path.isfile(path), "dir": os.path.dirname(path)}
    r["dir_exists"] = os.path.isdir(r["dir"])
    if not r["exists"]:
        return r
    st = os.stat(path)
    r.update(size=st.st_size, mtime=st.st_mtime, owner=owner_of(st))
    try:
        d = json.load(open(path, encoding="utf-8-sig"))
        r["station_id"] = d.get("stationId")
        r["readings"] = len(d.get("readings", []))
        r["interval_s"] = d.get("intervalS") or d.get("intervaloS")
        r["format"] = d.get("format") or d.get("formato")
    except Exception as e:
        r["error"] = str(e)
    return r


# ----------------------------------------------------------------------------- authorized_keys audit
KEY_RE = re.compile(r"(?:^|\s)((?:ssh-(?:rsa|dss|ed25519)|ecdsa-sha2-nistp(?:256|384|521)|"
                    r"sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com))\s+"
                    r"([A-Za-z0-9+/]+={0,3})(?:\s+(.*))?$")


def fingerprint(blob):
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")


def rsa_bits(blob):
    try:
        def rd(b, i):
            n = int.from_bytes(b[i:i + 4], "big")
            return b[i + 4:i + 4 + n], i + 4 + n
        _t, i = rd(blob, 0)
        _e, i = rd(blob, i)
        n, _ = rd(blob, i)
        return int.from_bytes(n, "big").bit_length()
    except Exception:
        return None


def parse_sshd_config(path="/etc/ssh/sshd_config", _seen=None):
    """Global directives of sshd_config (the first value wins, like sshd). Match blocks are ignored."""
    cfg, _seen = {}, (_seen if _seen is not None else set())
    if path in _seen:
        return cfg
    _seen.add(path)
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return cfg
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        key, val = parts[0].lower(), (parts[1].strip() if len(parts) > 1 else "")
        if key == "match":
            break
        if key == "include":
            for pat in val.split():
                pat = pat if os.path.isabs(pat) else os.path.join("/etc/ssh", pat)
                for p in sorted(glob.glob(pat)):
                    for k, v in parse_sshd_config(p, _seen).items():
                        cfg.setdefault(k, v)
            continue
        cfg.setdefault(key, val.strip('"'))
    return cfg


def _stat_info(path):
    try:
        st = os.stat(path)
    except OSError:
        return {"path": path, "exists": False}
    return {"path": path, "exists": True, "mode": oct(st.st_mode & 0o777)[2:], "mode_int": st.st_mode & 0o777,
            "owner": owner_of(st), "uid": st.st_uid, "size": st.st_size, "is_dir": os.path.isdir(path)}


def audit_authorized_keys(user=None):
    """Audit of the SSH keys that allow logging in as `user` (default: the login user, even under sudo)."""
    user = user or os.environ.get("SUDO_USER") or pwd.getpwuid(os.getuid()).pw_name
    res = {"user": user, "diag": []}
    d = res["diag"]
    try:
        pw = pwd.getpwnam(user)
    except KeyError:
        d.append(("err", ("k_nouser", user)))
        return res
    home = pw.pw_dir
    sshd = parse_sshd_config()
    res["sshd"] = {k: sshd.get(k) for k in ("pubkeyauthentication", "authorizedkeysfile", "passwordauthentication",
                                            "permitrootlogin", "strictmodes", "port") if sshd.get(k) is not None}
    strict = (sshd.get("strictmodes", "yes").lower() != "no")
    tokens = (sshd.get("authorizedkeysfile") or ".ssh/authorized_keys .ssh/authorized_keys2").split()
    paths = []
    for tok in tokens:
        p = tok.replace("%%", "\0").replace("%h", home).replace("%u", user).replace("\0", "%")
        paths.append(p if os.path.isabs(p) else os.path.join(home, p))
    akf = next((p for p in paths if os.path.isfile(p)), paths[0])
    res["home"] = {**_stat_info(home), "dir": home}
    res["ssh_dir"] = _stat_info(os.path.join(home, ".ssh"))
    res["file"] = _stat_info(akf)
    res["custom_file"] = bool(sshd.get("authorizedkeysfile")) and akf != os.path.join(home, ".ssh", "authorized_keys")
    if sshd.get("pubkeyauthentication", "yes").lower() == "no":
        d.append(("err", ("k_pubauth",)))
    if res["custom_file"]:
        d.append(("info", ("k_custom", sshd.get("authorizedkeysfile"))))
    if sshd.get("passwordauthentication", "yes").lower() == "yes":
        d.append(("info", ("k_pw_on",)))

    keys = []
    if not res["file"]["exists"]:
        if not res["ssh_dir"]["exists"]:
            d.append(("warn", ("k_nodir", res["ssh_dir"]["path"])))
        else:
            d.append(("warn", ("k_nofile", akf)))
    else:
        try:
            lines = open(akf, encoding="utf-8", errors="replace").read().splitlines()
        except OSError as e:
            d.append(("err", ("k_unread", akf, e.strerror or str(e))))
            lines = []
        for n, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = KEY_RE.search(line)
            if not m:
                continue
            ktype, b64, comment = m.group(1), m.group(2), (m.group(3) or "").strip()
            try:
                blob = base64.b64decode(b64 + "=" * (-len(b64) % 4))
            except Exception:
                continue
            bits = rsa_bits(blob) if ktype == "ssh-rsa" else None
            keys.append({"line": n, "type": ktype, "bits": bits, "fingerprint": fingerprint(blob),
                         "comment": comment, "options": line[:m.start()].strip()})
            if ktype == "ssh-dss":
                d.append(("warn", ("k_weak", n, ktype, "DSA")))
            elif bits and bits < 2048:
                d.append(("warn", ("k_weak", n, "RSA %d" % bits, "< 2048 bits")))
        if not keys and res["file"]["exists"]:
            d.append(("warn", ("k_empty", akf)))
    res["keys"] = keys

    # StrictModes: sshd rejects the keys if home, ~/.ssh or the file are writable by others or foreign
    if strict:
        h = res["home"]
        if h["exists"] and (h["mode_int"] & 0o022):
            d.append(("err", ("k_home_w", home, h["mode"], home)))
        for key, want in (("ssh_dir", "700"), ("file", "600")):
            e = res[key]
            if e["exists"]:
                if e["mode_int"] & 0o022:
                    d.append(("err", ("k_perm", e["path"], e["mode"], want, e["path"])))
                if e["uid"] not in (pw.pw_uid, 0):
                    d.append(("err", ("k_owner", e["path"], e["owner"], user)))
    if keys and not any(l == "err" for l, *_ in d):
        d.append(("ok", ("k_ok", len(keys))))
    return res


def keys_text(t, diag_item):
    """('k_xxx', args…) -> translated text."""
    return t[diag_item[0]] % tuple(diag_item[1:]) if len(diag_item) > 1 else t[diag_item[0]]


def print_keys(o, t, k):
    o.head(t["k_title"])
    o.row(t["k_user"], k["user"])
    if "home" not in k:
        return
    o.row(t["k_home"], "%s · %s · %s" % (k["home"]["dir"], k["home"].get("mode", "?"), k["home"].get("owner", "?")))
    for label, e in ((t["k_sshdir"], k["ssh_dir"]), (t["k_file"], k["file"])):
        o.row(label, "%s · %s" % (e["path"], ("%s · %s" % (e["mode"], e["owner"])) if e["exists"] else t["k_missing"]))
    sshd = k.get("sshd", {})
    dflt = {"pubkeyauthentication": "yes", "passwordauthentication": "yes", "permitrootlogin": "prohibit-password",
            "strictmodes": "yes", "authorizedkeysfile": ".ssh/authorized_keys"}
    o.row(t["k_sshd"], ", ".join("%s=%s" % (n, sshd[n.lower()] if n.lower() in sshd else "%s (%s)" % (dflt[n.lower()], t["k_default"]))
                                  for n in ("PubkeyAuthentication", "PasswordAuthentication", "PermitRootLogin",
                                            "StrictModes")))
    print("  " + o.paint("2", t["k_keys"] + " (%d):" % len(k["keys"])) + ("" if k["keys"] else " " + t["k_none"]))
    for i, key in enumerate(k["keys"], 1):
        kind = key["type"] + (" %d" % key["bits"] if key["bits"] else "")
        extra = ("  [%s: %s]" % (t["k_opts"], key["options"])) if key["options"] else ""
        print("    #%d %s  %s  %s%s" % (i, kind, key["fingerprint"], key["comment"] or "-", o.paint("2", extra)))


def print_diag(o, t, diag):
    for lvl, msg in diag:
        sym, col, lab = {"err": ("✘", "31", t["err"]), "warn": ("▲", "33", t["warn"]),
                         "info": ("ℹ", "36", t["info"]), "ok": ("✔", "32", t["ok"])}[lvl]
        print("  " + o.paint(col, "%s %s" % (sym, lab)) + " " + msg)


# ----------------------------------------------------------------------------- report
class Out:
    def __init__(self, color):
        self.c = color

    def paint(self, code, s):
        return "\033[%sm%s\033[0m" % (code, s) if self.c else s

    def head(self, s):
        print("\n" + self.paint("1;36", "▌ " + s))

    def row(self, k, v, indent=2):
        print("%s%s %s" % (" " * indent, self.paint("2", (k + ":").ljust(26)), v))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Shows all the parameters of TeleMet Collector (read only).")
    ap.add_argument("-c", "--config", default=None, help="path of config.ini (default: %s)" % DEFAULT_CONFIG)
    ap.add_argument("--service", default=DEFAULT_SERVICE, help="systemd service name (default: %s)" % DEFAULT_SERVICE)
    ap.add_argument("--show-key", action="store_true", help="show the API Key in full")
    ap.add_argument("--use-shell-env", action="store_true", help="also apply TELEMET_* of this shell (the service does not see them)")
    ap.add_argument("--no-service", action="store_true", help="do not query systemd")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--color", action="store_true", help="force colors even if the output is not a terminal (used by the SSH version)")
    ap.add_argument("--lang", choices=("es", "en"), default=default_lang())
    ap.add_argument("--authorized-keys", nargs="?", const="", default=None, metavar="USER",
                    help="also audit the SSH keys that allow logging in (default: the login user)")
    ap.add_argument("--keys-only", nargs="?", const="", default=None, metavar="USER",
                    help="show only the authorized_keys audit (no config.ini, no sudo needed)")
    a = ap.parse_args(argv)
    t = T[a.lang]
    o = Out((sys.stdout.isatty() or a.color) and not a.no_color and not a.json)

    if a.keys_only is not None:
        k = audit_authorized_keys(a.keys_only or None)
        kd = [(l, keys_text(t, m)) for l, m in k["diag"]]
        if a.json:
            print(json.dumps({"authorized_keys": {**{n: v for n, v in k.items() if n != "diag"}},
                              "diagnostics": [{"level": l, "message": m} for l, m in kd]}, indent=2, ensure_ascii=False))
        else:
            print(o.paint("2", "%s %s" % (t["generated"], fmt_time(time.time()))))
            print_keys(o, t, k)
            o.head(t["diag"])
            print_diag(o, t, kd or [("ok", t["i_all_ok"])])
            print()
        return 1 if any(l == "err" for l, _ in kd) else 0

    path = a.config
    if not path:
        for c in (DEFAULT_CONFIG, "./config.ini", os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")):
            if os.path.isfile(c):
                path = c
                break
        path = path or DEFAULT_CONFIG
    if not os.path.isfile(path):
        print(t["e_nofile"] % path, file=sys.stderr)
        return 2
    if not os.access(path, os.R_OK):
        print(t["e_noread"] % path, file=sys.stderr)
        return 2

    unit = {"file": None, "keys": {}, "rw": [], "env": {}} if a.no_service else read_unit(a.service)
    env = dict(unit["env"])
    shell_env = {k: v for k, v in os.environ.items() if k.startswith("TELEMET_")}
    if a.use_shell_env:
        env.update(shell_env)
    try:
        cfg = load_config(path, env)
    except (configparser.Error, ValueError) as e:
        print(t["e_parse"] % e, file=sys.stderr)
        return 2

    st = os.stat(path)
    svc_user = unit["keys"].get("User", "telemet")
    mode = oct(st.st_mode & 0o777)[2:]
    diag = []   # (level, text)
    cal = lambda s: int(86400 / s)

    # ---- diagnostics: file
    if cfg["bom"]:
        diag.append(("warn", t["w_bom"] % cfg["path"]))
    if (st.st_mode & 0o077):
        diag.append(("warn", t["w_perm"] % mode))
    try:
        own = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        own = str(st.st_uid)
    if own != svc_user and not (st.st_mode & 0o004):
        diag.append(("warn", t["w_owner"] % (owner_of(st), svc_user)))

    # ---- stations
    rows = []
    for s in cfg["stations"]:
        ph = s["id"] in PLACEHOLDERS or s["key"] in PLACEHOLDERS
        if not s["id"] or not s["key"]:
            diag.append(("err", t["e_nokey"] % (s["id"] or "?")))
        elif ph:
            diag.append(("err", t["e_placeholder"] % s["id"]))
        db, js = inspect_db(s["db_path"]), inspect_json(s["json_path"])
        rows.append((s, db, js))
        if s["interval_s"] < 60:
            diag.append(("warn", t["w_calls"] % (int(s["interval_s"]), cal(s["interval_s"]))))
        # JSON folder / permissions
        if not js["dir_exists"]:
            diag.append(("err", t["e_jsondir"] % js["dir"]))
        else:
            if can_write(js["dir"], svc_user) is False:
                diag.append(("err", t["e_jsonw"] % (svc_user, js["dir"])))
        dbdir = os.path.dirname(s["db_path"])
        if os.path.isdir(dbdir) and can_write(dbdir, svc_user) is False:
            diag.append(("err", t["e_dbw"] % (svc_user, dbdir)))
        if unit["keys"].get("ProtectSystem") in ("strict", "full", "true") and unit["rw"]:
            for p in (js["dir"], dbdir):
                if not under(p, unit["rw"]):
                    diag.append(("warn", t["w_rw"] % p))
        if js["exists"]:
            age = time.time() - js["mtime"]
            if age > max(3 * s["interval_s"], 900):
                diag.append(("warn", t["w_stale"] % (s["id"], fmt_age(age), int(s["interval_s"]))))
        elif js["dir_exists"]:
            diag.append(("warn", t["w_nojson"] % s["id"]))
        if db.get("db_station") and s["id"] and db["db_station"].lower() != s["id"].lower():
            diag.append(("warn", t["w_station_mismatch"] % (s["db_path"], db["db_station"], s["id"])))

    # ---- service
    svc = {"name": a.service, "unit": unit["file"]}
    if not a.no_service and unit["file"]:
        svc["active"] = run(["systemctl", "is-active", a.service]) or t["na"]
        svc["enabled"] = run(["systemctl", "is-enabled", a.service]) or t["na"]
        show = run(["systemctl", "show", a.service, "-p", "NRestarts", "-p", "ActiveEnterTimestamp"]) or ""
        sh = dict(l.split("=", 1) for l in show.splitlines() if "=" in l)
        svc["restarts"] = sh.get("NRestarts")
        svc["since"] = sh.get("ActiveEnterTimestamp")
        if svc["active"] != "active":
            diag.append(("warn", t["w_inactive"] % (a.service, svc["active"])))
        try:
            if int(svc["restarts"] or 0) >= 3:
                diag.append(("warn", t["w_restarts"] % (svc["restarts"], a.service)))
        except ValueError:
            pass
    if not a.no_service and os.path.isfile("/etc/systemd/system/%s.service" % OTHER_SERVICE) and a.service != OTHER_SERVICE:
        diag.append(("warn", t["w_other"] % OTHER_SERVICE))

    keys_audit = None
    if a.authorized_keys is not None:
        keys_audit = audit_authorized_keys(a.authorized_keys or None)
        diag += [(l if l != "ok" else "info", keys_text(t, m)) for l, m in keys_audit["diag"] if l != "ok"]
    diag = list(dict.fromkeys(diag))   # without repeated messages (stations that share a folder)

    # ---- JSON mode
    if a.json:
        out = {"config_file": {"path": path, "owner": owner_of(st), "mode": mode, "bom": cfg["bom"]},
               "stations": [{"id": s["id"], "api_key": mask(s["key"], a.show_key), "interval_s": s["interval_s"],
                             "db": db, "json": js} for s, db, js in rows],
               "reading": cfg["reading"], "cycle": cfg["cycle"], "storage": cfg["storage"],
               "output": cfg["output"], "log": cfg["log"],
               "service": {**svc, "user": svc_user, "read_write_paths": unit["rw"], "keys": unit["keys"],
                           "environment": sorted(unit["env"])},
               "diagnostics": [{"level": l, "message": m} for l, m in diag]}
        if keys_audit:
            out["authorized_keys"] = {n: v for n, v in keys_audit.items() if n != "diag"}
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 1 if any(l == "err" for l, _ in diag) else 0

    # ---- text report
    print(o.paint("1", t["title"]) + o.paint("2", "   · %s %s" % (t["generated"], fmt_time(time.time()))))

    o.head(t["file"])
    o.row(t["path"], path)
    o.row(t["owner"], owner_of(st))
    o.row(t["mode"], mode)
    o.row(t["size"], "%d %s" % (st.st_size, t["bytes"]))
    o.row(t["modified"], fmt_time(st.st_mtime))
    o.row(t["bom"], o.paint("33", t["yes"]) if cfg["bom"] else t["no"])

    o.head(t["stations"] + " (%d)" % len(rows))
    if not rows:
        print("  " + t["no_stations"])
    srcname = {"ini": t["src_ini"], "env": t["src_env"], "env_sec": t["src_env_sec"], "stations": t["src_stations"]}
    for i, (s, db, js) in enumerate(rows, 1):
        print("  " + o.paint("1", "%s %d" % (t["station"], i)))
        o.row(t["id"], (s["id"] or t["empty"]) + o.paint("2", "   [%s]" % srcname[s["src_id"]]), 4)
        o.row(t["key"], (mask(s["key"], a.show_key) or t["empty"]) + o.paint("2", "   [%s]%s" % (
            srcname[s["src_key"]], "" if a.show_key else " " + t["key_hint"])), 4)
        o.row(t["interval"], "%d s  (%d %s)" % (s["interval_s"], cal(s["interval_s"]), t["calls"]), 4)
        o.row(t["db"], s["db_path"], 4)
        o.row(t["json"], s["json_path"], 4)

    r = cfg["reading"]
    o.head(t["reading"])
    o.row("base_url", r["base_url"])
    o.row("interval_s", "%g" % r["interval_s"])
    o.row("timeout_s", "%g" % r["timeout_s"])
    o.row("backoff_base_s / max_s", "%g / %g" % (r["backoff_base_s"], r["backoff_max_s"]))

    c = cfg["cycle"]
    o.head(t["cycle"])
    o.row("duration_hours", "%g  (%s: %s)" % (c["duration_hours"], t["hours_src"], t["hours_env"] if c["hours_src"] == "env" else t["hours_ini"]))
    o.row("mode", c["mode"])

    o.head(t["output"] + " / " + t["log"])
    o.row("db_path", "%s   [%s]" % (cfg["storage"]["db_path"], cfg["storage"]["db_template"]))
    o.row("json_path", "%s   [%s]" % (cfg["output"]["json_path"], cfg["output"]["json_template"]))
    o.row("decimals", cfg["output"]["decimals"])
    o.row("log level", cfg["log"]["level"])
    o.row("log file", cfg["log"]["file"] or t["empty"] + " (journald)")

    o.head(t["paths"])
    o.row(t["instdir"], cfg["base_dir"])
    for s, db, js in rows:
        print("  " + o.paint("1", "%s %s" % (t["station"], s["id"] or "?")))
        if db["exists"]:
            extra = ""
            if "readings" in db and db["readings"]:
                extra = " · %d %s · %s %s · %s %s" % (db["readings"], t["readings"], t["from"], fmt_time(db["first"]), t["to"], fmt_time(db["last"]))
            elif "readings" in db:
                extra = " · 0 %s" % t["readings"]
            elif "error" in db:
                extra = " · %s (%s)" % (t["unreadable"], db["error"])
            o.row("DB", "%s · %d %s · %s%s" % (db["path"], db["size"], t["bytes"], db["owner"], extra), 4)
        else:
            o.row("DB", "%s · %s" % (db["path"], o.paint("33", t["na"])), 4)
        if js["exists"]:
            extra = " · %s %s %s" % (t["age"], fmt_age(time.time() - js["mtime"]), "")
            if "readings" in js:
                extra += "· %d %s · station %s" % (js["readings"], t["readings"], js.get("station_id"))
            o.row("JSON", "%s · %d %s · %s%s" % (js["path"], js["size"], t["bytes"], js["owner"], extra), 4)
        else:
            o.row("JSON", "%s · %s" % (js["path"], o.paint("33", t["dir_missing"] if not js["dir_exists"] else t["na"])), 4)

    o.head(t["service"])
    if not unit["file"] and not a.no_service:
        o.row(t["unit"], "%s.service · %s" % (a.service, t["noservice"]))
    elif unit["file"]:
        o.row(t["unit"], unit["file"])
        act = svc.get("active", t["na"])
        o.row(t["active"], o.paint("32" if act == "active" else "31", act))
        o.row(t["enabled"], svc.get("enabled", t["na"]))
        o.row(t["user"], "%s:%s" % (unit["keys"].get("User", "root"), unit["keys"].get("Group", "")))
        o.row(t["workdir"], unit["keys"].get("WorkingDirectory", "-"))
        o.row(t["exec"], unit["keys"].get("ExecStart", "-"))
        o.row(t["rwpaths"], " ".join(unit["rw"]) or "-")
        o.row("Restart", unit["keys"].get("Restart", "-"))
        if svc.get("restarts") is not None:
            o.row(t["restarts"], svc["restarts"])
        if svc.get("since"):
            o.row(t["since"], svc["since"])
        o.row(t["env_unit"], ", ".join("%s=%s" % (k, "***" if "KEY" in k else v) for k, v in sorted(unit["env"].items())) or t["none"])
    if shell_env:
        o.row(t["env_shell"], ", ".join("%s=%s" % (k, "***" if "KEY" in k else v) for k, v in sorted(shell_env.items())))

    if keys_audit:
        print_keys(o, t, keys_audit)

    o.head(t["diag"])
    if not diag:
        print("  " + o.paint("32", "✔ " + t["ok"]) + " " + t["i_all_ok"])
    print_diag(o, t, diag)
    print()
    return 1 if any(l == "err" for l, _ in diag) else 0


if __name__ == "__main__":
    sys.exit(main())

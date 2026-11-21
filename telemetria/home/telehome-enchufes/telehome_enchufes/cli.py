"""Línea de órdenes: servir la interfaz, buscar, probar e importar enchufes."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import logging
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from typing import List, Optional

from . import APP_NAME, __version__
from .cloud import REGIONS, CloudError, CloudHub, SimCloudHub
from .config import CLOUD_REGIONS, MAX_DEVICES, Config, ConfigError, data_dir
from .devices import PlugError, make_plug, scan_network
from .monitor import Monitor
from .server import AppContext, make_server
from .store import Store

log = logging.getLogger("telehome-enchufes")
DEFAULT_PORT = 8765


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")


def _already_running(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen("http://%s:%d/api/health" % (host, port), timeout=1.5) as r:
            return json.load(r).get("app") == APP_NAME
    except Exception:
        return False


def _seed_simulation(cfg: Config, n: int) -> None:
    if cfg.devices:
        return
    for i in range(n):
        nube = n > 1 and i == n - 1  # el último, en modo nube, para ver ambos modos
        cfg.add_device({"name": "Enchufe simulado %d" % (i + 1), "dev_id": "sim%07d" % (i + 1),
                        "mode": "nube" if nube else "local",
                        "local_key": "" if nube else "0123456789abcdef", "ip": "192.168.1.%d" % (50 + i)})


def _hub(cfg: Config, simulate: bool = False):
    if simulate:
        return SimCloudHub()
    return CloudHub(lambda: cfg.options, cfg.cloud_ids)


def _cfg(args) -> Config:
    try:
        return Config(data_dir(args.data_dir) / "config.json")
    except ConfigError as exc:
        print("Error de configuración: %s" % exc, file=sys.stderr)
        sys.exit(2)


def cmd_serve(args) -> int:
    base = data_dir(args.data_dir)
    if args.simulate:
        if not 1 <= args.simulate <= MAX_DEVICES:
            print("--simulate admite de 1 a %d enchufes" % MAX_DEVICES, file=sys.stderr)
            return 2
        base = base / "simulacion"
    base.mkdir(parents=True, exist_ok=True)
    try:
        cfg = Config(base / "config.json")
    except ConfigError as exc:
        print("Error de configuración: %s" % exc, file=sys.stderr)
        return 2
    if args.simulate:
        _seed_simulation(cfg, args.simulate)

    url_host = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    url = "http://%s:%d/" % (url_host, args.port)
    if _already_running(url_host, args.port):
        print("%s ya está en marcha en %s" % (APP_NAME, url))
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    store = Store(base / "telemetria.sqlite3")
    hub = _hub(cfg, bool(args.simulate))
    if hasattr(hub, "on_calls"):
        hub.on_calls = store.add_api_calls  # llamadas a la nube guardadas por día
    monitor = Monitor(cfg, store, simulate=bool(args.simulate), hub=hub)
    loopback = args.host in ("127.0.0.1", "localhost", "::1")
    ctx = AppContext(cfg, store, monitor, bool(args.simulate), loopback_only=loopback,
                     extra_hosts=args.allow_host, hub=hub, extra_origins=args.allow_origin)
    try:
        server = make_server(ctx, args.host, args.port)
    except OSError as exc:
        print("No se puede abrir %s:%d (%s). Prueba con --port." % (args.host, args.port, exc), file=sys.stderr)
        return 1

    monitor.start()
    print("%s %s%s\n  Interfaz: %s\n  Datos:    %s\n  Pulsa Ctrl+C para salir."
          % (APP_NAME, __version__, " (SIMULACIÓN)" if args.simulate else "", url, base))
    if not loopback and not cfg.options.get("password_hash"):
        print("  AVISO: escuchando fuera de localhost SIN contraseña. Ponla con: telehome-enchufes password")
    if any(d["mode"] == "nube" for d in cfg.devices) and not hub.configured():
        print("  AVISO: hay enchufes en modo nube pero faltan las credenciales (telehome-enchufes cloud-setup)")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando…")
    finally:
        monitor.stop()
        server.server_close()
    return 0


def cmd_scan(args) -> int:
    try:
        found = scan_network(args.time)
    except ImportError:
        print("Falta TinyTuya: pip install tinytuya", file=sys.stderr)
        return 2
    if not found:
        print("No se ha encontrado ningún dispositivo Tuya (¿misma red? ¿Wi-Fi de 2,4 GHz?).")
        return 1
    for f in found:
        print("%-16s %-24s v%s" % (f["ip"], f["dev_id"], f["version"]))
    return 0


def cmd_probe(args) -> int:
    """Muestra los DPS crudos de un enchufe configurado (o de uno suelto)."""
    cfg = _cfg(args)
    dev = next((d for d in cfg.devices if args.enchufe in (d["id"], d["dev_id"], d["name"])), None)
    if dev is None:
        print("Enchufe no configurado: %s" % args.enchufe, file=sys.stderr)
        return 2
    try:
        dps = make_plug(dev, hub=_hub(cfg)).probe()
    except PlugError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(dps, indent=2, ensure_ascii=False))
    if dev["mode"] == "nube":
        keys = (dev["code_switch"], dev["code_power"], dev["code_voltage"], dev["code_current"])
    else:
        keys = (dev["dp_switch"], dev["dp_power"], dev["dp_voltage"], dev["dp_current"])
    print("\nMapa actual (%s): interruptor=%s potencia=%s (÷%g) tensión=%s (÷%g) corriente=%s (÷%g)" % (
        dev["mode"], keys[0], keys[1], dev["scale_power"], keys[2], dev["scale_voltage"],
        keys[3], dev["scale_current"]))
    return 0


def cmd_import(args) -> int:
    cfg = _cfg(args)
    try:
        rows = json.loads(Path(args.fichero).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print("No se puede leer %s: %s" % (args.fichero, exc), file=sys.stderr)
        return 2
    rep = cfg.import_devices(rows if isinstance(rows, list) else rows.get("devices", []),
                             "nube" if args.nube else "local")
    print("Añadidos: %s" % (", ".join(rep["añadidos"]) or "ninguno"))
    for o in rep["omitidos"]:
        print("Omitido %s: %s" % (o["name"], o["motivo"]))
    print("Total: %d/%d" % (len(cfg.devices), MAX_DEVICES))
    return 0


def cmd_list(args) -> int:
    cfg = _cfg(args)
    for d in cfg.devices:
        where = "nube" if d["mode"] == "nube" else "%s v%s" % (d["ip"], d["version"])
        print("%-24s %-22s %s" % (d["id"], d["dev_id"], where))
    print("%d/%d enchufes" % (len(cfg.devices), MAX_DEVICES))
    return 0


def cmd_password(args) -> int:
    cfg = _cfg(args)
    if args.quitar:
        cfg.set_password(None)
        print("Contraseña eliminada: la interfaz queda sin protección.")
        return 0
    pw = os.environ.get(args.password_env, "") if args.password_env else ""
    if not pw:
        pw = getpass.getpass("Nueva contraseña (mín. 8): ")
        if pw != getpass.getpass("Repítela: "):
            print("No coinciden.", file=sys.stderr)
            return 2
    try:
        cfg.set_password(pw)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    print("Contraseña guardada (se aplica al momento; usuario: cualquiera).")
    return 0


def cmd_cloud_setup(args) -> int:
    cfg = _cfg(args)
    secret = os.environ.get(args.secret_env, "") if args.secret_env else ""
    if not secret and not args.keep_secret:
        secret = getpass.getpass("Access Secret / Client Secret: ")
    try:
        cfg.set_cloud({"region": args.region, "api_key": args.access_id, "api_secret": secret})
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    print("Credenciales guardadas (región %s, %s)." % (args.region, REGIONS.get(args.region, "")))
    return cmd_cloud_list(args)


def cmd_cloud_list(args) -> int:
    cfg = _cfg(args)
    try:
        devs = _hub(cfg).list_devices()
    except CloudError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
    known = {d["dev_id"] for d in cfg.devices}
    for d in devs:
        print("%-24s %-28s %-6s %s%s" % (d["dev_id"], d["name"][:28], d["category"],
                                         "en línea" if d.get("online") else "desconectado",
                                         "  (ya configurado)" if d["dev_id"] in known else ""))
    print("%d dispositivos en la cuenta enlazada" % len(devs))
    return 0


def cmd_cloud_import(args) -> int:
    cfg = _cfg(args)
    try:
        devs = _hub(cfg).list_devices()
    except CloudError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
    if args.ids:
        devs = [d for d in devs if d["dev_id"] in set(args.ids)]
    elif not args.todos:
        devs = [d for d in devs if d.get("category") in ("cz", "pc")]  # enchufes y regletas
    rep = cfg.import_devices(devs, "nube")
    print("Añadidos: %s" % (", ".join(rep["añadidos"]) or "ninguno"))
    for o in rep["omitidos"]:
        print("Omitido %s: %s" % (o["name"], o["motivo"]))
    print("Total: %d/%d" % (len(cfg.devices), MAX_DEVICES))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="telehome-enchufes",
                                description="%s: telemetría y control local de enchufes Tuya (máx. %d)." % (APP_NAME, MAX_DEVICES))
    p.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--data-dir", help="carpeta de datos (por defecto ~/Library/Application Support/telehome-enchufes)")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="inicia la interfaz web local (orden por defecto)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    s.add_argument("--no-browser", action="store_true", help="no abrir el navegador")
    s.add_argument("--simulate", type=int, metavar="N", help="usa N enchufes simulados (prueba sin hardware)")
    s.add_argument("--allow-host", action="append", default=[], metavar="NOMBRE",
                   help="nombre de host adicional permitido (p. ej. tras un proxy inverso); repetible")
    s.add_argument("--allow-origin", action="append", default=[], metavar="ORIGEN",
                   help="origen web externo autorizado a usar la API (CORS), p. ej. https://usuario.github.io; repetible")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("scan", help="busca enchufes Tuya en la red local")
    s.add_argument("--time", type=int, default=12, help="segundos de escucha (12)")
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("probe", help="muestra los DPS crudos de un enchufe configurado")
    s.add_argument("enchufe", help="id, Device ID o nombre")
    s.set_defaults(fn=cmd_probe)

    s = sub.add_parser("import", help="importa el devices.json de «python -m tinytuya wizard»")
    s.add_argument("fichero")
    s.add_argument("--nube", action="store_true", help="darlos de alta en modo nube")
    s.set_defaults(fn=cmd_import)

    s = sub.add_parser("cloud-setup", help="guarda las credenciales de la nube de Tuya y lista los dispositivos")
    s.add_argument("--region", choices=CLOUD_REGIONS, default="eu", help="centro de datos (eu = Europa central)")
    s.add_argument("--access-id", required=True, help="Access ID / Client ID del proyecto")
    s.add_argument("--secret-env", metavar="VAR", help="leer el Access Secret de esta variable de entorno")
    s.add_argument("--keep-secret", action="store_true", help="conservar el secreto ya guardado")
    s.set_defaults(fn=cmd_cloud_setup)

    s = sub.add_parser("cloud-list", help="lista los dispositivos de la cuenta enlazada en la nube")
    s.set_defaults(fn=cmd_cloud_list)

    s = sub.add_parser("cloud-import", help="añade en modo nube los enchufes de la cuenta (máx. 7)")
    s.add_argument("ids", nargs="*", help="Device ID concretos (por defecto, todos los enchufes)")
    s.add_argument("--todos", action="store_true", help="incluir también lo que no sean enchufes")
    s.set_defaults(fn=cmd_cloud_import)

    s = sub.add_parser("password", help="pone (o quita) la contraseña de la interfaz web")
    s.add_argument("--quitar", action="store_true")
    s.add_argument("--password-env", metavar="VAR", help="leer la contraseña de esta variable de entorno")
    s.set_defaults(fn=cmd_password)

    s = sub.add_parser("list", help="lista los enchufes configurados")
    s.set_defaults(fn=cmd_list)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    if not args.cmd:
        args = parser.parse_args((argv or []) + ["serve"])
        _setup_logging(args.verbose)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

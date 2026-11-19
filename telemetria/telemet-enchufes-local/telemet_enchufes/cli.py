"""Línea de órdenes: servir la interfaz, buscar, probar e importar enchufes."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from typing import List, Optional

from . import APP_NAME, __version__
from .config import MAX_DEVICES, Config, ConfigError, data_dir
from .devices import PlugError, SimPlug, TuyaPlug, scan_network
from .monitor import Monitor
from .server import AppContext, make_server
from .store import Store

log = logging.getLogger("telemet-enchufes")
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
        cfg.add_device({"name": "Enchufe simulado %d" % (i + 1), "dev_id": "sim%07d" % (i + 1),
                        "local_key": "0123456789abcdef", "ip": "192.168.1.%d" % (50 + i)})


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
    monitor = Monitor(cfg, store, simulate=bool(args.simulate))
    loopback = args.host in ("127.0.0.1", "localhost", "::1")
    ctx = AppContext(cfg, store, monitor, bool(args.simulate), loopback_only=loopback)
    try:
        server = make_server(ctx, args.host, args.port)
    except OSError as exc:
        print("No se puede abrir %s:%d (%s). Prueba con --port.", file=sys.stderr)
        log.error("%s", exc)
        return 1

    monitor.start()
    print("%s %s%s\n  Interfaz: %s\n  Datos:    %s\n  Pulsa Ctrl+C para salir."
          % (APP_NAME, __version__, " (SIMULACIÓN)" if args.simulate else "", url, base))
    if not loopback:
        print("  AVISO: escuchando fuera de localhost; esta interfaz no tiene contraseña.")
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
    cfg = Config(data_dir(args.data_dir) / "config.json")
    dev = next((d for d in cfg.devices if args.enchufe in (d["id"], d["dev_id"], d["name"])), None)
    if dev is None:
        print("Enchufe no configurado: %s" % args.enchufe, file=sys.stderr)
        return 2
    try:
        dps = TuyaPlug(dev).probe()
    except PlugError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(dps, indent=2, ensure_ascii=False))
    print("\nMapa actual: interruptor=%s potencia=%s (÷%g) tensión=%s (÷%g) corriente=%s (÷%g)" % (
        dev["dp_switch"], dev["dp_power"], dev["scale_power"], dev["dp_voltage"], dev["scale_voltage"],
        dev["dp_current"], dev["scale_current"]))
    return 0


def cmd_import(args) -> int:
    cfg = Config(data_dir(args.data_dir) / "config.json")
    try:
        rows = json.loads(Path(args.fichero).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print("No se puede leer %s: %s" % (args.fichero, exc), file=sys.stderr)
        return 2
    rep = cfg.import_devices(rows if isinstance(rows, list) else rows.get("devices", []))
    print("Añadidos: %s" % (", ".join(rep["añadidos"]) or "ninguno"))
    for o in rep["omitidos"]:
        print("Omitido %s: %s" % (o["name"], o["motivo"]))
    print("Total: %d/%d" % (len(cfg.devices), MAX_DEVICES))
    return 0


def cmd_list(args) -> int:
    cfg = Config(data_dir(args.data_dir) / "config.json")
    for d in cfg.devices:
        print("%-24s %-22s %-16s v%s" % (d["id"], d["dev_id"], d["ip"], d["version"]))
    print("%d/%d enchufes" % (len(cfg.devices), MAX_DEVICES))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="telemet-enchufes",
                                description="%s: telemetría y control local de enchufes Tuya (máx. %d)." % (APP_NAME, MAX_DEVICES))
    p.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--data-dir", help="carpeta de datos (por defecto ~/Library/Application Support/telemet-enchufes)")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="inicia la interfaz web local (orden por defecto)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    s.add_argument("--no-browser", action="store_true", help="no abrir el navegador")
    s.add_argument("--simulate", type=int, metavar="N", help="usa N enchufes simulados (prueba sin hardware)")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("scan", help="busca enchufes Tuya en la red local")
    s.add_argument("--time", type=int, default=12, help="segundos de escucha (12)")
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("probe", help="muestra los DPS crudos de un enchufe configurado")
    s.add_argument("enchufe", help="id, Device ID o nombre")
    s.set_defaults(fn=cmd_probe)

    s = sub.add_parser("import", help="importa el devices.json de «python -m tinytuya wizard»")
    s.add_argument("fichero")
    s.set_defaults(fn=cmd_import)

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

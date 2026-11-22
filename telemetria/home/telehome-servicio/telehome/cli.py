"""Línea de órdenes: servir la interfaz, buscar, probar e importar enchufes."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import logging
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import List, Optional

from . import APP_NAME, __version__
from .cloud import REGIONS, CloudError, CloudHub, SimCloudHub
from .config import CLOUD_REGIONS, MAX_DEVICES, Config, ConfigError, data_dir
from .devices import PlugError, make_plug, scan_network
from .monitor import Monitor
from .scheduler import Scheduler, instante
from .server import AppContext, make_server
from .store import Store

log = logging.getLogger("telehome")
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
    scheduler = Scheduler(cfg, monitor, store)
    ctx = AppContext(cfg, store, monitor, bool(args.simulate), loopback_only=loopback,
                     extra_hosts=args.allow_host, hub=hub, extra_origins=args.allow_origin,
                     scheduler=scheduler)
    try:
        server = make_server(ctx, args.host, args.port)
    except OSError as exc:
        print("No se puede abrir %s:%d (%s). Prueba con --port." % (args.host, args.port, exc), file=sys.stderr)
        return 1

    monitor.start()
    scheduler.start()
    print("%s %s%s\n  Interfaz: %s\n  Datos:    %s\n  Pulsa Ctrl+C para salir."
          % (APP_NAME, __version__, " (SIMULACIÓN)" if args.simulate else "", url, base))
    if not loopback and not cfg.options.get("password_hash"):
        print("  AVISO: escuchando fuera de localhost SIN contraseña. Ponla con: telehome password")
    activas = [x for x in cfg.schedules if x.get("enabled")]
    if activas:
        print("  Programaciones: %d activas de %d" % (len(activas), len(cfg.schedules)))
    if any(d["mode"] == "nube" for d in cfg.devices) and not hub.configured():
        print("  AVISO: hay enchufes en modo nube pero faltan las credenciales (telehome cloud-setup)")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando…")
    finally:
        scheduler.stop()
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


def cmd_export_config(args) -> int:
    """Escribe toda la configuración (sin la contraseña del servicio) para dársela a otro usuario."""
    cfg = _cfg(args)
    try:
        text = json.dumps(cfg.export_config(args.ruta), ensure_ascii=False, indent=2)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.salida == "-":
        print(text)
    else:
        out = Path(args.salida or "telehome-config-%s.json" % time.strftime("%Y%m%d"))
        fd = os.open(str(out), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        os.chmod(str(out), 0o600)
        print("Configuración guardada en %s (%d enchufes)." % (out, len(cfg.devices)))
    print("AVISO: el fichero lleva las credenciales de Tuya y las Local Key. Compártelo solo con quien debas.", file=sys.stderr)
    return 0


def cmd_import_config(args) -> int:
    cfg = _cfg(args)
    try:
        data = json.loads(Path(args.fichero).read_text(encoding="utf-8-sig"))
        rep = cfg.import_config(data, replace=not args.anadir)
    except (OSError, ValueError) as exc:
        print("No se puede leer %s: %s" % (args.fichero, exc), file=sys.stderr)
        return 2
    print("Añadidos: %s" % (", ".join(rep["añadidos"]) or "ninguno"))
    if rep["actualizados"]:
        print("Actualizados: %s" % ", ".join(rep["actualizados"]))
    for o in rep["omitidos"]:
        print("Omitido %s: %s" % (o["name"], o["motivo"]))
    print("Ajustes aplicados: %s" % (", ".join(rep["opciones"]) or "ninguno"))
    if rep.get("servicio"):
        print("Ruta del servicio indicada en el fichero: %s (se usa en la app TeleHome, campo «Servicio TeleHome»)" % rep["servicio"]["ruta"])
    print("Total: %d/%d (la contraseña del servicio no se ha tocado)" % (rep["total"], MAX_DEVICES))
    return 0


def _texto_momento(sch) -> str:
    w = sch["when"]
    if w["kind"] == "clock":
        return "a las " + w["time"]
    cual = "amanecer" if w["kind"] == "sunrise" else "anochecer"
    off = w.get("offset", 0)
    if not off:
        return "al " + cual
    return "%d min %s del %s" % (abs(off), "antes" if off < 0 else "después", cual)


def _texto_orden(sch) -> str:
    a, v = sch["action"], sch["value"]
    if a == "switch":
        return "encender" if v else "apagar"
    if a == "level":
        return "brillo al %d %%" % v
    if a == "position":
        return "abrir al %d %%" % v
    return "parar"


def cmd_schedules(args) -> int:
    """Lista las programaciones, o activa y desactiva una."""
    cfg = _cfg(args)
    if args.activar or args.desactivar:
        quien = args.activar or args.desactivar
        sch = next((x for x in cfg.schedules if quien in (x["id"], x["name"])), None)
        if sch is None:
            print("No hay ninguna programación «%s»" % quien, file=sys.stderr)
            return 2
        cfg.update_schedule(sch["id"], {"enabled": bool(args.activar)})
        print("«%s» %s." % (sch["name"], "activada" if args.activar else "desactivada"))
        return 0
    if args.borrar:
        sch = next((x for x in cfg.schedules if args.borrar in (x["id"], x["name"])), None)
        if sch is None:
            print("No hay ninguna programación «%s»" % args.borrar, file=sys.stderr)
            return 2
        cfg.delete_schedule(sch["id"])
        print("«%s» borrada." % sch["name"])
        return 0
    if not cfg.schedules:
        print("No hay programaciones. Se crean desde la app, en Ajustes → Programaciones.")
        return 0
    dias_cortos = ["L", "M", "X", "J", "V", "S", "D"]
    for x in cfg.schedules:
        dias = "".join(dias_cortos[d - 1] if d in x["days"] else "·" for d in range(1, 8))
        extra = []
        if x.get("condition"):
            c = x["condition"]
            extra.append("si %s %s %g%s" % (c["metric"], c["op"], c["value"],
                                            " durante %d s" % c["for"] if c.get("for") else ""))
        if x.get("skip_if_manual"):
            extra.append("salvo si lo tocaste")
        print("%-22s %-3s %-8s %-26s %s → %s" % (
            x["id"], "on" if x["enabled"] else "off", dias, _texto_momento(x),
            _texto_orden(x), x["device"]))
        if extra:
            print("%-22s     %s" % ("", "; ".join(extra)))
        if x.get("last_result"):
            print("%-22s     última vez: %s (%s)" % ("", x["last_result"],
                  time.strftime("%d/%m %H:%M", time.localtime(x["last_fire"])) if x.get("last_fire") else "nunca"))
    n = len(cfg.schedules)
    print("%d %s" % (n, "programación" if n == 1 else "programaciones"))
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


def cmd_admin_password(args) -> int:
    """Contraseña del modo Administrador: con ella puesta, quien no la tenga solo puede ver los datos."""
    cfg = _cfg(args)
    if args.quitar:
        cfg.set_admin_password(None)
        print("Modo Administrador desactivado: cualquiera que llegue al servicio puede cambiarlo todo.")
        return 0
    pw = os.environ.get(args.password_env, "") if args.password_env else ""
    if not pw:
        pw = getpass.getpass("Nueva contraseña de administrador (mín. 8): ")
        if pw != getpass.getpass("Repítela: "):
            print("No coinciden.", file=sys.stderr)
            return 2
    try:
        cfg.set_admin_password(pw)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    print("Contraseña de administrador guardada: sin ella, la interfaz queda en solo lectura (se aplica al momento).")
    return 0


def cmd_user_password(args) -> int:
    """Contraseña del usuario de confianza: puede encender y apagar, pero no cambiar nada."""
    cfg = _cfg(args)
    if args.quitar:
        cfg.set_user_password(None)
        print("Usuario de confianza desactivado.")
        return 0
    pw = os.environ.get(args.password_env, "") if args.password_env else ""
    if not pw:
        pw = getpass.getpass("Nueva contraseña de usuario (mín. 8): ")
        if pw != getpass.getpass("Repítela: "):
            print("No coinciden.", file=sys.stderr)
            return 2
    try:
        cfg.set_user_password(pw)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    print("Contraseña de usuario guardada: con ella se pueden mandar órdenes, pero no cambiar la configuración.")
    if not cfg.options.get("admin_password_hash"):
        print("AVISO: no hay contraseña de administrador (telehome admin-password). Mientras no la pongas, quien no "
              "tenga sesión no podrá mandar órdenes y la configuración solo se cambia desde aquí.", file=sys.stderr)
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
    p = argparse.ArgumentParser(prog="telehome",
                                description="%s: telemetría y control local de enchufes Tuya (máx. %d)." % (APP_NAME, MAX_DEVICES))
    p.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--data-dir", help="carpeta de datos (por defecto ~/Library/Application Support/telehome)")
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

    s = sub.add_parser("export-config", help="exporta dispositivos, credenciales de Tuya y ajustes (sin la contraseña del servicio)")
    s.add_argument("-o", "--salida", metavar="FICHERO", help="fichero de salida (por defecto telehome-config-AAAAMMDD.json; «-» = pantalla)")
    s.add_argument("--ruta", metavar="RUTA", help="ruta por la que se llega al servicio (p. ej. /rafa/telehome/) para que vaya en el fichero")
    s.set_defaults(fn=cmd_export_config)

    s = sub.add_parser("import-config", help="aplica un fichero creado con export-config")
    s.add_argument("fichero")
    s.add_argument("--anadir", action="store_true", help="solo añade los dispositivos que falten (por defecto reemplaza)")
    s.set_defaults(fn=cmd_import_config)

    s = sub.add_parser("admin-password", help="pone (o quita) la contraseña del modo Administrador (sin ella la interfaz es de solo lectura)")
    s.add_argument("--quitar", action="store_true")
    s.add_argument("--password-env", metavar="VAR", help="leer la contraseña de esta variable de entorno")
    s.set_defaults(fn=cmd_admin_password)

    s = sub.add_parser("user-password", help="pone (o quita) la contraseña del usuario de confianza (manda órdenes, no configura)")
    s.add_argument("--quitar", action="store_true")
    s.add_argument("--password-env", metavar="VAR", help="leer la contraseña de esta variable de entorno")
    s.set_defaults(fn=cmd_user_password)

    s = sub.add_parser("schedules", help="lista las programaciones (o activa, desactiva y borra una)")
    s.add_argument("--activar", metavar="ID")
    s.add_argument("--desactivar", metavar="ID")
    s.add_argument("--borrar", metavar="ID")
    s.set_defaults(fn=cmd_schedules)

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

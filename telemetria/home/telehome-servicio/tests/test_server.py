import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from telehome.config import Config
from telehome.monitor import Monitor
from telehome.server import AppContext, make_server
from telehome.store import Store


@pytest.fixture()
def app(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.set_options({"poll_interval": 5})
    for i in range(2):
        cfg.add_device({"name": "Sim %d" % i, "dev_id": "sim%07d" % i, "local_key": "0123456789abcdef", "ip": "10.0.0.%d" % (i + 1)})
    store = Store(tmp_path / "t.db")
    mon = Monitor(cfg, store, simulate=True)
    ctx = AppContext(cfg, store, mon, True)
    srv = make_server(ctx, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    mon.start()
    time.sleep(0.6)
    yield "http://127.0.0.1:%d" % srv.server_address[1], cfg, mon
    mon.stop()
    srv.shutdown()
    srv.server_close()


def call(base, path, method="GET", body=None, headers=None):
    h = {"X-TeleHome": "1"} if method != "GET" else {}
    h.update(headers or {})
    data = None if body is None else json.dumps(body).encode()
    if data:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if r.headers["Content-Type"].startswith("application/json") else raw)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_index_and_state(app):
    base, cfg, mon = app
    st, html = call(base, "/")
    assert st == 200 and b"TeleHome" in html
    st, state = call(base, "/api/state")
    assert st == 200 and state["max_devices"] == 7 and len(state["devices"]) == 2
    assert all("local_key" not in d for d in state["devices"])
    assert all(d["reading"]["online"] and d["reading"]["power_w"] > 0 for d in state["devices"])


def test_power_toggle(app):
    base, cfg, mon = app
    pid = cfg.devices[0]["id"]
    st, r = call(base, "/api/plugs/%s/power" % pid, "POST", {"on": False})
    assert st == 200 and r["on"] is False
    st, state = call(base, "/api/state")
    d = next(x for x in state["devices"] if x["id"] == pid)
    assert d["reading"]["on"] is False and d["reading"]["power_w"] == 0.0
    assert call(base, "/api/plugs/%s/power" % pid, "POST", {"on": "si"})[0] == 400
    assert call(base, "/api/plugs/nope/power", "POST", {"on": True})[0] == 404


def test_limit_of_seven_via_api(app):
    base, cfg, mon = app
    for i in range(5):
        st, _ = call(base, "/api/devices", "POST", {"name": "N%d" % i, "dev_id": "bf0000000%d" % i, "local_key": "0123456789abcdef"})
        assert st == 201
    st, err = call(base, "/api/devices", "POST", {"name": "Octavo", "dev_id": "bf99999999", "local_key": "0123456789abcdef"})
    assert st == 400 and "Máximo 7" in err["error"]
    time.sleep(0.5)
    assert len(call(base, "/api/state")[1]["devices"]) == 7


def test_edit_delete_and_threads_follow_config(app):
    base, cfg, mon = app
    pid = cfg.devices[0]["id"]
    assert call(base, "/api/devices/" + pid, "PUT", {"name": "Nevera"})[0] == 200
    assert call(base, "/api/devices/" + pid, "DELETE")[0] == 200
    assert pid not in mon.plugs and pid not in mon.latest
    assert call(base, "/api/devices/" + pid, "DELETE")[0] == 404


def test_history_summary_csv(app):
    base, cfg, mon = app
    pid = cfg.devices[0]["id"]
    st, h = call(base, "/api/history?plug=all&range=3600")
    assert st == 200 and pid in h["series"] and len(h["series"][pid]) >= 1
    st, s = call(base, "/api/summary?range=3600")
    assert st == 200 and s["plugs"][pid]["samples"] >= 1
    st, csv_ = call(base, "/api/export.csv?plug=%s&range=3600" % pid)
    assert st == 200 and csv_.startswith(b"fecha_hora_utc")
    assert call(base, "/api/history?plug=zzz")[0] == 404


def test_security_guards(app):
    base, cfg, mon = app
    # DNS rebinding: Host ajeno
    assert call(base, "/api/state", headers={"Host": "evil.example.com"})[0] == 403
    # CSRF: POST sin cabecera personalizada
    req = urllib.request.Request(base + "/api/options", data=b"{}", method="PUT")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 403
    # Origin de otro sitio
    assert call(base, "/api/options", "PUT", {"poll_interval": 7}, headers={"Origin": "http://evil.example.com"})[0] == 403
    assert call(base, "/api/options", "PUT", {"poll_interval": 3})[0] == 400


def test_import_and_discover(app):
    base, cfg, mon = app
    st, rep = call(base, "/api/devices/import", "POST",
                   {"devices": [{"id": "bf11111111", "key": "0123456789abcdef", "name": "Importado", "ip": "10.0.0.9", "version": "3.4"}]})
    assert st == 200 and rep["añadidos"] == ["Importado"]
    st, d = call(base, "/api/discover", "POST", {})
    assert st == 200 and d["found"]


def test_generic_protocol(app):
    """api/health, api/state y api/summary hablan también el modelo genérico de TeleHome."""
    base, cfg, mon = app
    st, h = call(base, "/api/health")
    assert st == 200 and h["api"] == "telehome" and h["types"] == ["enchufe", "luz"]
    st, state = call(base, "/api/state")
    assert state["api"] == "telehome" and state["types"] == ["enchufe", "luz"]
    d = state["devices"][0]
    assert d["type"] == "enchufe" and "room" in d
    assert d["reading"]["state"]["on"] is True
    assert d["reading"]["values"]["p"] == d["reading"]["power_w"]
    assert d["accum"]["energy_today_kwh"] == d["energy_today_kwh"]
    pid = d["id"]
    st, s = call(base, "/api/summary?range=3600")
    assert st == 200 and s["devices"][pid] == s["plugs"][pid]
    assert s["devices"][pid]["m"]["p"]["avg"] == s["devices"][pid]["avg_w"]
    assert s["devices"][pid]["on_ratio"] == 1.0
    # «dev» es el alias genérico de «plug»
    assert pid in call(base, "/api/history?dev=all&range=3600")[1]["series"]
    assert call(base, "/api/export.csv?dev=%s&range=3600" % pid)[0] == 200
    assert call(base, "/api/history?dev=zzz")[0] == 404


def test_generic_command(app):
    base, cfg, mon = app
    pid = cfg.devices[0]["id"]
    st, r = call(base, "/api/devices/%s/command" % pid, "POST", {"action": "switch", "value": False})
    assert st == 200 and r["state"]["on"] is False and r["on"] is False
    d = next(x for x in call(base, "/api/state")[1]["devices"] if x["id"] == pid)
    assert d["reading"]["values"]["p"] == 0.0
    st, r = call(base, "/api/devices/%s/command" % pid, "POST", {"action": "switch", "value": True})
    assert st == 200 and r["state"]["on"] is True
    # órdenes de otros tipos de dispositivo y valores no booleanos: 400
    assert call(base, "/api/devices/%s/command" % pid, "POST", {"action": "level", "value": 50})[0] == 400
    assert call(base, "/api/devices/%s/command" % pid, "POST", {"action": "switch", "value": "si"})[0] == 400
    assert call(base, "/api/devices/nope/command", "POST", {"action": "switch", "value": True})[0] == 404


def test_type_and_room(app):
    base, cfg, mon = app
    st, dev = call(base, "/api/devices", "POST",
                   {"name": "Caldera", "room": "  Garaje  ", "type": "enchufe",
                    "dev_id": "bf7777777777", "local_key": "0123456789abcdef"})
    assert st == 201 and dev["room"] == "Garaje" and dev["type"] == "enchufe"
    st, err = call(base, "/api/devices", "POST",
                   {"name": "Persiana", "type": "persiana", "dev_id": "bf8888888888", "local_key": "0123456789abcdef"})
    assert st == 400 and "no admitido" in err["error"]
    st, lamp = call(base, "/api/devices", "POST",
                    {"name": "Lámpara", "type": "luz", "dev_id": "bf9999999999", "local_key": "0123456789abcdef"})
    assert st == 201 and lamp["type"] == "luz" and lamp["code_level"] == "bright_value_v2" and "code_power" not in lamp
    st, cambiada = call(base, "/api/devices/%s" % lamp["id"], "PUT", {"type": "enchufe"})
    assert st == 200 and cambiada["type"] == "enchufe" and cambiada["code_power"] == "cur_power" and "code_level" not in cambiada


def _cors_server(tmp_path, origins):
    cfg = Config(tmp_path / "config.json")
    store = Store(tmp_path / "t.db")
    mon = Monitor(cfg, store, simulate=True)
    ctx = AppContext(cfg, store, mon, True, extra_origins=origins)
    srv = make_server(ctx, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


def test_cors_allow_origin(tmp_path):
    srv, base = _cors_server(tmp_path, ["https://rafaumh2110.github.io/"])
    try:
        ok = {"Origin": "https://rafaumh2110.github.io"}
        # preflight de un origen autorizado
        req = urllib.request.Request(base + "/api/health", method="OPTIONS", headers=dict(ok, **{"Access-Control-Request-Method": "GET"}))
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 204
            assert r.headers["Access-Control-Allow-Origin"] == ok["Origin"]
            assert "X-TeleHome" in r.headers["Access-Control-Allow-Headers"]
        # lectura y escritura con ese origen
        req = urllib.request.Request(base + "/api/health", headers=ok)
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.headers["Access-Control-Allow-Origin"] == ok["Origin"]
        st, _ = call(base, "/api/options", "PUT", {"poll_interval": 20}, ok)
        assert st == 200
        # origen no autorizado: ni preflight ni escritura
        bad = {"Origin": "https://malo.example"}
        req = urllib.request.Request(base + "/api/health", method="OPTIONS", headers=bad)
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 403
        st, body = call(base, "/api/options", "PUT", {"poll_interval": 20}, bad)
        assert st == 403
        req = urllib.request.Request(base + "/api/health", headers=bad)
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.headers.get("Access-Control-Allow-Origin") is None
    finally:
        srv.shutdown()
        srv.server_close()


def test_state_incluye_llamadas_por_dia(app):
    base, cfg, mon = app
    mon.store.add_api_calls(4)
    st, state = call(base, "/api/state")
    c = state["cloud"]
    assert c["today"] == 4 and c["yesterday"] == 0 and c["month"] >= 4 and c["last30"] == 4
    assert len(c["by_day"]) == 31 and c["by_day"][-1]["n"] == 4


def test_energia_de_hoy_sobrevive_al_reinicio_con_lecturas_de_nube(tmp_path):
    """Con lecturas cada 300 s (nube) la energía de hoy no debe quedar a cero al arrancar."""
    from telehome.monitor import local_midnight
    cfg = Config(tmp_path / "config.json")
    cfg.add_device({"name": "Nube", "dev_id": "vdev0000000000000001", "mode": "nube"})
    dev = cfg.devices[0]
    store = Store(tmp_path / "t.db")
    now = time.time()
    t0 = max(local_midnight(now), now - 3 * 3600)
    for k in range(int((now - t0) // 300)):
        store.add(dev["id"], t0 + k * 300, True, True, 1000.0, 230.0, 4.3)
    mon = Monitor(cfg, store, simulate=True)
    mon._spawn(dev)
    mon._stops[dev["id"]].set()
    kwh = mon._energy[dev["id"]]["kwh"]
    esperado = 1000.0 * (int((now - t0) // 300) - 1) * 300 / 3_600_000.0
    assert kwh > 0 and abs(kwh - esperado) < 0.01


def test_exportar_e_importar_configuracion_por_api(app):
    base, cfg, mon = app
    cfg.set_cloud({"region": "eu", "api_key": "abcdefghij12", "api_secret": "secretsecret1234"})
    cfg.set_password("clave-del-servicio")
    auth = {"Authorization": "Basic " + __import__("base64").b64encode(b":clave-del-servicio").decode()}
    st, _ = call(base, "/api/config/export", "POST")
    assert st == 401                                           # exige la contraseña del servicio
    st, exp = call(base, "/api/config/export", "POST", headers=auth)
    assert st == 200 and exp["format"] == "telehome-config" and len(exp["devices"]) == 2 and "servicio" not in exp
    st, con_ruta = call(base, "/api/config/export", "POST", {"ruta": "/rafa/telehome/"}, headers=auth)
    assert st == 200 and con_ruta["servicio"] == {"ruta": "/rafa/telehome/"}
    assert call(base, "/api/config/export", "POST", {"ruta": "no-es-ruta"}, headers=auth)[0] == 400
    assert exp["options"]["cloud_api_secret"] == "secretsecret1234" and "password_hash" not in json.dumps(exp)
    req = urllib.request.Request(base + "/api/config/export", method="POST", headers={"X-TeleHome": "1", **auth})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert "attachment" in r.headers["Content-Disposition"]
    cfg.delete_device(cfg.devices[0]["id"])
    st, rep = call(base, "/api/config/import", "POST", {"config": exp, "modo": "añadir"}, headers=auth)
    assert st == 200 and len(rep["añadidos"]) == 1 and rep["total"] == 2
    st, rep = call(base, "/api/config/import", "POST", {"config": exp}, headers=auth)
    assert st == 200 and rep["total"] == 2 and len(rep["actualizados"]) == 2
    assert call(base, "/api/config/import", "POST", {"config": {"format": "x"}}, headers=auth)[0] == 400
    assert call(base, "/api/config/import", "POST", {"config": exp, "modo": "raro"}, headers=auth)[0] == 400
    st, _ = call(base, "/api/config/import", "POST", exp, headers={"Authorization": auth["Authorization"], "X-TeleHome": ""})
    assert st == 403                                           # sin la cabecera X-TeleHome no se acepta
    assert cfg.options["password_hash"]                        # la contraseña del servicio sigue puesta


def test_cli_exportar_e_importar(tmp_path, capsys):
    from telehome.cli import main
    d1, d2 = tmp_path / "a", tmp_path / "b"
    c1 = Config(d1 / "config.json")
    c1.set_cloud({"region": "eu", "api_key": "abcdefghij12", "api_secret": "secretsecret1234"})
    c1.set_password("clave-del-servicio")
    c1.add_device({"name": "Uno", "dev_id": "bf00000001", "local_key": "0123456789abcdef"})
    fich = tmp_path / "cfg.json"
    assert main(["--data-dir", str(d1), "export-config", "-o", str(fich)]) == 0
    assert oct(fich.stat().st_mode & 0o777) == "0o600" and "pbkdf2" not in fich.read_text()
    fich2 = tmp_path / "cfg2.json"
    assert main(["--data-dir", str(d1), "export-config", "-o", str(fich2), "--ruta", "/rafa/telehome/"]) == 0
    assert json.loads(fich2.read_text())["servicio"]["ruta"] == "/rafa/telehome/"
    assert main(["--data-dir", str(d1), "export-config", "-o", str(tmp_path / "x.json"), "--ruta", "mala"]) == 2
    assert main(["--data-dir", str(d2), "import-config", str(fich)]) == 0
    c2 = Config(d2 / "config.json")
    assert c2.options["cloud_api_secret"] == "secretsecret1234" and c2.devices[0]["name"] == "Uno" and not c2.options["password_hash"]
    (tmp_path / "mal.json").write_text('{"format": "otro"}')
    assert main(["--data-dir", str(d2), "import-config", str(tmp_path / "mal.json")]) == 2


def _admin_headers(token):
    return {"X-TeleHome-Admin": token} if token else {}


def test_modo_administrador_solo_lectura_sin_sesion(app):
    base, cfg, mon = app
    dev0 = cfg.devices[0]["id"]
    # sin contraseña de administrador todo está abierto, como antes
    st, state = call(base, "/api/state")
    assert state["admin"] == {"required": False, "active": True} and "dev_id" in state["devices"][0]
    assert call(base, "/api/devices/%s/command" % dev0, "POST", {"action": "switch", "value": False})[0] == 200
    cfg.set_admin_password("clave-admin-1")
    assert call(base, "/api/health")[1]["admin_required"] is True
    # solo lectura: se ven las lecturas, no la configuración
    st, state = call(base, "/api/state")
    assert st == 200 and state["admin"] == {"required": True, "active": False}
    d = state["devices"][0]
    assert d["name"] and d["reading"] and not any(k in d for k in ("dev_id", "ip", "version", "has_key", "dp_power", "code_power", "scale_power"))
    assert set(state["options"]) <= {"poll_interval", "cloud_poll_interval", "retention_days"} and state["cloud"]["configured"] is False
    assert call(base, "/api/history?dev=all&range=600")[0] == 200 and call(base, "/api/summary")[0] == 200
    # todo lo que cambia algo exige ser administrador
    for method, path, body in (("POST", "/api/devices/%s/command" % dev0, {"action": "switch", "value": True}),
                               ("POST", "/api/plugs/%s/power" % dev0, {"on": True}),
                               ("POST", "/api/devices", {"name": "X", "dev_id": "bf99999999", "local_key": "0123456789abcdef"}),
                               ("PUT", "/api/devices/%s" % dev0, {"name": "Otro"}),
                               ("DELETE", "/api/devices/%s" % dev0, None),
                               ("POST", "/api/devices/import", {"devices": []}),
                               ("PUT", "/api/options", {"poll_interval": 9}),
                               ("PUT", "/api/cloud", {"region": "eu"}),
                               ("POST", "/api/cloud/test", {}), ("POST", "/api/discover", {}),
                               ("POST", "/api/config/export", None), ("POST", "/api/config/import", {"config": {}}),
                               ("PUT", "/api/admin/password", {"password": "otra-clave-9"})):
        st, r = call(base, path, method, body)
        assert st == 403 and r.get("admin_required") is True, (method, path, st)
    assert len(cfg.devices) == 2 and cfg.options["poll_interval"] == 5


def test_login_de_administrador(app):
    base, cfg, mon = app
    dev0 = cfg.devices[0]["id"]
    cfg.set_admin_password("clave-admin-1")
    st, r = call(base, "/api/admin/login", "POST", {"password": "mala-mala"})
    assert st == 403 and "incorrecta" in r["error"] and "token" not in r
    assert call(base, "/api/admin/login", "POST", {"password": "clave-admin-1"}, headers={"X-TeleHome": ""})[0] == 403   # sin X-TeleHome
    st, r = call(base, "/api/admin/login", "POST", {"password": "clave-admin-1"})
    assert st == 200 and r["active"] and len(r["token"]) >= 32
    tok = r["token"]
    st, state = call(base, "/api/state", headers=_admin_headers(tok))
    assert state["admin"] == {"required": True, "active": True} and state["devices"][0]["dev_id"]
    assert call(base, "/api/devices/%s/command" % dev0, "POST", {"action": "switch", "value": False}, headers=_admin_headers(tok))[0] == 200
    assert call(base, "/api/devices/%s/command" % dev0, "POST", {"action": "switch", "value": True}, headers=_admin_headers("falso"))[0] == 403
    st, exp = call(base, "/api/config/export", "POST", headers=_admin_headers(tok))
    assert st == 200 and "admin_password_hash" not in json.dumps(exp) and "pbkdf2" not in json.dumps(exp)
    # cerrar sesión invalida el token
    assert call(base, "/api/admin/logout", "POST", {}, headers=_admin_headers(tok))[0] == 200
    assert call(base, "/api/devices/%s/command" % dev0, "POST", {"action": "switch", "value": True}, headers=_admin_headers(tok))[0] == 403


def test_cambiar_o_quitar_la_contrasena_de_administrador(app):
    base, cfg, mon = app
    cfg.set_admin_password("clave-admin-1")
    tok = call(base, "/api/admin/login", "POST", {"password": "clave-admin-1"})[1]["token"]
    st, r = call(base, "/api/admin/password", "PUT", {"password": "corta"}, headers=_admin_headers(tok))
    assert st == 400                                                         # mínimo 8
    st, r = call(base, "/api/admin/password", "PUT", {"password": "clave-nueva-2"}, headers=_admin_headers(tok))
    assert st == 200 and r["token"] and r["token"] != tok
    assert call(base, "/api/options", "PUT", {"poll_interval": 8}, headers=_admin_headers(tok))[0] == 403     # sesiones antiguas cerradas
    assert call(base, "/api/options", "PUT", {"poll_interval": 8}, headers=_admin_headers(r["token"]))[0] == 200
    assert call(base, "/api/admin/login", "POST", {"password": "clave-admin-1"})[0] == 403
    assert call(base, "/api/admin/password", "PUT", {"quitar": True}, headers=_admin_headers(r["token"]))[0] == 200
    assert call(base, "/api/options", "PUT", {"poll_interval": 9})[0] == 200                                  # vuelve a estar abierto
    assert call(base, "/api/state")[1]["admin"] == {"required": False, "active": True}


def test_cambiar_la_contrasena_por_la_cli_cierra_las_sesiones(app):
    base, cfg, mon = app
    cfg.set_admin_password("clave-admin-1")
    tok = call(base, "/api/admin/login", "POST", {"password": "clave-admin-1"})[1]["token"]
    other = Config(cfg.path)                                                 # como hace «telehome admin-password» en otro proceso
    other.set_admin_password("clave-cli-nueva")
    assert call(base, "/api/options", "PUT", {"poll_interval": 8}, headers=_admin_headers(tok))[0] == 403


def test_administrador_y_contrasena_del_servicio_conviven(app):
    base, cfg, mon = app
    cfg.set_password("clave-del-servicio")
    cfg.set_admin_password("clave-admin-1")
    basic = {"Authorization": "Basic " + __import__("base64").b64encode(b":clave-del-servicio").decode()}
    assert call(base, "/api/state")[0] == 401                                # sin la del servicio no se ve nada
    assert call(base, "/api/state", headers=basic)[1]["admin"]["active"] is False
    tok = call(base, "/api/admin/login", "POST", {"password": "clave-admin-1"}, headers=basic)[1]["token"]
    st, _ = call(base, "/api/options", "PUT", {"poll_interval": 8}, headers={**basic, **_admin_headers(tok)})
    assert st == 200
    assert call(base, "/api/options", "PUT", {"poll_interval": 9}, headers=_admin_headers(tok))[0] == 401   # la del servicio sigue mandando


def test_cli_admin_password(tmp_path, monkeypatch):
    from telehome.cli import main
    d = tmp_path / "d"
    monkeypatch.setenv("TH_ADMIN", "clave-admin-cli")
    assert main(["--data-dir", str(d), "admin-password", "--password-env", "TH_ADMIN"]) == 0
    c = Config(d / "config.json")
    assert c.options["admin_password_hash"] and c.public_options()["admin_set"] is True and "admin_password_hash" not in c.public_options()
    monkeypatch.setenv("TH_ADMIN", "corta")
    assert main(["--data-dir", str(d), "admin-password", "--password-env", "TH_ADMIN"]) == 2
    assert main(["--data-dir", str(d), "admin-password", "--quitar"]) == 0
    assert not Config(d / "config.json").options["admin_password_hash"]


def test_cambiar_y_quitar_la_contrasena_del_servicio_desde_la_api(app):
    base, cfg, mon = app
    # sin contraseña de administrador, cualquiera puede (igual que el resto de la API)
    st, opts = call(base, "/api/password", "PUT", {"password": "clave-nueva-123"})
    assert st == 200 and opts["password_set"] is True and "password_hash" not in opts
    basic = {"Authorization": "Basic " + __import__("base64").b64encode(b":clave-nueva-123").decode()}
    assert call(base, "/api/state")[0] == 401 and call(base, "/api/state", headers=basic)[0] == 200
    # la nueva contraseña manda de verdad
    assert call(base, "/api/password", "PUT", {"password": "otra-mas-larga"}, headers=basic)[0] == 200
    assert call(base, "/api/state", headers=basic)[0] == 401
    basic2 = {"Authorization": "Basic " + __import__("base64").b64encode(b":otra-mas-larga").decode()}
    assert call(base, "/api/password", "PUT", {"password": "corta"}, headers=basic2)[0] == 400       # mínimo 8
    assert call(base, "/api/password", "PUT", {"password": ""}, headers=basic2)[0] == 400            # vacía no borra
    st, opts = call(base, "/api/password", "PUT", {"quitar": True}, headers=basic2)
    assert st == 200 and opts["password_set"] is False
    assert call(base, "/api/state")[0] == 200


def test_la_contrasena_del_servicio_solo_la_cambia_un_administrador(app):
    base, cfg, mon = app
    cfg.set_admin_password("clave-admin-1")
    st, r = call(base, "/api/password", "PUT", {"password": "clave-nueva-123"})
    assert st == 403 and r["admin_required"] is True and not cfg.options["password_hash"]
    tok = call(base, "/api/admin/login", "POST", {"password": "clave-admin-1"})[1]["token"]
    assert call(base, "/api/password", "PUT", {"password": "clave-nueva-123"}, headers={"X-TeleHome-Admin": tok})[0] == 200
    assert cfg.options["password_hash"].startswith("pbkdf2_sha256$")
    # la contraseña nunca sale por la API, ni siquiera siendo administrador
    basic = {"Authorization": "Basic " + __import__("base64").b64encode(b":clave-nueva-123").decode()}
    st, state = call(base, "/api/state", headers={**basic, "X-TeleHome-Admin": tok})
    assert state["options"]["password_set"] is True and "password_hash" not in json.dumps(state)
    assert "clave-nueva-123" not in json.dumps(state)


def _hdr(token):
    return {"X-TeleHome-Admin": token} if token else {}


def _login(base, pw, ruta="/api/login"):
    return call(base, ruta, "POST", {"password": pw})


def test_usuario_de_confianza_manda_ordenes_pero_no_configura(app):
    base, cfg, mon = app
    dev0 = cfg.devices[0]["id"]
    cfg.set_admin_password("clave-admin-1")
    cfg.set_user_password("clave-usuario-1")
    st, salud = call(base, "/api/health")
    assert salud["admin_required"] is True and salud["user_required"] is True
    # sin sesión: solo lectura
    st, state = call(base, "/api/state")
    assert state["sesion"] == {"nivel": "none", "admin_required": True, "user_required": True,
                               "puede_mandar": False, "ttl": {"admin": 12 * 3600, "user": 7 * 24 * 3600}, "user_sessions": 0}
    assert call(base, "/api/devices/%s/command" % dev0, "POST", {"action": "switch", "value": True})[0] == 403
    # con la contraseña de usuario
    st, r = _login(base, "clave-usuario-1")
    assert st == 200 and r["nivel"] == "user" and r["active"] is False and r["token"]
    tok = r["token"]
    st, state = call(base, "/api/state", headers=_hdr(tok))
    assert state["sesion"]["nivel"] == "user" and state["sesion"]["puede_mandar"] is True
    assert state["admin"]["active"] is False
    assert "dev_id" not in state["devices"][0]                      # sigue sin ver la configuración
    # puede encender y apagar, por las dos rutas
    assert call(base, "/api/devices/%s/command" % dev0, "POST", {"action": "switch", "value": False}, headers=_hdr(tok))[0] == 200
    assert call(base, "/api/plugs/%s/power" % dev0, "POST", {"on": True}, headers=_hdr(tok))[0] == 200
    # no puede tocar nada más
    for method, path, body in (("POST", "/api/devices", {"name": "X", "dev_id": "bf99999999", "local_key": "0123456789abcdef"}),
                               ("PUT", "/api/devices/%s" % dev0, {"name": "Otro"}),
                               ("DELETE", "/api/devices/%s" % dev0, None),
                               ("PUT", "/api/options", {"poll_interval": 9}),
                               ("PUT", "/api/cloud", {"region": "eu"}),
                               ("PUT", "/api/password", {"password": "loquesea12"}),
                               ("PUT", "/api/admin/password", {"password": "otra-clave-9"}),
                               ("PUT", "/api/user-password", {"password": "otra-clave-9"}),
                               ("POST", "/api/config/export", None),
                               ("POST", "/api/config/import", {"config": {}}),
                               ("POST", "/api/discover", {})):
        st, r = call(base, path, method, body, headers=_hdr(tok))
        assert st == 403 and r.get("nivel_necesario") == "admin", (method, path, st)
    assert len(cfg.devices) == 2 and cfg.options["poll_interval"] == 5 and cfg.options["admin_password_hash"]


def test_el_administrador_sigue_pudiendo_todo(app):
    base, cfg, mon = app
    cfg.set_admin_password("clave-admin-1")
    cfg.set_user_password("clave-usuario-1")
    st, r = _login(base, "clave-admin-1")
    assert st == 200 and r["nivel"] == "admin" and r["active"] is True
    tok = r["token"]
    st, state = call(base, "/api/state", headers=_hdr(tok))
    assert state["sesion"]["nivel"] == "admin" and state["devices"][0]["dev_id"]
    assert call(base, "/api/options", "PUT", {"poll_interval": 8}, headers=_hdr(tok))[0] == 200
    assert call(base, "/api/devices/%s/command" % cfg.devices[0]["id"], "POST", {"action": "switch", "value": True}, headers=_hdr(tok))[0] == 200
    assert _login(base, "pues-no-acierto")[0] == 403


def test_poner_y_quitar_la_contrasena_de_usuario(app):
    base, cfg, mon = app
    cfg.set_admin_password("clave-admin-1")
    tok = _login(base, "clave-admin-1")[1]["token"]
    assert call(base, "/api/state", headers=_hdr(tok))[1]["sesion"]["user_required"] is False
    st, r = call(base, "/api/user-password", "PUT", {"password": "corta"}, headers=_hdr(tok))
    assert st == 400 and not cfg.options["user_password_hash"]
    st, r = call(base, "/api/user-password", "PUT", {"password": "clave-usuario-1"}, headers=_hdr(tok))
    assert st == 200 and r["user_required"] is True and r["token"]
    assert call(base, "/api/options", "PUT", {"poll_interval": 7}, headers=_hdr(tok))[0] == 403      # la sesión vieja ya no vale
    tok = r["token"]                                                                                 # la nueva sí
    assert call(base, "/api/options", "PUT", {"poll_interval": 7}, headers=_hdr(tok))[0] == 200
    assert _login(base, "clave-usuario-1")[1]["nivel"] == "user"
    st, r = call(base, "/api/user-password", "PUT", {"quitar": True}, headers=_hdr(tok))
    assert st == 200 and r["user_required"] is False
    assert _login(base, "clave-usuario-1")[0] == 403


def test_cambiar_la_contrasena_de_administrador_cierra_las_sesiones_de_usuario(app):
    base, cfg, mon = app
    cfg.set_admin_password("clave-admin-1")
    cfg.set_user_password("clave-usuario-1")
    utok = _login(base, "clave-usuario-1")[1]["token"]
    atok = _login(base, "clave-admin-1")[1]["token"]
    assert call(base, "/api/admin/password", "PUT", {"password": "clave-admin-2"}, headers=_hdr(atok))[0] == 200
    assert call(base, "/api/devices/%s/command" % cfg.devices[0]["id"], "POST", {"action": "switch", "value": True}, headers=_hdr(utok))[0] == 403


def test_cerrar_sesion_y_compatibilidad_con_la_ruta_de_administrador(app):
    base, cfg, mon = app
    cfg.set_admin_password("clave-admin-1")
    cfg.set_user_password("clave-usuario-1")
    # la ruta antigua solo acepta la de administrador
    assert _login(base, "clave-usuario-1", "/api/admin/login")[0] == 403
    st, r = _login(base, "clave-admin-1", "/api/admin/login")
    assert st == 200 and r["active"] is True and r["nivel"] == "admin"
    tok = r["token"]
    assert call(base, "/api/admin/logout", "POST", {}, headers=_hdr(tok))[0] == 200
    assert call(base, "/api/options", "PUT", {"poll_interval": 9}, headers=_hdr(tok))[0] == 403
    utok = _login(base, "clave-usuario-1")[1]["token"]
    assert call(base, "/api/logout", "POST", {}, headers=_hdr(utok))[0] == 200
    assert call(base, "/api/devices/%s/command" % cfg.devices[0]["id"], "POST", {"action": "switch", "value": True}, headers=_hdr(utok))[0] == 403


def test_sin_contrasenas_el_servicio_sigue_abierto(app):
    base, cfg, mon = app
    st, state = call(base, "/api/state")
    assert state["sesion"] == {"nivel": "admin", "admin_required": False, "user_required": False,
                               "puede_mandar": True, "ttl": {"admin": 12 * 3600, "user": 7 * 24 * 3600}, "user_sessions": 0}
    assert call(base, "/api/options", "PUT", {"poll_interval": 9})[0] == 200
    assert _login(base, "")[1]["nivel"] == "admin"


def test_solo_contrasena_de_usuario_sin_administrador(app):
    base, cfg, mon = app
    cfg.set_user_password("clave-usuario-1")
    assert call(base, "/api/options", "PUT", {"poll_interval": 9})[0] == 403        # ya no está abierto
    tok = _login(base, "clave-usuario-1")[1]["token"]
    assert call(base, "/api/devices/%s/command" % cfg.devices[0]["id"], "POST", {"action": "switch", "value": True}, headers=_hdr(tok))[0] == 200
    assert call(base, "/api/options", "PUT", {"poll_interval": 9}, headers=_hdr(tok))[0] == 403


def test_cli_user_password(tmp_path, monkeypatch, capsys):
    from telehome.cli import main
    d = tmp_path / "d"
    monkeypatch.setenv("TH_USER", "clave-usuario-1")
    assert main(["--data-dir", str(d), "user-password", "--password-env", "TH_USER"]) == 0
    assert "AVISO" in capsys.readouterr().err                      # sin contraseña de administrador, avisa
    c = Config(d / "config.json")
    assert c.options["user_password_hash"] and c.public_options()["user_set"] is True
    assert "user_password_hash" not in c.public_options() and "user_password_hash" not in json.dumps(c.export_config())
    monkeypatch.setenv("TH_USER", "corta")
    assert main(["--data-dir", str(d), "user-password", "--password-env", "TH_USER"]) == 2
    assert main(["--data-dir", str(d), "user-password", "--quitar"]) == 0
    assert not Config(d / "config.json").options["user_password_hash"]


def test_api_de_programaciones(app):
    base, cfg, mon = app
    dev0 = cfg.devices[0]["id"]
    prog = {"name": "Mañanas", "device": dev0, "action": "switch", "value": True,
            "when": {"kind": "clock", "time": "07:00"}, "days": [1, 2, 3, 4, 5]}
    st, s = call(base, "/api/schedules", "POST", prog)
    assert st == 201 and s["id"] == "mananas" and s["enabled"] is True
    st, state = call(base, "/api/state")
    assert [x["id"] for x in state["schedules"]] == ["mananas"] and state["max_schedules"] == 32
    st, s2 = call(base, "/api/schedules/mananas", "PUT", {"enabled": False})
    assert st == 200 and s2["enabled"] is False and s2["when"]["time"] == "07:00"
    assert call(base, "/api/schedules", "POST", {**prog, "device": "no-existe"})[0] == 400
    assert call(base, "/api/schedules", "POST", {**prog, "when": {"kind": "clock", "time": "99:99"}})[0] == 400
    assert call(base, "/api/schedules/no-hay", "PUT", {"enabled": True})[0] == 404
    st, r = call(base, "/api/schedules/mananas/run", "POST", {})
    assert st == 200 and r["resultado"] == "ejecutada"
    assert call(base, "/api/schedules/mananas", "DELETE")[0] == 200
    assert call(base, "/api/state")[1]["schedules"] == []


def test_api_lugar_y_sol(app):
    base, cfg, mon = app
    st, r = call(base, "/api/sun")
    assert st == 200 and r["sunrise"] < r["sunset"] and round(r["lat"], 2) == 38.27
    st, o = call(base, "/api/place", "PUT", {"lat": 40.4, "lon": -3.7})
    assert st == 200 and o["lat"] == 40.4
    assert call(base, "/api/place", "PUT", {"lat": 999, "lon": 0})[0] == 400
    assert call(base, "/api/sun")[1]["lat"] == 40.4


def test_las_programaciones_son_cosa_de_administradores(app):
    base, cfg, mon = app
    dev0 = cfg.devices[0]["id"]
    cfg.add_schedule({"name": "Mañanas", "device": dev0, "action": "switch", "value": True,
                      "when": {"kind": "clock", "time": "07:00"}})
    cfg.set_admin_password("clave-admin-1")
    cfg.set_user_password("clave-usuario-1")
    # el usuario de confianza no las ve ni las toca
    utok = call(base, "/api/login", "POST", {"password": "clave-usuario-1"})[1]["token"]
    assert call(base, "/api/state", headers={"X-TeleHome-Admin": utok})[1]["schedules"] == []
    for metodo, ruta, cuerpo in (("POST", "/api/schedules", {"name": "x"}),
                                 ("PUT", "/api/schedules/mananas", {"enabled": False}),
                                 ("DELETE", "/api/schedules/mananas", None),
                                 ("POST", "/api/schedules/mananas/run", {}),
                                 ("PUT", "/api/place", {"lat": 1, "lon": 1})):
        assert call(base, ruta, metodo, cuerpo, headers={"X-TeleHome-Admin": utok})[0] == 403, ruta
    # el administrador sí
    atok = call(base, "/api/login", "POST", {"password": "clave-admin-1"})[1]["token"]
    assert len(call(base, "/api/state", headers={"X-TeleHome-Admin": atok})[1]["schedules"]) == 1
    assert call(base, "/api/schedules/mananas", "PUT", {"enabled": False}, headers={"X-TeleHome-Admin": atok})[0] == 200
    # api/sun es de lectura: lo ve cualquiera
    assert call(base, "/api/sun")[0] == 200


def test_la_sesion_de_usuario_dura_siete_dias_y_la_de_administrador_doce_horas(app):
    base, cfg, mon = app
    cfg.set_admin_password("clave-admin-1")
    cfg.set_user_password("clave-usuario-1")
    assert _login(base, "clave-usuario-1")[1]["expires_in"] == 7 * 24 * 3600
    atok = _login(base, "clave-admin-1")[1]
    assert atok["expires_in"] == 12 * 3600
    assert call(base, "/api/state", headers=_hdr(atok["token"]))[1]["sesion"]["ttl"] == {"admin": 12 * 3600, "user": 7 * 24 * 3600}


def test_el_administrador_cierra_las_sesiones_de_usuario(app):
    base, cfg, mon = app
    dev0 = cfg.devices[0]["id"]
    cfg.set_admin_password("clave-admin-1")
    cfg.set_user_password("clave-usuario-1")
    utok = _login(base, "clave-usuario-1")[1]["token"]
    otro = _login(base, "clave-usuario-1")[1]["token"]
    atok = _login(base, "clave-admin-1")[1]["token"]
    orden = ("/api/devices/%s/command" % dev0, "POST", {"action": "switch", "value": True})
    assert call(base, *orden, headers=_hdr(utok))[0] == 200
    assert call(base, "/api/state", headers=_hdr(atok))[1]["sesion"]["user_sessions"] == 2
    # un usuario no puede revocar
    assert call(base, "/api/sessions/revoke-users", "POST", {}, headers=_hdr(utok))[0] == 403
    st, r = call(base, "/api/sessions/revoke-users", "POST", {}, headers=_hdr(atok))
    assert st == 200 and r["cerradas"] == 2
    # las dos sesiones de usuario quedan fuera; la del administrador sigue valiendo
    assert call(base, *orden, headers=_hdr(utok))[0] == 403
    assert call(base, *orden, headers=_hdr(otro))[0] == 403
    assert call(base, "/api/options", "PUT", {"poll_interval": 6}, headers=_hdr(atok))[0] == 200
    assert call(base, "/api/state", headers=_hdr(atok))[1]["sesion"]["user_sessions"] == 0
    # la contraseña sigue siendo válida: puede volver a entrar
    nuevo = _login(base, "clave-usuario-1")[1]["token"]
    assert call(base, *orden, headers=_hdr(nuevo))[0] == 200


def test_quien_no_ha_entrado_no_puede_cerrar_sesiones_de_usuario(app):
    base, cfg, mon = app
    cfg.set_admin_password("clave-admin-1")
    cfg.set_user_password("clave-usuario-1")
    assert call(base, "/api/sessions/revoke-users", "POST", {})[0] == 403

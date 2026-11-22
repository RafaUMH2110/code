import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from telehome_enchufes.config import Config
from telehome_enchufes.monitor import Monitor
from telehome_enchufes.server import AppContext, make_server
from telehome_enchufes.store import Store


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
    assert st == 200 and b"TeleHome Enchufes" in html
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
    assert st == 200 and h["api"] == "telehome" and h["types"] == ["enchufe"]
    st, state = call(base, "/api/state")
    assert state["api"] == "telehome" and state["types"] == ["enchufe"]
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
                   {"name": "Lámpara", "type": "luz", "dev_id": "bf8888888888", "local_key": "0123456789abcdef"})
    assert st == 400 and "no admitido" in err["error"]


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
    from telehome_enchufes.monitor import local_midnight
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
    assert st == 200 and exp["format"] == "telehome-config" and len(exp["devices"]) == 2
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
    from telehome_enchufes.cli import main
    d1, d2 = tmp_path / "a", tmp_path / "b"
    c1 = Config(d1 / "config.json")
    c1.set_cloud({"region": "eu", "api_key": "abcdefghij12", "api_secret": "secretsecret1234"})
    c1.set_password("clave-del-servicio")
    c1.add_device({"name": "Uno", "dev_id": "bf00000001", "local_key": "0123456789abcdef"})
    fich = tmp_path / "cfg.json"
    assert main(["--data-dir", str(d1), "export-config", "-o", str(fich)]) == 0
    assert oct(fich.stat().st_mode & 0o777) == "0o600" and "pbkdf2" not in fich.read_text()
    assert main(["--data-dir", str(d2), "import-config", str(fich)]) == 0
    c2 = Config(d2 / "config.json")
    assert c2.options["cloud_api_secret"] == "secretsecret1234" and c2.devices[0]["name"] == "Uno" and not c2.options["password_hash"]
    (tmp_path / "mal.json").write_text('{"format": "otro"}')
    assert main(["--data-dir", str(d2), "import-config", str(tmp_path / "mal.json")]) == 2

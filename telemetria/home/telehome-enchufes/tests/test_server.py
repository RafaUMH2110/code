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

import base64
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from telehome.cloud import CloudError, CloudHub
from telehome.config import Config, ConfigError, normalize_device
from telehome.devices import CloudPlug, PlugError
from telehome.monitor import Monitor
from telehome.server import AppContext, make_server
from telehome.store import Store

IDS = ["bfaaaaaaaa", "bfbbbbbbbb"]


class FakeCloud:
    """Imita tinytuya.Cloud: estado por lotes, órdenes y lista de dispositivos."""

    def __init__(self, v1_ok=True, online=None, cmd_ok=("iot03", "v1", "shadow")):
        self.token = "t"
        self.v1_ok = v1_ok
        self.cmd_ok = cmd_ok
        self.online = online or {i: True for i in IDS}
        self.state = {i: {"switch_1": True, "cur_power": 1234, "cur_voltage": 2301, "cur_current": 543} for i in IDS}
        self.requests = []

    def cloudrequest(self, url, action=None, post=None, query=None):
        self.requests.append(url)
        for nombre, sufijo in (("iot03", "/commands"), ("v1", "/commands"), ("shadow", "/shadow/properties/issue")):
            pref = {"iot03": "/v1.0/iot-03/devices/", "v1": "/v1.0/devices/", "shadow": "/v2.0/cloud/thing/"}[nombre]
            if url.startswith(pref) and url.endswith(sufijo):
                assert action == "POST"
                if nombre not in self.cmd_ok:
                    return {"success": False, "code": 28841105, "msg": "No permissions. This project is not authorized to call this API."}
                dev = url[len(pref):-len(sufijo)]
                if nombre == "shadow":
                    self.state[dev].update(json.loads(post["properties"]))
                else:
                    c = post["commands"][0]
                    self.state[dev][c["code"]] = c["value"]
                return {"success": True, "result": True}
        ids = (query or {}).get("device_ids", "").split(",")
        if url == "/v1.0/devices":
            if not self.v1_ok:
                return {"success": False, "code": 1106, "msg": "permission deny"}
            return {"success": True, "result": {"devices": [
                {"id": i, "online": self.online[i], "status": [{"code": k, "value": v} for k, v in self.state[i].items()]}
                for i in ids if i in self.state]}}
        if url == "/v1.0/iot-03/devices/status":
            return {"success": True, "result": [
                {"id": i, "status": [{"code": k, "value": v} for k, v in self.state[i].items()]} for i in ids if i in self.state]}
        if url == "/v1.0/iot-03/devices":
            return {"success": True, "result": {"list": [{"id": i, "online": self.online[i]} for i in ids if i in self.state]}}
        return {"success": False, "msg": "?"}

    def getdevices(self):
        return [{"id": i, "name": "Enchufe %s" % i[-1], "key": "k" * 16, "category": "cz", "online": True} for i in IDS]


def make_hub(fake, opts=None):
    opts = opts or {"cloud_api_key": "abcdefgh12", "cloud_api_secret": "s" * 32, "cloud_region": "eu"}
    return CloudHub(lambda: opts, lambda: list(IDS), client_factory=lambda r, k, s: fake)


DEV = normalize_device({"name": "n", "mode": "nube", "dev_id": IDS[0]})


def test_cloud_device_needs_no_local_key():
    assert DEV["mode"] == "nube" and DEV["local_key"] == ""
    with pytest.raises(ConfigError):
        normalize_device({"name": "n", "mode": "local", "dev_id": IDS[0]})
    with pytest.raises(ConfigError):
        normalize_device({"name": "n", "mode": "nube", "dev_id": IDS[0], "code_power": "Cur Power!"})


def test_batch_read_is_shared_and_cached():
    fake = FakeCloud()
    hub = make_hub(fake)
    r = CloudPlug(DEV, hub, lambda: 60).read()
    assert r.online and r.on is True and r.power_w == 123.4 and r.voltage_v == 230.1 and r.current_a == 0.543
    other = normalize_device({"name": "m", "mode": "nube", "dev_id": IDS[1]})
    CloudPlug(other, hub, lambda: 60).read()
    CloudPlug(DEV, hub, lambda: 60).read()
    assert fake.requests == ["/v1.0/devices"]  # una sola llamada para ambos enchufes


def test_fallback_strategy_and_offline():
    fake = FakeCloud(v1_ok=False, online={IDS[0]: False, IDS[1]: True})
    hub = make_hub(fake)
    with pytest.raises(PlugError, match="desconectado"):
        CloudPlug(DEV, hub, lambda: 60).read()
    assert "/v1.0/iot-03/devices/status" in fake.requests and hub._strategy == "iot03"


def test_command_is_optimistic():
    fake = FakeCloud()
    hub = make_hub(fake)
    p = CloudPlug(DEV, hub, lambda: 60)
    p.read()
    p.set_power(False)
    n = len(fake.requests)
    r = p.read()
    assert r.on is False and len(fake.requests) == n and fake.state[IDS[0]]["switch_1"] is False
    assert fake.requests[-1] == "/v1.0/iot-03/devices/%s/commands" % IDS[0]


def test_command_falls_back_and_remembers_method():
    fake = FakeCloud(cmd_ok=("shadow",))
    hub = make_hub(fake)
    hub.command(IDS[0], "switch_1", False)
    assert fake.state[IDS[0]]["switch_1"] is False and hub._cmd_strategy == "shadow"
    fake.requests.clear()
    hub.command(IDS[0], "switch_1", True)
    assert fake.requests == ["/v2.0/cloud/thing/%s/shadow/properties/issue" % IDS[0]] and fake.state[IDS[0]]["switch_1"] is True


def test_command_permission_error_explains_fix():
    fake = FakeCloud(cmd_ok=())
    hub = make_hub(fake)
    with pytest.raises(CloudError) as e:
        hub.command(IDS[0], "switch_1", True)
    msg = str(e.value)
    assert "28841105" in msg and "IoT Core" in msg and "Controllable" in msg


def test_errors_are_cached_and_unconfigured():
    class Broken(FakeCloud):
        def cloudrequest(self, *a, **k):
            self.requests.append("x")
            return {"success": False, "msg": "sign invalid"}

        def getstatus(self, d):
            return {"success": False, "msg": "sign invalid"}

    fake = Broken()
    hub = make_hub(fake)
    with pytest.raises(PlugError, match="sign invalid"):
        CloudPlug(DEV, hub, lambda: 60).read()
    n = len(fake.requests)
    with pytest.raises(PlugError):
        CloudPlug(DEV, hub, lambda: 60).read()
    assert len(fake.requests) == n  # no reintenta hasta que caduca la caché
    empty = CloudHub(lambda: {}, lambda: [], client_factory=lambda *a: fake)
    with pytest.raises(CloudError, match="credenciales"):
        empty.status(IDS[0], 60)


# ---- servidor con nube (cliente falso) y contraseña -------------------------

@pytest.fixture()
def cloud_app(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.set_cloud({"region": "eu", "api_key": "abcdefgh12", "api_secret": "s" * 32})
    fake = FakeCloud()
    hub = CloudHub(lambda: cfg.options, cfg.cloud_ids, client_factory=lambda r, k, s: fake)
    store = Store(tmp_path / "t.db")
    mon = Monitor(cfg, store, simulate=False, hub=hub)
    srv = make_server(AppContext(cfg, store, mon, False, hub=hub), "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    mon.start()
    yield "http://127.0.0.1:%d" % srv.server_address[1], cfg, fake, tmp_path
    mon.stop()
    srv.shutdown()
    srv.server_close()


def call(base, path, method="GET", body=None, auth=None):
    h = {"X-TeleHome": "1"}
    if auth:
        h["Authorization"] = "Basic " + base64.b64encode(auth.encode()).decode()
    data = None if body is None else json.dumps(body).encode()
    if data:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_cloud_endpoints_import_and_read(cloud_app):
    base, cfg, fake, _ = cloud_app
    st, state = call(base, "/api/state")
    assert state["cloud"]["configured"] and "cloud_api_secret" not in state["options"] and state["options"]["cloud_secret_set"]
    st, lst = call(base, "/api/cloud/devices", "POST", {})
    assert st == 200 and len(lst["found"]) == 2 and all("key" not in d for d in lst["found"])
    st, rep = call(base, "/api/cloud/import", "POST", {"dev_ids": [IDS[0]]})
    assert st == 200 and rep["añadidos"] == ["Enchufe a"]
    assert cfg.devices[0]["mode"] == "nube" and cfg.devices[0]["local_key"] == "k" * 16
    time.sleep(0.5)
    d = call(base, "/api/state")[1]["devices"][0]
    assert d["mode"] == "nube" and d["reading"]["online"] and d["reading"]["power_w"] == 123.4
    pid = d["id"]
    st, r = call(base, "/api/plugs/%s/power" % pid, "POST", {"on": False})
    assert st == 200 and r["on"] is False
    assert call(base, "/api/options", "PUT", {"cloud_poll_interval": 30})[0] == 400
    assert call(base, "/api/cloud", "PUT", {"region": "marte"})[0] == 400


def test_password_and_live_reload_from_cli(cloud_app):
    base, cfg, fake, tmp = cloud_app
    other = Config(tmp / "config.json")  # como haría la orden «password» en otro proceso
    time.sleep(0.01)
    other.set_password("secreto-largo")
    assert call(base, "/api/state")[0] == 401
    assert call(base, "/api/state", auth="x:malo-malo")[0] == 401
    assert call(base, "/api/state", auth="rafa:secreto-largo")[0] == 200
    with pytest.raises(ConfigError):
        cfg.set_password("corta")


def test_reto_de_contrasena_solo_en_navegacion(cloud_app):
    """El diálogo nativo solo se provoca al navegar; las apps (fetch) reciben 401 a secas."""
    base, cfg, fake, tmp = cloud_app
    cfg.set_password("secreto-largo")

    def reto(destino):
        h = {"X-TeleHome": "1"}
        if destino:
            h["Sec-Fetch-Dest"] = destino
        try:
            urllib.request.urlopen(urllib.request.Request(base + "/api/state", headers=h), timeout=5)
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("WWW-Authenticate")
        raise AssertionError("debería pedir contraseña")

    assert reto(None)[0] == 401 and reto(None)[1].startswith("Basic")        # sin cabecera: como siempre
    assert reto("document")[1].startswith("Basic")                           # navegación: diálogo
    assert reto("empty") == (401, None)                                      # fetch de una app: sin diálogo


def test_virtual_device_error_says_so():
    fake = FakeCloud(cmd_ok=())
    fake.state["vdevo123"] = {"switch_1": False}
    hub = make_hub(fake)
    with pytest.raises(CloudError) as e:
        hub.command("vdevo123", "switch_1", True)
    assert "virtual" in str(e.value) and "Controllable" not in str(e.value)


def test_hub_avisa_de_cada_llamada(tmp_path):
    fake = FakeCloud()
    hub = CloudHub(lambda: {"cloud_api_key": "k", "cloud_api_secret": "s", "cloud_region": "eu"},
                   lambda: list(IDS), client_factory=lambda r, k, s: fake)
    store = Store(tmp_path / "c.db")
    hub.on_calls = store.add_api_calls
    hub.status(IDS[0], 0)
    hoy = store.api_calls_by_day(1)[-1]["n"]
    assert hoy == hub.calls and hoy >= 2  # token + lectura por lotes
    hub.on_calls = lambda n: 1 / 0  # un fallo al guardar no rompe la lectura
    hub.status(IDS[0], 0)

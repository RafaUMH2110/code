"""Luces: conversión de brillo, temperatura y color; órdenes por nube y por red local; tipo y migración."""

import json
import threading
import time

import pytest

from telehome import luces
from telehome.cloud import CloudHub
from telehome.config import Config, ConfigError, normalize_device
from telehome.devices import CloudPlug, SimLight, TipoIncorrecto, TuyaPlug, parse_cloud_status, parse_dps
from telehome.monitor import Monitor
from telehome.server import AppContext, make_server
from telehome.store import Store
from test_cloud import FakeCloud, call

LID = "bflight0001"
PID = "bfplug00001"
ESTADO_LUZ = {"switch_led": True, "work_mode": "white", "bright_value_v2": 500, "temp_value_v2": 250,
              "colour_data_v2": json.dumps({"h": 120, "s": 800, "v": 600}), "countdown_1": 0}


def luz(**extra):
    return normalize_device({"name": "Salón", "mode": "nube", "dev_id": LID, "type": "luz", **extra})


# ---- conversiones ------------------------------------------------------------
def test_color_roundtrip_and_validation():
    assert luces.hsv_to_hex(0, 100, 100) == "#ff0000" and luces.hsv_to_hex(120, 100, 100) == "#00ff00"
    assert luces.hex_to_hsv("#0000ff") == (240, 100, 100)
    assert luces.parse_color_arg({"h": 360, "s": 50, "v": 0}) == (0, 50, 1)      # 360 = 0; valor mínimo 1 %
    assert luces.parse_color_arg("#ffffff") == (0, 0, 100)
    for malo in ("rojo", {"h": 400, "s": 1, "v": 1}, {"h": 1}, 5, {"h": 1, "s": 101, "v": 1}):
        with pytest.raises(ValueError):
            luces.parse_color_arg(malo)


def test_read_cloud_white_and_colour_modes():
    r = parse_cloud_status(ESTADO_LUZ, luz())
    assert r.on is True and r.level == 50.0 and r.extra["temp"] == 25.0 and r.extra["mode"] == "white"
    assert r.extra["color"] == {"h": 120, "s": 80, "v": 60} and r.extra["hex"] == luces.hsv_to_hex(120, 80, 60)
    assert r.extra["caps"] == {"mode": True, "level": True, "temp": True, "color": True}
    # en modo color el brillo que se enseña es el «valor» del color
    r = parse_cloud_status({**ESTADO_LUZ, "work_mode": "colour"}, luz())
    assert r.level == 60.0 and r.extra["level"] == 60.0
    # apagada: 0 % para la gráfica, pero el estado conserva el último brillo
    r = parse_cloud_status({**ESTADO_LUZ, "switch_led": False}, luz())
    assert r.on is False and r.level == 0.0 and r.extra["level"] == 50.0


def test_white_only_bulb_has_no_colour_controls():
    r = parse_cloud_status({"switch_led": True, "bright_value_v2": 1000, "temp_value_v2": 0}, luz())
    assert r.extra["caps"] == {"mode": False, "level": True, "temp": True, "color": False} and r.extra["color"] is None


def test_plan_orders():
    cur = luces.read_cloud(ESTADO_LUZ, luz())
    assert luces.plan("switch", True, cur) == [("switch", True)]
    assert luces.plan("level", 0, cur) == [("switch", False)]                       # 0 % = apagar
    assert luces.plan("level", 30, cur) == [("switch", True), ("level", 30)]
    colour = luces.read_cloud({**ESTADO_LUZ, "work_mode": "colour"}, luz())
    assert luces.plan("level", 30, colour) == [("switch", True), ("color", (120, 80, 30))]   # en color, brilla el «valor»
    assert luces.plan("temp", 80, cur) == [("switch", True), ("mode", "white"), ("temp", 80)]
    assert luces.plan("color", "#ff0000", cur) == [("switch", True), ("mode", "colour"), ("color", (0, 100, 100))]
    assert luces.plan("mode", "white", cur) == [("mode", "white")]
    for accion, valor in (("switch", 1), ("level", 101), ("level", True), ("temp", "x"), ("mode", "disco"), ("color", None), ("x", 1)):
        with pytest.raises(ValueError):
            luces.plan(accion, valor, cur)


def test_cloud_and_local_commands():
    d = luz()
    pasos = luces.plan("color", {"h": 200, "s": 50, "v": 40}, {})
    assert luces.cloud_commands(d, pasos) == [
        ("switch_led", True), ("work_mode", "colour"), ("colour_data_v2", '{"h":200,"s":500,"v":400}')]
    assert luces.local_dps(d, pasos) == {"20": True, "21": "colour", "24": "00c801f40190"}
    # brillo y temperatura crudos con su escala; el 1 % no baja de 10 (mínimo de la API v2)
    assert luces.cloud_commands(d, luces.plan("level", 1, {})) == [("switch_led", True), ("bright_value_v2", 10)]
    assert luces.local_dps(d, luces.plan("temp", 100, {})) == {"20": True, "21": "white", "23": 1000}
    # bombilla de la API antigua: colour_data de 14 dígitos
    assert luces.local_color(0, 100, 100, 14) == "ff0000" + "0000" + "ff" + "ff"
    assert luces.parse_local_color("00c801f40190") == {"h": 200, "s": 50, "v": 40}
    assert luces.parse_local_color("ff0000" + "0000ffff") == {"h": 0, "s": 100, "v": 100}
    assert luces.parse_local_color("xyz") is None and luces.parse_local_color(5) is None


def test_v1_bulb_uses_old_codes_without_touching_config():
    st = {"switch_led": True, "work_mode": "white", "bright_value": 255, "temp_value": 0,
          "colour_data": json.dumps({"h": 0, "s": 255, "v": 255})}
    d = luz()
    eff = luces.adaptar(d, st)
    assert eff["code_level"] == "bright_value" and eff["scale_level"] == 2.55 and d["code_level"] == "bright_value_v2"
    r = parse_cloud_status(st, eff)
    assert r.level == 100.0 and r.extra["color"] == {"h": 0, "s": 100, "v": 100}
    assert luces.cloud_commands(eff, luces.plan("level", 50, {}))[1] == ("bright_value", 127)


# ---- configuración ------------------------------------------------------------
def test_normalize_light_and_change_of_type():
    d = luz()
    assert d["type"] == "luz" and d["code_switch"] == "switch_led" and "code_power" not in d and d["dp_level"] == 22
    plug = normalize_device({"name": "P", "mode": "nube", "dev_id": PID})
    assert plug["type"] == "enchufe" and plug["code_switch"] == "switch_1" and "code_level" not in plug
    cambiado = normalize_device({"type": "luz"}, plug)
    assert cambiado["type"] == "luz" and cambiado["code_switch"] == "switch_led" and cambiado["name"] == "P"
    with pytest.raises(ConfigError, match="no admitido"):
        normalize_device({"type": "persiana"}, plug)
    with pytest.raises(ConfigError):
        luz(code_temp="Temp Value!")


def test_import_picks_type_from_tuya_category(tmp_path):
    cfg = Config(tmp_path / "c.json")
    rep = cfg.import_devices([
        {"dev_id": LID, "name": "Bombilla", "key": "k" * 16, "category": "dj"},
        {"dev_id": PID, "name": "Enchufe", "key": "k" * 16, "category": "cz"},
        {"dev_id": "bftira00001", "name": "Tira", "key": "k" * 16, "category": "dd"}], "nube")
    assert rep["omitidos"] == [] and [d["type"] for d in cfg.devices] == ["luz", "enchufe", "luz"]
    cfg2 = Config(tmp_path / "c2.json")
    cfg2.import_devices([{"dev_id": LID, "name": "B", "key": "k" * 16, "category": "dj"}], "nube", "enchufe")
    assert cfg2.devices[0]["type"] == "enchufe"             # el tipo indicado manda sobre la categoría


def test_schedule_values_for_light_actions(tmp_path):
    cfg = Config(tmp_path / "c.json")
    cfg.import_devices([{"dev_id": LID, "name": "B", "key": "k" * 16, "category": "dj"}], "nube")
    base = {"name": "Luz", "device": cfg.devices[0]["id"], "when": {"kind": "clock", "time": "21:00"}, "days": [1]}
    assert cfg.add_schedule({**base, "action": "color", "value": {"h": 0, "s": 100, "v": 100}})["value"] == "#ff0000"
    assert cfg.add_schedule({**base, "name": "t", "action": "temp", "value": 20})["value"] == 20
    assert cfg.add_schedule({**base, "name": "m", "action": "mode", "value": "white"})["value"] == "white"
    for accion, valor in (("color", "rojo"), ("temp", 101), ("mode", "disco")):
        with pytest.raises(ConfigError):
            cfg.add_schedule({**base, "name": "x", "action": accion, "value": valor})


# ---- nube: lectura, órdenes y migración ------------------------------------------
class NubeLuz(FakeCloud):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.state[LID] = dict(ESTADO_LUZ)
        self.online[LID] = True

    def getdevices(self):
        return [{"id": LID, "name": "Bombilla", "key": "k" * 16, "category": "dj", "online": True},
                {"id": PID, "name": "Enchufe", "key": "k" * 16, "category": "cz", "online": True}]


def hub_luz(fake):
    opts = {"cloud_api_key": "abcdefgh12", "cloud_api_secret": "s" * 32, "cloud_region": "eu"}
    return CloudHub(lambda: opts, lambda: [LID], client_factory=lambda r, k, s: fake)


def test_cloud_light_command_is_one_call_and_optimistic():
    fake = NubeLuz()
    hub = hub_luz(fake)
    p = CloudPlug(luz(), hub, lambda: 60)
    p.read()
    antes = len(fake.requests)
    p.apply("color", "#00ff00")
    assert len(fake.requests) == antes + 1                                   # tres códigos, una sola llamada
    r = p.read()                                                             # sin otra llamada: caché optimista
    assert len(fake.requests) == antes + 1
    assert r.on is True and r.extra["mode"] == "colour" and r.extra["color"] == {"h": 120, "s": 100, "v": 100}
    assert json.loads(fake.state[LID]["colour_data_v2"]) == {"h": 120, "s": 1000, "v": 1000}
    p.apply("temp", 100)
    assert fake.state[LID]["work_mode"] == "white" and fake.state[LID]["temp_value_v2"] == 1000


def test_enchufe_that_answers_as_light_is_flagged():
    fake = NubeLuz()
    p = CloudPlug(normalize_device({"name": "n", "mode": "nube", "dev_id": LID}), hub_luz(fake), lambda: 60)
    with pytest.raises(TipoIncorrecto) as e:
        p.read()
    assert e.value.tipo == "luz"


def test_local_light_reads_and_writes_dps():
    d = normalize_device({"name": "L", "mode": "local", "dev_id": LID, "type": "luz", "local_key": "k" * 16, "ip": "10.0.0.5"})
    dps = {"20": True, "21": "colour", "22": 400, "23": 0, "24": "007803e803e8"}
    r = parse_dps(dps, d)
    assert r.on is True and r.level == 100.0 and r.extra["color"] == {"h": 120, "s": 100, "v": 100}

    enviados = []

    class Falso:
        def status(self):
            return {"dps": dps}

        def set_multiple_values(self, datos):
            enviados.append(datos)
            return {"dps": datos}

    p = TuyaPlug(d)
    p._client = lambda: Falso()
    p.apply("color", {"h": 240, "s": 100, "v": 50})
    assert enviados[-1] == {"20": True, "21": "colour", "24": "00f003e801f4"}
    p.apply("level", 0)
    assert enviados[-1] == {"20": False}


def test_simulated_light_follows_commands():
    s = SimLight(luz())
    s.apply("color", "#ff0000")
    r = s.read()
    assert r.extra["mode"] == "colour" and r.extra["hex"] == "#ff0000" and r.level == 100.0
    s.apply("level", 0)
    assert s.read().on is False and s.read().level == 0.0
    s.apply("temp", 10)
    r = s.read()
    assert r.on is True and r.extra["mode"] == "white" and r.extra["temp"] == 10.0


# ---- servidor completo con nube falsa ----------------------------------------------
@pytest.fixture()
def app_luz(tmp_path):
    cfg = Config(tmp_path / "config.json")
    cfg.set_cloud({"region": "eu", "api_key": "abcdefgh12", "api_secret": "s" * 32})
    fake = NubeLuz()
    hub = CloudHub(lambda: cfg.options, cfg.cloud_ids, client_factory=lambda r, k, s: fake)
    store = Store(tmp_path / "t.db")
    mon = Monitor(cfg, store, simulate=False, hub=hub)
    srv = make_server(AppContext(cfg, store, mon, False, hub=hub), "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    mon.start()
    yield "http://127.0.0.1:%d" % srv.server_address[1], cfg, fake, store
    mon.stop()
    srv.shutdown()
    srv.server_close()


def test_server_imports_light_reads_and_commands(app_luz):
    base, cfg, fake, store = app_luz
    st, rep = call(base, "/api/cloud/import", "POST", {"dev_ids": [LID, PID]})
    assert st == 200 and len(rep["añadidos"]) == 2
    assert [d["type"] for d in cfg.devices] == ["luz", "enchufe"]
    time.sleep(0.6)
    st, state = call(base, "/api/state")
    lamp = next(d for d in state["devices"] if d["type"] == "luz")
    assert lamp["reading"]["state"]["br"] == 50.0 and lamp["reading"]["values"] == {"br": 50.0}
    assert lamp["caps"] == {"mode": True, "level": True, "temp": True, "color": True} and "power_w" not in lamp["reading"]
    st, r = call(base, "/api/devices/%s/command" % lamp["id"], "POST", {"action": "color", "value": "#ff0000"})
    assert st == 200 and r["state"]["mode"] == "colour" and r["state"]["hex"] == "#ff0000" and r["state"]["on"] is True
    st, r = call(base, "/api/devices/%s/command" % lamp["id"], "POST", {"action": "level", "value": 20})
    assert st == 200 and r["state"]["br"] == 20.0 and r["state"]["color"] == {"h": 0, "s": 100, "v": 20}
    assert call(base, "/api/devices/%s/command" % lamp["id"], "POST", {"action": "level", "value": 500})[0] == 400
    assert call(base, "/api/devices/%s/command" % lamp["id"], "POST", {"action": "color", "value": "rojo"})[0] == 400
    plug = next(d for d in state["devices"] if d["type"] == "enchufe")
    assert call(base, "/api/devices/%s/command" % plug["id"], "POST", {"action": "level", "value": 20})[0] == 400


def test_history_summary_and_csv_of_a_light(app_luz):
    base, cfg, fake, store = app_luz
    call(base, "/api/cloud/import", "POST", {"dev_ids": [LID]})
    time.sleep(0.6)
    lamp = cfg.devices[0]["id"]
    now = time.time()
    store.add(lamp, now - 20, True, True, None, None, None, level=80.0)
    store.add(lamp, now - 10, True, False, None, None, None, level=0.0)
    st, h = call(base, "/api/history?dev=%s&range=3600" % lamp)
    assert st == 200 and any(p["br"] is not None for p in h["series"][lamp])
    st, s = call(base, "/api/summary?range=3600")
    br = s["devices"][lamp]["m"]["br"]
    assert br["max"] == 80.0 and br["min"] == 0.0 and br["avg"] is not None
    import urllib.request
    req = urllib.request.Request(base + "/api/export.csv?dev=%s&range=3600" % lamp, headers={"X-TeleHome": "1"})
    csv_text = urllib.request.urlopen(req).read().decode()
    assert csv_text.splitlines()[0] == "fecha_hora_utc,epoch,dispositivo,en_linea,encendido,brillo_pct"


def test_enchufe_imported_as_such_becomes_light_by_itself(app_luz):
    """El caso real: una bombilla dada de alta como enchufe se reconfigura sola al ver que responde como luz."""
    base, cfg, fake, store = app_luz
    call(base, "/api/cloud/import", "POST", {"dev_ids": [LID], "type": "enchufe"})   # tipo forzado, como en la config antigua
    deadline = time.time() + 5
    while time.time() < deadline and cfg.devices[0]["type"] != "luz":
        time.sleep(0.1)
    assert cfg.devices[0]["type"] == "luz" and cfg.devices[0]["code_switch"] == "switch_led"
    time.sleep(0.8)
    lamp = call(base, "/api/state")[1]["devices"][0]
    assert lamp["reading"]["online"] and lamp["reading"]["state"]["br"] == 50.0


def test_old_database_gets_brightness_column(tmp_path):
    import sqlite3
    ruta = tmp_path / "viejo.db"
    c = sqlite3.connect(str(ruta))
    c.executescript("CREATE TABLE readings (ts INTEGER NOT NULL, plug TEXT NOT NULL, online INTEGER NOT NULL, on_ INTEGER,"
                    " power REAL, voltage REAL, current REAL); INSERT INTO readings VALUES (1000,'a',1,1,5.0,230.0,0.02);")
    c.commit()
    c.close()
    st = Store(ruta)
    st.add("a", 2000, True, True, 6.0, 230.0, 0.03, level=None)
    puntos = st.history("a", 0, 3000, 2000)
    assert [p["p"] for p in puntos] == [5.0, 6.0] and puntos[0]["br"] is None       # lo anterior se conserva intacto

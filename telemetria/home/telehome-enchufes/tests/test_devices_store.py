import time

from telehome_enchufes.config import normalize_device
from telehome_enchufes.devices import SimPlug, parse_dps, _error_text
from telehome_enchufes.store import Store

DEV = normalize_device({"name": "t", "dev_id": "bf00000001", "local_key": "0123456789abcdef"})


def test_parse_dps_scales():
    r = parse_dps({"1": True, "18": 543, "19": 1234, "20": 2301}, DEV, ts=1)
    assert r.on is True and r.power_w == 123.4 and r.voltage_v == 230.1 and r.current_a == 0.543 and r.online


def test_parse_dps_missing_values():
    r = parse_dps({"1": False}, DEV, ts=1)
    assert r.on is False and r.power_w is None and r.voltage_v is None


def test_error_text():
    assert "914" in _error_text({"Error": "x", "Err": "914"})


def test_sim_plug_toggle():
    p = SimPlug(DEV)
    assert p.read().power_w > 0
    p.set_power(False)
    r = p.read()
    assert r.on is False and r.power_w == 0.0


def test_store_energy_and_gaps(tmp_path):
    s = Store(tmp_path / "t.db")
    t0 = 1_700_000_000
    for k in range(7):                       # 100 W constantes durante 60 s (cada 10 s)
        s.add("a", t0 + 10 * k, True, True, 100.0, 230.0, 0.43)
    s.add("a", t0 + 10 * 6 + 3600, True, True, 100.0, 230.0, 0.43)   # hueco de 1 h: no se integra
    kwh = s.energy_kwh("a", t0, t0 + 10_000)
    assert abs(kwh - 100 * 60 / 3_600_000) < 1e-9


def test_store_history_summary_csv_prune(tmp_path):
    s = Store(tmp_path / "t.db")
    now = int(time.time())
    for k in range(100):
        s.add("a", now - 1000 + 10 * k, k % 10 != 0, True, 50.0 + k, 230.0, 0.2)
    h = s.history("a", now - 1000, now, max_points=50)
    assert 0 < len(h) <= 51
    sm = s.summary("a", now - 1000, now)
    assert sm["samples"] == 100 and 0.85 < sm["availability"] < 0.95
    rows = "".join(s.export_csv("a", now - 1000, now)).splitlines()
    assert rows[0].startswith("fecha_hora_utc") and len(rows) == 101
    s.add("a", now - 40 * 86400, True, True, 1, 1, 1)
    assert s.prune(30) == 1
    s.delete_plug("a")
    assert s.summary("a", 0, now + 1)["samples"] == 0

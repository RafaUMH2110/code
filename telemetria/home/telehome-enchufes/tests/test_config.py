import json
import os
import stat

import pytest

from telehome_enchufes.config import MAX_DEVICES, Config, ConfigError, public_device


def dev(i, **kw):
    d = {"name": "Enchufe %d" % i, "dev_id": "bf%08d" % i, "local_key": "0123456789abcdef"}
    d.update(kw)
    return d


def test_max_seven(tmp_path):
    cfg = Config(tmp_path / "c.json")
    for i in range(MAX_DEVICES):
        cfg.add_device(dev(i))
    with pytest.raises(ConfigError, match="Máximo 7"):
        cfg.add_device(dev(99))
    assert len(cfg.devices) == 7


def test_duplicate_dev_id_and_validation(tmp_path):
    cfg = Config(tmp_path / "c.json")
    cfg.add_device(dev(1))
    with pytest.raises(ConfigError):
        cfg.add_device(dev(2, dev_id="bf00000001"))
    for bad in ({"ip": "999.1.1.1"}, {"version": "2.0"}, {"dev_id": "x"}, {"name": " "},
                {"local_key": ""}, {"dp_power": 0}, {"scale_power": 0}):
        with pytest.raises(ConfigError):
            cfg.add_device(dev(3, **bad))


def test_slot_is_stable_after_delete(tmp_path):
    cfg = Config(tmp_path / "c.json")
    ids = [cfg.add_device(dev(i))["id"] for i in range(3)]
    slots = {d["id"]: d["slot"] for d in cfg.devices}
    cfg.delete_device(ids[0])
    assert {d["id"]: d["slot"] for d in cfg.devices} == {k: v for k, v in slots.items() if k != ids[0]}
    assert cfg.add_device(dev(10))["slot"] == slots[ids[0]]  # reutiliza el hueco libre


def test_persistence_permissions_and_key_not_public(tmp_path):
    p = tmp_path / "c.json"
    cfg = Config(p)
    d = cfg.add_device(dev(1))
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert "local_key" not in public_device(d) and public_device(d)["has_key"] is True
    again = Config(p)
    assert again.devices[0]["local_key"] == "0123456789abcdef"


def test_update_keeps_key_when_omitted(tmp_path):
    cfg = Config(tmp_path / "c.json")
    d = cfg.add_device(dev(1))
    new = cfg.update_device(d["id"], {"name": "Nevera", "ip": "192.168.1.20"})
    assert new["local_key"] == "0123456789abcdef" and new["ip"] == "192.168.1.20" and new["slot"] == d["slot"]


def test_import_tinytuya_devices_json(tmp_path):
    cfg = Config(tmp_path / "c.json")
    rows = [{"id": "bf%08d" % i, "key": "0123456789abcdef", "name": "Dev %d" % i, "ip": "192.168.1.%d" % (10 + i),
             "version": "3.4"} for i in range(9)]
    rep = cfg.import_devices(rows)
    assert len(rep["añadidos"]) == 7 and len(rep["omitidos"]) == 2
    assert cfg.devices[0]["version"] == "3.4"


def test_options_validation(tmp_path):
    cfg = Config(tmp_path / "c.json")
    assert cfg.set_options({"poll_interval": 5})["poll_interval"] == 5
    for bad in ({"poll_interval": 4}, {"poll_interval": "x"}, {"retention_days": 0}):
        with pytest.raises(ConfigError):
            cfg.set_options(bad)

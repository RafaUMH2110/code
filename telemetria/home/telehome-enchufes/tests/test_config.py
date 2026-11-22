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


def test_data_dir_por_defecto_conserva_carpeta_antigua(tmp_path, monkeypatch):
    from telehome_enchufes import config
    monkeypatch.delenv("TELEHOME_ENCHUFES_DIR", raising=False)
    monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: tmp_path))
    nuevo = config.data_dir()
    assert nuevo.name in ("telehome", ".telehome")
    viejo = nuevo.parent / nuevo.name.replace("telehome", "telehome-enchufes")
    viejo.mkdir(parents=True)
    assert config.data_dir() == viejo      # solo existe la antigua: se sigue usando
    nuevo.mkdir()
    assert config.data_dir() == nuevo      # si ya existe la nueva, gana


def _cfg_completa(tmp_path):
    cfg = Config(tmp_path / "origen.json")
    cfg.set_options({"poll_interval": 7, "cloud_poll_interval": 120, "retention_days": 45})
    cfg.set_cloud({"region": "us", "api_key": "abcdefghij12", "api_secret": "secretsecret1234"})
    cfg.set_password("clave-del-servicio")
    cfg.add_device(dev(1, room="Cocina"))
    cfg.add_device(dev(2, mode="nube", local_key=""))
    return cfg


def test_export_lleva_credenciales_y_claves_pero_no_la_contrasena(tmp_path):
    cfg = _cfg_completa(tmp_path)
    out = cfg.export_config()
    texto = json.dumps(out)
    assert out["format"] == "telehome-config" and out["version"] == 1
    assert out["options"]["cloud_api_key"] == "abcdefghij12" and out["options"]["cloud_api_secret"] == "secretsecret1234"
    assert out["options"]["cloud_region"] == "us" and out["options"]["poll_interval"] == 7
    assert "password_hash" not in texto and "pbkdf2" not in texto
    assert [d["local_key"] for d in out["devices"]] == ["0123456789abcdef", ""]
    assert out["devices"][0]["room"] == "Cocina"


def test_importar_reemplaza_y_no_toca_la_contrasena_del_servicio(tmp_path):
    origen = _cfg_completa(tmp_path)
    destino = Config(tmp_path / "destino.json")
    destino.set_password("otra-clave-distinta")
    hash_antes = destino.options["password_hash"]
    destino.add_device(dev(9))                                   # se sustituye por los del fichero
    rep = destino.import_config(json.loads(json.dumps(origen.export_config())))
    assert rep["total"] == 2 and len(rep["añadidos"]) == 2 and not rep["omitidos"]
    assert destino.options["password_hash"] == hash_antes
    assert destino.options["cloud_api_secret"] == "secretsecret1234" and destino.options["cloud_region"] == "us"
    assert destino.options["poll_interval"] == 7 and destino.options["retention_days"] == 45
    assert {d["dev_id"] for d in destino.devices} == {"bf00000001", "bf00000002"}
    assert Config(tmp_path / "destino.json").devices[0]["local_key"] == "0123456789abcdef"   # persistido


def test_importar_conserva_id_y_ajustes_de_los_que_ya_existian(tmp_path):
    origen = _cfg_completa(tmp_path)
    destino = Config(tmp_path / "destino.json")
    existente = destino.add_device(dev(1, name="Mi nevera"))
    rep = destino.import_config(origen.export_config(), replace=True)
    assert "Enchufe 1" in rep["actualizados"] and "Enchufe 2" in rep["añadidos"]
    assert destino.get(existente["id"])["dev_id"] == "bf00000001"           # mismo id: conserva su historial


def test_importar_anadir_no_duplica_ni_borra(tmp_path):
    origen = _cfg_completa(tmp_path)
    destino = Config(tmp_path / "destino.json")
    destino.add_device(dev(1))
    destino.add_device(dev(7))
    rep = destino.import_config(origen.export_config(), replace=False)
    assert rep["añadidos"] == ["Enchufe 2"] and rep["omitidos"][0]["motivo"].startswith("Ese Device ID")
    assert {d["dev_id"] for d in destino.devices} == {"bf00000001", "bf00000002", "bf00000007"}


def test_importar_credenciales_vacias_no_borran_las_de_quien_importa(tmp_path):
    destino = Config(tmp_path / "destino.json")
    destino.set_cloud({"region": "eu", "api_key": "miclaveacceso1", "api_secret": "misecretoacceso1"})
    sin_nube = {"format": "telehome-config", "version": 1, "options": {"cloud_api_key": "", "cloud_api_secret": ""}, "devices": []}
    destino.import_config(sin_nube, replace=False)
    assert destino.options["cloud_api_key"] == "miclaveacceso1"


def test_importar_valida_antes_de_tocar_nada(tmp_path):
    destino = Config(tmp_path / "destino.json")
    destino.add_device(dev(1))
    for malo in ({}, {"format": "otra-cosa", "version": 1}, {"format": "telehome-config", "version": 99},
                 {"format": "telehome-config", "version": 1, "options": {"poll_interval": 1}},
                 {"format": "telehome-config", "version": 1, "options": {"cloud_region": "zz"}},
                 {"format": "telehome-config", "version": 1, "options": {"cloud_api_key": "x", "cloud_api_secret": "y"}},
                 {"format": "telehome-config", "version": 1, "devices": "no"}, [1, 2]):
        with pytest.raises(ConfigError):
            destino.import_config(malo)
    assert [d["dev_id"] for d in destino.devices] == ["bf00000001"]          # sin cambios


def test_importar_omite_entradas_malas_y_respeta_el_maximo(tmp_path):
    destino = Config(tmp_path / "destino.json")
    devs = [dev(i) for i in range(MAX_DEVICES + 2)] + [{"name": "Sin id"}, "basura"]
    rep = destino.import_config({"format": "telehome-config", "version": 1, "devices": devs})
    assert len(destino.devices) == MAX_DEVICES and len(rep["omitidos"]) == 4
    assert len({d["id"] for d in destino.devices}) == MAX_DEVICES and len({d["slot"] for d in destino.devices}) == MAX_DEVICES


def test_export_lleva_la_ruta_del_servicio_si_se_indica(tmp_path):
    cfg = _cfg_completa(tmp_path)
    assert "servicio" not in cfg.export_config()
    assert cfg.export_config("/rafa/telehome/")["servicio"] == {"ruta": "/rafa/telehome/"}
    assert cfg.export_config("http://127.0.0.1:8765/")["servicio"]["ruta"] == "http://127.0.0.1:8765/"
    for mala in ("rafa/telehome", "javascript:alert(1)", "/a b", "/" + "x" * 300, '/a"b'):
        with pytest.raises(ConfigError, match="ruta"):
            cfg.export_config(mala)


def test_importar_devuelve_la_ruta_pero_no_la_guarda(tmp_path):
    origen = _cfg_completa(tmp_path)
    destino = Config(tmp_path / "destino.json")
    rep = destino.import_config(origen.export_config("/rafa/telehome/"))
    assert rep["servicio"] == {"ruta": "/rafa/telehome/"}
    assert "servicio" not in json.loads((tmp_path / "destino.json").read_text())      # el servicio no la conserva
    datos = origen.export_config("/rafa/telehome/")
    datos["servicio"] = {"ruta": "<script>"}
    assert destino.import_config(datos)["servicio"] is None                              # ruta no válida: se ignora
    assert destino.import_config(origen.export_config())["servicio"] is None


def test_la_contrasena_de_administrador_no_sale_en_la_exportacion_ni_se_importa(tmp_path):
    cfg = _cfg_completa(tmp_path)
    cfg.set_admin_password("clave-admin-1")
    texto = json.dumps(cfg.export_config())
    assert "admin_password_hash" not in texto and "pbkdf2" not in texto
    destino = Config(tmp_path / "destino.json")
    destino.set_admin_password("clave-admin-2")
    antes = destino.options["admin_password_hash"]
    malicioso = cfg.export_config()
    malicioso["options"]["admin_password_hash"] = "pbkdf2_sha256$1$x$y"
    malicioso["options"]["password_hash"] = "pbkdf2_sha256$1$x$y"
    destino.import_config(malicioso)
    assert destino.options["admin_password_hash"] == antes and destino.options["password_hash"] == ""
    with pytest.raises(ConfigError):
        cfg.set_admin_password("corta")

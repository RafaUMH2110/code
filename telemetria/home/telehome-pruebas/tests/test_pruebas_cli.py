"""Pruebas de telehome-pruebas.py (simulado y nube con un cliente falso)."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[1] / "telehome-pruebas.py"


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    """Carga el script como módulo, con el estado simulado en una carpeta temporal."""
    spec = importlib.util.spec_from_file_location("tep", RUTA)
    m = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "tep", m)  # las dataclasses necesitan el módulo registrado
    spec.loader.exec_module(m)
    monkeypatch.setattr(m.ConectorSimulado, "FICHERO_ESTADO", tmp_path / "sim.json")
    monkeypatch.delenv("TUYA_ACCESS_SECRET", raising=False)
    return m


def escribir(tmp_path, datos):
    ruta = tmp_path / "cfg.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


SIM = [{"nombre": "Nevera", "modo": "simulado", "dev_id": "sim00000001"},
       {"nombre": "Router", "modo": "simulado", "dev_id": "sim00000002", "protegido": True}]


# ---- configuración --------------------------------------------------------------

def test_codigo_y_json_json_gana(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "NUBE", {"region": "eu", "access_id": "codigo123", "access_secret": "s1"})
    monkeypatch.setattr(mod, "ENCHUFES", [SIM[0]])
    cfg = mod.cargar_configuracion(escribir(tmp_path, {"nube": {"access_id": "json12345"}, "enchufes": SIM}))
    assert cfg.nube.access_id == "json12345" and cfg.nube.access_secret == "s1"  # fusión campo a campo
    assert [e.nombre for e in cfg.enchufes] == ["Nevera", "Router"]            # la lista se sustituye
    assert cfg.origen["opciones"] == "código" and cfg.origen["enchufes"].startswith("JSON")
    solo_codigo = mod.cargar_configuracion(escribir(tmp_path, {"enchufes": SIM}), usar_json=False)
    assert [e.nombre for e in solo_codigo.enchufes] == ["Nevera"]


def test_secreto_desde_entorno(mod, tmp_path, monkeypatch):
    monkeypatch.setenv("TUYA_ACCESS_SECRET", "deentorno")
    cfg = mod.cargar_configuracion(escribir(tmp_path, {"nube": {"access_id": "abc12345"}}))
    assert cfg.nube.access_secret == "deentorno" and cfg.nube.completa


@pytest.mark.parametrize("enchufes, texto", [
    ([{"nombre": "x", "modo": "local", "dev_id": "bf12345678"}], "local_key"),
    ([{"nombre": "x", "modo": "marte", "dev_id": "bf12345678"}], "Modo no válido"),
    ([{"nombre": "x", "modo": "nube", "dev_id": "corto"}], "Device ID"),
    ([{"nombre": "x", "modo": "nube", "dev_id": "bf12345678", "potnecia": 1}], "desconocidos"),
    ([dict(SIM[0]), dict(SIM[0], dev_id="sim00000009")], "repetido"),
    ([dict(SIM[0], nombre="n%d" % i, dev_id="sim0000000%d" % i) for i in range(8)], "máximo es 7"),
])
def test_validacion(mod, tmp_path, enchufes, texto):
    with pytest.raises(mod.ErrorConfig, match=texto):
        mod.cargar_configuracion(escribir(tmp_path, {"enchufes": enchufes}))


def test_referencias(mod, tmp_path):
    cfg = mod.cargar_configuracion(escribir(tmp_path, {"enchufes": SIM}))
    assert [e.nombre for e in mod.resolver_enchufes(cfg, ["2", "nevera", "sim00000002"])] == ["Router", "Nevera"]
    assert len(mod.resolver_enchufes(cfg, ["todos"])) == 2
    with pytest.raises(mod.ErrorConfig, match="Disponibles"):
        mod.resolver_enchufes(cfg, ["9"])


# ---- órdenes en modo simulado --------------------------------------------------

def test_estado_apagar_y_proteccion(mod, tmp_path, capsys):
    ruta = str(escribir(tmp_path, {"enchufes": SIM}))
    assert mod.main(["-c", ruta, "--json", "apagar", "Nevera", "--espera", "0"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["encendido"] is False
    assert mod.main(["-c", ruta, "--json", "estado", "1"]) == 0
    lectura = json.loads(capsys.readouterr().out)[0]
    assert lectura["encendido"] is False and lectura["potencia_w"] == 0.0     # el estado persiste
    assert mod.main(["-c", ruta, "apagar", "Router"]) == 2                      # protegido
    assert mod.main(["-c", ruta, "apagar", "Router", "--forzar", "--espera", "0"]) == 0
    assert mod.main(["-c", ruta, "conmutar", "todos", "--forzar", "--espera", "0"]) == 2  # falta --si
    assert mod.main(["-c", ruta, "--json", "conmutar", "todos", "--forzar", "--si", "--espera", "0"]) == 0


def test_vigilar_csv_y_dps(mod, tmp_path, capsys):
    ruta = str(escribir(tmp_path, {"enchufes": SIM, "opciones": {"intervalo_vigilancia": 1}}))
    csv_ = tmp_path / "l.csv"
    assert mod.main(["-c", ruta, "vigilar", "-n", "2", "--csv", str(csv_)]) == 0
    assert len(csv_.read_text(encoding="utf-8").splitlines()) == 1 + 2 * 2
    capsys.readouterr()
    assert mod.main(["-c", ruta, "--json", "dps", "Nevera"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {"1", "18", "19", "20"}


def test_simular_sin_enchufes_usa_demo(mod, tmp_path, capsys):
    assert mod.main(["-c", str(escribir(tmp_path, {})), "--json", "--simular", "estado"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 3


# ---- modo nube con un tinytuya falso ----------------------------------------------

class NubeFalsa:
    def __init__(self, apiRegion, apiKey, apiSecret, configFile=None):
        self.token = "t"
        self.estado = {"switch_1": True, "cur_power": 1234, "cur_voltage": 2301, "cur_current": 543}

    def getstatus(self, dev_id):
        return {"success": True, "result": [{"code": k, "value": v} for k, v in self.estado.items()]}

    def getconnectstatus(self, dev_id):
        return {"success": True, "result": dev_id != "bfdesconectado1"}

    def sendcommand(self, dev_id, orden):
        c = orden["commands"][0]
        self.estado[c["code"]] = c["value"]
        return {"success": True, "result": True}

    def getdevices(self):
        return [{"id": "bfnube00000%d" % i, "name": "Enchufe %d" % i, "key": "k" * 16, "category": "cz", "online": True}
                for i in range(1, 4)] + [{"id": "bftermostato1", "name": "Termostato", "category": "wk"}]


@pytest.fixture()
def nube(mod, monkeypatch):
    monkeypatch.setattr(mod, "_tinytuya", lambda: types.SimpleNamespace(Cloud=NubeFalsa))
    return mod


def test_nube_estado_orden_y_desconectado(nube, tmp_path, capsys):
    ruta = str(escribir(tmp_path, {"nube": {"access_id": "abc12345", "access_secret": "x" * 32}, "enchufes": [
        {"nombre": "A", "modo": "nube", "dev_id": "bfnube000001"},
        {"nombre": "B", "modo": "nube", "dev_id": "bfdesconectado1"}]}))
    assert nube.main(["-c", ruta, "--json", "estado"]) == 1  # B desconectado
    a, b = json.loads(capsys.readouterr().out.split("(llamadas")[0])
    assert a["potencia_w"] == 123.4 and a["tension_v"] == 230.1 and a["corriente_a"] == 0.543 and a["en_linea"]
    assert not b["en_linea"] and "último estado" in b["error"]
    assert nube.main(["-c", ruta, "--json", "apagar", "A", "--espera", "0"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["encendido"] is False


def test_nube_dispositivos_guardar(nube, tmp_path, capsys):
    ruta = escribir(tmp_path, {"nube": {"access_id": "abc12345", "access_secret": "x" * 32},
                               "enchufes": [SIM[0]]})
    assert nube.main(["-c", str(ruta), "nube-dispositivos", "--guardar"]) == 0
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    nombres = [e["nombre"] for e in datos["enchufes"]]
    assert nombres == ["Nevera", "Enchufe 1", "Enchufe 2", "Enchufe 3"]  # sin el termostato
    assert datos["enchufes"][1]["modo"] == "nube" and datos["enchufes"][1]["local_key"] == "k" * 16
    capsys.readouterr()
    assert nube.main(["-c", str(ruta), "--json", "nube-dispositivos"]) == 0
    assert all("key" not in d for d in json.loads(capsys.readouterr().out))  # la Local Key no se muestra


def test_nube_sin_credenciales(mod, tmp_path, capsys):
    ruta = str(escribir(tmp_path, {"enchufes": [{"nombre": "A", "modo": "nube", "dev_id": "bfnube000001"}]}))
    assert mod.main(["-c", ruta, "estado"]) == 1
    assert "Faltan access_id" in capsys.readouterr().out

import json
import time
from datetime import date, datetime

import pytest

from telehome_enchufes.config import Config, ConfigError, MAX_SCHEDULES
from telehome_enchufes.monitor import Monitor
from telehome_enchufes.scheduler import Scheduler, instante
from telehome_enchufes.store import Store
from telehome_enchufes import sun


def _leer(mon):
    """Una lectura de cada dispositivo, como hace el bucle del monitor."""
    for dev_id, plug in list(mon.plugs.items()):
        mon._record(dev_id, mon._read(dev_id, plug), None)


def hoy_a(hh, mm=0, dia=None):
    d = dia or date.today()
    return time.mktime((d.year, d.month, d.day, hh, mm, 0, 0, 0, -1))


@pytest.fixture()
def app(tmp_path):
    cfg = Config(tmp_path / "c.json")
    cfg.add_device({"name": "Nevera", "dev_id": "bf00000001", "local_key": "0123456789abcdef"})
    store = Store(tmp_path / "t.db")
    mon = Monitor(cfg, store, simulate=True)
    mon.sync()
    sch = Scheduler(cfg, mon, store)
    return cfg, mon, store, sch


def prog(**kw):
    base = {"name": "Prueba", "device": "nevera", "action": "switch", "value": True,
            "when": {"kind": "clock", "time": "07:00"}}
    base.update(kw)
    return base


# ---------- validación ----------

def test_alta_y_valores_por_defecto(app):
    cfg, *_ = app
    s = cfg.add_schedule(prog())
    assert s["id"] == "prueba" and s["enabled"] is True and s["days"] == [1, 2, 3, 4, 5, 6, 7]
    assert s["condition"] is None and s["skip_if_manual"] is False and s["last_fire"] == 0
    assert json.loads((cfg.path).read_text())["schedules"][0]["name"] == "Prueba"


def test_validacion(app):
    cfg, *_ = app
    malos = [
        prog(name=""), prog(name="x" * 41),
        prog(device="no-existe"),
        prog(action="bailar"),
        prog(action="switch", value="si"),
        prog(action="level", value=120),
        prog(when={"kind": "reloj", "time": "07:00"}),
        prog(when={"kind": "clock", "time": "25:00"}),
        prog(when={"kind": "clock", "time": "7:00"}),
        prog(when={"kind": "sunrise", "offset": 900}),
        prog(days=[]), prog(days=[0]), prog(days=[8]),
        prog(condition={"metric": "p", "op": "~", "value": 5}),
        prog(condition={"metric": "p", "op": "<", "value": "mucho"}),
        prog(condition={"metric": "p", "op": "<", "value": 5, "for": 999999}),
    ]
    for m in malos:
        with pytest.raises(ConfigError):
            cfg.add_schedule(m)
    assert cfg.schedules == []


def test_maximo_y_ids_unicos(app):
    cfg, *_ = app
    for _ in range(MAX_SCHEDULES):
        cfg.add_schedule(prog())
    with pytest.raises(ConfigError, match="Máximo"):
        cfg.add_schedule(prog())
    assert len({s["id"] for s in cfg.schedules}) == MAX_SCHEDULES


def test_modificar_y_borrar(app):
    cfg, *_ = app
    s = cfg.add_schedule(prog())
    s2 = cfg.update_schedule(s["id"], {"enabled": False})
    assert s2["enabled"] is False and s2["when"]["time"] == "07:00"      # lo no indicado se hereda
    cfg.delete_schedule(s["id"])
    assert cfg.schedules == []
    with pytest.raises(KeyError):
        cfg.delete_schedule("prueba")


# ---------- momento ----------

def test_instante_hora_fija(app):
    cfg, *_ = app
    s = cfg.add_schedule(prog(when={"kind": "clock", "time": "07:30"}, days=[date.today().isoweekday()]))
    assert instante(s, date.today(), 38.27, -0.71) == hoy_a(7, 30)
    otro = date.fromtimestamp(time.time() + 86400)
    if otro.isoweekday() != date.today().isoweekday():
        assert instante(s, otro, 38.27, -0.71) is None                   # otro día de la semana: no toca


def test_instante_amanecer_y_anochecer(app):
    cfg, *_ = app
    d = date(2026, 11, 22)
    a = cfg.add_schedule(prog(name="Al amanecer", when={"kind": "sunrise", "offset": 0}))
    b = cfg.add_schedule(prog(name="Antes del anochecer", when={"kind": "sunset", "offset": -30}))
    amanece, anochece = sun._eventos(d, sun.LAT_POR_DEFECTO, sun.LON_POR_DEFECTO)
    assert instante(a, d, sun.LAT_POR_DEFECTO, sun.LON_POR_DEFECTO) == pytest.approx(amanece)
    assert instante(b, d, sun.LAT_POR_DEFECTO, sun.LON_POR_DEFECTO) == pytest.approx(anochece - 1800)
    # en el círculo polar puede no haber orto: ese día no toca
    assert instante(a, date(2026, 6, 21), 85.0, 0.0) is None


def test_el_lugar_cambia_el_amanecer(app):
    cfg, *_ = app
    s = cfg.add_schedule(prog(when={"kind": "sunrise"}))
    d = date(2026, 11, 22)
    elche = instante(s, d, 38.2699, -0.7126)
    canarias = instante(s, d, 28.1, -15.4)
    assert canarias - elche > 1800        # amanece bastante más tarde, más al oeste


# ---------- disparo ----------

def test_dispara_una_vez_y_no_se_repite(app):
    cfg, mon, store, sch = app
    s = cfg.add_schedule(prog(when={"kind": "clock", "time": "07:00"}, value=False))
    ahora = hoy_a(7, 0) + 60
    assert [r for _, r in sch.tick(ahora)] == ["ejecutada"]
    assert mon.latest["nevera"].on is False
    assert cfg.schedules[0]["last_fire"] == hoy_a(7, 0)
    assert sch.tick(ahora + 60) == []                      # ya se hizo


def test_no_dispara_antes_de_hora_ni_mucho_despues(app):
    cfg, mon, store, sch = app
    cfg.add_schedule(prog(when={"kind": "clock", "time": "07:00"}))
    assert sch.tick(hoy_a(6, 59)) == []                    # todavía no
    assert sch.tick(hoy_a(7, 0) + 7200) == []              # demasiado tarde: no se recupera


def test_desactivada_no_dispara(app):
    cfg, mon, store, sch = app
    cfg.add_schedule(prog(enabled=False))
    assert sch.tick(hoy_a(7, 1)) == []


def test_solo_los_dias_elegidos(app):
    cfg, mon, store, sch = app
    manana = date.fromtimestamp(time.time() + 86400)
    cfg.add_schedule(prog(days=[manana.isoweekday()]))
    if manana.isoweekday() != date.today().isoweekday():
        assert sch.tick(hoy_a(7, 1)) == []


def test_la_orden_programada_no_cuenta_como_manual(app):
    cfg, mon, store, sch = app
    cfg.add_schedule(prog(value=False))
    sch.tick(hoy_a(7, 1))
    assert "nevera" not in mon.last_manual                 # si contara, se saltaría a sí misma


def test_saltar_si_lo_tocaste_a_mano(app):
    cfg, mon, store, sch = app
    cfg.add_schedule(prog(skip_if_manual=True, value=False))
    mon.set_power("nevera", True)                          # orden manual, ahora
    assert [r for _, r in sch.tick(hoy_a(7, 1))][0].startswith("saltada: lo manejaste a mano")
    assert mon.latest["nevera"].on is True                 # no la ha tocado
    # sin mando manual reciente sí se ejecuta
    cfg.schedules[0]["last_fire"] = 0
    mon.last_manual.clear()
    assert [r for _, r in sch.tick(hoy_a(7, 1))] == ["ejecutada"]


def test_condicion_sobre_la_lectura(app):
    cfg, mon, store, sch = app
    _leer(mon)
    potencia = mon.latest["nevera"].power_w
    cfg.add_schedule(prog(name="Si consume poco", value=False,
                          condition={"metric": "p", "op": "<", "value": potencia / 2}))
    assert [r for _, r in sch.tick(hoy_a(7, 1))][0].startswith("saltada: no se cumple")
    cfg.schedules[0]["last_fire"] = 0
    cfg.update_schedule(cfg.schedules[0]["id"], {"condition": {"metric": "p", "op": ">", "value": potencia / 2}})
    assert [r for _, r in sch.tick(hoy_a(7, 1))] == ["ejecutada"]


def test_condicion_mantenida_durante(app):
    """Con «for», la condición tiene que haberse cumplido en todo el histórico reciente."""
    cfg, mon, store, sch = app
    for _ in range(4):
        _leer(mon)
        time.sleep(0.02)
    # la hora de la programación es hace un minuto, para que la ventana del histórico sea la de verdad
    hace_un_minuto = time.localtime(time.time() - 60)
    hhmm = time.strftime("%H:%M", hace_un_minuto)
    potencia = mon.latest["nevera"].power_w
    cfg.add_schedule(prog(value=False, when={"kind": "clock", "time": hhmm},
                          condition={"metric": "p", "op": ">", "value": potencia / 2, "for": 120}))
    assert [r for _, r in sch.tick()] == ["ejecutada"]
    # con un umbral imposible no se cumple nunca
    cfg.schedules[0]["last_fire"] = 0
    cfg.update_schedule(cfg.schedules[0]["id"], {"condition": {"metric": "p", "op": ">", "value": 1e9, "for": 120}})
    assert [r for _, r in sch.tick()][0].startswith("saltada:")
    # sin histórico en la ventana tampoco se arriesga
    cfg.schedules[0]["last_fire"] = 0
    cfg.update_schedule(cfg.schedules[0]["id"], {"condition": {"metric": "p", "op": ">=", "value": 0, "for": 120}})
    store.delete_plug("nevera")
    assert [r for _, r in sch.tick()][0] == "saltada: no hay histórico para comprobar la condición"


def test_dispositivo_borrado(app):
    cfg, mon, store, sch = app
    cfg.add_schedule(prog())
    cfg.devices.clear()
    assert [r for _, r in sch.tick(hoy_a(7, 1))] == ["saltada: el dispositivo ya no existe"]


def test_una_programacion_rota_en_el_fichero_no_impide_arrancar(app, tmp_path):
    cfg, *_ = app
    cfg.add_schedule(prog())
    datos = json.loads(cfg.path.read_text())
    datos["schedules"].append({"name": "rota", "device": "nevera", "action": "nada"})
    cfg.path.write_text(json.dumps(datos))
    otro = Config(cfg.path)
    assert [s["name"] for s in otro.schedules] == ["Prueba"]


def test_exportar_e_importar_programaciones(app, tmp_path):
    cfg, *_ = app
    cfg.add_schedule(prog(name="Mañanas", when={"kind": "sunrise", "offset": -15}, days=[1, 2, 3, 4, 5]))
    cfg.set_place(28.1, -15.4)
    exportado = json.loads(json.dumps(cfg.export_config()))
    assert exportado["schedules"][0]["name"] == "Mañanas"
    assert "last_fire" not in exportado["schedules"][0]
    assert exportado["options"]["lat"] == 28.1
    destino = Config(tmp_path / "d.json")
    rep = destino.import_config(exportado)
    assert rep["programaciones"] == 1 and destino.schedules[0]["when"]["offset"] == -15
    assert destino.options["lat"] == 28.1 and destino.options["lon"] == -15.4
    # una programación cuyo dispositivo no venga se omite
    exportado["devices"] = []
    otro = Config(tmp_path / "e.json")
    rep = otro.import_config(exportado)
    assert rep["programaciones"] == 0 and any("dispositivo" in o["motivo"] for o in rep["omitidos"])


def test_set_place_valida(app):
    cfg, *_ = app
    for mala in ((91, 0), (0, 181), ("x", 0)):
        with pytest.raises(ConfigError):
            cfg.set_place(*mala)
    assert cfg.set_place(40.4, -3.7)["lat"] == 40.4

"""TeleHome Pro: transiciones, temporizadores, escenas, grupos, límites de brillo y programaciones nuevas."""

import threading
import time

import pytest

from telehome import luces, pro
from telehome.config import Config, ConfigError
from telehome.monitor import Monitor
from telehome.pro import Automatismos
from telehome.scheduler import Scheduler
from telehome.server import AppContext, make_server
from telehome.store import Store
from test_server import call


class Reloj:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def hacer(tmp_path, luces_n=2, enchufes=1, **extra):
    cfg = Config(tmp_path / "config.json")
    for i in range(luces_n):
        cfg.add_device({"name": "Luz %d" % i, "type": "luz", "dev_id": "bflight%04d" % i, "local_key": "0123456789abcdef", **extra})
    for i in range(enchufes):
        cfg.add_device({"name": "Enchufe %d" % i, "dev_id": "bfplug%05d" % i, "local_key": "0123456789abcdef"})
    mon = Monitor(cfg, Store(tmp_path / "t.db"), simulate=True)
    clock = Reloj()
    mon.auto = Automatismos(mon, clock)
    mon.auto._asegurar_hilo = lambda: None          # los tests dan los pasos a mano con tick()
    mon.sync()
    for _ in range(100):
        if len(mon.latest) == len(cfg.devices):
            break
        time.sleep(0.05)
    return cfg, mon, clock


def estado(mon, dev_id):
    return mon.light_state(dev_id)


# ---- cálculo de pasos (puro) ----------------------------------------------------
def test_pasos_nivel_subir_bajar_y_apagar():
    p = pro.pasos_nivel(20, True, 80, 60, pro.PASO_LOCAL)
    assert p[-1][:2] == (60.0, "level") and p[-1][2] == 80
    assert [x[2] for x in p] == sorted(x[2] for x in p) and len(p) <= pro.MAX_PASOS
    p = pro.pasos_nivel(50, True, 0, 30, pro.PASO_LOCAL)
    assert p[-1] == (30.0, "switch", False) and p[-2][2] == 1       # baja hasta el 1 % y apaga al final
    p = pro.pasos_nivel(None, False, 50, 40, pro.PASO_LOCAL)
    assert p[0] == (0.0, "level", 1)                                # desde apagada empieza en el 1 %


def test_pasos_respetan_el_minimo_entre_llamadas_en_la_nube():
    assert len(pro.pasos_nivel(10, True, 90, 60, pro.PASO_NUBE)) == 15       # 60 s / 4 s
    assert len(pro.pasos_nivel(10, True, 90, 3600, pro.PASO_NUBE)) <= pro.MAX_PASOS


def test_pasos_color_toman_el_camino_corto_del_tono():
    p = pro.pasos_color({"h": 350, "s": 100, "v": 100}, False, (10, 100, 100), 100, 20, 1.0)
    tonos = [x[2]["h"] for x in p]
    assert all(h >= 340 or h <= 20 for h in tonos) and tonos[-1] == 10
    desde_blanco = pro.pasos_color(None, True, (120, 100, 80), 50, 10, 1.0)
    assert desde_blanco[0][2] == {"h": 120, "s": 0, "v": 50}       # empieza sin color, en el mismo tono


# ---- límites y modos --------------------------------------------------------------
def test_limites_de_brillo_y_modos_extra(tmp_path):
    cfg, mon, _ = hacer(tmp_path, 1, 0, level_min=20, level_max=80)
    d = cfg.devices[0]["id"]
    mon.command(d, "level", 5)
    assert estado(mon, d)["level"] == 20
    mon.command(d, "level", 100)
    assert estado(mon, d)["level"] == 80
    mon.command(d, "color", "#ff0000")                               # el valor del color también se limita
    assert estado(mon, d)["color"]["v"] == 80
    mon.command(d, "mode", "scene")
    assert estado(mon, d)["mode"] == "scene"
    with pytest.raises(ValueError):
        mon.command(d, "mode", "disco")
    with pytest.raises(ConfigError, match="mínimo"):
        cfg.update_device(d, {"level_min": 90, "level_max": 50})
    with pytest.raises(ConfigError):
        cfg.update_device(d, {"kelvin_min": 6000, "kelvin_max": 3000})


# ---- transiciones ------------------------------------------------------------------
def test_transicion_de_brillo_y_cancelacion_manual(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    d = cfg.devices[0]["id"]
    mon.command(d, "level", 10)
    mon.command(d, "level", 90, fade=30)
    clock.t += 15
    mon.auto.tick()
    medio = estado(mon, d)["level"]
    assert 10 < medio < 90
    clock.t += 20
    mon.auto.tick()
    assert estado(mon, d)["level"] == 90 and not mon.auto.listar()["fades"]
    # una orden a mano cancela lo que quede
    mon.command(d, "level", 10)
    mon.command(d, "level", 90, fade=30)
    clock.t += 10
    mon.auto.tick()
    mon.command(d, "level", 50)
    clock.t += 60
    mon.auto.tick()
    assert estado(mon, d)["level"] == 50


def test_transicion_a_cero_apaga_al_final(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    d = cfg.devices[0]["id"]
    mon.command(d, "level", 60)
    mon.command(d, "level", 0, fade=20)
    clock.t += 21
    mon.auto.tick()
    assert estado(mon, d)["on"] is False


def test_transicion_de_color_y_de_blanco(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    d = cfg.devices[0]["id"]
    mon.command(d, "temp", 0, fade=10)
    clock.t += 11
    mon.auto.tick()
    assert estado(mon, d)["temp"] == 0
    mon.command(d, "color", "#00ff00", fade=10)
    assert estado(mon, d)["mode"] == "colour"                        # el primer paso ya cambió de modo
    clock.t += 11
    mon.auto.tick()
    assert estado(mon, d)["color"] == {"h": 120, "s": 100, "v": 100}


def test_transicion_solo_en_luces_y_con_valores_validos(tmp_path):
    cfg, mon, _ = hacer(tmp_path, 1, 1)
    luz, enchufe = cfg.devices[0]["id"], cfg.devices[1]["id"]
    with pytest.raises(ValueError):
        mon.command(enchufe, "switch", True, fade=10)
    with pytest.raises(ValueError):
        mon.command(luz, "switch", True, fade=10)
    with pytest.raises(ValueError):
        mon.command(luz, "level", 500, fade=10)
    with pytest.raises(ValueError):
        mon.command(luz, "level", 50, fade=pro.MAX_FADE + 1)


# ---- temporizadores ------------------------------------------------------------------
def test_temporizador_apaga_y_se_puede_cancelar(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    d = cfg.devices[0]["id"]
    mon.command(d, "switch", True)
    mon.auto.temporizador(d, 30, "off")
    assert mon.auto.listar()["timers"][0]["device"] == d
    clock.t += 29 * 60
    mon.auto.tick()
    assert estado(mon, d)["on"] is True
    clock.t += 2 * 60
    mon.auto.tick()
    assert estado(mon, d)["on"] is False and not mon.auto.listar()["timers"]
    mon.command(d, "switch", True)
    mon.auto.temporizador(d, 5, "off")
    assert mon.auto.cancelar_temporizador(d) is True and mon.auto.cancelar_temporizador(d) is False
    for malo in (0, -3, pro.MAX_TEMPORIZADOR + 1):
        with pytest.raises(ValueError):
            mon.auto.temporizador(d, malo)


def test_temporizador_con_transicion(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    d = cfg.devices[0]["id"]
    mon.command(d, "level", 70)
    mon.auto.temporizador(d, 1, "off", fade=20)
    clock.t += 61
    mon.auto.tick()                                                  # vence: empieza la transición
    assert mon.auto.listar()["fades"]
    clock.t += 25
    mon.auto.tick()
    assert estado(mon, d)["on"] is False


def test_hilo_duerme_sin_tareas(tmp_path):
    cfg, mon, _ = hacer(tmp_path, 1, 0)
    auto = Automatismos(mon)
    assert auto._hilo is None and auto._proximo() is None
    auto.stop()


# ---- escenas y grupos -----------------------------------------------------------------
def test_escenas_validacion_y_aplicacion(tmp_path):
    cfg, mon, _ = hacer(tmp_path, 2, 1)
    a, b, e = [d["id"] for d in cfg.devices]
    sc = cfg.add_scene({"name": "Cine", "items": [
        {"device": a, "on": True, "mode": "colour", "color": "#ff8800", "level": 30},
        {"device": b, "on": True, "mode": "white", "level": 60, "temp": 10},
        {"device": e, "on": False}]})
    assert sc["id"] == "cine" and sc["items"][0]["color"].startswith("#ff") and sc["items"][0]["level"] == 30
    res = mon.apply_scene(sc)
    assert all(r["ok"] for r in res)
    assert estado(mon, a)["mode"] == "colour" and estado(mon, a)["level"] == 30
    assert estado(mon, b)["mode"] == "white" and estado(mon, b)["temp"] == 10 and estado(mon, b)["level"] == 60
    assert mon.latest[e].on is False
    for malo, texto in (({"name": "x", "items": []}, "al menos"),
                        ({"name": "", "items": [{"device": a}]}, "nombre"),
                        ({"name": "x", "items": [{"device": a}, {"device": a}]}, "dos veces"),
                        ({"name": "x", "items": [{"device": "no-existe", "on": True}]}, "identificador"),
                        ({"name": "x", "items": [{"device": a, "level": 500}]}, "level"),
                        ({"name": "x", "items": [{"device": a, "color": "rojo", "mode": "colour"}]}, "color")):
        with pytest.raises(ConfigError, match=texto):
            cfg.add_scene(malo)
    cfg.update_scene("cine", {"name": "Cine 2"})
    assert cfg.get_scene("cine")["name"] == "Cine 2"
    cfg.delete_scene("cine")
    with pytest.raises(KeyError):
        cfg.delete_scene("cine")


def test_escena_con_un_dispositivo_roto_sigue_con_los_demas(tmp_path):
    cfg, mon, _ = hacer(tmp_path, 2, 0)
    a, b = [d["id"] for d in cfg.devices]
    sc = cfg.add_scene({"name": "Todo", "items": [{"device": a, "on": True, "level": 40}, {"device": b, "on": True, "level": 40}]})
    mon.plugs[a].offline = True
    res = {r["device"]: r for r in mon.apply_scene(sc)}
    assert res[a]["ok"] is False and "alcanzable" in res[a]["error"] and res[b]["ok"] is True


def test_grupos_saltan_lo_que_no_admiten(tmp_path):
    cfg, mon, _ = hacer(tmp_path, 2, 1)
    a, b, e = [d["id"] for d in cfg.devices]
    g = cfg.add_group({"name": "Salón", "devices": [a, b, e]})
    res = {r["device"]: r for r in mon.group_command(g, "level", 25)}
    assert res[a]["ok"] and res[b]["ok"] and res[e].get("skipped")
    assert estado(mon, a)["level"] == 25 and estado(mon, b)["level"] == 25
    res = mon.group_command(g, "switch", False)
    assert all(r["ok"] for r in res) and mon.latest[e].on is False
    with pytest.raises(ConfigError):
        cfg.add_group({"name": "Vacío", "devices": []})
    with pytest.raises(ConfigError, match="identificador"):
        cfg.add_group({"name": "Mal", "devices": ["fantasma"]})


def test_borrar_un_dispositivo_lo_quita_de_escenas_y_grupos(tmp_path):
    cfg, mon, _ = hacer(tmp_path, 2, 0)
    a, b = [d["id"] for d in cfg.devices]
    cfg.add_scene({"name": "Solo a", "items": [{"device": a, "on": True}]})
    cfg.add_scene({"name": "Los dos", "items": [{"device": a, "on": True}, {"device": b, "on": False}]})
    cfg.add_group({"name": "G", "devices": [a, b]})
    cfg.delete_device(a)
    assert [s["id"] for s in cfg.scenes] == ["los-dos"] and [i["device"] for i in cfg.scenes[0]["items"]] == [b]
    assert cfg.groups[0]["devices"] == [b]


def test_escenas_y_grupos_se_guardan_y_se_exportan(tmp_path):
    cfg, mon, _ = hacer(tmp_path, 2, 0)
    a, b = [d["id"] for d in cfg.devices]
    cfg.add_scene({"name": "Noche", "items": [{"device": a, "on": True, "mode": "white", "level": 20, "temp": 5}]})
    cfg.add_group({"name": "Todas", "devices": [a, b]})
    de_nuevo = Config(tmp_path / "config.json")
    assert [s["name"] for s in de_nuevo.scenes] == ["Noche"] and de_nuevo.groups[0]["devices"] == [a, b]
    datos = cfg.export_config()
    otra = Config(tmp_path / "otra.json")
    rep = otra.import_config(datos)
    assert rep["escenas"] == 1 and rep["grupos"] == 1
    assert otra.scenes[0]["items"][0]["level"] == 20 and otra.groups[0]["name"] == "Todas"
    # un fichero antiguo, sin escenas ni grupos, se importa igual
    datos.pop("scenes"), datos.pop("groups")
    assert Config(tmp_path / "x.json").import_config(datos)["total"] == 2


# ---- programaciones ------------------------------------------------------------------------
def test_programaciones_con_escena_grupo_y_transicion(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 2, 0)
    a, b = [d["id"] for d in cfg.devices]
    cfg.add_scene({"name": "Cena", "items": [{"device": a, "on": True, "mode": "white", "level": 35, "temp": 15}]})
    cfg.add_group({"name": "Pareja", "devices": [a, b]})
    base = {"when": {"kind": "clock", "time": "21:00"}, "days": [1]}
    s1 = cfg.add_schedule({**base, "name": "Cena", "action": "scene", "value": "cena"})
    s2 = cfg.add_schedule({**base, "name": "Amanecer", "device": "grupo:pareja", "action": "level", "value": 80, "fade": 600})
    assert s1["device"] == "" and s2["fade"] == 600
    motor = Scheduler(cfg, mon, mon.store)
    assert motor.ejecutar_ahora(s1) == "ejecutada" and estado(mon, a)["level"] == 35
    assert motor.ejecutar_ahora(s2) == "ejecutada" and {f["device"] for f in mon.auto.listar()["fades"]} == {a, b}
    for malo, texto in (({"name": "m1", "action": "scene", "value": "no-hay"}, "ninguna escena"),
                        ({"name": "m2", "device": "grupo:no-hay", "action": "level", "value": 5}, "ningún grupo"),
                        ({"name": "m3", "device": a, "action": "switch", "value": True, "fade": 5}, "transición"),
                        ({"name": "m4", "device": a, "action": "level", "value": 5, "fade": 99999}, "fade"),
                        ({"name": "m5", "device": "grupo:pareja", "action": "level", "value": 5,
                          "condition": {"metric": "br", "op": "<", "value": 5}}, "condición")):
        with pytest.raises(ConfigError, match=texto):
            cfg.add_schedule({**base, **malo})
    cfg.delete_scene("cena")
    assert motor.ejecutar_ahora(s1) == "saltada: la escena ya no existe"


# ---- API ------------------------------------------------------------------------------------
@pytest.fixture()
def api(tmp_path):
    cfg, mon, _ = hacer(tmp_path, 2, 1)
    ctx = AppContext(cfg, mon.store, mon, True)
    srv = make_server(ctx, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1], cfg, mon
    mon.stop()
    srv.shutdown()
    srv.server_close()


def test_api_escenas_grupos_temporizador_y_raw(api):
    base, cfg, mon = api
    a, b, e = [d["id"] for d in cfg.devices]
    st, estado_ = call(base, "/api/state")
    assert "escenas" in estado_["features"] and estado_["scenes"] == [] and estado_["timers"] == []
    luz = next(d for d in estado_["devices"] if d["id"] == a)
    assert luz["level_min"] == 1 and luz["level_max"] == 100 and luz["kelvin_min"] == 2700
    st, sc = call(base, "/api/scenes", "POST", {"name": "Lectura", "items": [
        {"device": a, "on": True, "mode": "white", "level": 70, "temp": 40}, {"device": e, "on": True}]})
    assert st == 201 and sc["id"] == "lectura"
    st, r = call(base, "/api/scenes/lectura/apply", "POST")
    assert st == 200 and r["ok"] and len(r["resultados"]) == 2
    assert mon.light_state(a)["temp"] == 40
    st, g = call(base, "/api/groups", "POST", {"name": "Todo", "devices": [a, b, e]})
    assert st == 201
    st, r = call(base, "/api/groups/todo/command", "POST", {"action": "level", "value": 15})
    assert st == 200 and r["ok"] and any(x.get("skipped") for x in r["resultados"])
    st, r = call(base, "/api/groups/todo/command", "POST", {"action": "position", "value": 15})
    assert st == 400
    st, t = call(base, "/api/devices/%s/timer" % a, "POST", {"minutes": 20, "action": "off", "fade": 30})
    assert st == 200 and t["fade"] == 30
    st, estado_ = call(base, "/api/state")
    assert estado_["timers"][0]["device"] == a
    st, r = call(base, "/api/devices/%s/timer" % a, "DELETE")
    assert st == 200 and r["cancelado"] is True
    st, r = call(base, "/api/devices/%s/timer" % a, "POST", {"minutes": 0})
    assert st == 400
    st, r = call(base, "/api/devices/%s/command" % a, "POST", {"action": "level", "value": 80, "fade": 10})
    assert st == 200
    st, r = call(base, "/api/devices/%s/command" % e, "POST", {"action": "switch", "value": True, "fade": 10})
    assert st == 400
    st, raw = call(base, "/api/devices/%s/raw" % a)
    assert st == 200 and raw["datos"]
    st, r = call(base, "/api/scenes/lectura", "PUT", {"name": "Lectura 2"})
    assert st == 200 and r["name"] == "Lectura 2"
    st, _ = call(base, "/api/scenes/lectura", "DELETE")
    assert st == 200
    st, _ = call(base, "/api/scenes/lectura/apply", "POST")
    assert st == 404


def test_api_permisos_de_escenas_y_grupos(tmp_path):
    cfg, mon, _ = hacer(tmp_path, 1, 0)
    cfg.set_admin_password("secreto-admin")
    cfg.set_user_password("secreto-user")
    ctx = AppContext(cfg, mon.store, mon, True)
    srv = make_server(ctx, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        st, r = call(base, "/api/login", "POST", {"password": "secreto-user"})
        assert st == 200 and r["nivel"] == "user"
        user = {"X-TeleHome-Admin": r["token"]}
        st, r = call(base, "/api/login", "POST", {"password": "secreto-admin"})
        admin = {"X-TeleHome-Admin": r["token"]}
        a = cfg.devices[0]["id"]
        assert call(base, "/api/scenes", "POST", {"name": "X", "items": [{"device": a}]}, user)[0] == 403
        assert call(base, "/api/groups", "POST", {"name": "X", "devices": [a]}, user)[0] == 403
        assert call(base, "/api/devices/%s/raw" % a, "GET", None, user)[0] == 403
        assert call(base, "/api/scenes", "POST", {"name": "X", "items": [{"device": a}]}, admin)[0] == 201
        assert call(base, "/api/scenes/x/apply", "POST", None, user)[0] == 200
        assert call(base, "/api/devices/%s/timer" % a, "POST", {"minutes": 5}, user)[0] == 200
        assert call(base, "/api/devices/%s/raw" % a, "GET", None, admin)[0] == 200
    finally:
        mon.stop()
        srv.shutdown()
        srv.server_close()


# ---- 0.12.0: temporizadores que sobreviven al reinicio, escena puntual y escena con transición ----
def test_temporizador_se_guarda_y_se_recupera_al_arrancar(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    a = cfg.devices[0]["id"]
    mon.auto.temporizador(a, 30)
    assert cfg.timers and cfg.timers[0]["device"] == a            # queda apuntado en el fichero
    otra = Config(tmp_path / "config.json")
    assert otra.timers[0]["action"] == "off" and otra.timers[0]["at"] == cfg.timers[0]["at"]
    mon.auto.cancelar_temporizador(a)
    assert cfg.timers == [] and Config(tmp_path / "config.json").timers == []


def test_al_arrancar_se_recuperan_los_pendientes_y_se_descartan_los_viejos(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 2, 0)
    a, b = [d["id"] for d in cfg.devices]
    mon.auto.temporizador(a, 30)                                   # vence dentro de media hora
    mon.auto.temporizador(b, 10)
    cfg.set_timer({**cfg.timers[1], "at": clock.t - 10 * 3600})    # como si el servicio hubiera estado parado un día
    otro = Automatismos(mon, clock)
    otro._asegurar_hilo = lambda: None
    assert otro.restaurar() == 1                                   # solo queda el que aún no vencía
    assert [t["device"] for t in otro.listar()["timers"]] == [a]
    assert [t["device"] for t in cfg.timers] == [a]                # el caducado se borra del fichero


def test_un_temporizador_vencido_hace_poco_se_ejecuta_al_arrancar(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    a = cfg.devices[0]["id"]
    mon.command(a, "level", 70)
    mon.auto.temporizador(a, 10)
    cfg.set_timer({**cfg.timers[0], "at": clock.t - 60})           # venció hace un minuto
    otro = Automatismos(mon, clock)
    otro._asegurar_hilo = lambda: None
    otro.restaurar()
    assert estado(mon, a)["on"] is False and cfg.timers == []


def test_temporizador_en_un_enchufe_ignora_la_transicion(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 0, 1)
    e = cfg.devices[0]["id"]
    t = mon.auto.temporizador(e, 5, "off", fade=60)
    assert t["fade"] == 0
    clock.t += 5 * 60
    mon.auto.tick()
    assert mon.latest[e].on is False


def test_borrar_el_dispositivo_quita_su_temporizador(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    a = cfg.devices[0]["id"]
    mon.auto.temporizador(a, 20)
    cfg.delete_device(a)
    assert cfg.timers == []


def test_escena_con_transicion_pone_el_color_ya_y_el_brillo_poco_a_poco(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    a = cfg.devices[0]["id"]
    mon.command(a, "level", 20)
    mon.apply_scene({"items": [{"device": a, "on": True, "mode": "white", "level": 80, "temp": 90}]}, fade=30)
    s = estado(mon, a)
    assert s["mode"] == "white" and s["temp"] == 90                # el blanco se pone de golpe
    assert s["level"] == 20                                        # el brillo todavía no ha subido
    clock.t += 30
    mon.auto.tick()
    assert estado(mon, a)["level"] == 80


def test_escena_con_transicion_apaga_bajando_el_brillo(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    a = cfg.devices[0]["id"]
    mon.command(a, "level", 60)
    mon.apply_scene({"items": [{"device": a, "on": False}]}, fade=20)
    assert estado(mon, a)["on"] is True                            # aún encendida: va bajando
    clock.t += 20
    mon.auto.tick()
    assert estado(mon, a)["on"] is False


def test_escena_con_transicion_desde_apagada_empieza_en_el_minimo(tmp_path):
    cfg, mon, clock = hacer(tmp_path, 1, 0)
    a = cfg.devices[0]["id"]
    mon.command(a, "switch", False)
    mon.apply_scene({"items": [{"device": a, "on": True, "mode": "white", "level": 100, "temp": 10}]}, fade=30)
    s = estado(mon, a)
    assert s["on"] is True and s["level"] == 1                     # enciende al mínimo y sube desde ahí
    clock.t += 30
    mon.auto.tick()
    assert estado(mon, a)["level"] == 100


def test_api_escena_puntual_y_limites(api):
    base, cfg, mon = api
    a, b, e = [d["id"] for d in cfg.devices]
    st, estado_ = call(base, "/api/state")
    lim = estado_["limits"]
    assert lim["max_fade"] == pro.MAX_FADE and lim["fade_step_cloud"] == pro.PASO_NUBE
    assert "escena-puntual" in estado_["features"]
    st, r = call(base, "/api/scenes/apply", "POST", {"items": [
        {"device": a, "on": True, "mode": "white", "level": 44, "temp": 20},
        {"device": e, "on": False}]})
    assert st == 200 and r["ok"] and r["id"] is None
    assert mon.light_state(a)["level"] == 44 and mon.latest[e].on is False
    assert cfg.scenes == []                                        # no se guarda nada
    st, r = call(base, "/api/scenes/apply", "POST", {"items": [{"device": "no-existe", "on": True}]})
    assert st == 400
    st, r = call(base, "/api/scenes/apply", "POST", {"items": []})
    assert st == 400


def test_api_escena_guardada_admite_transicion(api):
    base, cfg, mon = api
    a = cfg.devices[0]["id"]
    st, sc = call(base, "/api/scenes", "POST", {"name": "Suave", "items": [{"device": a, "on": True, "level": 90}]})
    st, r = call(base, "/api/scenes/" + sc["id"] + "/apply", "POST", {"fade": 20})
    assert st == 200 and r["ok"]
    st, estado_ = call(base, "/api/state")
    assert [f["device"] for f in estado_["fades"]] == [a]
    st, r = call(base, "/api/scenes/" + sc["id"] + "/apply", "POST", {"fade": 99999})
    assert st == 400


def test_api_temporizador_en_enchufe(api):
    base, cfg, mon = api
    e = cfg.devices[2]["id"]
    st, t = call(base, "/api/devices/" + e + "/timer", "POST", {"minutes": 45, "action": "off", "fade": 30})
    assert st == 200 and t["fade"] == 0 and t["device"] == e
    st, estado_ = call(base, "/api/state")
    assert [x["device"] for x in estado_["timers"]] == [e]

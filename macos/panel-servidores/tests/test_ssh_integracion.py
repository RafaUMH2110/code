"""Pruebas de integración de la capa SSH contra un sshd real (ver ``conftest.py``)."""

from __future__ import annotations

import subprocess

import pytest

from panel_servidores.nucleo import claves, colector, remoto
from panel_servidores.nucleo.modelos import (AUTH_CLAVE, AUTH_PASSWORD, ORIGEN_ENTORNO, FuenteSecreto, SUDO_AUTO,
                                             SUDO_NUNCA)
from tests.conftest import InteraccionGuion


def test_contrasena_con_caracteres_especiales_por_askpass(fabrica, servidor_ssh):
    inter = InteraccionGuion([servidor_ssh.contrasena])
    con = fabrica(inter, autenticacion=AUTH_PASSWORD)
    r = con.ejecutar("id -un")
    assert r.ok, r.error
    assert r.salida.strip() == servidor_ssh.usuario
    # La contraseña se pidió UNA vez (queda en memoria durante la sesión)
    assert len(inter.preguntas) == 1
    assert con.ejecutar("echo dos").ok
    assert len(inter.preguntas) == 1


def test_multiplexado_reutiliza_la_conexion(fabrica, servidor_ssh):
    inter = InteraccionGuion([servidor_ssh.contrasena])
    con = fabrica(inter, autenticacion=AUTH_PASSWORD)
    assert con.ejecutar("true").ok
    assert con.abierta
    # Con la conexión principal viva no hace falta ninguna respuesta más
    inter.secretos.clear()
    for _ in range(3):
        assert con.ejecutar("echo ok").ok
    con.cerrar()
    assert not con.abierta


def test_sin_multiplexado_cada_orden_se_autentica(fabrica, servidor_ssh):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD, multiplexar=False)
    assert con.ejecutar("echo a").ok and con.ejecutar("echo b").ok
    assert not con.abierta


def test_contrasena_incorrecta_falla_con_un_solo_intento(fabrica, servidor_ssh):
    con = fabrica(InteraccionGuion(["mala"]), autenticacion=AUTH_PASSWORD)
    r = con.ejecutar("true")
    assert not r.ok and r.fallo_conexion
    assert "Permission denied" in r.error
    assert "Permission denied" in con.explicar_fallo(r)


def test_cancelar_el_dialogo_aborta(fabrica):
    con = fabrica(InteraccionGuion([]), autenticacion=AUTH_PASSWORD)    # el usuario cancela
    assert not con.ejecutar("true").ok


def test_contrasena_desde_variable_de_entorno(fabrica, servidor_ssh, monkeypatch):
    monkeypatch.setenv("PSV_PW", servidor_ssh.contrasena)
    inter = InteraccionGuion([])
    con = fabrica(inter, autenticacion=AUTH_PASSWORD, password=FuenteSecreto(ORIGEN_ENTORNO, "PSV_PW"))
    assert con.ejecutar("true").ok
    assert inter.preguntas == []        # no hubo diálogo


def test_huella_nueva_pide_confirmacion(fabrica, servidor_ssh, tmp_path):
    inter = InteraccionGuion([servidor_ssh.contrasena], confirmar=True)
    con = fabrica(inter, autenticacion=AUTH_PASSWORD, aceptar_huella_nueva=False,
                  opciones_ssh=["-o UserKnownHostsFile=%s" % (tmp_path / "kh_nuevo")])
    assert con.ejecutar("true").ok
    assert len(inter.confirmaciones) == 1
    assert "fingerprint" in inter.confirmaciones[0][1].lower()


def test_huella_rechazada_no_conecta(fabrica, servidor_ssh, tmp_path):
    inter = InteraccionGuion([servidor_ssh.contrasena], confirmar=False)
    con = fabrica(inter, autenticacion=AUTH_PASSWORD, aceptar_huella_nueva=False,
                  opciones_ssh=["-o UserKnownHostsFile=%s" % (tmp_path / "kh_rechazo")])
    r = con.ejecutar("true")
    assert not r.ok and r.fallo_conexion


def test_destino_invalido(fabrica):
    con = fabrica(destino="usuario@@mal:host")
    r = con.ejecutar("true")
    assert r.codigo == 3 and "Destino no válido" in r.error


def test_sudo_reutiliza_la_contrasena_ssh(fabrica, servidor_ssh):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD, sudo_modo=SUDO_AUTO)
    r = con.ejecutar_sudo(remoto.como_root("id -un"))
    assert r.ok, r.error
    assert r.salida.strip() == "root"


def test_sudo_pide_contrasena_y_reintenta(fabrica, servidor_ssh):
    # Entra con clave... aquí con contraseña SSH pero sin reutilizarla: sudo falla y se pide de nuevo
    inter = InteraccionGuion([servidor_ssh.contrasena, servidor_ssh.contrasena])
    con = fabrica(inter, autenticacion=AUTH_PASSWORD, reutilizar_password_sudo=False)
    r = con.ejecutar_sudo(remoto.como_root("id -un"))
    assert r.ok, r.error
    assert r.salida.strip() == "root"
    assert len(inter.preguntas) == 2


def test_sudo_nunca_no_usa_sudo(fabrica, servidor_ssh):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD, sudo_modo=SUDO_NUNCA)
    r = con.ejecutar_sudo(remoto.como_root("id -un", usar_sudo=False))
    assert r.ok and r.salida.strip() == servidor_ssh.usuario


def test_streaming_linea_a_linea(fabrica, servidor_ssh):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD)
    lineas = []
    r = con.ejecutar("for i in 1 2 3; do echo l$i; done; echo e >&2", on_salida=lineas.append)
    assert lineas == ["l1", "l2", "l3"] and r.error.strip() == "e"


def test_cancelacion(fabrica, servidor_ssh):
    from panel_servidores.nucleo.ssh import Cancelador
    import threading
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD)
    assert con.ejecutar("true").ok
    c = Cancelador()
    threading.Timer(0.5, c.cancelar).start()
    r = con.ejecutar("sleep 30", cancelador=c)
    assert r.cancelado and r.duracion < 10


def test_timeout(fabrica, servidor_ssh):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD)
    r = con.ejecutar("sleep 30", timeout=1)
    assert r.codigo == 124 and "timeout" in r.error


# ----------------------------------------------------------------------------- claves
@pytest.fixture
def clave_local(tmp_path, askpass):
    from panel_servidores.nucleo.modelos import Ajustes
    ruta = tmp_path / "id_prueba"
    r = claves.generar_clave(Ajustes(), askpass, str(ruta), "ed25519", "", "prueba@mac")
    assert r.ok, r.error
    return ruta


def test_generar_clave_no_sobrescribe(askpass, tmp_path):
    from panel_servidores.nucleo.modelos import Ajustes
    ruta = tmp_path / "k"
    assert claves.generar_clave(Ajustes(), askpass, str(ruta), "rsa").ok
    otra = claves.generar_clave(Ajustes(), askpass, str(ruta), "rsa")
    assert not otra.ok and "no se sobrescribe" in otra.error


def test_generar_clave_con_frase_por_askpass(askpass, tmp_path):
    from panel_servidores.nucleo.modelos import Ajustes
    ruta = tmp_path / "k_frase"
    assert claves.generar_clave(Ajustes(), askpass, str(ruta), "ed25519", "frase secreta").ok
    # sin la frase la clave no se puede usar; con ella sí
    assert subprocess.run(["ssh-keygen", "-y", "-P", "", "-f", str(ruta)], capture_output=True).returncode != 0
    assert subprocess.run(["ssh-keygen", "-y", "-P", "frase secreta", "-f", str(ruta)], capture_output=True).returncode == 0
    lista = claves.listar_claves_locales(Ajustes(), tmp_path)
    assert len(lista) == 1 and lista[0].protegida is True and lista[0].huella.startswith("SHA256:")


def test_flujo_completo_de_clave(fabrica, servidor_ssh, clave_local):
    # 1) antes de instalar, el acceso solo con clave falla porque no está autorizada
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_CLAVE, identidad=str(clave_local))
    antes = claves.comprobar_acceso_clave(con)
    assert not antes["ok"] and antes["motivo"] == "not_authorized"
    # 2) instalar (entra con contraseña porque la clave aún no vale)
    pub, _ = claves.buscar_publica(str(clave_local))
    res = claves.instalar_clave(con, pub)
    assert res["ok"] and res["resultado"] == "added"
    again = claves.instalar_clave(con, pub)
    assert again["resultado"] == "already"                      # idempotente
    # 3) ahora sí entra solo con clave y dice qué clave usó
    despues = claves.comprobar_acceso_clave(con)
    assert despues["ok"], despues
    assert despues["clave"]["huella"] == claves.huella_sha256(pub)
    assert despues["usuario"] == servidor_ssh.usuario
    # 4) permisos reparados en el servidor
    ssh = servidor_ssh.home / ".ssh"
    assert oct(ssh.stat().st_mode & 0o777) == "0o700"
    assert oct((ssh / "authorized_keys").stat().st_mode & 0o777) == "0o600"
    # 5) revocar la quita (con copia) y el acceso vuelve a fallar
    rev = claves.revocar_clave(con, pub)
    assert rev["ok"] and rev["resultado"] == "removed" and rev["cantidad"] == 1
    assert (ssh / rev["copia"].rsplit("/", 1)[1]).exists()
    assert not claves.comprobar_acceso_clave(con)["ok"]
    assert claves.revocar_clave(con, pub)["resultado"] == "absent"


def test_acceso_con_clave_con_frase_sin_agente(fabrica, servidor_ssh, tmp_path, askpass):
    """Mejora sobre el script: --check-key con frase de paso, pedida por el askpass gráfico."""
    from panel_servidores.nucleo.modelos import Ajustes
    ruta = tmp_path / "k_frase2"
    assert claves.generar_clave(Ajustes(), askpass, str(ruta), "ed25519", "mi frase").ok
    inter = InteraccionGuion([servidor_ssh.contrasena, "mi frase"])
    con = fabrica(inter, autenticacion=AUTH_CLAVE, identidad=str(ruta))
    pub, _ = claves.buscar_publica(str(ruta))
    assert claves.instalar_clave(con, pub)["ok"]
    inter.secretos[:] = ["mi frase"]
    r = claves.comprobar_acceso_clave(con)
    assert r["ok"], r
    assert any("frase" in t.lower() or "passphrase" in t.lower() for t, _ in inter.preguntas)
    claves.revocar_clave(con, pub)


def test_auditoria_de_authorized_keys(fabrica, servidor_ssh, recursos, clave_local):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_CLAVE, identidad=str(clave_local))
    pub, _ = claves.buscar_publica(str(clave_local))
    claves.instalar_clave(con, pub)
    res = colector.auditar_claves(con, recursos)
    assert res["ok"], res
    claves_remotas = res["datos"]["authorized_keys"]["keys"]
    assert any(k["fingerprint"] == claves.huella_sha256(pub) for k in claves_remotas)
    assert "authorized_keys" in res["texto"]
    claves.revocar_clave(con, pub)


# ----------------------------------------------------------------------------- informe del colector


def test_informe_json_y_texto_con_sudo(fabrica, servidor_ssh, recursos, config_colector):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD)
    op = colector.OpcionesInforme(ruta_config=config_colector, sin_servicio=True, auditar_claves=True)
    inf = colector.generar_informe(con, recursos, op)
    assert inf.ok, inf.error
    assert inf.datos["stations"][0]["id"] == "IELCHE12"
    assert inf.datos["stations"][0]["api_key"].startswith("abcd")          # enmascarada
    assert "abcd1234efgh5678" not in inf.texto
    assert "Estaciones" in inf.texto and "\x1b[" in inf.texto               # texto con color
    assert "authorized_keys" in inf.datos


def test_informe_mostrar_clave_completa(fabrica, servidor_ssh, recursos, config_colector):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD)
    op = colector.OpcionesInforme(ruta_config=config_colector, sin_servicio=True, mostrar_clave=True)
    inf = colector.generar_informe(con, recursos, op)
    assert inf.datos["stations"][0]["api_key"] == "abcd1234efgh5678"


def test_informe_sin_config_devuelve_codigo_2(fabrica, servidor_ssh, recursos):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD)
    inf = colector.generar_informe(con, recursos, colector.OpcionesInforme(ruta_config="/no/existe.ini", sin_servicio=True))
    assert inf.codigo == 2 and not inf.ok


def test_informe_sudo_nunca_sin_permiso_de_lectura(fabrica, servidor_ssh, recursos):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD, sudo_modo=SUDO_NUNCA)
    inf = colector.generar_informe(con, recursos, colector.OpcionesInforme(ruta_config="/root/no-legible.ini", sin_servicio=True))
    assert inf.codigo == 2


def test_resumen_y_comprobacion(fabrica, servidor_ssh, config_colector):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD)
    res = colector.resumen_servidor(con, config_colector)
    assert res["ok"] and res["datos"]["usuario"] == servidor_ssh.usuario
    assert res["datos"]["sudo"] == "password" and res["datos"]["python"].startswith("Python 3")
    chk = colector.comprobar(con, config_colector)
    assert chk.ok and "sudo=needs password" in chk.salida


def test_estado_servicio_inexistente(fabrica, servidor_ssh):
    con = fabrica(InteraccionGuion([servidor_ssh.contrasena]), autenticacion=AUTH_PASSWORD)
    est = colector.estado_servicio(con, "servicio-que-no-existe")
    assert est["ok"] and est["datos"]["active"] in ("inactive", "unknown", "")

"""Prueba de humo de la interfaz: se maneja la aplicación entera sin pantalla (QT_QPA_PLATFORM=offscreen)
contra el sshd de pruebas. Los diálogos (contraseña, confirmaciones) los contesta un «autopiloto»."""

from __future__ import annotations

import os
import subprocess
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from panel_servidores.nucleo.almacen import Almacen  # noqa: E402
from panel_servidores.nucleo.askpass import GestorAskpass  # noqa: E402
from panel_servidores.nucleo.instalador import OpcionesInstalador, SELECCION_TODOS  # noqa: E402
from panel_servidores.nucleo.modelos import AUTH_PASSWORD, Perfil  # noqa: E402
from panel_servidores.nucleo.secretos import Llavero  # noqa: E402
from panel_servidores.ui import hilos  # noqa: E402
from panel_servidores.ui.contexto import Contexto  # noqa: E402
from panel_servidores.ui.dialogo_flota import DialogoFlota  # noqa: E402
from panel_servidores.ui.dialogo_servidor import DialogoServidor  # noqa: E402
from panel_servidores.ui.puente import DialogoSecreto, PuenteInteraccion  # noqa: E402
from panel_servidores.ui.ventana_principal import VentanaPrincipal  # noqa: E402
from tests.conftest import CONTRASENA, LlaveroFalso  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    hilos.iniciar()
    return a


def esperar(app, condicion, segundos=40):
    fin = time.time() + segundos
    while time.time() < fin:
        app.processEvents()
        if condicion():
            for _ in range(5):
                app.processEvents()
            return
        time.sleep(0.02)
    raise AssertionError("tiempo agotado esperando la condición")


@pytest.fixture
def autopiloto(app):
    """Contesta los diálogos: contraseña correcta en DialogoSecreto y «Sí» en los QMessageBox."""
    visto = {"secretos": 0, "mensajes": []}

    def tick():
        w = QApplication.activeModalWidget()
        if isinstance(w, DialogoSecreto):
            visto["secretos"] += 1
            w.campo.setText(CONTRASENA)
            w.accept()
        elif isinstance(w, QMessageBox):
            visto["mensajes"].append(w.text())
            boton = w.button(QMessageBox.StandardButton.Yes) or w.button(QMessageBox.StandardButton.Ok)
            boton.click()

    t = QTimer()
    t.setInterval(40)
    t.timeout.connect(tick)
    t.start()
    yield visto
    t.stop()


@pytest.fixture
def entorno(app, servidor_ssh, config_colector, datos, tmp_path, autopiloto):
    askpass = GestorAskpass()
    askpass.iniciar()
    llavero = Llavero(LlaveroFalso())
    almacen = Almacen()
    ventana_ref = [None]
    puente = PuenteInteraccion(lambda: ventana_ref[0], lambda: True)
    ctx = Contexto(almacen, askpass, llavero, puente)
    # scripts «de mentira» para la prueba del instalador (carpeta propia con prioridad sobre los incluidos)
    falsos = tmp_path / "falsos"
    falsos.mkdir()
    (falsos / "instalar-todo.sh").write_text(
        '#!/bin/bash\necho "ARGS: $*"\n'
        'echo "[2026-11-08 10:00:00] === 1/6 Dependencias ==="\n'
        'echo "[2026-11-08 10:00:01] === 3/6 Despliegue en Apache ==="\n'
        'echo "[x] Repos -> nuevos: 2 | actualizados: 3 (con cambios: 1, sin cambios: 2) | errores: 0"\n'
        'echo "[x] FIN. Entrada: http://h/rafa/  |  Errores: 0  |  Duración: 7s"\n')
    (falsos / "index.html").write_text("<html/>")
    almacen.ajustes.carpeta_scripts = str(falsos)
    web = servidor_ssh.home / "web"
    (web / "rafa").mkdir(parents=True, exist_ok=True)
    (web / "rafa" / "apps.json").write_text('{"generated":"08/11/2026 10:00","apps":[{"repo":"code","path":"a.html",'
                                            '"title":"App A","description":"d","project":"p","size":2048,"updated":"2026-11-01"}]}')
    subprocess.run(["chown", "-R", "psv-test:psv-test", str(web)], check=True)
    perfil = Perfil(nombre="Servidor de pruebas", destino="psv-test@127.0.0.1:%d" % servidor_ssh.puerto,
                    autenticacion=AUTH_PASSWORD, opciones_ssh=["-o UserKnownHostsFile=%s" % servidor_ssh.known_hosts],
                    aceptar_huella_nueva=True, ruta_config=config_colector, servicio="telemet-x",
                    url_base="http://127.0.0.1")
    almacen.anadir(perfil)
    ventana = VentanaPrincipal(ctx)
    ventana_ref[0] = ventana
    yield ventana, ctx, perfil, str(web)
    ctx.cerrar_todo()
    askpass.detener()
    ventana.close()


def terminar(app, pagina):
    esperar(app, lambda: pagina.barra.progreso.isHidden() and not pagina.ocupada)


def test_ventana_y_flujo_completo(app, entorno, autopiloto):
    ventana, ctx, perfil, web = entorno
    assert ventana.lista.count() == 1 and ventana.perfil_actual().id == perfil.id
    res, inf, srv, ins, cla, apl = ventana.paginas

    # --- Resumen: conecta (pregunta la contraseña por askpass), muestra el estado y marca la sesión como abierta
    res.actualizar()
    terminar(app, res)
    assert res.valores["usuario"].text() == "psv-test", res.barra.estado.text()
    assert autopiloto["secretos"] == 1
    assert ctx.abierta(perfil.id)
    res.comprobar()
    terminar(app, res)
    assert "user=psv-test" in res.texto.toPlainText()

    # --- Informe (sin servicio) con sudo reutilizando la contraseña SSH ya conocida
    inf.sin_servicio.setChecked(True)
    inf.generar()
    terminar(app, inf)
    assert inf.informe is not None and inf.informe.ok, inf.barra.estado.text()
    assert "IELCHE12" in inf.vista_texto.toPlainText()
    assert "diagnóstico" in inf.vista_diag.toPlainText().lower() or "problemas" in inf.vista_diag.toPlainText().lower()
    assert '"stations"' in inf.vista_json.toPlainText()
    assert autopiloto["secretos"] == 1          # no volvió a preguntar

    # --- Servicio: nombre no válido se rechaza sin tocar el servidor
    srv.nombre.setText("x; rm -rf /")
    srv.consultar()
    assert "solo admite" in srv.barra.estado.text()
    srv.nombre.setText("telemet-inexistente")
    srv.consultar()
    terminar(app, srv)

    # --- Instalador (script falso): pasos, resumen y guardado de opciones sin la clave API ni --forzar
    ins.docroot.setText(web)
    ins.destino.setText(web + "/rafa")
    ins.dir_script.setText("~/panel-test/instalador")
    ins.radios[SELECCION_TODOS].setChecked(True)
    ins.colector.setChecked(True)
    ins.clave_api.setText("SECRETA")
    assert "--todos" in ins.vista_previa.text() and "--colector" in ins.vista_previa.text()
    ins.instalar()
    terminar(app, ins)
    texto = ins.consola.texto_plano()
    assert "ARGS: -u RafaUMH2110 -d %s/rafa --docroot %s --todos --colector" % (web, web) in texto, texto
    assert ins._pasos[0].text().startswith("✔") and ins._pasos[2].text().startswith("✔")
    assert "http://h/rafa/" in ins.resumen.text() and "2 nuevos" in ins.resumen.text()
    guardado = Almacen().obtener(perfil.id).instalador
    assert guardado["seleccion"] == SELECCION_TODOS and guardado["forzar"] is False
    assert "SECRETA" not in str(guardado)
    ins.ver_registro()
    terminar(app, ins)
    assert autopiloto["secretos"] == 1          # guardar las opciones del instalador no reinicia la sesión SSH
    assert ctx.abierta(perfil.id)

    # --- Aplicaciones: catálogo del servidor
    perfil.instalador = ins.opciones().a_dict()
    apl.poner_perfil(perfil)
    apl.leer()
    terminar(app, apl)
    assert apl.tabla.rowCount() == 1 and apl.tabla.item(0, 0).text() == "App A"

    # --- Claves: el listado local no falla aunque no haya claves
    cla.actualizar()
    terminar(app, cla)
    cla.comprobar()
    terminar(app, cla)
    assert cla.barra.estado.text()


def test_flota_y_dialogo_servidor(app, entorno, autopiloto):
    ventana, ctx, perfil, _ = entorno
    d = DialogoFlota(ctx, ventana)
    d.c_servicio.setChecked(False)
    d.ejecutar()
    esperar(app, lambda: d.b_ejecutar.isEnabled(), 60)
    assert d.tabla.rowCount() == 1 and d.tabla.item(0, 1).text() in ("correcto", "con errores")
    d._mostrar_seleccion()
    d.tabla.selectRow(0)
    app.processEvents()
    assert "IELCHE12" in d.visor.toPlainText()
    d.close()

    dlg = DialogoServidor(ctx, perfil, ventana)
    p = dlg._construir()
    assert p.destino == perfil.destino and p.autenticacion == AUTH_PASSWORD and p.opciones_ssh == perfil.opciones_ssh
    dlg._probar()
    esperar(app, lambda: dlg.b_probar.isEnabled(), 30)
    assert dlg.resultado.text().startswith("✔"), dlg.resultado.text()
    dlg.destino.setText("-oProxyCommand=x")
    assert dlg._validar(dlg._construir())
    dlg.close()


def test_menus_y_acciones_de_lista(app, entorno):
    ventana, ctx, perfil, _ = entorno
    n = len(ctx.almacen.perfiles)
    ventana.duplicar_servidor()
    assert len(ctx.almacen.perfiles) == n + 1 and ventana.lista.count() == n + 1
    ventana.desconectar_todos()
    assert not ctx.abierta(perfil.id)

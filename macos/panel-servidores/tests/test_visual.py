"""Revisión visual: renderiza cada pestaña y diálogo en tema claro y oscuro (sin pantalla) y comprueba
que ningún texto queda recortado. Con ``PSV_CAPTURAS=/ruta`` guarda además las imágenes PNG."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QPalette  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QComboBox, QHeaderView,  # noqa: E402
                               QLabel, QTabWidget, QTableWidget, QTreeWidget, QWidget)

from panel_servidores.ui import estilo  # noqa: E402
from panel_servidores.ui.dialogo_ajustes import DialogoAjustes  # noqa: E402
from panel_servidores.ui.dialogo_flota import DialogoFlota  # noqa: E402
from panel_servidores.ui.dialogo_servidor import DialogoServidor  # noqa: E402
from panel_servidores.ui.puente import DialogoSecreto  # noqa: E402
from tests.test_ui import app, autopiloto, entorno, esperar, terminar  # noqa: E402,F401

TAMANOS = {"grande": QSize(1280, 820), "pequena": QSize(1000, 680)}
TEMAS = ("claro", "oscuro")


def poner_tema(app_, tema: str) -> None:
    """En la plataforma «offscreen» el esquema de color del sistema no cambia la paleta, así que se aplica
    una paleta equivalente a la de macOS (Fusion + colores de ventana y de texto) y se avisa a la interfaz."""
    app_.setStyle("Fusion")
    p = QPalette()
    if tema == "oscuro":
        for rol, c in ((QPalette.ColorRole.Window, "#2b2b2b"), (QPalette.ColorRole.Base, "#1e1e1e"),
                       (QPalette.ColorRole.AlternateBase, "#262626"), (QPalette.ColorRole.Text, "#f0f0f0"),
                       (QPalette.ColorRole.WindowText, "#f0f0f0"), (QPalette.ColorRole.Button, "#3a3a3a"),
                       (QPalette.ColorRole.ButtonText, "#f0f0f0"), (QPalette.ColorRole.Highlight, "#0a60d0"),
                       (QPalette.ColorRole.HighlightedText, "#ffffff"), (QPalette.ColorRole.Mid, "#8e8e93"),
                       (QPalette.ColorRole.PlaceholderText, "#8e8e93")):
            p.setColor(rol, QColor(c))
    app_.setPalette(p)
    estilo._reaplicar()
    for _ in range(4):
        app_.processEvents()


def _visibles(raiz: QWidget):
    for w in raiz.findChildren(QWidget):
        if w.isVisibleTo(raiz) and w.width() > 0 and w.height() > 0:
            yield w


def detectar_recortes(raiz: QWidget) -> list:
    """Devuelve una lista de problemas de maquetación: textos que no caben en su widget."""
    fallos = []
    fm_cache = {}
    for w in _visibles(raiz):
        nombre = "%s«%s»" % (type(w).__name__, (getattr(w, "text", lambda: "")() or w.objectName())[:40])
        if isinstance(w, QAbstractButton) and w.text() and not isinstance(w, QComboBox):
            necesario = w.minimumSizeHint().width()
            if w.width() < necesario - 1:
                fallos.append("%s: ancho %d < mínimo %d" % (nombre, w.width(), necesario))
        elif isinstance(w, QLabel) and w.text() and not w.pixmap() and w.textFormat() != Qt.TextFormat.RichText:
            if w.wordWrap():
                if w.heightForWidth(w.width()) > w.height() + 2:
                    fallos.append("%s: alto %d < %d con ajuste de línea" % (nombre, w.height(),
                                                                          w.heightForWidth(w.width())))
            elif w.width() < w.minimumSizeHint().width() - 1:
                fallos.append("%s: ancho %d < mínimo %d" % (nombre, w.width(), w.minimumSizeHint().width()))
        elif isinstance(w, QComboBox) and w.count():
            if w.width() < w.minimumSizeHint().width() - 1:
                fallos.append("%s: ancho %d < mínimo %d" % (nombre, w.width(), w.minimumSizeHint().width()))
        elif isinstance(w, QTableWidget):
            fallos.extend(_revisar_tabla(w, nombre))
        elif isinstance(w, QTreeWidget):
            fallos.extend(_revisar_arbol(w, nombre))
    return fallos


def _revisar_tabla(t: QTableWidget, nombre: str) -> list:
    """Cabeceras cortadas: la columna debe ser al menos tan ancha como el texto de su cabecera."""
    fallos = []
    cab = t.horizontalHeader()
    for c in range(t.columnCount()):
        item = t.horizontalHeaderItem(c)
        if item is None:
            continue
        if cab.sectionSize(c) < cab.sectionSizeHint(c):
            fallos.append("%s: cabecera «%s» cortada (%d < %d)" % (nombre, item.text(), cab.sectionSize(c),
                                                                  cab.sectionSizeHint(c)))
    # homogeneidad: todas las cabeceras con la misma alineación y la misma altura
    if cab.defaultAlignment() != (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter):
        fallos.append("%s: cabeceras no alineadas a la izquierda" % nombre)
    return fallos


def _revisar_arbol(a: QTreeWidget, nombre: str) -> list:
    """Misma norma que en las tablas: ninguna cabecera cortada y todas alineadas a la izquierda."""
    fallos = []
    cab = a.header()
    for c in range(a.columnCount()):
        if cab.sectionSize(c) < cab.sectionSizeHint(c):
            fallos.append("%s: cabecera «%s» cortada (%d < %d)" % (nombre, a.headerItem().text(c), cab.sectionSize(c),
                                                                  cab.sectionSizeHint(c)))
    if cab.defaultAlignment() != (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter):
        fallos.append("%s: cabeceras no alineadas a la izquierda" % nombre)
    return fallos


def _guardar(w: QWidget, carpeta: Path, nombre: str) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    w.grab().save(str(carpeta / (nombre + ".png")))


def _poblar(app_, ventana, ctx, perfil, web, autopiloto_):
    """Recorre las pestañas para que muestren datos reales (conexión, informe, catálogo…)."""
    res, inf, srv, ins, cla, apl = ventana.paginas
    res.actualizar()
    terminar(app_, res)
    inf.sin_servicio.setChecked(True)
    inf.generar()
    terminar(app_, inf)
    cla.actualizar()
    terminar(app_, cla)
    ins.docroot.setText(web)
    ins.destino.setText(web + "/rafa")
    perfil.instalador = ins.opciones().a_dict()
    apl.poner_perfil(perfil)
    apl.leer()
    terminar(app_, apl)


def test_maquetacion_claro_y_oscuro(app, entorno, autopiloto):  # noqa: F811
    ventana, ctx, perfil, web = entorno
    estilo.instalar(app)
    _poblar(app, ventana, ctx, perfil, web, autopiloto)
    destino = os.environ.get("PSV_CAPTURAS")
    carpeta = Path(destino) if destino else None
    problemas = []
    ventana.show()
    for tema in TEMAS:
        poner_tema(app, tema)
        for tam_nombre, tam in TAMANOS.items():
            ventana.resize(tam)
            for _ in range(6):
                app.processEvents()
            for i, pagina in enumerate(ventana.paginas):
                ventana.pestanas.setCurrentIndex(i)
                for _ in range(4):
                    app.processEvents()
                etiqueta = "%s-%s-%d-%s" % (tema, tam_nombre, i, pagina.titulo.lower().replace(" ", "_"))
                if carpeta:
                    _guardar(ventana, carpeta, etiqueta)
                for f in detectar_recortes(pagina):
                    problemas.append("[%s/%s/%s] %s" % (tema, tam_nombre, pagina.titulo, f))
                # sub-pestañas (Instalador: Configuración / Repositorios / Ejecución / Mantenimiento; Informe: …)
                for interior in pagina.findChildren(QTabWidget):
                    for k in range(interior.count()):
                        interior.setCurrentIndex(k)
                        for _ in range(3):
                            app.processEvents()
                        sub = interior.tabText(k).lower().replace(" ", "_")
                        if carpeta:
                            _guardar(ventana, carpeta, etiqueta + "-sub-" + sub)
                        for f in detectar_recortes(pagina):
                            problemas.append("[%s/%s/%s/%s] %s" % (tema, tam_nombre, pagina.titulo, sub, f))
                    interior.setCurrentIndex(0)
        # diálogos
        dialogos = {"servidor": DialogoServidor(ctx, perfil, ventana), "ajustes": DialogoAjustes(ctx, ventana),
                    "flota": DialogoFlota(ctx, ventana),
                    "secreto": DialogoSecreto("Contraseña de psv-test@127.0.0.1", "Introduce la contraseña de SSH.",
                                              True, ventana)}
        for nombre, d in dialogos.items():
            d.show()
            for _ in range(6):
                app.processEvents()
            if carpeta:
                _guardar(d, carpeta, "%s-dialogo-%s" % (tema, nombre))
            for f in detectar_recortes(d):
                problemas.append("[%s/diálogo %s] %s" % (tema, nombre, f))
            d.close()
    poner_tema(app, "claro")
    assert not problemas, "\n".join(problemas)


def _luminancia(hexcolor: str) -> float:
    c = QColor(hexcolor)
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c.red()) + 0.7152 * lin(c.green()) + 0.0722 * lin(c.blue())


def contraste(a: str, b: str) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_contraste_de_los_colores():
    """Todos los colores semánticos y los de ANSI se leen (WCAG AA, 4,5:1) sobre el fondo de su tema."""
    from panel_servidores.nucleo import ansi
    fondos = {"claro": "#ffffff", "oscuro": "#1e1e1e"}
    malos = []
    for tema, fondo in fondos.items():
        for rol, c in estilo.COLORES[tema].items():
            if contraste(c, fondo) < 4.5:
                malos.append("%s/%s %s %.2f" % (tema, rol, c, contraste(c, fondo)))
        colores, tenue = ansi.PALETAS[tema == "oscuro"]
        for cod, c in list(colores.items()) + [("atenuado", tenue)]:
            if contraste(c, fondo) < 4.5:
                malos.append("ansi %s/%s %s %.2f" % (tema, cod, c, contraste(c, fondo)))
    assert not malos, "\n".join(malos)


def test_cambio_de_tema_repinta_colores(app):
    """El color de un rol cambia de verdad al pasar de claro a oscuro y la consola se repinta."""
    from panel_servidores.ui.widgets import ConsolaAnsi
    c = ConsolaAnsi(100)
    poner_tema(app, "claro")
    c.anadir("\x1b[32mhecho\x1b[0m")
    claro = c.document().toHtml()
    assert estilo.color("ok") == estilo.COLORES["claro"]["ok"]
    poner_tema(app, "oscuro")
    assert estilo.color("ok") == estilo.COLORES["oscuro"]["ok"]
    assert c.document().toHtml() != claro and "hecho" in c.toPlainText()
    poner_tema(app, "claro")


def test_menu_apariencia_guarda_la_eleccion(app, entorno):  # noqa: F811
    """Ver ▸ Apariencia recuerda la elección en las preferencias y deja marcada la opción."""
    from panel_servidores.nucleo.almacen import Almacen
    ventana, ctx, _perfil, _web = entorno
    ventana.cambiar_tema("oscuro")
    assert ctx.ajustes.tema == "oscuro" and Almacen().ajustes.tema == "oscuro"
    marcada = [a.text() for a in ventana._grupo_tema.actions() if a.isChecked()]
    assert marcada == ["Oscuro"]
    ventana.cambiar_tema("sistema")
    assert Almacen().ajustes.tema == "sistema"
    app.processEvents()

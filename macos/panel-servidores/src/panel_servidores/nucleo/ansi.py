"""Conversión de secuencias ANSI (colores SGR) a HTML.

El informe del colector se genera con colores ANSI (``--color``), igual que en el terminal.
Para mostrarlo en la interfaz se traduce a ``<span style=…>`` dentro de un ``<pre>``. Solo
se interpretan las secuencias de estilo (negrita, atenuado, colores 30-37 y 90-97); el resto
de secuencias de control se descartan.
"""

from __future__ import annotations

import html
import re

_RE_SGR = re.compile(r"\x1b\[([0-9;]*)m")
_RE_OTRAS = re.compile(r"\x1b\[[0-9;?]*[A-LN-Za-ln-z]")

# Dos paletas, una por tema: los colores del terminal «de siempre» no se leen sobre fondo blanco (amarillo,
# cian) ni sobre fondo oscuro (negro, azul). Todos cumplen un contraste mínimo de 4,5:1 con el fondo típico
# de cada tema (blanco #ffffff y gris oscuro #1e1e1e); lo comprueba tests/test_unitarias.py.
_COLORES_CLARO = {
    30: "#4b5563", 31: "#c0392b", 32: "#1e7a43", 33: "#8f5f00", 34: "#1d4ed8",
    35: "#7e22ce", 36: "#0e7490", 37: "#6b7280",
    90: "#4b5563", 91: "#b91c1c", 92: "#15803d", 93: "#8a5a00", 94: "#1e40af",
    95: "#6b21a8", 96: "#0e7490", 97: "#6b7280",
}
_COLORES_OSCURO = {
    30: "#9ca3af", 31: "#ff7b72", 32: "#4cc26e", 33: "#e0a800", 34: "#79b8ff",
    35: "#d2a8ff", 36: "#56d4dd", 37: "#d1d5db",
    90: "#9ca3af", 91: "#ff9d96", 92: "#7ee787", 93: "#f2cc60", 94: "#a5c8ff",
    95: "#e0c0ff", 96: "#7fe3ee", 97: "#f3f4f6",
}
_ATENUADO_CLARO = "#6b7280"
_ATENUADO_OSCURO = "#9ca3af"
PALETAS = {False: (_COLORES_CLARO, _ATENUADO_CLARO), True: (_COLORES_OSCURO, _ATENUADO_OSCURO)}


def _estilo(negrita: bool, atenuado: bool, color: int, oscuro: bool) -> str:
    colores, tenue = PALETAS[bool(oscuro)]
    css = []
    if negrita:
        css.append("font-weight:bold")
    if color in colores:
        css.append("color:%s" % colores[color])
    elif atenuado:
        css.append("color:%s" % tenue)
    return ";".join(css)


def ansi_a_html(texto: str, envolver: bool = True, oscuro: bool = False) -> str:
    """Traduce ``texto`` con ANSI a HTML. Con ``envolver`` lo mete en un ``<pre>`` de fuente fija.
    ``oscuro`` elige la paleta para fondo oscuro."""
    texto = _RE_OTRAS.sub("", texto)
    salida: list = []
    negrita = atenuado = False
    color = 0
    abierto = False
    posicion = 0
    for m in _RE_SGR.finditer(texto):
        salida.append(html.escape(texto[posicion:m.start()]))
        posicion = m.end()
        if abierto:
            salida.append("</span>")
            abierto = False
        codigos = [int(c) for c in m.group(1).split(";") if c.isdigit()] or [0]
        for c in codigos:
            if c == 0:
                negrita = atenuado = False
                color = 0
            elif c == 1:
                negrita = True
            elif c == 2:
                atenuado = True
            elif c == 22:
                negrita = atenuado = False
            elif c == 39:
                color = 0
            elif c in _COLORES_CLARO:
                color = c
        css = _estilo(negrita, atenuado, color, oscuro)
        if css:
            salida.append('<span style="%s">' % css)
            abierto = True
    salida.append(html.escape(texto[posicion:]))
    if abierto:
        salida.append("</span>")
    cuerpo = "".join(salida)
    if not envolver:
        return cuerpo
    return '<pre style="font-family:Menlo,Monaco,monospace;font-size:12px;margin:0">%s</pre>' % cuerpo


def quitar_ansi(texto: str) -> str:
    """Texto sin ninguna secuencia de escape (para copiar o guardar en un fichero)."""
    return _RE_OTRAS.sub("", _RE_SGR.sub("", texto))

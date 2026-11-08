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

# Colores medios que se leen bien tanto en tema claro como oscuro.
_COLORES = {
    30: "#6b7280", 31: "#d6453d", 32: "#2e9d4f", 33: "#c98a00", 34: "#3b82f6",
    35: "#a855f7", 36: "#1fa2b8", 37: "#9ca3af",
    90: "#6b7280", 91: "#ef6a62", 92: "#4cc26e", 93: "#e0a800", 94: "#60a5fa",
    95: "#c084fc", 96: "#38bdf8", 97: "#d1d5db",
}
_ATENUADO = "#8a8f98"


def _estilo(negrita: bool, atenuado: bool, color: int) -> str:
    css = []
    if negrita:
        css.append("font-weight:bold")
    if color in _COLORES:
        css.append("color:%s" % _COLORES[color])
    elif atenuado:
        css.append("color:%s" % _ATENUADO)
    return ";".join(css)


def ansi_a_html(texto: str, envolver: bool = True) -> str:
    """Traduce ``texto`` con ANSI a HTML. Con ``envolver`` lo mete en un ``<pre>`` de fuente fija."""
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
            elif c in _COLORES:
                color = c
        estilo = _estilo(negrita, atenuado, color)
        if estilo:
            salida.append('<span style="%s">' % estilo)
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

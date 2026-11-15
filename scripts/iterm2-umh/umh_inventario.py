# -*- coding: utf-8 -*-
"""
umh_inventario.py · Lectura y validación del inventario de servidores.

Lo usan generar_perfiles.py y generar_claves.py, para que ambos entiendan
exactamente lo mismo por un CSV.

El CSV se exporta desde la hoja de cálculo (pestaña «Servidores»).
Las columnas se leen POR EL NOMBRE DE LA CABECERA, no por su posición:
puedes reordenarlas, añadir otras (se ignoran) u omitir las opcionales.
Las líneas en blanco y las que empiezan por «#» se ignoran.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata

# --------------------------------------------------------------- constantes
COLUMNAS = [
    "incluir", "grupo", "nombre", "direccion", "usuario", "badge", "color",
    "tema", "atajo", "clave", "tipo_clave", "puerto", "salto", "alias_host",
    "ventana", "fuente_pt", "confirmar", "comando", "generar_clave", "notas",
]
OBLIGATORIAS = ["nombre", "direccion"]

TEMAS = ("oscuro", "claro", "aviso")
TIPOS_CLAVE = ("ed25519", "rsa")
LOCAL = "local"            # valor de «direccion» para un perfil sin SSH

COLORES = {
    "azul":    "#2C5AA0",
    "cian":    "#1E6E74",
    "verde":   "#3F7A45",
    "violeta": "#7A3C8C",
    "ocre":    "#8A6A12",
    "rojo":    "#B4352F",
    "gris":    "#4A5260",
}
_PALETA = ["#2C5AA0", "#1E6E74", "#3F7A45", "#7A3C8C", "#8A6A12", "#4A5260"]

DEFECTOS = {
    "incluir": "si", "grupo": "UMH", "usuario": "rpuerto", "tema": "oscuro",
    "tipo_clave": "ed25519", "puerto": "22", "ventana": "120x34",
    "fuente_pt": "14", "confirmar": "no", "generar_clave": "si",
}

_RE_NOMBRE  = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RE_CLAVE   = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RE_VENTANA = re.compile(r"^(\d{2,4})x(\d{1,4})$")
_RE_HEX     = re.compile(r"^#[0-9A-Fa-f]{6}$")
_RE_ALIAS   = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ErrorInventario(Exception):
    pass


# ----------------------------------------------------------------- utilidades
def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _clave_cabecera(s: str) -> str:
    """«Tipo Clave» / «tipo_clave» / «TIPO-CLAVE» -> «tipo_clave»."""
    s = _sin_acentos((s or "").strip().lower())
    s = re.sub(r"[\s\-]+", "_", s)
    return re.sub(r"[^a-z0-9_]", "", s)


def _txt(v) -> str:
    if v is None:
        return ""
    s = str(v).replace(" ", " ").strip()
    return "" if s in ("-", "—") and False else s


def _num(v) -> str:
    """La hoja puede exportar 22.0 o 14.0; se quiere 22 y 14."""
    s = _txt(v)
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.split(".")[0]
    return s


def _es_si(v, por_defecto=False) -> bool:
    s = _sin_acentos(_txt(v).lower())
    if s == "":
        return por_defecto
    return s in ("si", "s", "yes", "y", "true", "1", "x", "verdadero")


def color_de_grupo(grupo: str) -> str:
    """Color estable: el mismo grupo da siempre el mismo color."""
    semilla = sum(ord(c) for c in (grupo or "").lower())
    return _PALETA[semilla % len(_PALETA)]


def hex_de_color(valor: str, grupo: str) -> str:
    v = _txt(valor)
    if not v:
        return color_de_grupo(grupo)
    if _RE_HEX.match(v):
        return v.upper()
    return COLORES.get(_sin_acentos(v.lower()), color_de_grupo(grupo))


# -------------------------------------------------------------------- lectura
def leer(ruta: str):
    """Devuelve (filas, errores, avisos). Las filas incluyen las excluidas,
    marcadas con fila['_incluir'] = False."""
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        bruto = f.read()

    utiles = [l for l in bruto.splitlines()
              if l.strip() and not l.lstrip().startswith("#")]
    if not utiles:
        raise ErrorInventario("El CSV no tiene ninguna línea útil.")

    lector = csv.reader(io.StringIO("\n".join(utiles)))
    crudo = list(lector)
    cabecera = [_clave_cabecera(c) for c in crudo[0]]

    errores, avisos = [], []
    faltan = [c for c in OBLIGATORIAS if c not in cabecera]
    if faltan:
        raise ErrorInventario(
            "Faltan columnas obligatorias en la cabecera: " + ", ".join(faltan)
            + "\nCabecera leída: " + ", ".join(cabecera))
    desconocidas = [c for c in cabecera if c and c not in COLUMNAS]
    if desconocidas:
        avisos.append("Columnas que no reconozco y se ignoran: "
                      + ", ".join(sorted(set(desconocidas))))

    filas = []
    for i, campos in enumerate(crudo[1:], start=2):
        if not any(_txt(c) for c in campos):
            continue
        d = {}
        for j, nombre_col in enumerate(cabecera):
            if nombre_col in COLUMNAS:
                d[nombre_col] = campos[j] if j < len(campos) else ""
        fila = _normalizar(d, i, errores)
        filas.append(fila)

    _validar_conjunto(filas, errores, avisos)
    return filas, errores, avisos


def _normalizar(d: dict, nlinea: int, errores: list) -> dict:
    g = lambda k: _txt(d.get(k, ""))
    n = lambda k: _num(d.get(k, ""))

    f = {"_linea": nlinea}
    f["_incluir"] = _es_si(d.get("incluir", ""), por_defecto=True)
    f["grupo"] = g("grupo") or DEFECTOS["grupo"]
    f["nombre"] = g("nombre")
    f["direccion"] = g("direccion")
    f["usuario"] = g("usuario") or DEFECTOS["usuario"]
    f["badge"] = g("badge")
    f["tema"] = (_sin_acentos(g("tema").lower()) or DEFECTOS["tema"])
    f["atajo"] = g("atajo")
    f["tipo_clave"] = (g("tipo_clave").lower() or DEFECTOS["tipo_clave"])
    f["puerto"] = n("puerto") or DEFECTOS["puerto"]
    f["salto"] = g("salto")
    f["alias_host"] = g("alias_host")
    f["ventana"] = g("ventana") or DEFECTOS["ventana"]
    f["fuente_pt"] = n("fuente_pt") or DEFECTOS["fuente_pt"]
    f["confirmar"] = _es_si(d.get("confirmar", ""), por_defecto=False)
    f["comando"] = g("comando")
    f["notas"] = g("notas")
    f["_es_local"] = f["direccion"].lower() == LOCAL
    f["generar_clave"] = (_es_si(d.get("generar_clave", ""), por_defecto=True)
                          and not f["_es_local"])
    prefijo = "id_rsa" if f["tipo_clave"] == "rsa" else "id_ed25519"
    f["clave"] = g("clave") or ("" if f["_es_local"]
                                else "%s_%s" % (prefijo, re.sub(r"[^a-z0-9]", "", f["grupo"].lower())))
    f["color_hex"] = hex_de_color(g("color"), f["grupo"])
    f["_color_crudo"] = g("color")

    # ---- validación de la fila
    e = lambda m: errores.append("línea %d (%s): %s" % (nlinea, f["nombre"] or "¿?", m))
    if not f["nombre"]:
        e("«nombre» está vacío y es obligatorio")
    elif not _RE_NOMBRE.match(f["nombre"]):
        e("«nombre» solo admite letras, dígitos, punto, guion y guion bajo: %r" % f["nombre"])
    if not f["direccion"]:
        e("«direccion» está vacía; usa la palabra «local» para un perfil sin SSH")
    if f["tema"] not in TEMAS:
        e("«tema» no admitido: %r (usa %s)" % (f["tema"], "/".join(TEMAS)))
    if f["tipo_clave"] not in TIPOS_CLAVE:
        e("«tipo_clave» no admitido: %r (usa %s)" % (f["tipo_clave"], "/".join(TIPOS_CLAVE)))
    if not f["_es_local"]:
        if not f["puerto"].isdigit() or not 1 <= int(f["puerto"]) <= 65535:
            e("«puerto» no válido: %r" % f["puerto"])
    if not _RE_VENTANA.match(f["ventana"]):
        e("«ventana» debe ser COLUMNASxFILAS, p. ej. 120x34: %r" % f["ventana"])
    if not f["fuente_pt"].isdigit() or not 6 <= int(f["fuente_pt"]) <= 96:
        e("«fuente_pt» no válido: %r" % f["fuente_pt"])
    if len(f["atajo"]) > 1:
        e("«atajo» debe ser un solo carácter: %r" % f["atajo"])
    if f["clave"] and not _RE_CLAVE.match(f["clave"]):
        e("«clave» debe ser un nombre de archivo sin rutas: %r" % f["clave"])
    if f["alias_host"] and not _RE_ALIAS.match(f["alias_host"]):
        e("«alias_host» no válido: %r" % f["alias_host"])
    if f["_color_crudo"] and not _RE_HEX.match(f["_color_crudo"]) \
            and _sin_acentos(f["_color_crudo"].lower()) not in COLORES:
        e("«color» no reconocido: %r (usa %s, o #RRGGBB)"
          % (f["_color_crudo"], " ".join(COLORES)))
    return f


def _validar_conjunto(filas, errores, avisos):
    activas = [f for f in filas if f["_incluir"]]

    def repetidos(clave_fn, filas_):
        vistos = {}
        for f in filas_:
            k = clave_fn(f)
            if k:
                vistos.setdefault(k, []).append(f)
        return {k: v for k, v in vistos.items() if len(v) > 1}

    for nombre, grupo in repetidos(lambda f: f["nombre"].lower(), activas).items():
        errores.append("«nombre» repetido %r en las líneas %s: es el alias SSH y el "
                       "nombre del perfil, tiene que ser único"
                       % (nombre, ", ".join(str(f["_linea"]) for f in grupo)))

    for atajo, grupo in repetidos(lambda f: f["atajo"], activas).items():
        errores.append("«atajo» repetido %r en las líneas %s: ⌥⌘%s solo puede abrir un perfil"
                       % (atajo, ", ".join(str(f["_linea"]) for f in grupo), atajo))

    # una clave, un tipo
    tipos = {}
    for f in activas:
        if f["clave"]:
            tipos.setdefault(f["clave"], set()).add(f["tipo_clave"])
    for clave, ts in tipos.items():
        if len(ts) > 1:
            errores.append("la clave %r aparece con «tipo_clave» distinto (%s): "
                           "decide uno" % (clave, ", ".join(sorted(ts))))

    nombres_activos = {f["nombre"].lower() for f in activas}
    for f in activas:
        if f["salto"]:
            if f["salto"].lower() not in nombres_activos:
                errores.append("línea %d (%s): «salto» apunta a %r, que no es el «nombre» "
                               "de ninguna fila incluida" % (f["_linea"], f["nombre"], f["salto"]))
            elif f["salto"].lower() == f["nombre"].lower():
                errores.append("línea %d (%s): «salto» apunta a sí misma"
                               % (f["_linea"], f["nombre"]))
        if f["_es_local"] and f["comando"]:
            avisos.append("línea %d (%s): es un perfil local; «comando» se ignora"
                          % (f["_linea"], f["nombre"]))

    # mismo destino exacto en dos filas
    for k, grupo in repetidos(
            lambda f: None if f["_es_local"] else
            (f["direccion"].lower(), f["usuario"], f["puerto"]), activas).items():
        avisos.append("mismo destino %s@%s:%s en las líneas %s. Es correcto si son "
                      "perfiles distintos a propósito (ventana, comando); revísalo si no."
                      % (k[1], k[0], k[2], ", ".join(str(f["_linea"]) for f in grupo)))

    # misma IP con alias distintos: arranque dual o dos máquinas con la misma IP
    por_dir = {}
    for f in activas:
        if not f["_es_local"]:
            por_dir.setdefault(f["direccion"].lower(), []).append(f)
    for direccion, grupo in por_dir.items():
        alias = {f["alias_host"] for f in grupo}
        if len(alias) > 1:
            sin_alias = [f["nombre"] for f in grupo if not f["alias_host"]]
            if sin_alias:
                avisos.append(
                    "%s la usan varias filas con «alias_host» distinto y %s sin ninguno. "
                    "Si son sistemas o máquinas diferentes con la misma IP, dale a cada "
                    "una su propio «alias_host»: sus claves de host no coinciden."
                    % (direccion, ", ".join(sin_alias)))
    return

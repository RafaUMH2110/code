#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar_perfiles.py · Genera los perfiles de iTerm2 y la configuración SSH
a partir del inventario en CSV.

    python3 generar_perfiles.py                      # solo genera y valida
    python3 generar_perfiles.py --instalar           # ...y lo instala
    python3 generar_perfiles.py --csv otra_hoja.csv

Produce:
    perfiles/Perfiles-Servidores.json   un perfil «Base» + un hijo por fila
    ssh/servidores.conf                 fragmento para ~/.ssh/config.d/

Con --instalar copia el JSON a la carpeta DynamicProfiles de iTerm2 (que lo
recarga al instante) y servidores.conf a ~/.ssh/config.d/, añadiendo si falta la
línea «Include config.d/*.conf» al principio de ~/.ssh/config.

NO renombres el perfil «Base»: su identificador se deriva del nombre y
es el que iTerm2 tiene guardado como perfil predeterminado.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import platform
import plistlib
from collections import Counter
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inventario as inv

BASE = "Base"
FUENTE_DEFECTO = "menlo"      # clave en datos/fuentes.csv
VENTANA_DEFECTO = inv.DEFECTOS["ventana"]
DYN = os.path.expanduser(
    "~/Library/Application Support/iTerm2/DynamicProfiles")
# iTerm2 carga TODOS los archivos de DynamicProfiles: una copia de seguridad
# dentro de esa carpeta son perfiles duplicados y avisos al abrir cada ventana.
COPIAS = os.path.expanduser("~/.iterm2-copias")

# ------------------------------------------------------------------ paletas
OSCURO = {
    "background": "#000000", "foreground": "#F2F2F2", "bold": "#FFFFFF",
    "link": "#7FB8F0", "selection": "#2B3A55", "selected_text": "#FFFFFF",
    "cursor": "#E6E6E6", "cursor_text": "#000000", "cursor_guide": "#1C1C1C",
    "badge": "#E5696B",
    "ansi": ["#2B2B2B", "#E5696B", "#5FD068", "#E8C05A",
             "#6FA3F0", "#C58AE0", "#5CC8CC", "#D8D8D8",
             "#6E6E6E", "#FF8A8C", "#86E88E", "#F5D98A",
             "#9CC2FF", "#DDAAF2", "#8EE3E6", "#FFFFFF"],
}
CLARO = {
    "background": "#FBFAF7", "foreground": "#23262B", "bold": "#000000",
    "link": "#1F5FA8", "selection": "#D6E2F2", "selected_text": "#14171A",
    "cursor": "#B4352F", "cursor_text": "#FBFAF7", "cursor_guide": "#EDF2FA",
    "badge": "#B4352F",
    "ansi": ["#3A3F46", "#B4352F", "#3F7A45", "#8A6A12",
             "#2C5AA0", "#7A3C8C", "#1E6E74", "#5A6069",
             "#6B727C", "#C9453E", "#4C8F52", "#9B7A1A",
             "#3A6BB5", "#8C4A9E", "#27818A", "#23262B"],
}
AVISO = dict(OSCURO, background="#1A0A0C", cursor_text="#1A0A0C",
             cursor_guide="#2A1518")
PALETAS = {"oscuro": OSCURO, "claro": CLARO, "aviso": AVISO}


def comp(h, alpha=1.0):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return {"Color Space": "sRGB", "Red Component": round(r, 6),
            "Green Component": round(g, 6), "Blue Component": round(b, 6),
            "Alpha Component": alpha}


def colores(p):
    d = {"Ansi %d Color" % i: comp(c) for i, c in enumerate(p["ansi"])}
    d.update({
        "Background Color": comp(p["background"]),
        "Foreground Color": comp(p["foreground"]),
        "Bold Color": comp(p["bold"]),
        "Link Color": comp(p["link"]),
        "Selection Color": comp(p["selection"]),
        "Selected Text Color": comp(p["selected_text"]),
        "Cursor Color": comp(p["cursor"]),
        "Cursor Text Color": comp(p["cursor_text"]),
        "Cursor Guide Color": comp(p["cursor_guide"], 0.25),
        "Badge Color": comp(p["badge"], 0.5),
    })
    return d


def escribir_itermcolors(paleta, ruta):
    with open(ruta, "wb") as f:
        plistlib.dump(colores(paleta), f, fmt=plistlib.FMT_XML, sort_keys=True)


def guid(nombre):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "iterm2:" + nombre))


# ------------------------------------------------------------------ perfiles
def nombre_maquina(raiz, indicado=""):
    """El nombre de este ordenador: lo que se pasó por la línea de órdenes, o
    lo que instalar-iterm2.sh dejó en datos/maquina.txt."""
    if indicado:
        return indicado.strip()
    ruta = os.path.join(raiz, "datos", "maquina.txt")
    if os.path.isfile(ruta):
        with open(ruta, encoding="utf-8") as f:
            return f.read().strip()
    return ""


def leer_fuentes(ruta):
    """datos/fuentes.csv -> {clave: {nombre, postscript, tamano, archivo, instalacion, notas}}"""
    if not os.path.isfile(ruta):
        sys.exit("ERROR: no encuentro %s (las opciones de tipografía)." % ruta)
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        utiles = [l for l in f.read().splitlines()
                  if l.strip() and not l.lstrip().startswith("#")]
    lector = csv.DictReader(io.StringIO("\n".join(utiles)))
    campos = {c.strip().lower() for c in (lector.fieldnames or [])}
    for c in ("clave", "postscript", "tamano"):
        if c not in campos:
            sys.exit("ERROR: fuentes.csv no tiene la columna «%s»." % c)
    fuentes = {}
    for n, fila in enumerate(lector, 2):
        if None in fila:
            sys.exit("ERROR: fuentes.csv, línea de «%s»: sobran campos "
                     "(una nota con comas va entre comillas)." % (fila.get("clave") or n))
        d = {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()}
        if not d.get("clave"):
            continue
        k = d["clave"].lower()
        if k in fuentes:
            sys.exit("ERROR: fuentes.csv repite la clave «%s»." % k)
        if not d["postscript"] or not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", d["postscript"]):
            sys.exit("ERROR: fuentes.csv, «%s»: nombre PostScript no válido: %r" % (k, d["postscript"]))
        if not d["tamano"].isdigit() or not 6 <= int(d["tamano"]) <= 96:
            sys.exit("ERROR: fuentes.csv, «%s»: tamaño no válido: %r" % (k, d["tamano"]))
        d["archivo"] = os.path.expanduser(d.get("archivo", ""))
        d["nombre"] = d.get("nombre") or d["postscript"]
        fuentes[k] = d
    if not fuentes:
        sys.exit("ERROR: fuentes.csv no tiene ninguna fuente.")
    return fuentes


def fuente_elegida(raiz, fuentes, indicada=""):
    """La clave pedida con --fuente, o la que dejó instalar-iterm2.sh en
    datos/fuente.txt, o la primera por defecto. Devuelve (clave, datos).
    Si lo indicado no es una clave, se toma como nombre PostScript suelto."""
    k = (indicada or "").strip()
    if not k:
        ruta = os.path.join(raiz, "datos", "fuente.txt")
        if os.path.isfile(ruta):
            with open(ruta, encoding="utf-8") as f:
                k = f.read().strip()
    k = k or FUENTE_DEFECTO
    if k.lower() in fuentes:
        return k.lower(), fuentes[k.lower()]
    if indicada:        # --fuente NombrePostScript: compatibilidad con la opción antigua
        tam = next(iter(fuentes.values()))["tamano"]
        return k, {"clave": k, "nombre": k, "postscript": k, "tamano": tam,
                   "archivo": "", "instalacion": "", "notas": ""}
    sys.exit("ERROR: la fuente «%s» (datos/fuente.txt) no está en fuentes.csv. "
             "Claves: %s" % (k, ", ".join(fuentes)))


def perfil_base(fuente, tam, maquina="", ventana=VENTANA_DEFECTO):
    cols, rows = inv._RE_VENTANA.match(ventana).groups()
    p = {
        "Name": BASE,
        "Guid": guid(BASE),
        "Normal Font": "%s %s" % (fuente, tam),
        "Non Ascii Font": "%s %s" % (fuente, tam),
        "Use Non-ASCII Font": False,
        "Horizontal Spacing": 1.0,
        "Vertical Spacing": 1.0,
        "Use Bold Font": True,
        "Use Italic Font": True,
        "ASCII Anti Aliased": True,
        "Non-ASCII Anti Aliased": True,
        "ASCII Ligatures": False,
        "Blinking Cursor": True,
        "Cursor Type": 1,
        "Draw Powerline Glyphs": True,
        "Unicode Version": 9,
        "Ambiguous Double Width": False,
        "Columns": int(cols),
        "Rows": int(rows),
        "Transparency": 0.0,
        "Blur": False,
        "Scrollback Lines": 50000,
        "Unlimited Scrollback": False,
        "Minimum Contrast": 0.0,
        "Cursor Boost": 0.0,
        "Terminal Type": "xterm-256color",
        "Mouse Reporting": True,
        "Mouse Reporting allow mouse wheel": True,
        "Silence Bell": True,
        "Visual Bell": True,
        "Flashing Bell": False,
        "Set Local Environment Vars": True,
        "Character Encoding": 4,
        "Place Prompt at First Column": True,
        "Show Mark Indicators": True,
        "Option Key Sends": 2,
        "Right Option Key Sends": 2,
        "Close Sessions On End": True,
        "Custom Directory": "Recycle",
        "Custom Command": "No",
    }
    if maquina:
        # Solo se ve en las sesiones locales: cada perfil hijo declara su
        # propio «Badge Text», así que ninguno hereda este.
        p["Badge Text"] = maquina
        p["Badge Max Width"] = 0.25
        p["Badge Max Height"] = 0.08
    p.update(colores(OSCURO))
    return p


def perfil_de_fila(f, fuente):
    nombre = "%s · %s" % (f["grupo"], f["nombre"])
    cols, rows = inv._RE_VENTANA.match(f["ventana"]).groups()
    p = {
        "Name": nombre,
        "Guid": guid(nombre),
        "Dynamic Profile Parent Name": BASE,
        "Columns": int(cols),
        "Rows": int(rows),
        "Use Tab Color": True,
        "Tab Color": comp(f["color_hex"]),
    }
    if f["fuente_pt"]:      # vacío: hereda la fuente y el tamaño de «Base»
        p["Normal Font"] = "%s %s" % (fuente, f["fuente_pt"])
        p["Non Ascii Font"] = p["Normal Font"]
    if f["tema"] != "oscuro":
        p.update(colores(PALETAS[f["tema"]]))
    badge = f["badge"] if f["badge"] else f["nombre"]
    if badge in ("-", "—"):
        badge = ""
    p["Badge Text"] = badge
    if badge:
        p["Badge Max Width"] = 0.45 if len(badge) > 12 else 0.3
        p["Badge Max Height"] = 0.12
    if f["atajo"]:
        p["Shortcut"] = f["atajo"].upper()
    if f["confirmar"]:
        p["Prompt Before Closing 2"] = 1
    if f["_es_local"]:
        p["Custom Command"] = "No"
    else:
        p["Custom Command"] = "Yes"
        p["Command"] = "ssh %s" % f["nombre"]
    return p


PLANTILLA = {
    "_leeme": [
        "JSON no admite comentarios, así que esta plantilla va aquí, fuera de",
        "«Profiles»: iTerm2 ignora las claves que no conoce, de modo que no",
        "aparece como un perfil fantasma en la lista.",
        "Lo normal es añadir el servidor a la hoja de cálculo y volver a",
        "ejecutar generar_perfiles.py. Esto es para un añadido a mano:",
        "copia el bloque «perfil», pégalo como último elemento de «Profiles»",
        "(con una coma delante), cambia Name, Guid, Command y Badge Text, y",
        "guarda: iTerm2 lo recoge al instante.",
        "El Guid puede ser cualquier texto único que no uses en otro perfil.",
    ],
    "perfil": {
        "Name": "GRUPO · nombre-del-servidor",
        "Guid": "pon-aqui-un-identificador-unico",
        "Dynamic Profile Parent Name": BASE,
        "Custom Command": "Yes",
        "Command": "ssh nombre-del-servidor",
        "Badge Text": "etiqueta",
        "Badge Max Width": 0.3,
        "Badge Max Height": 0.12,
        "Columns": 120,
        "Rows": 59,
        "Use Tab Color": True,
        "Tab Color": comp("#4A5260"),
    },
}


# ----------------------------------------------------------------- ssh config
def bloque_ssh(f):
    L = []
    if f["notas"]:
        L.append("# %s" % f["notas"])
    L.append("Host %s" % f["nombre"])
    L.append("    HostName        %s" % f["direccion"])
    L.append("    User            %s" % f["usuario"])
    if f["puerto"] != "22":
        L.append("    Port            %s" % f["puerto"])
    if f["clave"]:
        L.append("    IdentityFile    ~/.ssh/%s" % f["clave"])
        L.append("    IdentitiesOnly  yes")
    if f["alias_host"]:
        # Una sola entrada de known_hosts para todas las direcciones de esta
        # máquina, y ninguna indexada por IP (si no, dos sistemas o dos
        # máquinas con la misma IP se pisarían las huellas).
        L.append("    HostKeyAlias    %s" % f["alias_host"])
        L.append("    CheckHostIP     no")
    if f["salto"]:
        L.append("    ProxyJump       %s" % f["salto"])
    if f["tipo_clave"] == "rsa":
        L.append("    PubkeyAcceptedAlgorithms +ssh-rsa")
        L.append("    PubkeyAcceptedKeyTypes   +ssh-rsa")   # OpenSSH < 8.5
        L.append("    HostKeyAlgorithms        +ssh-rsa")
    if f["comando"]:
        L.append("    RequestTTY      yes")
        L.append("    RemoteCommand   %s && exec $SHELL -l" % f["comando"])
    return "\n".join(L)


PORTABILIDAD = """
# ---------------------------------------------------------------------
#  Esto va primero a propósito: IgnoreUnknown no se aplica a las opciones
#  desconocidas que aparezcan antes de él. Con esta línea, el mismo archivo
#  vale en macOS (donde UseKeychain existe) y en Linux o en un OpenSSH
#  antiguo (donde no), sin que ssh aborte con «Bad configuration option».
# ---------------------------------------------------------------------
Host *
    IgnoreUnknown UseKeychain,PubkeyAcceptedAlgorithms,PubkeyAcceptedKeyTypes
"""

GLOBALES = """
# ---------------------------------------------------------------------
#  Opciones comunes. Van al final: SSH se queda con el PRIMER valor que
#  encuentra para cada opción, así que lo de cada Host de arriba manda.
# ---------------------------------------------------------------------
Host *
    AddKeysToAgent          yes
    UseKeychain             yes
    PreferredAuthentications publickey,keyboard-interactive,password
    ServerAliveInterval     60
    ServerAliveCountMax     3
    TCPKeepAlive            yes
    Compression             yes
    ControlMaster           auto
    ControlPath             ~/.ssh/cm/%r@%h:%p
    ControlPersist          10m
    HashKnownHosts          yes
"""

PLANTILLA_SSH = """
# =====================================================================
#  PLANTILLA · copia este bloque, quítale las almohadillas y edítalo
#  para añadir un servidor a mano. Lo normal es añadirlo a la hoja de
#  cálculo y volver a ejecutar generar_perfiles.py (este archivo se
#  regenera completo, así que lo que escribas aquí se perderá: para algo
#  permanente, usa otro archivo en ~/.ssh/config.d/).
# ---------------------------------------------------------------------
# Host nombre-corto
#     HostName        servidor.example.es
#     User            usuario
#     Port            22
#     IdentityFile    ~/.ssh/id_ed25519_servidores
#     IdentitiesOnly  yes
#     HostKeyAlias    nombre-de-la-maquina    # si llega por varias IP
#     CheckHostIP     no                      # acompaña a HostKeyAlias
#     ProxyJump       otro-host               # si hay que saltar
#     RequestTTY      yes                     # si usas RemoteCommand
#     RemoteCommand   cd /ruta && exec $SHELL -l
# =====================================================================
"""


# ----------------------------------------------------------------- instalación
def guardar_copia(ruta, sello):
    """Copia de seguridad, siempre FUERA de la carpeta de la que se copia."""
    os.makedirs(COPIAS, exist_ok=True)
    destino = os.path.join(COPIAS, "%s.bak-%s" % (os.path.basename(ruta), sello))
    shutil.copy2(ruta, destino)
    return destino


# Nombres de versiones anteriores del kit. Se retiran al instalar: si se quedaran,
# iTerm2 cargaría también el perfil antiguo (los dos archivos de DynamicProfiles
# se cargan) y ssh leería dos veces los mismos «Host».
ANTIGUOS_COPIAS = os.path.expanduser("~/.iterm2-umh-copias")
ANTIGUOS_JSON = "UMH-Perfiles.json"
ANTIGUOS_CONF = "umh.conf"


def retirar_antiguos(ssh_dir, sello):
    """Mueve a COPIAS los archivos con el nombre antiguo. Devuelve lo retirado."""
    os.makedirs(COPIAS, exist_ok=True)
    if os.path.isdir(ANTIGUOS_COPIAS):
        for n in os.listdir(ANTIGUOS_COPIAS):
            destino = os.path.join(COPIAS, n)
            if not os.path.exists(destino):
                shutil.move(os.path.join(ANTIGUOS_COPIAS, n), destino)
        try:
            os.rmdir(ANTIGUOS_COPIAS)
        except OSError:
            pass
    retirados = []
    candidatos = [os.path.join(ssh_dir, "config.d", ANTIGUOS_CONF)]
    if os.path.isdir(DYN):
        candidatos += [os.path.join(DYN, n) for n in sorted(os.listdir(DYN))
                       if n == ANTIGUOS_JSON or n.startswith(ANTIGUOS_JSON + ".bak-")]
    for ruta in candidatos:
        if os.path.isfile(ruta):
            destino = os.path.join(COPIAS, "%s.retirado-%s" % (os.path.basename(ruta), sello))
            shutil.move(ruta, destino)
            retirados.append(ruta)
    return retirados


def asegurar_include(ruta_config):
    linea = "Include config.d/*.conf"
    if os.path.exists(ruta_config):
        with open(ruta_config, encoding="utf-8") as f:
            texto = f.read()
        if re.search(r"^\s*Include\s+config\.d/\*\.conf\s*$", texto, re.M):
            return False
        guardar_copia(ruta_config, datetime.now().strftime("%Y%m%d-%H%M%S"))
        with open(ruta_config, "w", encoding="utf-8") as f:
            f.write("# Añadido por generar_perfiles.py: tiene que ir al principio,\n"
                    "# porque SSH se queda con el primer valor de cada opción.\n"
                    + linea + "\n\n" + texto)
    else:
        with open(ruta_config, "w", encoding="utf-8") as f:
            f.write(linea + "\n")
    os.chmod(ruta_config, 0o600)
    return True


def main():
    # Carpeta del kit (donde están datos/, colores/…); se admite también
    # una subcarpeta por compatibilidad con versiones antiguas
    _aqui = os.path.dirname(os.path.abspath(__file__))
    aquí = _aqui if os.path.isdir(os.path.join(_aqui, "datos")) else os.path.dirname(_aqui)
    ap = argparse.ArgumentParser(description="Genera perfiles de iTerm2 y config SSH.")
    ap.add_argument("--csv", default=os.path.join(aquí, "datos/servidores.csv"))
    ap.add_argument("--salida", default=aquí)
    ap.add_argument("--fuente", default="",
                    help="clave de la tipografía de «Base» en datos/fuentes.csv "
                         "(menlo, jetbrains, monaco...); por defecto, datos/fuente.txt")
    ap.add_argument("--lista-fuentes", action="store_true",
                    help="muestra las tipografías disponibles y sale")
    ap.add_argument("--fuentes-csv", default=os.path.join(aquí, "datos/fuentes.csv"))
    ap.add_argument("--ventana", default="",
                    help="tamaño COLUMNASxFILAS de «Base» (la sesión local); "
                         "por defecto, el más repetido en la hoja")
    ap.add_argument("--colores", action="store_true",
                    help="regenera colores/*.itermcolors desde las paletas")
    ap.add_argument("--maquina", default="",
                    help="nombre de este ordenador para el distintivo de las "
                         "sesiones locales; por defecto, datos/maquina.txt")
    ap.add_argument("--instalar", action="store_true",
                    help="copia el resultado a iTerm2 y a ~/.ssh/config.d/")
    ap.add_argument("--sin-globales", action="store_true",
                    help="no escribir el bloque «Host *» de opciones comunes")
    a = ap.parse_args()

    fuentes = leer_fuentes(a.fuentes_csv)
    if a.lista_fuentes:
        # clave|nombre|tamaño|archivo|instalación|postscript: lo lee instalar-iterm2.sh
        for k, d in fuentes.items():
            print("|".join((k, d["nombre"], d["tamano"], d["archivo"],
                            d["instalacion"], d["postscript"])))
        return
    clave_fuente, fuente = fuente_elegida(aquí, fuentes, a.fuente)

    try:
        filas, errores, avisos = inv.leer(a.csv)
    except inv.ErrorInventario as exc:
        sys.exit("ERROR: %s" % exc)
    except FileNotFoundError:
        sys.exit("ERROR: no encuentro el CSV: %s" % a.csv)

    for m in avisos:
        print("AVISO: %s" % m)
    if errores:
        print("\nNo he generado nada. Corrige esto en la hoja y vuelve a exportar:")
        for m in errores:
            print("  ERROR: %s" % m)
        sys.exit(1)

    activas = [f for f in filas if f["_incluir"]]
    if not activas:
        sys.exit("ERROR: ninguna fila tiene «incluir» = si.")

    maquina = nombre_maquina(aquí, a.maquina)
    # «Base» es lo que abre ⌘N: lleva el tamaño que más se repite en la
    # hoja (o el de --ventana), para que no discrepe de lo que se ha pedido.
    if a.ventana:
        if not inv._RE_VENTANA.match(a.ventana):
            sys.exit("ERROR: --ventana debe ser COLUMNASxFILAS, p. ej. 120x59")
        ventana = a.ventana
    else:
        ventana = Counter(f["ventana"] for f in activas).most_common(1)[0][0]
    perfiles = ([perfil_base(fuente["postscript"], fuente["tamano"], maquina, ventana)]
                + [perfil_de_fila(f, fuente["postscript"]) for f in activas])
    if a.colores:
        os.makedirs(os.path.join(a.salida, "colores"), exist_ok=True)
        escribir_itermcolors(OSCURO, os.path.join(a.salida, "colores/Elegante-Oscuro.itermcolors"))
        escribir_itermcolors(CLARO, os.path.join(a.salida, "colores/Elegante-Claro.itermcolors"))
        print("Presets de color regenerados en colores/")
    doc = {"Profiles": perfiles, "_PLANTILLA": PLANTILLA}

    ruta_json = os.path.join(a.salida, "perfiles/Perfiles-Servidores.json")
    os.makedirs(os.path.dirname(ruta_json), exist_ok=True)
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    cabecera = ("# =====================================================================\n"
                "#  ~/.ssh/config.d/servidores.conf · GENERADO POR generar_perfiles.py\n"
                "#  Fuente: %s\n"
                "#  Fecha:  %s\n"
                "#  No lo edites a mano: se sobrescribe en cada ejecución.\n"
                "# =====================================================================\n"
                % (os.path.basename(a.csv), datetime.now().strftime("%Y-%m-%d %H:%M")))
    partes = [cabecera, PORTABILIDAD]
    grupo_actual = None
    for f in activas:
        if f["_es_local"]:
            continue
        if f["grupo"] != grupo_actual:
            grupo_actual = f["grupo"]
            partes.append("\n# ---------- %s ----------" % grupo_actual)
        partes.append(bloque_ssh(f))
    partes.append(PLANTILLA_SSH)
    if not a.sin_globales:
        partes.append(GLOBALES)

    ruta_conf = os.path.join(a.salida, "ssh/servidores.conf")
    os.makedirs(os.path.dirname(ruta_conf), exist_ok=True)
    with open(ruta_conf, "w", encoding="utf-8") as f:
        f.write("\n".join(partes).rstrip() + "\n")

    # ---- resumen
    print("\n%-26s %-24s %-21s %-6s %s" % ("PERFIL", "DESTINO", "CLAVE", "ATAJO", "NOTAS"))
    print("-" * 100)
    for f in activas:
        destino = "local" if f["_es_local"] else "%s@%s" % (f["usuario"], f["direccion"])
        print("%-26s %-24s %-21s %-6s %s" % (
            ("%s · %s" % (f["grupo"], f["nombre"]))[:26], destino[:24],
            (f["clave"] or "—")[:21],
            ("⌥⌘" + f["atajo"]) if f["atajo"] else "—", f["notas"][:24]))
    print("-" * 100)
    excluidas = [f["nombre"] for f in filas if not f["_incluir"]]
    print("%d perfiles · %d claves distintas%s"
          % (len(activas), len({f["clave"] for f in activas if f["clave"]}),
             (" · fuera por «incluir = no»: " + ", ".join(excluidas)) if excluidas else ""))
    print("«Base»: ventana %s · fuente %s (%s) %s pt"
          % (ventana, fuente["nombre"], clave_fuente, fuente["tamano"]))
    print("máquina local: %s" % (maquina or "sin nombre (bash instalar-iterm2.sh -m NOMBRE)"))
    print("\n  %s\n  %s" % (ruta_json, ruta_conf))

    if not a.instalar:
        print("\nNo he instalado nada. Repite con --instalar cuando lo veas bien.")
        return

    # ---- instalar
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    es_mac = platform.system() == "Darwin"
    destino_json = None
    if es_mac:
        os.makedirs(DYN, exist_ok=True)
        destino_json = os.path.join(DYN, "Perfiles-Servidores.json")
        if os.path.exists(destino_json):
            guardar_copia(destino_json, sello)
        shutil.copy2(ruta_json, destino_json)

    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(os.path.join(ssh_dir, "config.d"), exist_ok=True)
    os.makedirs(os.path.join(ssh_dir, "cm"), exist_ok=True)
    os.chmod(ssh_dir, 0o700)
    os.chmod(os.path.join(ssh_dir, "config.d"), 0o700)
    os.chmod(os.path.join(ssh_dir, "cm"), 0o700)
    destino_conf = os.path.join(ssh_dir, "config.d/servidores.conf")
    if os.path.exists(destino_conf):
        guardar_copia(destino_conf, sello)
    shutil.copy2(ruta_conf, destino_conf)
    os.chmod(destino_conf, 0o600)
    añadido = asegurar_include(os.path.join(ssh_dir, "config"))
    retirados = retirar_antiguos(ssh_dir, sello)

    print("\nInstalado:")
    if destino_json:
        print("  %s" % destino_json)
    else:
        print("  (iTerm2 solo existe en macOS: aquí instalo solo la parte SSH;")
        print("   el JSON de perfiles queda generado en %s)" % ruta_json)
    print("  %s" % destino_conf)
    print("  ~/.ssh/config: %s" % ("añadida la línea Include" if añadido
                                   else "ya tenía la línea Include"))
    for r in retirados:
        print("  retirado el archivo con el nombre antiguo: %s" % r)
    if os.path.isdir(COPIAS):
        print("  copias de seguridad en ~/.iterm2-copias")
    print("\nComprueba una conexión con:  ssh -G %s | head -5" % activas[0]["nombre"])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar_perfiles.py · Genera los perfiles de iTerm2 y la configuración SSH
a partir del inventario en CSV.

    python3 scripts/generar_perfiles.py                      # solo genera y valida
    python3 scripts/generar_perfiles.py --instalar           # ...y lo instala
    python3 scripts/generar_perfiles.py --csv otra_hoja.csv

Produce:
    perfiles/UMH-Perfiles.json   un perfil «UMH · Base» + un hijo por fila
    ssh/umh.conf                 fragmento para ~/.ssh/config.d/

Con --instalar copia el JSON a la carpeta DynamicProfiles de iTerm2 (que lo
recarga al instante) y umh.conf a ~/.ssh/config.d/, añadiendo si falta la
línea «Include config.d/*.conf» al principio de ~/.ssh/config.

NO renombres el perfil «UMH · Base»: su identificador se deriva del nombre y
es el que iTerm2 tiene guardado como perfil predeterminado.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import platform
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import umh_inventario as inv

BASE = "UMH · Base"
FUENTE_DEFECTO = "JetBrainsMonoNFM-Regular"
DYN = os.path.expanduser(
    "~/Library/Application Support/iTerm2/DynamicProfiles")
# iTerm2 carga TODOS los archivos de DynamicProfiles: una copia de seguridad
# dentro de esa carpeta son perfiles duplicados y avisos al abrir cada ventana.
COPIAS = os.path.expanduser("~/.iterm2-umh-copias")

# ------------------------------------------------------------------ paletas
OSCURO = {
    "background": "#11141A", "foreground": "#D7DCE3", "bold": "#EDF0F4",
    "link": "#7FB8D9", "selection": "#2E3950", "selected_text": "#EDF0F4",
    "cursor": "#D8B06A", "cursor_text": "#11141A", "cursor_guide": "#1A2030",
    "badge": "#D4696A",
    "ansi": ["#2A2F3A", "#D4696A", "#86B38A", "#D8B06A",
             "#7FA5D9", "#B38AC4", "#6FB5B8", "#C9CFD8",
             "#4A5260", "#E68A8B", "#A3CCA6", "#EDCB8A",
             "#A0C0E8", "#CBA8D8", "#92CDD0", "#EDF0F4"],
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
AVISO = dict(OSCURO, background="#1A1113", cursor_text="#1A1113",
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


def guid(nombre):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "umh-iterm2:" + nombre))


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


def perfil_base(fuente, maquina=""):
    p = {
        "Name": BASE,
        "Guid": guid(BASE),
        "Normal Font": "%s 14" % fuente,
        "Non Ascii Font": "%s 14" % fuente,
        "Use Non-ASCII Font": False,
        "Horizontal Spacing": 1.0,
        "Vertical Spacing": 1.12,
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
        "Columns": 120,
        "Rows": 34,
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
    if f["fuente_pt"] != "14":
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
        "Rows": 34,
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
#     IdentityFile    ~/.ssh/id_ed25519_umh
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
    # El paquete puede tener los scripts en su raíz o en scripts/
    _aqui = os.path.dirname(os.path.abspath(__file__))
    aquí = _aqui if os.path.isdir(os.path.join(_aqui, "datos")) else os.path.dirname(_aqui)
    ap = argparse.ArgumentParser(description="Genera perfiles de iTerm2 y config SSH.")
    ap.add_argument("--csv", default=os.path.join(aquí, "datos/servidores.csv"))
    ap.add_argument("--salida", default=aquí)
    ap.add_argument("--fuente", default=FUENTE_DEFECTO,
                    help="nombre PostScript de la tipografía (sin el tamaño)")
    ap.add_argument("--maquina", default="",
                    help="nombre de este ordenador para el distintivo de las "
                         "sesiones locales; por defecto, datos/maquina.txt")
    ap.add_argument("--instalar", action="store_true",
                    help="copia el resultado a iTerm2 y a ~/.ssh/config.d/")
    ap.add_argument("--sin-globales", action="store_true",
                    help="no escribir el bloque «Host *» de opciones comunes")
    a = ap.parse_args()

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
    perfiles = ([perfil_base(a.fuente, maquina)]
                + [perfil_de_fila(f, a.fuente) for f in activas])
    doc = {"Profiles": perfiles, "_PLANTILLA": PLANTILLA}

    ruta_json = os.path.join(a.salida, "perfiles/UMH-Perfiles.json")
    os.makedirs(os.path.dirname(ruta_json), exist_ok=True)
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    cabecera = ("# =====================================================================\n"
                "#  ~/.ssh/config.d/umh.conf · GENERADO POR generar_perfiles.py\n"
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

    ruta_conf = os.path.join(a.salida, "ssh/umh.conf")
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
        destino_json = os.path.join(DYN, "UMH-Perfiles.json")
        if os.path.exists(destino_json):
            guardar_copia(destino_json, sello)
        shutil.copy2(ruta_json, destino_json)

    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(os.path.join(ssh_dir, "config.d"), exist_ok=True)
    os.makedirs(os.path.join(ssh_dir, "cm"), exist_ok=True)
    os.chmod(ssh_dir, 0o700)
    os.chmod(os.path.join(ssh_dir, "config.d"), 0o700)
    os.chmod(os.path.join(ssh_dir, "cm"), 0o700)
    destino_conf = os.path.join(ssh_dir, "config.d/umh.conf")
    if os.path.exists(destino_conf):
        guardar_copia(destino_conf, sello)
    shutil.copy2(ruta_conf, destino_conf)
    os.chmod(destino_conf, 0o600)
    añadido = asegurar_include(os.path.join(ssh_dir, "config"))

    print("\nInstalado:")
    if destino_json:
        print("  %s" % destino_json)
    else:
        print("  (iTerm2 solo existe en macOS: aquí instalo solo la parte SSH;")
        print("   el JSON de perfiles queda generado en %s)" % ruta_json)
    print("  %s" % destino_conf)
    print("  ~/.ssh/config: %s" % ("añadida la línea Include" if añadido
                                   else "ya tenía la línea Include"))
    if os.path.isdir(COPIAS):
        print("  copias de seguridad en ~/.iterm2-umh-copias")
    print("\nComprueba una conexión con:  ssh -G %s | head -5" % activas[0]["nombre"])


if __name__ == "__main__":
    main()

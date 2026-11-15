#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar_claves.py · Crea las claves SSH del inventario, las guarda en el
Llavero y las instala en cada servidor.

    python3 generar_claves.py --dry-run               # qué haría, sin tocar nada
    python3 generar_claves.py                         # todo el inventario
    python3 generar_claves.py --solo equipo-lan        # una sola máquina
    python3 generar_claves.py --grupo LAB             # un grupo
    python3 generar_claves.py --solo-claves           # crear claves, sin copiarlas

Una clave se crea UNA vez por cada valor distinto de la columna «clave», y
luego se copia una vez por cada fila que la use: así varios usuarios o varias
máquinas pueden compartirla.

Los filtros --solo y --grupo existen sobre todo para máquinas de arranque
dual: la pública hay que copiarla con cada sistema arrancado, porque cada uno
tiene su propio authorized_keys.

Ejecuta primero generar_perfiles.py --instalar: con ~/.ssh/config.d/umh.conf
puesto, este script usa los alias (y con ellos el puerto, el usuario y los
saltos) en vez de repetir los datos.
"""
from __future__ import annotations

import argparse
import os
import shlex
import platform
import shutil
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import umh_inventario as inv

SSH = os.path.expanduser("~/.ssh")
ES_MAC = platform.system() == "Darwin"


def correr(cmd, dry, interactivo=True):
    """Ejecuta y devuelve el código de salida. Interactivo = sin capturar,
    para que ssh-keygen y ssh-copy-id puedan preguntar."""
    print("   $ " + " ".join(shlex.quote(c) for c in cmd))
    if dry:
        return 0
    if interactivo:
        return subprocess.call(cmd)
    return subprocess.run(cmd, capture_output=True, text=True).returncode


def alias_resuelve(nombre, direccion):
    """¿Está instalado ~/.ssh/config.d/umh.conf y el alias apunta donde debe?"""
    try:
        r = subprocess.run(["ssh", "-G", nombre], capture_output=True, text=True,
                           timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    if r.returncode != 0:
        return False
    for linea in r.stdout.splitlines():
        if linea.startswith("hostname "):
            return linea.split(None, 1)[1].strip().lower() == direccion.lower()
    return False


def main():
    # El paquete puede tener los scripts en su raíz o en scripts/
    _aqui = os.path.dirname(os.path.abspath(__file__))
    aquí = _aqui if os.path.isdir(os.path.join(_aqui, "datos")) else os.path.dirname(_aqui)
    ap = argparse.ArgumentParser(description="Crea y reparte las claves SSH del inventario.")
    ap.add_argument("--csv", default=os.path.join(aquí, "datos/servidores.csv"))
    ap.add_argument("--solo", default="", help="nombres separados por comas")
    ap.add_argument("--grupo", default="", help="grupos separados por comas")
    ap.add_argument("--dry-run", action="store_true", help="enseña los comandos y no ejecuta nada")
    ap.add_argument("--solo-claves", action="store_true", help="crear las claves y no copiarlas")
    ap.add_argument("--comentario", default="",
                    help="comentario de la clave (por defecto: equipo y mes)")
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
        print("\nNo he hecho nada. Corrige esto en la hoja y vuelve a exportar:")
        for m in errores:
            print("  ERROR: %s" % m)
        sys.exit(1)

    objetivo = [f for f in filas if f["_incluir"] and f["generar_clave"] and f["clave"]]
    if a.solo:
        quiero = {s.strip().lower() for s in a.solo.split(",") if s.strip()}
        objetivo = [f for f in objetivo if f["nombre"].lower() in quiero]
    if a.grupo:
        quiero = {s.strip().lower() for s in a.grupo.split(",") if s.strip()}
        objetivo = [f for f in objetivo if f["grupo"].lower() in quiero]
    if not objetivo:
        sys.exit("No queda ninguna fila que tratar con esos filtros.")

    os.makedirs(os.path.join(SSH, "cm"), exist_ok=True)
    if not a.dry_run:
        os.chmod(SSH, 0o700)
        os.chmod(os.path.join(SSH, "cm"), 0o700)

    comentario = a.comentario or "%s-%s" % (platform.node().split(".")[0],
                                            datetime.now().strftime("%Y%m"))

    # ------------------------------------------------- 1. crear las claves
    claves = {}
    for f in objetivo:
        claves.setdefault(f["clave"], f["tipo_clave"])
    print("\n=== 1/3 · Claves (%d distintas) ===" % len(claves))
    for clave, tipo in sorted(claves.items()):
        ruta = os.path.join(SSH, clave)
        if os.path.exists(ruta):
            print(" · %s ya existe, no la toco" % clave)
            continue
        cmd = ["ssh-keygen", "-t", tipo, "-a", "100",
               "-C", "%s %s" % (clave, comentario), "-f", ruta]
        if tipo == "rsa":
            cmd[3:3] = ["-b", "4096"]
        print(" · %s: creándola (te pedirá una passphrase; ponla)" % clave)
        if correr(cmd, a.dry_run) != 0:
            sys.exit("ERROR: ssh-keygen falló para %s" % clave)
        if not a.dry_run:
            os.chmod(ruta, 0o600)
            os.chmod(ruta + ".pub", 0o644)

    # ------------------------------------------------- 2. agente y Llavero
    print("\n=== 2/3 · Agente y Llavero ===")
    for clave in sorted(claves):
        ruta = os.path.join(SSH, clave)
        cmd = (["ssh-add", "--apple-use-keychain", ruta] if ES_MAC
               else ["ssh-add", ruta])
        if correr(cmd, a.dry_run) != 0 and ES_MAC:
            correr(["ssh-add", "-K", ruta], a.dry_run)   # macOS antiguo

    if a.solo_claves:
        print("\n--solo-claves: no copio nada. Hecho.")
        return

    # ------------------------------------------------- 3. instalar en cada host
    print("\n=== 3/3 · Copiar la pública a cada servidor (%d) ===" % len(objetivo))
    hay_copy_id = shutil.which("ssh-copy-id") is not None
    resultados = []
    for f in objetivo:
        pub = os.path.join(SSH, f["clave"] + ".pub")
        usa_alias = alias_resuelve(f["nombre"], f["direccion"])
        destino = f["nombre"] if usa_alias else "%s@%s" % (f["usuario"], f["direccion"])
        print("\n--- %s (%s)%s" % (f["nombre"], destino,
                                   "" if usa_alias else "  [sin alias: uso usuario@dirección]"))
        if not usa_alias and f["salto"]:
            print("   OMITIDA: necesita el salto por %r y eso solo funciona con "
                  "~/.ssh/config.d/umh.conf instalado." % f["salto"])
            resultados.append((f["nombre"], "omitida (falta el config)"))
            continue
        if hay_copy_id:
            cmd = ["ssh-copy-id", "-i", pub]
            if not usa_alias and f["puerto"] != "22":
                cmd += ["-p", f["puerto"]]
            cmd.append(destino)
            rc = correr(cmd, a.dry_run)
        else:
            orden = "umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys"
            print("   (sin ssh-copy-id: lo hago con ssh)")
            if a.dry_run:
                print("   $ ssh %s '%s' < %s" % (destino, orden, pub))
                rc = 0
            else:
                with open(pub, "rb") as fh:
                    rc = subprocess.call(["ssh", destino, orden], stdin=fh)
        if rc != 0:
            resultados.append((f["nombre"], "FALLÓ al copiar"))
            continue
        rc2 = correr(["ssh", "-o", "PasswordAuthentication=no", "-o", "BatchMode=yes",
                      destino, "true"], a.dry_run, interactivo=False)
        if a.dry_run:
            resultados.append((f["nombre"], "(dry-run: no he ejecutado nada)"))
        else:
            resultados.append((f["nombre"], "OK, entra sin contraseña" if rc2 == 0
                               else "copiada, pero la comprobación falló"))

    # ------------------------------------------------- resumen
    print("\n%-26s %s" % ("SERVIDOR", "RESULTADO"))
    print("-" * 60)
    for nombre, estado in resultados:
        print("%-26s %s" % (nombre[:26], estado))
    print("-" * 60)
    if any("FALL" in e or "omitida" in e for _, e in resultados):
        print("Si una máquina es de arranque dual, un fallo puede significar solo que\n"
              "ahora está arrancado el otro sistema: repítelo con --solo <nombre>\n"
              "cuando toque.")
    print("""
# =====================================================================
#  PLANTILLA · añadir un servidor más a mano, sin pasar por la hoja
# ---------------------------------------------------------------------
#  1) la clave, si no comparte una ya creada:
# ssh-keygen -t ed25519 -a 100 -C "id_ed25519_nuevo %s" -f ~/.ssh/id_ed25519_nuevo
#  2) al Llavero:
# ssh-add --apple-use-keychain ~/.ssh/id_ed25519_nuevo
#  3) copiarla al servidor (última vez que escribes la contraseña):
# ssh-copy-id -i ~/.ssh/id_ed25519_nuevo.pub usuario@servidor.umh.es
#  4) comprobar que entra sin contraseña:
# ssh -o PasswordAuthentication=no usuario@servidor.umh.es 'hostname; whoami'
#  Lo normal, de todos modos, es añadir la fila a la hoja y repetir:
# python3 scripts/generar_perfiles.py --instalar && python3 scripts/generar_claves.py --solo nuevo
# =====================================================================""" % comentario)


if __name__ == "__main__":
    main()

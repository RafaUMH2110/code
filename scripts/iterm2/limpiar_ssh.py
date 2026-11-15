#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
limpiar_ssh.py · Deja ~/.ssh lo más limpio posible, con copia completa antes.

    python3 limpiar_ssh.py                         # enseña el plan, no toca nada
    python3 limpiar_ssh.py --aplicar               # lo hace (con copia previa)
    python3 limpiar_ssh.py --aplicar --claves-sobrantes
    python3 limpiar_ssh.py --aplicar --known-hosts todo

Qué hace con --aplicar:
  0. Copia ~/.ssh entero a ~/.iterm2-copias/ssh-FECHA. Todo lo que se quita
     está ahí: si algo deja de funcionar, se recupera de la copia.
  1. known_hosts: quita las entradas de los servidores del inventario
     (nombre, dirección, alias y [dirección]:puerto). Con «--known-hosts todo»
     lo vacía entero; con «no» no lo toca. La primera conexión a cada servidor
     volverá a preguntar por su huella (o la aceptará generar_claves.py
     --regenerar, que usa «accept-new»).
  2. Restos: known_hosts.old, *.bak*, *.old, *~, *.retirado-*.
  3. Sockets viejos de ~/.ssh/cm (las conexiones compartidas).
  4. Solo con --claves-sobrantes: las claves que NO están en la columna
     «clave» del inventario. OJO: entre ellas puede estar la de GitHub u otra
     que uses fuera del inventario; mira la lista del plan antes.

Las claves del inventario NO se tocan aquí: para cambiarlas por otras nuevas
sin quedarte fuera de los servidores, usa después
    python3 generar_claves.py --regenerar
que instala la nueva con ayuda de la antigua, comprueba que entra y solo
entonces retira la antigua del servidor y de este ordenador.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inventario as inv

SSH = os.path.expanduser("~/.ssh")
COPIAS = os.path.expanduser("~/.iterm2-copias")
RESTOS = ["known_hosts.old", "*.bak", "*.bak-*", "*.bak.*", "*.old", "*~",
          "*.retirado-*", "*.tmp"]
NO_TOCAR = {"config", "known_hosts", "authorized_keys", "environment", "rc"}


def es_privada(ruta):
    try:
        with open(ruta, "rb") as fh:
            cab = fh.read(64)
    except OSError:
        return False
    return b"PRIVATE KEY-----" in cab


def hosts_del_inventario(filas):
    """(host, puerto) de todas las filas, también las de «incluir = no»."""
    hs = set()
    for f in filas:
        p = f.get("puerto") or "22"
        for h in (f.get("nombre"), f.get("direccion"), f.get("alias_host")):
            if h:
                hs.add((h.lower(), p))
    return sorted(hs)


def entradas_known_hosts(kh, host, puerto):
    """Cuántas líneas de known_hosts corresponden a host (y [host]:puerto)."""
    claves = [host] + (["[%s]:%s" % (host, puerto)] if puerto != "22" else [])
    n = 0
    for c in claves:
        r = subprocess.run(["ssh-keygen", "-F", c, "-f", kh],
                           capture_output=True, text=True)
        n += sum(1 for l in r.stdout.splitlines() if l and not l.startswith("#"))
    return claves, n


def main():
    _aqui = os.path.dirname(os.path.abspath(__file__))
    aquí = _aqui if os.path.isdir(os.path.join(_aqui, "datos")) else os.path.dirname(_aqui)
    ap = argparse.ArgumentParser(description="Limpia ~/.ssh con copia previa.")
    ap.add_argument("--csv", default=os.path.join(aquí, "datos/servidores.csv"))
    ap.add_argument("--aplicar", action="store_true",
                    help="hacerlo; sin esto solo se enseña el plan")
    ap.add_argument("--known-hosts", choices=["inventario", "todo", "no"],
                    default="inventario",
                    help="qué quitar de known_hosts (por defecto, los servidores del inventario)")
    ap.add_argument("--claves-sobrantes", action="store_true",
                    help="quitar también las claves que no están en el inventario")
    a = ap.parse_args()

    if not os.path.isdir(SSH):
        sys.exit("No existe ~/.ssh: no hay nada que limpiar.")
    try:
        filas, errores, avisos = inv.leer(a.csv)
    except inv.ErrorInventario as exc:
        sys.exit("ERROR: %s" % exc)
    except FileNotFoundError:
        sys.exit("ERROR: no encuentro el CSV: %s" % a.csv)
    if errores:
        print("No he hecho nada. Corrige el inventario:")
        for m in errores:
            print("  ERROR: %s" % m)
        sys.exit(1)

    del_inventario = {f["clave"] for f in filas if f["clave"]}

    # ---------------------------------------------------------------- plan
    restos, sobrantes, propias, otros, pendientes = [], [], [], [], []
    for n in sorted(os.listdir(SSH)):
        ruta = os.path.join(SSH, n)
        if os.path.isdir(ruta) or os.path.islink(ruta):
            continue
        base = n[:-4] if n.endswith(".pub") else n
        base = base[:-5] if base.endswith("-cert") else base
        if ".antigua" in n:
            pendientes.append(n)       # regeneración a medias: no se toca
        elif any(fnmatch.fnmatch(n, p) for p in RESTOS):
            restos.append(n)
        elif n in NO_TOCAR:
            continue
        elif base in del_inventario:
            propias.append(n)
        elif es_privada(ruta) or (n.endswith(".pub") and
                                  (es_privada(os.path.join(SSH, base)) or
                                   not os.path.exists(os.path.join(SSH, base)))):
            sobrantes.append(n)
        else:
            otros.append(n)

    cm = os.path.join(SSH, "cm")
    sockets = []
    if os.path.isdir(cm):
        sockets = [n for n in sorted(os.listdir(cm))
                   if not os.path.isdir(os.path.join(cm, n))]

    confd = os.path.join(SSH, "config.d")
    ajenos_confd = []
    if os.path.isdir(confd):
        ajenos_confd = [n for n in sorted(os.listdir(confd)) if n != "servidores.conf"]

    kh = os.path.join(SSH, "known_hosts")
    kh_quitar = []
    if a.known_hosts == "inventario" and os.path.isfile(kh):
        for h, p in hosts_del_inventario(filas):
            claves, n = entradas_known_hosts(kh, h, p)
            if n:
                kh_quitar.append((claves, n))
    kh_total = 0
    if os.path.isfile(kh):
        with open(kh, encoding="utf-8", errors="replace") as fh:
            kh_total = sum(1 for l in fh if l.strip() and not l.startswith("#"))

    print("=== Plan para %s ===" % SSH)
    print("\n1. known_hosts (%d entradas ahora):" % kh_total)
    if a.known_hosts == "todo":
        print("   se vacía entero")
    elif a.known_hosts == "no":
        print("   no se toca")
    elif kh_quitar:
        for claves, n in kh_quitar:
            print("   - %-40s %d entrada(s)" % (" / ".join(claves), n))
    else:
        print("   ninguna entrada de los servidores del inventario")
    print("\n2. Restos:", ", ".join(restos) if restos else "ninguno")
    print("\n3. Sockets en cm/:", len(sockets))
    print("\n4. Claves que NO están en el inventario:",
          ", ".join(sobrantes) if sobrantes else "ninguna")
    if sobrantes:
        print("   %s" % ("SE QUITAN (--claves-sobrantes)" if a.claves_sobrantes
                         else "se quedan; para quitarlas: --claves-sobrantes"))
        print("   Antes, comprueba que ninguna es la de GitHub u otro servicio que uses.")
    print("\nSe quedan: config, known_hosts (lo que no se quite), config.d/servidores.conf"
          + (", authorized_keys" if os.path.exists(os.path.join(SSH, "authorized_keys")) else ""))
    if propias:
        print("Claves del inventario (las cambia generar_claves.py --regenerar):")
        print("   " + ", ".join(propias))
    if pendientes:
        print("Claves antiguas de una regeneración a medias (no las toco; termina con")
        print("generar_claves.py --regenerar): " + ", ".join(pendientes))
    if otros:
        print("Otros archivos que no reconozco (no los toco): " + ", ".join(otros))
    if ajenos_confd:
        print("En config.d hay más archivos (no los toco): " + ", ".join(ajenos_confd))

    if not a.aplicar:
        print("\nNo he tocado nada. Repite con --aplicar cuando lo veas bien.")
        return

    # ---------------------------------------------------------------- hacer
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    copia = os.path.join(COPIAS, "ssh-" + sello)
    os.makedirs(COPIAS, exist_ok=True)

    def ignorar(dirpath, nombres):
        # Los sockets no se pueden copiar y no sirven de nada en una copia
        return [n for n in nombres
                if stat.S_ISSOCK(os.lstat(os.path.join(dirpath, n)).st_mode)]

    shutil.copytree(SSH, copia, symlinks=True, ignore=ignorar)
    os.chmod(copia, 0o700)
    print("\n0. Copia completa: %s" % copia)

    if a.known_hosts == "todo" and os.path.isfile(kh):
        open(kh, "w").close()
        os.chmod(kh, 0o600)
        print("1. known_hosts vaciado")
    elif kh_quitar:
        for claves, _ in kh_quitar:
            for c in claves:
                subprocess.run(["ssh-keygen", "-R", c, "-f", kh],
                               capture_output=True, text=True)
        print("1. known_hosts: quitadas %d entradas" % sum(n for _, n in kh_quitar))
    old = kh + ".old"                 # lo deja ssh-keygen -R
    if os.path.exists(old):
        os.remove(old)

    for n in restos:
        if os.path.exists(os.path.join(SSH, n)):
            os.remove(os.path.join(SSH, n))
    print("2. Restos quitados: %d" % len(restos))

    for n in sockets:
        try:
            os.remove(os.path.join(cm, n))
        except OSError:
            pass
    print("3. Sockets quitados: %d" % len(sockets))

    if a.claves_sobrantes and sobrantes:
        for n in sobrantes:
            ruta = os.path.join(SSH, n)
            if not n.endswith(".pub"):
                subprocess.run(["ssh-add", "-d", ruta], capture_output=True)
            os.remove(ruta)
        print("4. Claves sobrantes quitadas: %d" % len(sobrantes))

    print("\nHecho. Lo quitado está en %s" % copia)
    print("Siguiente paso, cambiar las claves del inventario por otras nuevas:")
    print("  python3 generar_claves.py --regenerar --dry-run")
    print("  python3 generar_claves.py --regenerar")


if __name__ == "__main__":
    main()

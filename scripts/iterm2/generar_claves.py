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
    python3 generar_claves.py --regenerar --dry-run   # cambiar TODAS por nuevas

Una clave se crea UNA vez por cada valor distinto de la columna «clave», y
luego se copia una vez por cada fila que la use: así varios usuarios o varias
máquinas pueden compartirla.

Los filtros --solo y --grupo existen sobre todo para máquinas de arranque
dual: la pública hay que copiarla con cada sistema arrancado, porque cada uno
tiene su propio authorized_keys.

--regenerar cambia cada clave del inventario por una nueva sin quedarte
fuera: aparta la antigua como <clave>.antigua, crea la nueva, la instala en
cada servidor entrando con la antigua (o con contraseña si la antigua ya no
vale), comprueba que la nueva entra y SOLO ENTONCES borra la antigua del
authorized_keys de ese servidor. Cuando todos los servidores de una clave han
ido bien, la antigua sale de ~/.ssh (queda en ~/.iterm2-copias). Si alguno
falla (apagado, el otro sistema arrancado), la antigua se queda y basta con
repetir: el script retoma donde lo dejó.

Ejecuta primero generar_perfiles.py --instalar: con ~/.ssh/config.d/servidores.conf
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
import inventario as inv

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


COPIAS = os.path.expanduser("~/.iterm2-copias")

# Se añade la pública solo si no estaba: repetir no duplica líneas
ORDEN_AÑADIR = ('umask 077; mkdir -p ~/.ssh; k=$(cat); touch ~/.ssh/authorized_keys; '
                'grep -qxF "$k" ~/.ssh/authorized_keys || '
                'printf "%s\\n" "$k" >> ~/.ssh/authorized_keys')


def orden_quitar(blob):
    """Quita del authorized_keys remoto las líneas con esa pública. El blob es
    base64 (sin comillas ni espacios), así que va seguro entre comillas simples.
    Reescribe con cat > para conservar dueño y permisos. Imprime cuántas quitó."""
    return ("f=~/.ssh/authorized_keys; [ -f \"$f\" ] || { echo 0; exit 0; }; "
            "n=$(grep -cF '%s' \"$f\"); [ \"$n\" -gt 0 ] || { echo 0; exit 0; }; "
            "{ grep -vF '%s' \"$f\" || true; } > \"$f.tmp\" && cat \"$f.tmp\" > \"$f\" "
            "&& rm -f \"$f.tmp\"; echo $n" % (blob, blob))


def blob_de(pub):
    """La parte base64 de una pública (lo que identifica la clave)."""
    try:
        with open(pub, encoding="utf-8") as fh:
            partes = fh.read().split()
    except OSError:
        return ""
    return partes[1] if len(partes) >= 2 else ""


def cargar_en_agente(ruta, dry):
    """Mete una clave privada en el agente SSH.

    Por qué hace falta antes de apartar la antigua: el Llavero de macOS
    guarda la passphrase asociada a la RUTA del archivo. En cuanto la clave
    se renombra a «.antigua», el Llavero ya no la reconoce y ssh pediría la
    passphrase en cada servidor. El agente, en cambio, guarda la clave en
    memoria: da igual cómo se llame después el archivo. ssh usa la del
    agente si encuentra al lado la pública correspondiente (.pub).

    Devuelve True si la clave quedó en el agente."""
    if ES_MAC:
        # Con la ruta original el Llavero da la passphrase sin preguntar
        rc = correr(["ssh-add", "--apple-use-keychain", ruta], dry)
        if rc != 0:
            rc = correr(["ssh-add", "-K", ruta], dry)       # macOS antiguo
    else:
        rc = correr(["ssh-add", ruta], dry)
    return rc == 0


def ssh_base(f, destino, usa_alias, regenerar):
    """ssh hacia el servidor anulando RemoteCommand/RequestTTY del config
    (con ellos, ssh no admite un comando propio)."""
    cmd = ["ssh", "-o", "RemoteCommand=none", "-o", "RequestTTY=no"]
    if regenerar:
        # known_hosts recién limpiado: acepta la huella de un servidor nuevo,
        # pero sigue rechazando una que haya CAMBIADO
        cmd += ["-o", "StrictHostKeyChecking=accept-new"]
    if not usa_alias and f["puerto"] != "22":
        cmd += ["-p", f["puerto"]]
    return cmd


def alias_resuelve(nombre, direccion):
    """¿Está instalado ~/.ssh/config.d/servidores.conf y el alias apunta donde debe?"""
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
    # Carpeta del kit (donde están datos/, colores/…); se admite también
    # una subcarpeta por compatibilidad con versiones antiguas
    _aqui = os.path.dirname(os.path.abspath(__file__))
    aquí = _aqui if os.path.isdir(os.path.join(_aqui, "datos")) else os.path.dirname(_aqui)
    ap = argparse.ArgumentParser(description="Crea y reparte las claves SSH del inventario.")
    ap.add_argument("--csv", default=os.path.join(aquí, "datos/servidores.csv"))
    ap.add_argument("--solo", default="", help="nombres separados por comas")
    ap.add_argument("--grupo", default="", help="grupos separados por comas")
    ap.add_argument("--dry-run", action="store_true", help="enseña los comandos y no ejecuta nada")
    ap.add_argument("--solo-claves", action="store_true", help="crear las claves y no copiarlas")
    ap.add_argument("--regenerar", action="store_true",
                    help="cambiar cada clave por una nueva y retirar la antigua de "
                         "los servidores (no admite --solo ni --grupo)")
    ap.add_argument("--comentario", default="",
                    help="nombre de este ordenador para el comentario de la "
                         "clave; por defecto, datos/maquina.txt")
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
    if a.regenerar and (a.solo or a.grupo or a.solo_claves):
        sys.exit("--regenerar va con todo el inventario: una clave nueva deja sin "
                 "acceso a los demás servidores que compartían la antigua.")
    if a.regenerar:
        en_uso = {f["clave"] for f in objetivo}
        fuera = [f for f in filas if not f["_incluir"] and f["clave"] in en_uso]
        if fuera:
            print("AVISO: estas filas tienen «incluir = no» pero comparten clave con")
            print("otras que sí se regeneran. No recibirán la nueva y la antigua se")
            print("retirará de este ordenador: pon «incluir = si» si quieres mantenerlas.")
            for f in fuera:
                print("   - %s (%s)" % (f["nombre"], f["clave"]))

    os.makedirs(os.path.join(SSH, "cm"), exist_ok=True)
    if not a.dry_run:
        os.chmod(SSH, 0o700)
        os.chmod(os.path.join(SSH, "cm"), 0o700)

    # El comentario identifica DE QUÉ ORDENADOR es la clave cuando dentro de
    # dos años leas el authorized_keys del servidor.
    maquina = a.comentario
    if not maquina:
        ruta = os.path.join(aquí, "datos", "maquina.txt")
        if os.path.isfile(ruta):
            with open(ruta, encoding="utf-8") as fh:
                maquina = fh.read().strip()
    if not maquina:
        maquina = platform.node().split(".")[0]
    comentario = "%s %s" % (maquina, datetime.now().strftime("%Y-%m"))

    # ------------------------------------------------- 1. crear las claves
    claves = {}
    for f in objetivo:
        claves.setdefault(f["clave"], f["tipo_clave"])
    if a.regenerar:
        # Si quedó alguna .antigua, una regeneración anterior está a medias:
        # se retoma SOLO esa, para no volver a cambiar las que ya terminaron.
        pendientes = {c for c in claves if os.path.exists(os.path.join(SSH, c + ".antigua"))}
        if pendientes:
            print("\nRetomo la regeneración pendiente de: %s" % ", ".join(sorted(pendientes)))
            print("(las demás claves ya se cambiaron y no se tocan)")
            claves = {c: t for c, t in claves.items() if c in pendientes}
            objetivo = [f for f in objetivo if f["clave"] in pendientes]
    antiguas = {}      # clave -> blob de la pública antigua (para retirarla)
    print("\n=== 1/3 · Claves (%d distintas) ===" % len(claves))
    for clave, tipo in sorted(claves.items()):
        ruta = os.path.join(SSH, clave)
        vieja = ruta + ".antigua"
        if a.regenerar and os.path.exists(vieja):
            # Una ejecución anterior se quedó a medias: la antigua sigue apartada
            antiguas[clave] = blob_de(vieja + ".pub")
            print(" · %s: retomo (la antigua ya estaba apartada)" % clave)
            # El Llavero no la conoce con este nombre: se pide la passphrase
            # una sola vez para el agente, en vez de una vez por servidor.
            if not cargar_en_agente(vieja, a.dry_run):
                print("   (no se cargó: en cada servidor te pedirá su passphrase; si no\n"
                      "    la recuerdas, pulsa Enter y entrarás con la contraseña)")
        elif a.regenerar and os.path.exists(ruta):
            antiguas[clave] = blob_de(ruta + ".pub")
            # Primero al agente, con su nombre de siempre (el Llavero la
            # reconoce y no pregunta). Desde ahí se entra a cada servidor
            # para instalar la nueva. Sale del agente al terminar.
            print(" · %s: la cargo en el agente para entrar con ella" % clave)
            if not cargar_en_agente(ruta, a.dry_run):
                print("   (no se cargó: en cada servidor te pedirá su passphrase; si no\n"
                      "    la recuerdas, pulsa Enter y entrarás con la contraseña)")
            print(" · %s: aparto la antigua como %s.antigua" % (clave, clave))
            if not a.dry_run:
                os.rename(ruta, vieja)
                if os.path.exists(ruta + ".pub"):
                    os.rename(ruta + ".pub", vieja + ".pub")
                if os.path.exists(ruta + "-cert.pub"):
                    os.remove(ruta + "-cert.pub")   # el certificado era de la antigua
        if os.path.exists(ruta) and not (a.regenerar and a.dry_run and clave in antiguas
                                         and not os.path.exists(vieja)):
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
    resultados = []
    fallos_por_clave = {}
    for f in objetivo:
        pub = os.path.join(SSH, f["clave"] + ".pub")
        nueva = os.path.join(SSH, f["clave"])
        vieja = nueva + ".antigua"
        usa_alias = alias_resuelve(f["nombre"], f["direccion"])
        destino = f["nombre"] if usa_alias else "%s@%s" % (f["usuario"], f["direccion"])
        print("\n--- %s (%s)%s" % (f["nombre"], destino,
                                   "" if usa_alias else "  [sin alias: uso usuario@dirección]"))
        if not usa_alias and f["salto"]:
            print("   OMITIDA: necesita el salto por %r y eso solo funciona con "
                  "~/.ssh/config.d/servidores.conf instalado." % f["salto"])
            resultados.append((f["nombre"], "omitida (falta el config)"))
            fallos_por_clave.setdefault(f["clave"], []).append(f["nombre"])
            continue
        base = ssh_base(f, destino, usa_alias, a.regenerar)
        # Para entrar: la clave del config (la nueva, que aún no está) y, al
        # regenerar, la antigua; si ninguna vale, ssh pide la contraseña.
        entrar = base + (["-i", vieja] if a.regenerar and (os.path.exists(vieja) or a.dry_run)
                         else [])
        print("   $ %s '<añadir la pública si no está>' < %s"
              % (" ".join(shlex.quote(c) for c in entrar + [destino]), pub))
        if a.dry_run:
            rc = 0
        else:
            with open(pub, "rb") as fh:
                rc = subprocess.call(entrar + [destino, ORDEN_AÑADIR], stdin=fh)
        if rc != 0:
            resultados.append((f["nombre"], "FALLÓ al copiar"))
            fallos_por_clave.setdefault(f["clave"], []).append(f["nombre"])
            continue
        probar = base + ["-o", "PasswordAuthentication=no", "-o", "BatchMode=yes",
                         "-o", "IdentitiesOnly=yes", "-i", nueva, destino, "true"]
        rc2 = correr(probar, a.dry_run, interactivo=False)
        if a.dry_run:
            estado = "(dry-run: no he ejecutado nada)"
        elif rc2 != 0:
            estado = "copiada, pero la comprobación falló"
            fallos_por_clave.setdefault(f["clave"], []).append(f["nombre"])
        else:
            estado = "OK, entra sin contraseña"
        blob = antiguas.get(f["clave"], "")
        if a.regenerar and (rc2 == 0 or a.dry_run) and blob and (a.dry_run or blob != blob_de(pub)):
            # Solo con la nueva comprobada: entrar con ella y borrar la antigua
            orden = base + ["-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                            "-i", nueva, destino]
            print("   $ %s '<quitar la pública antigua de authorized_keys>'"
                  % " ".join(shlex.quote(c) for c in orden))
            if not a.dry_run:
                r = subprocess.run(orden + [orden_quitar(blob)],
                                   capture_output=True, text=True)
                n = (r.stdout.strip().splitlines() or ["?"])[-1]
                estado += ("; antigua retirada (%s línea/s)" % n if r.returncode == 0
                           else "; NO pude retirar la antigua")
        resultados.append((f["nombre"], estado))

    # Antiguas que ya no hacen falta: fuera de ~/.ssh
    if a.regenerar and not a.dry_run:
        sello = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino_copias = os.path.join(COPIAS, "claves-antiguas-" + sello)
        for clave in sorted(claves):
            vieja = os.path.join(SSH, clave + ".antigua")
            if not os.path.exists(vieja):
                continue
            if fallos_por_clave.get(clave):
                print("\n%s.antigua se queda en ~/.ssh: falta(n) %s. Repite con "
                      "--regenerar cuando estén accesibles." % (clave, ", ".join(fallos_por_clave[clave])))
                continue
            if os.path.exists(vieja + ".pub"):
                subprocess.run(["ssh-add", "-d", vieja + ".pub"], capture_output=True)
            os.makedirs(destino_copias, mode=0o700, exist_ok=True)
            for ext in ("", ".pub"):
                if os.path.exists(vieja + ext):
                    shutil.move(vieja + ext, os.path.join(destino_copias,
                                                          os.path.basename(vieja + ext)))
            print("\n%s.antigua retirada de ~/.ssh (copia en %s)" % (clave, destino_copias))

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
# ssh-copy-id -i ~/.ssh/id_ed25519_nuevo.pub usuario@servidor.example.es
#  4) comprobar que entra sin contraseña:
# ssh -o PasswordAuthentication=no usuario@servidor.example.es 'hostname; whoami'
#  Lo normal, de todos modos, es añadir la fila a la hoja y repetir:
# python3 generar_perfiles.py --instalar && python3 generar_claves.py --solo nuevo
# =====================================================================""" % comentario)


if __name__ == "__main__":
    main()

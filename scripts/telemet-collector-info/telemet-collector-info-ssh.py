#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
telemet-collector-info-ssh.py  ·  TeleMet Collector parameters on a REMOTE server, from your computer

Runs on YOUR computer (Linux, macOS or Windows with the OpenSSH client), connects by SSH
to the server where telemet-collector is installed (password or key) and shows the same
report as telemet-collector-info.py. Nothing is installed on the server: the report script is
sent through the SSH connection, runs there (with sudo if needed) and is not left on disk.

Requirements
  · Local: Python 3.7+ and the `ssh` command (OpenSSH). telemet-collector-info.py must be in
    the same folder as this script (it is the report that gets sent).
  · Remote: python3 and, if you are not root, a user that can run sudo.

Usage (CLI or VS Code, see MANUAL.md):
    python3 telemet-collector-info-ssh.py rafa@192.168.0.129
    python3 telemet-collector-info-ssh.py rafa@servidor -i ~/.ssh/id_rsa
    python3 telemet-collector-info-ssh.py rafa@servidor:2222 --ask-password
    python3 telemet-collector-info-ssh.py mi-alias-de-ssh-config --show-key
    python3 telemet-collector-info-ssh.py srv1 srv2 srv3 --json
    python3 telemet-collector-info-ssh.py                    # no arguments: asks for what it needs
    python3 telemet-collector-info-ssh.py rafa@servidor --check   # only checks the connection

Login with authorized_keys (public key):
    python3 telemet-collector-info-ssh.py rafa@servidor --check-key     # does key-only login work? + server audit
    python3 telemet-collector-info-ssh.py rafa@servidor --install-key   # copies your public key (asks the password once)
    python3 telemet-collector-info-ssh.py --generate-key                # creates an RSA 4096 key pair if you have none
"""

import argparse
import base64
import getpass
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = "telemet-collector-info.py"
PW_ENV = "TELEMET_SSH_PASSWORD"          # env var read by the temporary askpass helper
TARGET_RE = re.compile(r"^(?:(?P<user>[^@]+)@)?(?P<host>\[[^\]]+\]|[^:@]+)(?::(?P<port>\d+))?$")

T = {
    "es": {
        "no_ssh": "No se encuentra el comando 'ssh'. Instala el cliente OpenSSH (Windows: Configuración > Aplicaciones > Características opcionales > Cliente OpenSSH).",
        "no_payload": "No se encuentra %s junto a este script (%s).",
        "bad_target": "Destino no válido: '%s' (formato: [usuario@]servidor[:puerto] o un alias de ~/.ssh/config).",
        "ask_target": "Servidor [usuario@]host[:puerto] (también vale un alias de ~/.ssh/config): ",
        "ask_pw": "Contraseña SSH de %s (Enter = usar clave / ssh-agent): ",
        "ask_sudo": "Contraseña de sudo en %s (Enter = ninguna / NOPASSWD): ",
        "env_empty": "La variable de entorno %s está vacía o no existe.",
        "connecting": "Conectando con %s …",
        "ssh_fail": "No se pudo conectar por SSH con %s (código 255). Revisa servidor, puerto, usuario, contraseña o clave y la huella del servidor.",
        "ssh_hint_hostkey": "Pista: es la primera vez que te conectas; usa --accept-new-host-key o conéctate antes una vez con 'ssh %s'.",
        "ssh_hint_batch": "Pista: con --batch / sin terminal no se puede pedir contraseña: usa clave, --ask-password o --password-env.",
        "sudo_fail": "sudo necesita contraseña en %s y no se ha podido autenticar.",
        "sudo_hint": "Usa --ask-sudo-password, --sudo-password-env VAR, o configura sudo sin contraseña para este usuario (NOPASSWD).",
        "py_missing": "El servidor no tiene python3 (o la ruta --remote-python es incorrecta).",
        "retry_sudo": "sudo pide contraseña. ",
        "check_title": "Comprobación de conexión con %s",
        "done_hosts": "Terminado: %d servidor(es), %d con errores.",
        "key_title": "Acceso por clave SSH (authorized_keys) en %s",
        "key_ok": "Acceso por clave correcto: entras en %s como '%s' sin contraseña.",
        "key_used": "Clave usada: %s",
        "key_agent": "ssh-agent",
        "key_fail": "El servidor NO admite el acceso solo con clave desde este equipo.",
        "key_hint_nokeys": "ssh no tiene ninguna clave privada que ofrecer. Indica una con -i RUTA, cárgala en ssh-agent o créala con --generate-key.",
        "key_hint_notauth": "La clave se ha ofrecido pero el servidor no la ha aceptado: o no está en authorized_keys, o sshd la ignora por permisos incorrectos. --install-key la añade (si falta) y corrige los permisos de ~/.ssh y authorized_keys; pide la contraseña una sola vez.",
        "key_hint_other": "Revisa en el servidor los permisos (chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; tu carpeta personal no escribible por otros), PubkeyAuthentication y el log (journalctl -u ssh).",
        "key_hint_audit": "Para diagnosticar el servidor añade --ask-password y se auditará authorized_keys.",
        "key_audit": "Auditoría de authorized_keys en el servidor:",
        "key_gen": "Creando clave RSA 4096 en %s …",
        "key_gen_exists": "Ya existe la clave %s: no se sobrescribe.",
        "key_gen_fail": "ssh-keygen ha fallado (código %d).",
        "key_no_pub": "No hay clave pública que instalar. Usa --generate-key, --pubkey FICHERO.pub o -i CLAVE.",
        "key_bad_pub": "El fichero %s no contiene una clave pública válida.",
        "key_installing": "Instalando %s en %s …",
        "key_added": "Clave añadida a authorized_keys (%s).",
        "key_already": "La clave ya estaba autorizada (%s): no se ha duplicado.",
        "key_install_fail": "No se pudo instalar la clave en %s (código %d).",
        "key_pw_needed": "Necesito la contraseña SSH para instalar la clave; usa --ask-password o --password-env VAR (o ejecútalo en una terminal).",
        "key_json_skip": "(sin clave pública que validar)",
    },
    "en": {
        "no_ssh": "The 'ssh' command was not found. Install the OpenSSH client (Windows: Settings > Apps > Optional features > OpenSSH Client).",
        "no_payload": "%s was not found next to this script (%s).",
        "bad_target": "Invalid target: '%s' (format: [user@]host[:port] or an alias from ~/.ssh/config).",
        "ask_target": "Server [user@]host[:port] (an alias from ~/.ssh/config also works): ",
        "ask_pw": "SSH password for %s (Enter = use key / ssh-agent): ",
        "ask_sudo": "sudo password on %s (Enter = none / NOPASSWD): ",
        "env_empty": "The environment variable %s is empty or missing.",
        "connecting": "Connecting to %s …",
        "ssh_fail": "Could not connect by SSH to %s (code 255). Check server, port, user, password or key, and the server fingerprint.",
        "ssh_hint_hostkey": "Hint: this is the first connection; use --accept-new-host-key or connect once beforehand with 'ssh %s'.",
        "ssh_hint_batch": "Hint: with --batch / no terminal a password cannot be asked: use a key, --ask-password or --password-env.",
        "sudo_fail": "sudo needs a password on %s and authentication failed.",
        "sudo_hint": "Use --ask-sudo-password, --sudo-password-env VAR, or set up passwordless sudo for this user (NOPASSWD).",
        "py_missing": "The server has no python3 (or the --remote-python path is wrong).",
        "retry_sudo": "sudo asks for a password. ",
        "check_title": "Connection check with %s",
        "done_hosts": "Finished: %d server(s), %d with errors.",
        "key_title": "SSH key login (authorized_keys) on %s",
        "key_ok": "Key login works: you get into %s as '%s' without a password.",
        "key_used": "Key used: %s",
        "key_agent": "ssh-agent",
        "key_fail": "The server does NOT accept key-only login from this computer.",
        "key_hint_nokeys": "ssh has no private key to offer. Give one with -i PATH, load it into ssh-agent or create it with --generate-key.",
        "key_hint_notauth": "The key was offered but the server did not accept it: either it is not in authorized_keys or sshd ignores it because of wrong permissions. --install-key adds it (if missing) and fixes the permissions of ~/.ssh and authorized_keys; it asks the password once.",
        "key_hint_other": "Check on the server the permissions (chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; home not writable by others), PubkeyAuthentication and the log (journalctl -u ssh).",
        "key_hint_audit": "To diagnose the server add --ask-password and authorized_keys will be audited.",
        "key_audit": "authorized_keys audit on the server:",
        "key_gen": "Creating RSA 4096 key at %s …",
        "key_gen_exists": "The key %s already exists: not overwritten.",
        "key_gen_fail": "ssh-keygen failed (code %d).",
        "key_no_pub": "There is no public key to install. Use --generate-key, --pubkey FILE.pub or -i KEY.",
        "key_bad_pub": "The file %s does not contain a valid public key.",
        "key_installing": "Installing %s on %s …",
        "key_added": "Key added to authorized_keys (%s).",
        "key_already": "The key was already authorized (%s): not duplicated.",
        "key_install_fail": "Could not install the key on %s (code %d).",
        "key_pw_needed": "The SSH password is needed to install the key; use --ask-password or --password-env VAR (or run it in a terminal).",
        "key_json_skip": "(no public key to check)",
    },
}


def default_lang():
    return "es" if (os.environ.get("LANG") or os.environ.get("LC_ALL") or "es").lower().startswith("es") else "en"


# ----------------------------------------------------------------------------- remote command
PY_CODE = ("import base64,sys,zlib;src=zlib.decompress(base64.b64decode(sys.argv.pop(1)));"
           "sys.argv[0]='telemet-collector-info.py';"
           "exec(compile(src,'telemet-collector-info.py','exec'),"
           "{'__name__':'__main__','__file__':'/opt/telemet-collector/telemet-collector-info.py'})")


def sudo_prefix(use_sudo):
    # `set --` keeps the empty argument of -p '' (a plain variable would lose it)
    if not use_sudo:
        return "set --; "
    return 'if [ "$(id -u)" -ne 0 ]; then set -- sudo -S -p ""; else set --; fi; '


def remote_report_command(payload, info_args, use_sudo, python):
    b64 = base64.b64encode(zlib.compress(payload, 9)).decode("ascii")
    script = "%s\"$@\" %s -c \"%s\" %s %s" % (
        sudo_prefix(use_sudo), shlex.quote(python), PY_CODE, shlex.quote(b64),
        " ".join(shlex.quote(a) for a in info_args))
    return "sh -c " + shlex.quote(script)


def remote_check_command(config_path, use_sudo, python):
    script = (
        'echo "user=$(id -un) uid=$(id -u) host=$(hostname)"; '
        '%(py)s --version 2>&1 || echo "python=MISSING"; '
        'ls -l %(cfg)s 2>&1; '
        'if [ "$(id -u)" -eq 0 ]; then echo "sudo=not needed (root)"; '
        'elif sudo -n true 2>/dev/null; then echo "sudo=OK without password"; '
        'else echo "sudo=needs password (or not allowed)"; fi; '
        'for s in telemet-collector telemet-colector; do '
        'if [ -f /etc/systemd/system/$s.service ]; then echo "service $s=installed ($(systemctl is-active $s 2>/dev/null))"; fi; done'
    ) % {"py": shlex.quote(python), "cfg": shlex.quote(config_path)}
    return "sh -c " + shlex.quote(script)


# ----------------------------------------------------------------------------- ssh
def parse_target(text):
    """[user@]host[:port] -> (user, host, port). A bare alias of ~/.ssh/config also matches."""
    m = TARGET_RE.match(text.strip())
    if not m:
        return None
    host = m.group("host")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return m.group("user"), host, m.group("port")


def make_askpass():
    d = tempfile.mkdtemp(prefix="telemet-ssh-")
    if os.name == "nt":
        p = os.path.join(d, "askpass.cmd")
        with open(p, "w") as f:
            f.write("@echo off\r\necho %" + PW_ENV + "%\r\n")
    else:
        p = os.path.join(d, "askpass.sh")
        with open(p, "w") as f:
            # does not answer host-key questions (yes/no): those must be accepted explicitly
            f.write('#!/bin/sh\ncase "$1" in *yes/no*|*fingerprint*) exit 1;; esac\n'
                    'printf "%%s\\n" "$%s"\n' % PW_ENV)
        os.chmod(p, 0o700)
    return d, p


def ssh_base(a, user, host, port, password, key_only=False):
    cmd = [a.ssh_path]
    if port or a.port:
        cmd += ["-p", str(port or a.port)]
    if a.identity:
        cmd += ["-i", os.path.expanduser(a.identity), "-o", "IdentitiesOnly=yes"]
    cmd += ["-o", "ConnectTimeout=%d" % a.connect_timeout, "-o", "ServerAliveInterval=15",
            "-o", "ForwardAgent=no", "-o", "ForwardX11=no", "-T"]
    if key_only:
        # key-only login test: no passwords at all; -v tells which key was offered/accepted
        # (LogLevel is not set: the first -o LogLevel would win over -v)
        cmd += ["-v", "-o", "PreferredAuthentications=publickey", "-o", "PubkeyAuthentication=yes",
                "-o", "PasswordAuthentication=no", "-o", "KbdInteractiveAuthentication=no", "-o", "BatchMode=yes"]
    else:
        cmd += ["-o", "LogLevel=ERROR"]
    if a.accept_new_host_key:
        cmd += ["-o", "StrictHostKeyChecking=accept-new"]
    if a.batch and not key_only:
        cmd += ["-o", "BatchMode=yes"]
    if password is not None:
        cmd += ["-o", "NumberOfPasswordPrompts=1"]
    for extra in a.ssh_arg or []:
        cmd += shlex.split(extra)
    user = user or a.user
    cmd.append("%s@%s" % (user, host) if user else host)
    return cmd


def run_ssh(a, user, host, port, remote_cmd, password, sudo_password, key_only=False):
    """Runs the command on the server and returns (code, stdout, stderr)."""
    cmd = ssh_base(a, user, host, port, None if key_only else password, key_only) + [remote_cmd]
    if key_only:
        password = None
    env = dict(os.environ)
    kwargs = {}
    tmpdir = None
    if password is not None:
        tmpdir, askpass = make_askpass()
        env.update({"SSH_ASKPASS": askpass, "SSH_ASKPASS_REQUIRE": "force", PW_ENV: password,
                    "DISPLAY": env.get("DISPLAY") or "none:0"})
        if os.name != "nt":
            kwargs["start_new_session"] = True      # no controlling terminal -> ssh uses the askpass helper
    stdin = ((sudo_password or "") + "\n").encode("utf-8") if sudo_password else b""
    try:
        r = subprocess.run(cmd, input=stdin, capture_output=True, env=env, timeout=a.timeout, **kwargs)
        return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 124, "", "timeout (%d s)\n" % a.timeout
    finally:
        env.pop(PW_ENV, None)
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


SUDO_FAIL = re.compile(r"sudo: (a password is required|no password was provided|\d+ incorrect password|"
                       r"Sorry, try again|a terminal is required)", re.I)



# ----------------------------------------------------------------------------- authorized_keys
PUB_RE = re.compile(r"^((?:ssh-(?:rsa|dss|ed25519)|ecdsa-sha2-nistp\d+|sk-[a-z0-9@.-]+))\s+([A-Za-z0-9+/]+={0,3})(?:\s+(.*))?$")
OFFER_RE = re.compile(r"Offering public key: (.+?) (SHA256:\S+)")
ACCEPT_RE = re.compile(r"Server accepts key: (.+?) (SHA256:\S+)")
AUTH_OK_RE = re.compile(r'Authenticated to .* using "publickey"|Authentication succeeded \(publickey\)')
DEBUG_RE = re.compile(r"^(debug\d:|OpenSSH_)")


def clean_err(err):
    """ssh -v stderr without the debug noise."""
    return "\n".join(l for l in err.splitlines() if not DEBUG_RE.match(l)).strip()


def remote_install_key_command(pubkey):
    script = (
        'umask 077; KEY="$1"; B64=$(printf "%s" "$KEY" | awk \'{print $2}\'); '
        'D="$HOME/.ssh"; F="$D/authorized_keys"; '
        'mkdir -p "$D" && chmod 700 "$D" || exit 20; '
        '[ -e "$F" ] || : > "$F"; chmod 600 "$F"; '
        'if grep -qF -- "$B64" "$F"; then echo "KEY=already"; else '
        '  if [ -s "$F" ] && [ -n "$(tail -c1 "$F")" ]; then echo >> "$F"; fi; '
        '  printf "%s\\n" "$KEY" >> "$F" && echo "KEY=added"; fi; '
        'echo "FILE=$F"; '
        'command -v restorecon >/dev/null 2>&1 && restorecon -R "$D" >/dev/null 2>&1; true')
    return "sh -c %s sh %s" % (shlex.quote(script), shlex.quote(pubkey))


def ssh_keygen_path(a):
    return shutil.which("ssh-keygen") or os.path.join(os.path.dirname(a.ssh_path) or ".", "ssh-keygen")


def read_pub(path):
    """First valid public-key line of a file -> (line, comment) or None."""
    try:
        for line in open(path, encoding="utf-8", errors="replace").read().splitlines():
            m = PUB_RE.match(line.strip())
            if m:
                return line.strip()
    except OSError:
        pass
    return None


def find_pubkey(a, t):
    """Public key to install: --pubkey, <identity>.pub (or derived from the private key), ~/.ssh/id_*.pub."""
    ssh_dir = os.path.join(os.path.expanduser("~"), ".ssh")
    if a.pubkey:
        p = os.path.expanduser(a.pubkey)
        line = read_pub(p)
        if not line:
            print(t["key_bad_pub"] % p, file=sys.stderr)
            return None, p
        return line, p
    if a.identity:
        priv = os.path.expanduser(a.identity)
        cands = [priv if priv.endswith(".pub") else priv + ".pub"]
        for p in cands:
            if read_pub(p):
                return read_pub(p), p
        if os.path.isfile(priv):     # private key without .pub: derive it
            r = subprocess.run([ssh_keygen_path(a), "-y", "-f", priv], capture_output=True, text=True, stdin=subprocess.DEVNULL)
            if r.returncode == 0 and PUB_RE.match(r.stdout.strip()):
                return r.stdout.strip(), priv + " (-y)"
        return None, cands[0]
    for name in ("id_ed25519", "id_rsa", "id_ecdsa"):
        p = os.path.join(ssh_dir, name + ".pub")
        if read_pub(p):
            return read_pub(p), p
    return None, os.path.join(ssh_dir, "id_rsa.pub")


def generate_key(a, t, interactive):
    """RSA 4096 key pair. It never overwrites an existing private key."""
    priv = os.path.expanduser(a.identity) if a.identity else os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa")
    if priv.endswith(".pub"):
        priv = priv[:-4]
    if os.path.exists(priv):
        print(t["key_gen_exists"] % priv)
        return 0
    os.makedirs(os.path.dirname(priv), mode=0o700, exist_ok=True)
    print(t["key_gen"] % priv)
    cmd = [ssh_keygen_path(a), "-q", "-t", "rsa", "-b", "4096", "-C", "telemet-info@%s" % socket.gethostname(), "-f", priv]
    if not interactive:
        cmd += ["-N", ""]
    rc = subprocess.run(cmd).returncode
    if rc:
        print(t["key_gen_fail"] % rc, file=sys.stderr)
        return 3
    print("  " + priv + "\n  " + priv + ".pub")
    a.identity = a.identity or priv
    return 0


def key_login_check(a, user, host, port):
    """Key-only login test. Returns a dict (ok, reason, key, user, host, error)."""
    code, out, err = run_ssh(a, user, host, port, "echo KEYLOGIN_OK; id -un; hostname", None, None, key_only=True)
    res = {"ok": False, "exit_code": code, "key": None, "method": None, "user": None, "host": None, "reason": None, "error": ""}
    offered = OFFER_RE.findall(err)
    accepted = ACCEPT_RE.findall(err)
    used = accepted[-1] if accepted else None
    if used:
        where, fp = used
        res["key"] = {"fingerprint": fp, "source": where.split(" ")[0] if "/" in where or "\\" in where else "agent",
                      "description": where}
    if code == 0 and "KEYLOGIN_OK" in out:
        lines = out.splitlines()
        i = lines.index("KEYLOGIN_OK")
        res.update(ok=True, user=lines[i + 1].strip() if len(lines) > i + 1 else user,
                   host=lines[i + 2].strip() if len(lines) > i + 2 else host)
        res["method"] = "publickey" if AUTH_OK_RE.search(err) else "publickey?"
        return res
    res["error"] = clean_err(err)
    if code == 124:
        res["reason"] = "timeout"
    elif code == 255 and "Permission denied" in err:
        res["reason"] = "not_authorized" if offered else "no_keys"
    elif code == 255:
        res["reason"] = "connection"
    else:
        res["reason"] = "other"
    return res


def print_key_result(a, t, label, kr):
    print("== " + t["key_title"] % label + " ==")
    if kr["ok"]:
        print("\033[32m✔\033[0m " if a.color_on else "✔ ", end="")
        print(t["key_ok"] % (kr["host"] or label, kr["user"]))
        if kr["key"]:
            src = t["key_agent"] if kr["key"]["source"] == "agent" else kr["key"]["source"]
            print("  " + t["key_used"] % ("%s  %s" % (kr["key"]["fingerprint"], src)))
        return
    print(("\033[31m✘\033[0m " if a.color_on else "✘ ") + t["key_fail"])
    if kr["reason"] == "connection" or kr["reason"] == "timeout":
        print("  " + (t["ssh_fail"] % label))
        if kr["error"]:
            print("  " + kr["error"].replace("\n", "\n  "))
        return
    hint = {"no_keys": "key_hint_nokeys", "not_authorized": "key_hint_notauth"}.get(kr["reason"], "key_hint_other")
    print("  " + t[hint])


def key_mode(a, t, targets, payload, password, interactive):
    """--install-key / --check-key."""
    results, worst = {}, 0
    pub = None
    if a.install_key:
        pub, pub_path = find_pubkey(a, t)
        if not pub:
            if pub_path and not a.pubkey:
                print(t["key_no_pub"], file=sys.stderr)
            return 3
        if password is None and interactive:
            password = getpass.getpass(t["ask_pw"] % ", ".join(targets))
            password = password or None
    if not a.identity:
        # validate with the private key that matches the public key we use (ssh would not find it if it is not a default one)
        _, ppath = (pub, pub_path) if a.install_key else ((None, os.path.expanduser(a.pubkey)) if a.pubkey else find_pubkey(a, t))
        priv = ppath[:-4] if ppath and ppath.endswith(".pub") else None
        if priv and os.path.isfile(priv):
            a.identity = priv
    a.color_on = a.color is True or (a.color is None and sys.stdout.isatty() and not a.json)
    for target in targets:
        pt = parse_target(target)
        if not pt:
            print(t["bad_target"] % target, file=sys.stderr)
            worst = max(worst, 3)
            continue
        user, host, port = pt
        res = {}
        log = sys.stderr if a.json else sys.stdout
        if a.install_key:
            comment = pub.split(None, 2)[2] if len(pub.split(None, 2)) > 2 else pub.split()[0]
            print(t["key_installing"] % (comment, target), file=log)
            code, out, err = run_ssh(a, user, host, port, remote_install_key_command(pub), password, None)
            if code != 0:
                print(t["key_install_fail"] % (target, code), file=sys.stderr)
                if err.strip():
                    print(err.rstrip(), file=sys.stderr)
                if code == 255 and password is None:
                    print(t["key_pw_needed"], file=sys.stderr)
                worst = max(worst, 4)
                continue
            info = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
            res["install"] = {"result": info.get("KEY"), "file": info.get("FILE")}
            print((t["key_added"] if info.get("KEY") == "added" else t["key_already"]) % info.get("FILE", "?"), file=log)
        # validation: key only, with no password
        kr = key_login_check(a, user, host, port)
        res["key_login"] = kr
        if not a.json:
            print_key_result(a, t, target, kr)
        # audit of authorized_keys on the server (needs a working login: key, or password if there is one)
        audit_pw = None if kr["ok"] else password
        if kr["ok"] or audit_pw is not None:
            args = ["--lang", a.lang, "--keys-only"] + (["--json"] if a.json else []) + (["--color"] if a.color_on else [])
            code, out, err = run_ssh(a, user, host, port, remote_report_command(payload, args, False, a.remote_python),
                                     audit_pw, None)
            if a.json:
                try:
                    res["audit"] = json.loads(out)
                except ValueError:
                    res["audit"] = {"error": clean_err(err) or "no JSON received"}
            else:
                print("\n" + t["key_audit"])
                sys.stdout.write(out)
                if code not in (0, 1) and err.strip():
                    print(err.rstrip(), file=sys.stderr)
            if code == 1 and kr["ok"]:
                worst = max(worst, 1)
        elif not a.json and kr["reason"] not in ("connection", "timeout"):
            print("  " + t["key_hint_audit"])
        if not kr["ok"]:
            worst = max(worst, 5 if kr["reason"] in ("no_keys", "not_authorized", "other") else 4)
        results[target] = res
    if a.json:
        print(json.dumps(next(iter(results.values())) if len(results) == 1 and len(targets) == 1 else results,
                         indent=2, ensure_ascii=False))
    return worst


def secret(env_name, t):
    v = os.environ.get(env_name)
    if not v:
        sys.exit(t["env_empty"] % env_name)
    return v


def info_args_from(a):
    out = ["--lang", a.lang]
    if a.config:
        out += ["-c", a.config]
    if a.service:
        out += ["--service", a.service]
    if a.no_service:
        out.append("--no-service")
    if a.show_key:
        out.append("--show-key")
    if a.authorized_keys:
        out.append("--authorized-keys")
    if a.json:
        out.append("--json")
    if a.color is True or (a.color is None and sys.stdout.isatty() and not a.json):
        out.append("--color")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Shows the TeleMet Collector parameters of one or several remote servers (SSH, password or key).")
    ap.add_argument("targets", nargs="*", help="[user@]host[:port] or an alias from ~/.ssh/config (one or several)")
    g = ap.add_argument_group("connection")
    g.add_argument("-u", "--user", help="SSH user (if not in the target)")
    g.add_argument("-p", "--port", type=int, help="SSH port (if not in the target)")
    g.add_argument("-i", "--identity", metavar="KEY", help="private key (RSA, ed25519…), e.g. ~/.ssh/id_rsa")
    g.add_argument("--ask-password", action="store_true", help="ask for the SSH password here (hidden) and use it")
    g.add_argument("--password-env", metavar="VAR", help="read the SSH password from this environment variable")
    g.add_argument("--accept-new-host-key", action="store_true",
                   help="trust the fingerprint of a server seen for the first time (StrictHostKeyChecking=accept-new)")
    g.add_argument("--batch", action="store_true", help="never ask anything (BatchMode): for scripts and cron")
    g.add_argument("--ssh-arg", action="append", metavar="'OPTS'", help="extra option for ssh, e.g. --ssh-arg '-J bastion' (repeatable)")
    g.add_argument("--ssh-path", default=shutil.which("ssh") or "ssh", help="path of the ssh command")
    g.add_argument("--connect-timeout", type=int, default=15, help="seconds to connect (default 15)")
    g.add_argument("--timeout", type=int, default=90, help="total seconds per server (default 90)")
    s = ap.add_argument_group("sudo on the server")
    s.add_argument("--no-sudo", action="store_true", help="do not use sudo (the user can already read config.ini)")
    s.add_argument("--ask-sudo-password", action="store_true", help="ask for the sudo password here (hidden)")
    s.add_argument("--sudo-password-env", metavar="VAR", help="read the sudo password from this environment variable")
    s.add_argument("--no-reuse-password", action="store_true", help="do not reuse the SSH password as sudo password")
    r = ap.add_argument_group("report")
    r.add_argument("-c", "--config", default="/opt/telemet-collector/config.ini", help="config.ini path ON THE SERVER")
    r.add_argument("--service", default="telemet-collector", help="service name on the server")
    r.add_argument("--no-service", action="store_true", help="do not query systemd")
    r.add_argument("--authorized-keys", action="store_true",
                   help="add the authorized_keys audit of the login user to the full report")
    r.add_argument("--show-key", action="store_true", help="show the API Key in full")
    r.add_argument("--json", action="store_true", help="JSON output (several servers: an object per server)")
    r.add_argument("--color", dest="color", action="store_true", default=None, help="force colors")
    r.add_argument("--no-color", dest="color", action="store_false", help="no colors")
    r.add_argument("--lang", choices=("es", "en"), default=default_lang())
    r.add_argument("--remote-python", default="python3", help="python command on the server (default python3)")
    r.add_argument("--check", action="store_true", help="only check the connection, python, config.ini and sudo")
    k = ap.add_argument_group("login with authorized_keys (public key)")
    k.add_argument("--check-key", action="store_true",
                   help="validate that key-only login works (no password) and audit authorized_keys on the server")
    k.add_argument("--install-key", action="store_true",
                   help="copy your public key to ~/.ssh/authorized_keys on the server (like ssh-copy-id) and validate it")
    k.add_argument("--pubkey", metavar="FILE.pub", help="public key to install (default: <-i key>.pub or ~/.ssh/id_*.pub)")
    k.add_argument("--generate-key", action="store_true",
                   help="create an RSA 4096 key pair (-i PATH, default ~/.ssh/id_rsa) if it does not exist")
    a = ap.parse_args(argv)
    t = T[a.lang]

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not shutil.which(a.ssh_path):
        print(t["no_ssh"], file=sys.stderr)
        return 3
    payload_path = os.path.join(HERE, PAYLOAD)
    if not os.path.isfile(payload_path):
        print(t["no_payload"] % (PAYLOAD, HERE), file=sys.stderr)
        return 3
    with open(payload_path, "rb") as f:
        payload = f.read()

    interactive = sys.stdin.isatty() and sys.stderr.isatty()
    targets = list(a.targets)
    if a.generate_key:
        rc = generate_key(a, t, interactive)
        if rc or not (targets and (a.install_key or a.check_key)):
            return rc
    asked_pw = None
    if not targets:
        if not interactive:
            ap.error("no target given (and no terminal to ask for it)")
        targets = [input(t["ask_target"]).strip()]
        if not (a.ask_password or a.password_env or a.identity):
            asked_pw = getpass.getpass(t["ask_pw"] % targets[0]) or None

    password = None
    if a.password_env:
        password = secret(a.password_env, t)
    elif a.ask_password:
        password = getpass.getpass(t["ask_pw"] % ", ".join(targets))
    elif asked_pw:
        password = asked_pw

    if a.install_key or a.check_key:
        return key_mode(a, t, targets, payload, password, interactive)

    sudo_pw = None
    if a.sudo_password_env:
        sudo_pw = secret(a.sudo_password_env, t)
    elif a.ask_sudo_password:
        sudo_pw = getpass.getpass(t["ask_sudo"] % ", ".join(targets))
    elif password and not a.no_reuse_password:
        sudo_pw = password

    use_sudo = not a.no_sudo
    info_args = info_args_from(a)
    results, errors, worst = {}, 0, 0

    for target in targets:
        pt = parse_target(target)
        if not pt:
            print(t["bad_target"] % target, file=sys.stderr)
            errors += 1
            worst = max(worst, 3)
            continue
        user, host, port = pt
        label = target
        if not a.json:
            print("\033[2m" + t["connecting"] % label + "\033[0m" if sys.stderr.isatty() else t["connecting"] % label,
                  file=sys.stderr)
        cmd = (remote_check_command(a.config, use_sudo, a.remote_python) if a.check
               else remote_report_command(payload, info_args, use_sudo, a.remote_python))
        spw = sudo_pw
        code, out, err = run_ssh(a, user, host, port, cmd, password, spw)
        # sudo asks for a password and we did not have it (or it was wrong): ask once
        if not a.check and use_sudo and code != 0 and SUDO_FAIL.search(err) and interactive and not a.sudo_password_env:
            print(t["retry_sudo"], end="", file=sys.stderr)
            spw = getpass.getpass(t["ask_sudo"] % label)
            code, out, err = run_ssh(a, user, host, port, cmd, password, spw)
        sudo_failed = bool(SUDO_FAIL.search(err)) and code != 0
        if code == 255:
            print(t["ssh_fail"] % label, file=sys.stderr)
            if "Host key verification failed" in err or "authenticity" in err:
                print(t["ssh_hint_hostkey"] % ("-p %s %s%s" % (port or a.port, (user + "@") if user else "", host)
                                               if (port or a.port) else "%s%s" % ((user + "@") if user else "", host)),
                      file=sys.stderr)
            if a.batch and "Permission denied" in err:
                print(t["ssh_hint_batch"], file=sys.stderr)
        elif sudo_failed:
            print(t["sudo_fail"] % label, file=sys.stderr)
            print(t["sudo_hint"], file=sys.stderr)
        elif code == 127:
            print(t["py_missing"], file=sys.stderr)
        if err.strip():
            print(err.rstrip(), file=sys.stderr)
        # 0 ok · 1 the report found errors · 2 config.ini unreadable on the server · 4 connection/sudo/python failure
        rc_t = 4 if (code in (255, 124, 127) or sudo_failed) else code
        worst = max(worst, rc_t)
        errors += 1 if rc_t >= 2 else 0

        if a.check:
            print("== " + t["check_title"] % label + " ==")
            print(out.rstrip() or "(sin salida / no output)")
            continue
        if a.json and len(targets) > 1:
            try:
                results[label] = json.loads(out)
            except ValueError:
                results[label] = {"error": err.strip() or "no JSON received", "exit_code": code}
        else:
            if len(targets) > 1:
                print("\n" + "═" * 70 + "\n  %s\n" % label + "═" * 70)
            sys.stdout.write(out)

    if a.json and len(targets) > 1:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    if len(targets) > 1 and not a.json:
        print("\n" + t["done_hosts"] % (len(targets), errors), file=sys.stderr)
    return worst


if __name__ == "__main__":
    sys.exit(main())

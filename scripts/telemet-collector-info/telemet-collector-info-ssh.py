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
"""

import argparse
import base64
import getpass
import json
import os
import re
import shlex
import shutil
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


def ssh_base(a, user, host, port, password):
    cmd = [a.ssh_path]
    if port or a.port:
        cmd += ["-p", str(port or a.port)]
    if a.identity:
        cmd += ["-i", os.path.expanduser(a.identity), "-o", "IdentitiesOnly=yes"]
    cmd += ["-o", "ConnectTimeout=%d" % a.connect_timeout, "-o", "ServerAliveInterval=15",
            "-o", "LogLevel=ERROR", "-o", "ForwardAgent=no", "-o", "ForwardX11=no", "-T"]
    if a.accept_new_host_key:
        cmd += ["-o", "StrictHostKeyChecking=accept-new"]
    if a.batch:
        cmd += ["-o", "BatchMode=yes"]
    if password is not None:
        cmd += ["-o", "NumberOfPasswordPrompts=1"]
    for extra in a.ssh_arg or []:
        cmd += shlex.split(extra)
    user = user or a.user
    cmd.append("%s@%s" % (user, host) if user else host)
    return cmd


def run_ssh(a, user, host, port, remote_cmd, password, sudo_password):
    """Runs the command on the server and returns (code, stdout, stderr)."""
    cmd = ssh_base(a, user, host, port, password) + [remote_cmd]
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
    r.add_argument("--show-key", action="store_true", help="show the API Key in full")
    r.add_argument("--json", action="store_true", help="JSON output (several servers: an object per server)")
    r.add_argument("--color", dest="color", action="store_true", default=None, help="force colors")
    r.add_argument("--no-color", dest="color", action="store_false", help="no colors")
    r.add_argument("--lang", choices=("es", "en"), default=default_lang())
    r.add_argument("--remote-python", default="python3", help="python command on the server (default python3)")
    r.add_argument("--check", action="store_true", help="only check the connection, python, config.ini and sudo")
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

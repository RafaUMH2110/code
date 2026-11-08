"""Fixtures comunes de las pruebas.

Las pruebas de integración usan un **sshd real** que se arranca en un puerto libre con un usuario
de prueba (contraseña con caracteres difíciles y sudo con contraseña). Solo se ejecutan si:

* el equipo tiene OpenSSH servidor (``/usr/sbin/sshd``) y cliente, y
* se ejecutan como root (hace falta para crear el usuario y arrancar sshd).

En el Mac de desarrollo se saltan solas; en el contenedor de CI o en un Debian de pruebas corren
completas. Todo lo demás (modelos, comandos, análisis) se prueba sin red ni servidor.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from panel_servidores.nucleo.askpass import GestorAskpass  # noqa: E402
from panel_servidores.nucleo.modelos import Ajustes, Perfil  # noqa: E402
from panel_servidores.nucleo.recursos import Recursos  # noqa: E402
from panel_servidores.nucleo.secretos import Llavero, ResolutorSecretos  # noqa: E402
from panel_servidores.nucleo.ssh import Conexion  # noqa: E402

USUARIO = "psv-test"
CONTRASENA = 'Pa55 w0rd"$x'      # espacios, comillas y $: la peor cara para cualquier script de shell


class InteraccionGuion:
    """Interacción de pruebas: responde con valores predefinidos y apunta lo que se le pregunta."""

    def __init__(self, secretos=None, confirmar=True):
        self.secretos = list(secretos or [])
        self.respuesta_confirmar = confirmar
        self.preguntas: list = []
        self.confirmaciones: list = []

    def pedir_secreto(self, titulo, mensaje, permitir_recordar=False):
        self.preguntas.append((titulo, mensaje))
        if not self.secretos:
            return None
        return (self.secretos.pop(0), False)

    def confirmar(self, titulo, mensaje):
        self.confirmaciones.append((titulo, mensaje))
        return self.respuesta_confirmar


class LlaveroFalso:
    """Sustituto en memoria de ``keyring`` para probar el Llavero sin tocar el de verdad."""

    def __init__(self):
        self.datos = {}

    def get_password(self, servicio, cuenta):
        return self.datos.get((servicio, cuenta))

    def set_password(self, servicio, cuenta, valor):
        self.datos[(servicio, cuenta)] = valor

    def delete_password(self, servicio, cuenta):
        self.datos.pop((servicio, cuenta), None)


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServidorSsh:
    """Datos del sshd de pruebas."""

    def __init__(self, puerto: int, home: Path):
        self.host = "127.0.0.1"
        self.puerto = puerto
        self.usuario = USUARIO
        self.contrasena = CONTRASENA
        self.home = home           # home del usuario de pruebas
        self.known_hosts = ""


@pytest.fixture(scope="session")
def servidor_ssh(tmp_path_factory):
    sshd = shutil.which("sshd") or "/usr/sbin/sshd"
    if os.geteuid() != 0 or not os.path.exists(sshd) or not shutil.which("ssh"):
        pytest.skip("hace falta root y OpenSSH (cliente y servidor) para las pruebas de integración")
    if subprocess.run(["id", USUARIO], capture_output=True).returncode != 0:
        subprocess.run(["useradd", "-m", "-s", "/bin/bash", USUARIO], check=True)
    subprocess.run(["chpasswd"], input=("%s:%s\n" % (USUARIO, CONTRASENA)).encode(), check=True)
    Path("/etc/sudoers.d/psv-test").write_text("%s ALL=(ALL) ALL\n" % USUARIO)
    os.chmod("/etc/sudoers.d/psv-test", 0o440)
    os.makedirs("/run/sshd", exist_ok=True)
    subprocess.run(["ssh-keygen", "-A"], capture_output=True)
    carpeta = tmp_path_factory.mktemp("sshd")
    puerto = _puerto_libre()
    conf = carpeta / "sshd.conf"
    conf.write_text("\n".join([
        "Port %d" % puerto, "ListenAddress 127.0.0.1",
        "HostKey /etc/ssh/ssh_host_ed25519_key", "HostKey /etc/ssh/ssh_host_rsa_key",
        "PasswordAuthentication yes", "KbdInteractiveAuthentication no", "PubkeyAuthentication yes",
        "UsePAM yes", "StrictModes yes", "LogLevel VERBOSE", "PidFile %s" % (carpeta / "sshd.pid"), ""]))
    proc = subprocess.Popen([sshd, "-D", "-f", str(conf), "-E", str(carpeta / "sshd.log")])
    for _ in range(50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", puerto)) == 0:
                break
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.skip("no arrancó el sshd de pruebas")
    srv = ServidorSsh(puerto, Path("/home") / USUARIO)
    srv.known_hosts = str(carpeta / "known_hosts")
    yield srv
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
def datos(tmp_path, monkeypatch):
    """Carpeta de datos aislada para cada prueba."""
    monkeypatch.setenv("PANEL_SERVIDORES_HOME", str(tmp_path / "datos"))
    return tmp_path / "datos"


@pytest.fixture
def askpass():
    g = GestorAskpass()
    g.iniciar()
    yield g
    g.detener()


@pytest.fixture
def fabrica(askpass, servidor_ssh, tmp_path):
    """Crea conexiones al sshd de pruebas con la interacción indicada."""
    creadas = []

    def crear(interaccion=None, **cambios) -> Conexion:
        perfil = Perfil(nombre="prueba", destino="%s@%s:%d" % (servidor_ssh.usuario, servidor_ssh.host, servidor_ssh.puerto),
                        opciones_ssh=["-o UserKnownHostsFile=%s" % servidor_ssh.known_hosts],
                        aceptar_huella_nueva=True, python_remoto="python3")
        for k, v in cambios.items():
            setattr(perfil, k, v)
        inter = interaccion or InteraccionGuion([servidor_ssh.contrasena])
        secretos = ResolutorSecretos(perfil, inter, Llavero(LlaveroFalso()))
        con = Conexion(perfil, Ajustes(), askpass, inter, secretos)
        creadas.append(con)
        return con

    yield crear
    for c in creadas:
        c.destruir()


@pytest.fixture
def recursos():
    return Recursos()


@pytest.fixture
def config_colector(servidor_ssh):
    """config.ini de prueba accesible para el usuario de pruebas."""
    base = servidor_ssh.home / "telemet"
    (base / "out").mkdir(parents=True, exist_ok=True)
    cfg = base / "config.ini"
    cfg.write_text("[station]\nstation_id = IELCHE12\napi_key = abcd1234efgh5678\n[output]\n"
                   "json_path = %s/out/history.json\n[storage]\ndb_path = %s/data.sqlite\n" % (base, base))
    subprocess.run(["chown", "-R", servidor_ssh.usuario + ":" + servidor_ssh.usuario, str(base)], check=True)
    os.chmod(cfg, 0o600)
    return str(cfg)

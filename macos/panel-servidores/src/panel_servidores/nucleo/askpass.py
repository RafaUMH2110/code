"""Servidor del *askpass*: el puente entre ``ssh`` y la interfaz.

Problema que resuelve
---------------------
Los scripts originales solo podían contestar a ``ssh`` con una contraseña fija (variable de
entorno) o dejar que ``ssh`` preguntase en el terminal. Una aplicación gráfica no tiene
terminal. La solución estándar de OpenSSH es ``SSH_ASKPASS``: un programa externo que ssh
invoca cuando necesita algo. Aquí ese programa habla con la aplicación por un socket Unix:

    ssh ──(argv[1] = pregunta)──▶ askpass.sh ──▶ askpass_cliente ──socket──▶ GestorAskpass
                                                                                  │
                                    ┌─────────────────────────────────────────────┘
                                    ▼
                          ResolutorSecretos.responder_askpass()
                          (secreto ya conocido, Llavero, o diálogo en la interfaz)

Con esto la aplicación gestiona de forma uniforme **contraseñas, frases de paso de claves,
códigos 2FA (keyboard-interactive) y la confirmación de huellas de servidores nuevos**.

Seguridad
---------
* El socket vive en un directorio ``/tmp/ps-XXXX`` creado con permisos 700.
* Cada conexión registra un *token* aleatorio; sin él el servidor no responde.
* Ningún secreto toca el disco ni la línea de comandos.
"""

from __future__ import annotations

import json
import os
import secrets
import shlex
import shutil
import socket
import stat
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

from . import askpass_cliente

Respondedor = Callable[[str], Optional[str]]


class GestorAskpass:
    """Servidor de sockets Unix + script ``askpass.sh``. Una instancia por aplicación."""

    def __init__(self) -> None:
        # /tmp explícito: la ruta del socket no puede pasar de ~104 caracteres en macOS y
        # $TMPDIR (/var/folders/…) ya ocupa casi la mitad.
        self.directorio = Path(tempfile.mkdtemp(prefix="ps-", dir="/tmp"))
        os.chmod(self.directorio, 0o700)
        self._ruta_socket = str(self.directorio / "a.sock")
        self._ruta_script = self.directorio / "askpass.sh"
        self._respondedores: dict[str, Respondedor] = {}
        self._cerrojo = threading.Lock()
        self._servidor: Optional[socket.socket] = None
        self._hilo: Optional[threading.Thread] = None
        self._activo = False
        self._escribir_script()

    # ------------------------------------------------------------------ ciclo de vida
    def iniciar(self) -> None:
        """Abre el socket y empieza a atender peticiones en un hilo."""
        if self._activo:
            return
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(self._ruta_socket)
        os.chmod(self._ruta_socket, 0o600)
        s.listen(16)
        self._servidor = s
        self._activo = True
        self._hilo = threading.Thread(target=self._bucle, name="askpass", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        """Cierra el socket y borra el directorio temporal."""
        self._activo = False
        if self._servidor:
            try:
                self._servidor.close()
            except OSError:
                pass
        shutil.rmtree(self.directorio, ignore_errors=True)

    # ------------------------------------------------------------------ registro de respondedores
    def registrar(self, respondedor: Respondedor) -> str:
        """Asocia un respondedor a un token nuevo y lo devuelve (va en el entorno de ssh)."""
        token = secrets.token_hex(16)
        with self._cerrojo:
            self._respondedores[token] = respondedor
        return token

    def liberar(self, token: str) -> None:
        with self._cerrojo:
            self._respondedores.pop(token, None)

    def entorno(self, token: str) -> dict:
        """Variables de entorno que hay que añadir al proceso ``ssh`` / ``ssh-keygen`` / ``ssh-add``."""
        return {
            "SSH_ASKPASS": str(self._ruta_script),
            # «force» (OpenSSH ≥ 8.4) usa el askpass aunque haya terminal; DISPLAY cubre versiones antiguas.
            "SSH_ASKPASS_REQUIRE": "force",
            "DISPLAY": os.environ.get("DISPLAY") or "none:0",
            askpass_cliente.VAR_SOCKET: self._ruta_socket,
            askpass_cliente.VAR_TOKEN: token,
        }

    # ------------------------------------------------------------------ internos
    def _escribir_script(self) -> None:
        """Crea ``askpass.sh``, que simplemente relanza el cliente con el Python adecuado."""
        if getattr(sys, "frozen", False):
            # Aplicación empaquetada: el propio ejecutable atiende la opción --askpass.
            orden = "exec %s --askpass \"$@\"" % shlex.quote(sys.executable)
        else:
            orden = "exec %s %s \"$@\"" % (shlex.quote(sys.executable), shlex.quote(askpass_cliente.__file__))
        self._ruta_script.write_text("#!/bin/sh\n%s\n" % orden, encoding="utf-8")
        self._ruta_script.chmod(stat.S_IRWXU)

    def _bucle(self) -> None:
        while self._activo:
            try:
                conexion, _ = self._servidor.accept()      # type: ignore[union-attr]
            except OSError:
                return
            # Un hilo por petición: el respondedor puede esperar minutos a que el usuario conteste.
            threading.Thread(target=self._atender, args=(conexion,), daemon=True).start()

    def _atender(self, conexion: socket.socket) -> None:
        with conexion:
            try:
                buffer = b""
                while not buffer.endswith(b"\n"):
                    trozo = conexion.recv(65536)
                    if not trozo:
                        return
                    buffer += trozo
                peticion = json.loads(buffer.decode("utf-8"))
                with self._cerrojo:
                    respondedor = self._respondedores.get(peticion.get("token", ""))
                valor = respondedor(peticion.get("prompt", "")) if respondedor else None
                respuesta = {"ok": True, "valor": valor} if valor is not None else {"ok": False}
                conexion.sendall((json.dumps(respuesta) + "\n").encode("utf-8"))
            except (OSError, ValueError):
                return
            except Exception:                       # un fallo del respondedor no debe colgar a ssh
                try:
                    conexion.sendall(b'{"ok": false}\n')
                except OSError:
                    pass

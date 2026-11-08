"""Cliente del *askpass*: lo ejecuta ``ssh`` (vía ``SSH_ASKPASS``) cada vez que necesita un dato.

``ssh`` lanza un programa externo, le pasa la pregunta como primer argumento y espera la
respuesta por su salida estándar. Este programa reenvía la pregunta, por un socket Unix
privado, a la aplicación (que muestra un diálogo o responde con un secreto ya conocido) y
escribe la respuesta.

Este módulo usa SOLO la biblioteca estándar y no importa nada del resto del paquete, para
que arranque en milisegundos y funcione igual desde el código fuente que dentro del
``.app`` empaquetado (donde se invoca como ``Panel de Servidores --askpass "pregunta"``).

Protocolo (una línea JSON en cada sentido, terminada en ``\\n``)::

    cliente → servidor   {"token": "...", "prompt": "Password: "}
    servidor → cliente   {"ok": true, "valor": "..."}      o      {"ok": false}

Código de salida: 0 si hay respuesta; 1 si el usuario cancela o algo falla (ssh lo trata
como «autenticación abortada»).
"""

from __future__ import annotations

import json
import os
import socket
import sys

VAR_SOCKET = "PANEL_ASKPASS_SOCK"
VAR_TOKEN = "PANEL_ASKPASS_TOKEN"
#: El usuario puede tardar en responder (buscar la contraseña, abrir el móvil para el 2FA…).
ESPERA_MAXIMA_S = 600


def main(argumentos: list) -> int:
    """Punto de entrada. ``argumentos`` son los argumentos que recibe el askpass (la pregunta)."""
    pregunta = " ".join(argumentos) if argumentos else ""
    ruta = os.environ.get(VAR_SOCKET)
    if not ruta:
        return 1
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(ESPERA_MAXIMA_S)
            s.connect(ruta)
            peticion = {"token": os.environ.get(VAR_TOKEN, ""), "prompt": pregunta}
            s.sendall((json.dumps(peticion) + "\n").encode("utf-8"))
            buffer = b""
            while not buffer.endswith(b"\n"):
                trozo = s.recv(65536)
                if not trozo:
                    break
                buffer += trozo
        respuesta = json.loads(buffer.decode("utf-8"))
    except (OSError, ValueError):
        return 1
    if not respuesta.get("ok"):
        return 1
    sys.stdout.write(respuesta.get("valor", "") + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

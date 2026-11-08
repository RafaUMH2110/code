"""Gestión de secretos: contraseña SSH, frase de paso de la clave y contraseña de sudo.

Tres orígenes posibles (``FuenteSecreto.origen``):

* ``preguntar``  → se pide en un diálogo la primera vez y se **recuerda solo en memoria**
                   mientras dure la sesión de ese servidor. El diálogo ofrece guardarla en el
                   Llavero.
* ``llavero``    → Llavero de macOS (a través de la librería opcional ``keyring``).
* ``entorno``    → variable de entorno (equivalente a ``--password-env`` del script).

Los secretos **jamás** se escriben en disco por esta aplicación ni se pasan por la línea de
comandos: viajan por el socket del *askpass* (ver ``askpass.py``) o por la entrada estándar
de la conexión SSH cifrada.
"""

from __future__ import annotations

import os
import re
import threading
from typing import Callable, Optional

from .modelos import (AUTH_INTERACTIVA, ORIGEN_ENTORNO, ORIGEN_LLAVERO, FuenteSecreto,
                      Interaccion, Perfil, SUDO_AUTO, SUDO_NUNCA)

try:                                   # ``keyring`` es opcional: sin él no hay Llavero
    import keyring as _keyring
    from keyring.errors import KeyringError as _KeyringError
except Exception:                      # pragma: no cover - depende del entorno
    _keyring = None
    _KeyringError = Exception

SERVICIO_LLAVERO = "Panel de Servidores"

# Tipos de secreto (se usan como parte del nombre de la cuenta en el Llavero)
TIPO_PASSWORD = "password"
TIPO_FRASE = "frase"
TIPO_SUDO = "sudo"
TIPO_GITHUB = "github"

_RE_YESNO = re.compile(r"\(yes/no(/\[fingerprint\])?\)|continue connecting", re.I)
_RE_FRASE = re.compile(r"passphrase", re.I)
_RE_PASSWORD = re.compile(r"password", re.I)


class Llavero:
    """Envoltorio mínimo sobre ``keyring`` con un único punto de fallo controlado."""

    def __init__(self, backend=None):
        self._kr = backend if backend is not None else _keyring

    @property
    def disponible(self) -> bool:
        return self._kr is not None

    @staticmethod
    def _cuenta(id_perfil: str, tipo: str) -> str:
        return "%s:%s" % (id_perfil, tipo)

    def leer(self, id_perfil: str, tipo: str) -> Optional[str]:
        if not self.disponible:
            return None
        try:
            return self._kr.get_password(SERVICIO_LLAVERO, self._cuenta(id_perfil, tipo))
        except _KeyringError:
            return None

    def guardar(self, id_perfil: str, tipo: str, valor: str) -> bool:
        if not self.disponible:
            return False
        try:
            self._kr.set_password(SERVICIO_LLAVERO, self._cuenta(id_perfil, tipo), valor)
            return True
        except _KeyringError:
            return False

    def borrar(self, id_perfil: str, tipo: str) -> None:
        if not self.disponible:
            return
        try:
            self._kr.delete_password(SERVICIO_LLAVERO, self._cuenta(id_perfil, tipo))
        except Exception:
            pass

    def borrar_todos(self, id_perfil: str) -> None:
        for tipo in (TIPO_PASSWORD, TIPO_FRASE, TIPO_SUDO):
            self.borrar(id_perfil, tipo)


class ResolutorSecretos:
    """Obtiene los secretos de UN perfil y contesta a las preguntas que hace ``ssh``.

    Una instancia vive tanto como la conexión de ese servidor. Es segura entre hilos: el
    cerrojo evita que dos diálogos pidan la misma contraseña a la vez.
    """

    def __init__(self, perfil: Perfil, interaccion: Interaccion, llavero: Optional[Llavero] = None,
                 entorno: Optional[dict] = None):
        self.perfil = perfil
        self.interaccion = interaccion
        self.llavero = llavero or Llavero()
        self._entorno = entorno if entorno is not None else os.environ
        self._memoria: dict[str, str] = {}
        self._cerrojo = threading.RLock()
        #: Se rellena cuando el usuario confirma la huella de un servidor nuevo (o ya era de confianza).
        self.huella_aceptada = False

    # ------------------------------------------------------------------ secretos "con nombre"
    def _fuente(self, tipo: str) -> FuenteSecreto:
        return {TIPO_PASSWORD: self.perfil.password,
                TIPO_FRASE: self.perfil.frase,
                TIPO_SUDO: self.perfil.sudo}[tipo]

    def _titulo(self, tipo: str) -> str:
        return {TIPO_PASSWORD: "Contraseña SSH", TIPO_FRASE: "Frase de paso de la clave",
                TIPO_SUDO: "Contraseña de sudo"}[tipo]

    def obtener(self, tipo: str, preguntar_si_falta: bool = True) -> Optional[str]:
        """Devuelve el secreto del tipo pedido o ``None`` si no hay o el usuario cancela."""
        with self._cerrojo:
            if tipo in self._memoria:
                return self._memoria[tipo]
            fuente = self._fuente(tipo)
            if fuente.origen == ORIGEN_ENTORNO:
                valor = self._entorno.get(fuente.variable or "") or None
                if valor:
                    self._memoria[tipo] = valor
                return valor
            if fuente.origen == ORIGEN_LLAVERO:
                valor = self.llavero.leer(self.perfil.id, tipo)
                if valor:
                    self._memoria[tipo] = valor
                    return valor
            if not preguntar_si_falta:
                return None
            return self._preguntar(tipo, "%s de %s" % (self._titulo(tipo), self.perfil.etiqueta()))

    def _preguntar(self, tipo: str, mensaje: str) -> Optional[str]:
        respuesta = self.interaccion.pedir_secreto(self._titulo(tipo), mensaje,
                                                   permitir_recordar=self.llavero.disponible)
        if respuesta is None:
            return None
        valor, recordar = respuesta
        if not valor:
            return None
        self._memoria[tipo] = valor
        if recordar:
            self.llavero.guardar(self.perfil.id, tipo, valor)
            self._fuente(tipo).origen = ORIGEN_LLAVERO
        return valor

    def olvidar(self) -> None:
        """Borra de memoria todos los secretos recordados (al cerrar la conexión)."""
        with self._cerrojo:
            self._memoria.clear()

    def olvidar_tipo(self, tipo: str) -> None:
        """Olvida un solo secreto (p. ej. una contraseña de sudo que resultó incorrecta)."""
        with self._cerrojo:
            self._memoria.pop(tipo, None)

    # ------------------------------------------------------------------ sudo
    def contrasena_sudo(self) -> Optional[str]:
        """Contraseña de sudo según el modo del perfil (sin preguntar si no hay)."""
        p = self.perfil
        if p.sudo_modo == SUDO_NUNCA:
            return None
        if p.sudo_modo == SUDO_AUTO:
            # Comportamiento del script: se reutiliza la contraseña SSH si se entró con ella.
            if p.reutilizar_password_sudo and self._memoria.get(TIPO_PASSWORD):
                return self._memoria[TIPO_PASSWORD]
            return None
        return self.obtener(TIPO_SUDO)

    def preguntar_sudo(self) -> Optional[str]:
        """Pide la contraseña de sudo al usuario (reintento tras un fallo de sudo)."""
        with self._cerrojo:
            return self._preguntar(TIPO_SUDO, "sudo necesita contraseña en %s" % self.perfil.etiqueta())

    # ------------------------------------------------------------------ respuestas a ssh (askpass)
    def responder_askpass(self, prompt: str) -> Optional[str]:
        """Contesta a lo que ``ssh``, ``ssh-keygen`` o ``ssh-add`` preguntan.

        ``None`` significa «cancelar»: el *askpass* termina con error y ssh aborta.
        """
        with self._cerrojo:
            if _RE_YESNO.search(prompt):
                # Servidor visto por primera vez: la huella (que va en el propio texto) se
                # muestra al usuario, que decide si confía.
                if self.perfil.aceptar_huella_nueva or self.interaccion.confirmar(
                        "Huella del servidor", prompt.strip()):
                    self.huella_aceptada = True
                    return "yes"
                return "no"
            if _RE_FRASE.search(prompt):
                return self.obtener(TIPO_FRASE)
            if _RE_PASSWORD.search(prompt):
                if self.perfil.autenticacion == AUTH_INTERACTIVA:
                    return self._pedir_directo(prompt)
                return self.obtener(TIPO_PASSWORD)
            # Cualquier otra pregunta (código de verificación 2FA, PIN, etc.): siempre al usuario.
            return self._pedir_directo(prompt)

    def _pedir_directo(self, prompt: str) -> Optional[str]:
        """Pregunta al usuario sin recordar la respuesta (códigos de un solo uso)."""
        respuesta = self.interaccion.pedir_secreto("Autenticación", prompt.strip(), permitir_recordar=False)
        return respuesta[0] if respuesta and respuesta[0] else None


FuncionRespuesta = Callable[[str], Optional[str]]

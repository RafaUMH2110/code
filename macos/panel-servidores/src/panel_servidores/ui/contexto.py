"""Estado compartido de la aplicación (lo que necesitan todas las pestañas).

El ``Contexto`` es el único sitio que crea y conserva conexiones: así una contraseña escrita
una vez se reutiliza en todas las pestañas del mismo servidor mientras dure la sesión, y al
salir se cierran todas las conexiones principales de ssh.
"""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QObject, Signal

from ..nucleo.almacen import Almacen
from ..nucleo.askpass import GestorAskpass
from ..nucleo.modelos import Perfil
from ..nucleo.recursos import Recursos
from ..nucleo.secretos import Llavero, ResolutorSecretos
from ..nucleo.ssh import Conexion
from . import hilos
from .hilos import Trabajo


class Contexto(QObject):
    """Servicios compartidos. Las señales se emiten siempre en el hilo de la interfaz."""

    actividad = Signal(str)          # una línea para la consola de actividad
    sesion_cambiada = Signal(str)    # id del perfil cuya conexión se abrió o cerró
    perfiles_cambiados = Signal()    # se añadió / editó / eliminó un perfil

    def __init__(self, almacen: Almacen, askpass: GestorAskpass, llavero: Llavero, interaccion) -> None:
        super().__init__()
        self.almacen = almacen
        self.askpass = askpass
        self.llavero = llavero
        self.interaccion = interaccion
        self._conexiones: dict = {}        # id de perfil -> (huella_de_perfil, Conexion)

    # ------------------------------------------------------------------ atajos
    @property
    def ajustes(self):
        return self.almacen.ajustes

    def recursos(self) -> Recursos:
        """Recursos según la configuración actual (carpeta propia de scripts)."""
        return Recursos(self.ajustes.carpeta_scripts)

    # ------------------------------------------------------------------ registro de actividad
    def registrar(self, texto: str) -> None:
        """Añade una línea con hora al registro de actividad (se puede llamar desde cualquier hilo)."""
        linea = "%s  %s" % (time.strftime("%H:%M:%S"), texto)
        hilos.en_gui(lambda: self.actividad.emit(linea))

    # ------------------------------------------------------------------ conexiones
    def conexion(self, perfil: Perfil) -> Conexion:
        """Devuelve la conexión del perfil, creándola si hace falta.

        Si el perfil cambió desde que se creó (otro destino, otra autenticación…) se descarta la
        antigua para que los cambios surtan efecto.
        """
        huella = self._huella(perfil)
        existente = self._conexiones.get(perfil.id)
        if existente and existente[0] == huella:
            # Mismos datos de conexión: se conserva la sesión (y su contraseña ya escrita), pero se apunta
            # al objeto de perfil actual para que nombre, notas, ruta del colector, etc. estén al día.
            existente[1].perfil = perfil
            existente[1].secretos.perfil = perfil
            return existente[1]
        if existente:
            existente[1].destruir()
        secretos = ResolutorSecretos(perfil, self.interaccion, self.llavero)
        con = Conexion(perfil, self.ajustes, self.askpass, self.interaccion, secretos, registro=self.registrar)
        self._conexiones[perfil.id] = (huella, con)
        return con

    #: Campos del perfil que NO afectan a la conexión: cambiarlos no debe obligar a autenticarse de nuevo.
    _CAMPOS_SIN_EFECTO_EN_CONEXION = ("nombre", "notas", "url_base", "variante", "instalador", "ruta_config", "servicio")

    @classmethod
    def _huella(cls, perfil: Perfil) -> str:
        datos = perfil.a_dict()
        for campo in cls._CAMPOS_SIN_EFECTO_EN_CONEXION:
            datos.pop(campo, None)
        return repr(datos)

    def abierta(self, perfil_id: str) -> bool:
        e = self._conexiones.get(perfil_id)
        return bool(e and e[1].abierta)

    def desconectar(self, perfil_id: str, olvidar_llavero: bool = False) -> None:
        e = self._conexiones.pop(perfil_id, None)
        if e:
            e[1].destruir()
        if olvidar_llavero:
            self.llavero.borrar_todos(perfil_id)
        self.sesion_cambiada.emit(perfil_id)

    def cerrar_todo(self) -> None:
        for e in list(self._conexiones.values()):
            e[1].destruir()
        self._conexiones.clear()

    # ------------------------------------------------------------------ trabajos
    def lanzar(self, funcion: Callable[[Trabajo], object], titulo: str, **devoluciones) -> Trabajo:
        """Crea e inicia un ``Trabajo``. Las devoluciones (al_terminar, al_error, al_linea, al_fin) corren en la interfaz."""
        return Trabajo(funcion, titulo, **devoluciones).iniciar()

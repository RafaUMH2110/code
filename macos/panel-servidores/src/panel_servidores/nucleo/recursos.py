"""Acceso a los scripts del repositorio que la aplicación lleva incluidos.

La aplicación NO reimplementa el instalador ni el informe: **envía al servidor los propios
scripts** (``instalar-todo.sh``, ``instalar-todo-isa.sh``, ``telemet-collector-info.py``) y
los ejecuta allí. Así el comportamiento es exactamente el que ya conoces y una corrección
del script se hereda sin tocar la aplicación.

Origen de cada fichero, por orden de prioridad:

1. La carpeta indicada en *Preferencias → Carpeta de scripts propios* (si el fichero existe).
2. La carpeta ``scripts/`` descargada con *Actualizar scripts desde GitHub*.
3. Los incluidos en la aplicación (``recursos/``), copiados del repo con
   ``scripts/sincronizar-recursos.sh``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from .. import rutas
from .modelos import VARIANTE_ISA

INSTALADOR_LOCAL = "instalar-todo.sh"
INSTALADOR_ISA = "instalar-todo-isa.sh"
INFORME = "telemet-collector-info.py"
#: Ficheros que acompañan al instalador (el portal y sus iconos) y que se copian junto a él.
ACOMPANANTES = ("index.html", "favicon.svg", "favicon.ico", "apple-touch-icon.png")

TODOS = (INSTALADOR_LOCAL, INSTALADOR_ISA, INFORME) + ACOMPANANTES


class Recursos:
    """Resuelve y lee los scripts incluidos (o sus sustitutos personalizados)."""

    def __init__(self, carpeta_personal: str = ""):
        self.carpeta_personal = Path(carpeta_personal).expanduser() if carpeta_personal else None

    def _candidatos(self, nombre: str) -> list:
        lista = []
        if self.carpeta_personal:
            lista.append(self.carpeta_personal / nombre)
        lista.append(rutas.dir_scripts_personalizados() / nombre)
        lista.append(rutas.dir_recursos() / nombre)
        return lista

    def ruta(self, nombre: str) -> Optional[Path]:
        """Primera ruta existente para ``nombre`` o ``None``."""
        return next((c for c in self._candidatos(nombre) if c.is_file()), None)

    def leer(self, nombre: str) -> bytes:
        ruta = self.ruta(nombre)
        if ruta is None:
            raise FileNotFoundError("No se encuentra el recurso «%s» (¿falta sincronizar los recursos?)" % nombre)
        return ruta.read_bytes()

    def origen(self, nombre: str) -> str:
        """Descripción legible de dónde sale un recurso: «incluido», «descargado» o «propio»."""
        ruta = self.ruta(nombre)
        if ruta is None:
            return "no encontrado"
        if self.carpeta_personal and ruta.parent == self.carpeta_personal:
            return "carpeta propia"
        if ruta.parent == rutas.dir_scripts_personalizados():
            return "descargado de GitHub"
        return "incluido en la aplicación"

    def huella(self, nombre: str) -> str:
        """SHA-256 abreviado: sirve para saber qué versión del script se está enviando."""
        return hashlib.sha256(self.leer(nombre)).hexdigest()[:12]

    @staticmethod
    def nombre_instalador(variante: str) -> str:
        return INSTALADOR_ISA if variante == VARIANTE_ISA else INSTALADOR_LOCAL

    def inventario(self) -> list:
        """Lista ``(nombre, origen, huella)`` de todos los recursos, para mostrar en Preferencias."""
        filas = []
        for n in TODOS:
            existe = self.ruta(n) is not None
            filas.append((n, self.origen(n), self.huella(n) if existe else "—"))
        return filas

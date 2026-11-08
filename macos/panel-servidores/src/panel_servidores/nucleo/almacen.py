"""Persistencia de perfiles y ajustes en JSON.

Los ficheros se guardan en ``rutas.dir_datos()`` con permisos 600. La escritura es
*atómica* (fichero temporal + ``os.replace``) para no dejar un JSON a medias si la
aplicación se cierra a mitad de un guardado.

IMPORTANTE: aquí **nunca** se guardan contraseñas. Un perfil solo recuerda *de dónde*
sale cada secreto (preguntar, Llavero de macOS o variable de entorno).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from .. import rutas
from .modelos import Ajustes, Perfil

VERSION_FORMATO = 1


def _escribir_json_atomico(destino: Path, datos: object) -> None:
    """Escribe ``datos`` en ``destino`` de forma atómica y con permisos 600."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=destino.name + ".", dir=str(destino.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, destino)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _leer_json(origen: Path, por_defecto):
    """Lee un JSON; si no existe o está corrupto devuelve ``por_defecto`` (y guarda una copia .bak)."""
    if not origen.exists():
        return por_defecto
    try:
        return json.loads(origen.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        try:
            os.replace(origen, origen.with_suffix(origen.suffix + ".bak"))
        except OSError:
            pass
        return por_defecto


class Almacen:
    """Lista de perfiles de servidor y ajustes globales."""

    def __init__(self, carpeta: Optional[Path] = None):
        self.carpeta = Path(carpeta) if carpeta else rutas.dir_datos()
        self._f_perfiles = self.carpeta / "perfiles.json"
        self._f_ajustes = self.carpeta / "ajustes.json"
        self.perfiles: list[Perfil] = []
        self.ajustes = Ajustes()
        self.cargar()

    # ------------------------------------------------------------------ carga / guardado
    def cargar(self) -> None:
        datos = _leer_json(self._f_perfiles, {"perfiles": []})
        self.perfiles = [Perfil.desde_dict(p) for p in datos.get("perfiles", []) if isinstance(p, dict)]
        self.ajustes = Ajustes.desde_dict(_leer_json(self._f_ajustes, {}))

    def guardar_perfiles(self) -> None:
        _escribir_json_atomico(self._f_perfiles, {"version": VERSION_FORMATO,
                                                  "perfiles": [p.a_dict() for p in self.perfiles]})

    def guardar_ajustes(self) -> None:
        _escribir_json_atomico(self._f_ajustes, self.ajustes.a_dict())

    # ------------------------------------------------------------------ operaciones sobre perfiles
    def obtener(self, id_perfil: str) -> Optional[Perfil]:
        return next((p for p in self.perfiles if p.id == id_perfil), None)

    def anadir(self, perfil: Perfil) -> Perfil:
        self.perfiles.append(perfil)
        self.guardar_perfiles()
        return perfil

    def actualizar(self, perfil: Perfil) -> None:
        """Sustituye el perfil con el mismo ``id`` (o lo añade si no existía)."""
        for i, p in enumerate(self.perfiles):
            if p.id == perfil.id:
                self.perfiles[i] = perfil
                break
        else:
            self.perfiles.append(perfil)
        self.guardar_perfiles()

    def eliminar(self, id_perfil: str) -> None:
        self.perfiles = [p for p in self.perfiles if p.id != id_perfil]
        self.guardar_perfiles()

    def duplicar(self, id_perfil: str) -> Optional[Perfil]:
        """Copia un perfil con otro ``id`` y el nombre «… (copia)»."""
        original = self.obtener(id_perfil)
        if not original:
            return None
        copia = Perfil.desde_dict(original.a_dict())
        copia.id = Perfil().id
        copia.nombre = (original.nombre or original.destino) + " (copia)"
        return self.anadir(copia)

    # ------------------------------------------------------------------ importar / exportar
    def exportar(self, destino: Path, perfiles: Optional[Iterable[Perfil]] = None) -> int:
        """Exporta perfiles (sin secretos) a un JSON. Devuelve cuántos."""
        lista = list(perfiles if perfiles is not None else self.perfiles)
        _escribir_json_atomico(Path(destino), {"version": VERSION_FORMATO,
                                               "perfiles": [p.a_dict() for p in lista]})
        return len(lista)

    def importar(self, origen: Path) -> int:
        """Importa perfiles de un JSON exportado. Les da un ``id`` nuevo para no pisar los existentes."""
        datos = json.loads(Path(origen).read_text(encoding="utf-8"))
        nuevos = 0
        for d in datos.get("perfiles", []):
            if not isinstance(d, dict):
                continue
            p = Perfil.desde_dict(d)
            p.id = Perfil().id
            self.perfiles.append(p)
            nuevos += 1
        if nuevos:
            self.guardar_perfiles()
        return nuevos

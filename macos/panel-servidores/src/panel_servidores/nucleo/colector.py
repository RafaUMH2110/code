"""Informe de TeleMet Collector, auditoría de ``authorized_keys`` y control del servicio systemd.

Equivale a ``telemet-collector-info-ssh.py`` (informe, ``--check``, ``--authorized-keys``,
``--keys-only``) más el control del servicio que antes se hacía a mano con ``systemctl``.

El informe lo genera el propio ``telemet-collector-info.py``, que se envía por SSH y se
ejecuta en memoria en el servidor. Se le piden dos salidas por la misma conexión:

* ``--json``  → estructura para pintar la vista ordenada de la interfaz,
* ``--color`` → el texto con colores ANSI, idéntico al que verías en el terminal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from . import remoto
from .modelos import (COD_CONEXION, COD_DIAGNOSTICO, COD_OK, RC_CANCELADO, RC_NO_ENCONTRADO, RC_SSH_FALLO,
                      RC_TIMEOUT, Resultado, SUDO_NUNCA)
from .recursos import INFORME, Recursos
from .ssh import RE_SUDO_FALLO, Cancelador, Conexion

#: Presets de colector: el instalador despliega el español; el informe entiende el inglés.
PRESETS_COLECTOR = {
    "TeleMet Collector (inglés)": ("/opt/telemet-collector/config.ini", "telemet-collector", "/opt/telemet-collector"),
    "TeleMet Colector (español)": ("/opt/telemet-colector/config.ini", "telemet-colector", "/opt/telemet-colector"),
}


@dataclass
class OpcionesInforme:
    """Opciones del informe (las mismas que el script, ver su manual §8)."""

    ruta_config: str = "/opt/telemet-collector/config.ini"   # -c  (ruta EN EL SERVIDOR)
    servicio: str = "telemet-collector"                      # --service
    sin_servicio: bool = False                               # --no-service
    mostrar_clave: bool = False                              # --show-key
    auditar_claves: bool = False                             # --authorized-keys
    idioma: str = "es"                                       # --lang


@dataclass
class Informe:
    """Resultado de un informe: estructura, texto coloreado y diagnóstico resumido."""

    codigo: int = COD_OK                  # 0 ok · 1 hay errores · 2 sin config · 4 fallo de conexión/sudo/python
    datos: Optional[dict] = None          # JSON del informe
    texto: str = ""                       # texto con ANSI
    error: str = ""
    duracion: float = 0.0
    diagnostico: list = field(default_factory=list)   # [{"level","message"}]

    def contar(self, nivel: str) -> int:
        return sum(1 for d in self.diagnostico if d.get("level") == nivel)

    @property
    def errores(self) -> int:
        return self.contar("err")

    @property
    def avisos(self) -> int:
        return self.contar("warn")

    @property
    def ok(self) -> bool:
        return self.codigo in (COD_OK, COD_DIAGNOSTICO) and self.datos is not None


def codigo_informe(r: Resultado) -> int:
    """Traduce el código de salida del proceso remoto al convenio del script (0,1,2,4)."""
    sudo_fallo = bool(RE_SUDO_FALLO.search(r.error)) and r.codigo != 0
    if r.codigo in (RC_SSH_FALLO, RC_TIMEOUT, RC_NO_ENCONTRADO, RC_CANCELADO) or sudo_fallo:
        return COD_CONEXION
    return r.codigo


def _argumentos(o: OpcionesInforme) -> list:
    args = ["--lang", o.idioma]
    if o.ruta_config:
        args += ["-c", o.ruta_config]
    if o.servicio:
        args += ["--service", o.servicio]
    if o.sin_servicio:
        args.append("--no-service")
    if o.mostrar_clave:
        args.append("--show-key")
    if o.auditar_claves:
        args.append("--authorized-keys")
    return args


def generar_informe(conexion: Conexion, recursos: Recursos, opciones: OpcionesInforme,
                    cancelador: Optional[Cancelador] = None) -> Informe:
    """Genera el informe del colector del servidor (JSON + texto coloreado)."""
    carga = recursos.leer(INFORME)
    usar_sudo = conexion.perfil.sudo_modo != SUDO_NUNCA
    ficticia = opciones.ruta_config.rsplit("/", 1)[0] + "/telemet-collector-info.py" if "/" in opciones.ruta_config \
        else "/opt/telemet-collector/telemet-collector-info.py"
    base = _argumentos(opciones)

    cmd_json = remoto.comando_informe(carga, base + ["--json"], usar_sudo, conexion.perfil.python_remoto, ficticia)
    r = conexion.ejecutar_sudo(cmd_json, cancelador=cancelador, etiqueta="informe del colector (JSON)")
    informe = Informe(codigo=codigo_informe(r), error=r.error.strip(), duracion=r.duracion)
    if informe.codigo in (COD_OK, COD_DIAGNOSTICO):
        try:
            informe.datos = json.loads(r.salida)
            informe.diagnostico = list(informe.datos.get("diagnostics", []))
        except ValueError:
            informe.error = (informe.error + "\nLa salida del informe no es JSON válido.").strip()
            informe.codigo = COD_CONEXION
    if informe.datos is not None:
        cmd_txt = remoto.comando_informe(carga, base + ["--color"], usar_sudo, conexion.perfil.python_remoto, ficticia)
        t = conexion.ejecutar_sudo(cmd_txt, cancelador=cancelador, etiqueta="informe del colector (texto)")
        informe.texto = t.salida
        informe.duracion += t.duracion
    else:
        informe.texto = r.salida
    return informe


def auditar_claves(conexion: Conexion, recursos: Recursos, idioma: str = "es",
                   cancelador: Optional[Cancelador] = None) -> dict:
    """Auditoría de ``authorized_keys`` del usuario de login (``--keys-only``). Sin sudo.

    Devuelve ``{"ok": bool, "datos": {...}, "texto": str, "error": str}``. ``datos`` contiene
    ``authorized_keys`` (claves, permisos, ajustes de sshd) y ``diagnostics``.
    """
    carga = recursos.leer(INFORME)
    ficticia = "/opt/telemet-collector/telemet-collector-info.py"
    r = conexion.ejecutar(remoto.comando_informe(carga, ["--lang", idioma, "--keys-only", "--json"], False,
                                                 conexion.perfil.python_remoto, ficticia),
                          cancelador=cancelador, etiqueta="auditar authorized_keys")
    try:
        datos = json.loads(r.salida)
    except ValueError:
        return {"ok": False, "datos": None, "texto": "", "error": r.error.strip() or conexion.explicar_fallo(r)}
    t = conexion.ejecutar(remoto.comando_informe(carga, ["--lang", idioma, "--keys-only", "--color"], False,
                                                 conexion.perfil.python_remoto, ficticia),
                          cancelador=cancelador, etiqueta="auditar authorized_keys (texto)")
    return {"ok": True, "datos": datos, "texto": t.salida, "error": ""}


# ----------------------------------------------------------------------------- comprobación y resumen
def comprobar(conexion: Conexion, ruta_config: str, cancelador: Optional[Cancelador] = None) -> Resultado:
    """Equivalente de ``--check``: texto plano con usuario, python, config.ini, sudo y servicios."""
    return conexion.ejecutar(remoto.comando_comprobar(ruta_config, conexion.perfil.python_remoto),
                             cancelador=cancelador, etiqueta="comprobar servidor")


def _parsear_clave_valor(texto: str) -> dict:
    datos = {}
    for linea in texto.splitlines():
        if "=" in linea:
            k, v = linea.split("=", 1)
            datos[k.strip()] = v.strip()
    return datos


def resumen_servidor(conexion: Conexion, ruta_config: str, cancelador: Optional[Cancelador] = None) -> dict:
    """Datos de estado del servidor para la pestaña Resumen. ``{"ok", "datos", "error"}``."""
    r = conexion.ejecutar(remoto.comando_resumen(ruta_config, conexion.perfil.python_remoto),
                          cancelador=cancelador, etiqueta="resumen del servidor")
    if not r.ok:
        return {"ok": False, "datos": {}, "error": r.error.strip() or conexion.explicar_fallo(r)}
    return {"ok": True, "datos": _parsear_clave_valor(r.salida), "error": ""}


# ----------------------------------------------------------------------------- servicio systemd
def estado_servicio(conexion: Conexion, nombre: str, cancelador: Optional[Cancelador] = None) -> dict:
    """Estado de un servicio: ``active``, ``enabled``, ``NRestarts``, ``ActiveEnterTimestamp``… y texto de status."""
    r = conexion.ejecutar(remoto.comando_estado_servicio(nombre), cancelador=cancelador,
                          etiqueta="estado del servicio %s" % nombre)
    if r.fallo_conexion or r.cancelado:
        return {"ok": False, "datos": {}, "texto": "", "error": r.error.strip() or conexion.explicar_fallo(r)}
    cabecera, _, status = r.salida.partition("\n---\n")
    return {"ok": True, "datos": _parsear_clave_valor(cabecera), "texto": status.strip(), "error": ""}


def accion_servicio(conexion: Conexion, accion: str, nombre: str,
                    cancelador: Optional[Cancelador] = None) -> Resultado:
    """``systemctl start|stop|restart|reload|enable|disable`` (con sudo si hace falta)."""
    usar = conexion.perfil.sudo_modo != SUDO_NUNCA
    return conexion.ejecutar_sudo(remoto.comando_accion_servicio(accion, nombre, usar), cancelador=cancelador,
                                  etiqueta="systemctl %s %s" % (accion, nombre))


def registro_servicio(conexion: Conexion, nombre: str, lineas: int = 200,
                      cancelador: Optional[Cancelador] = None) -> Resultado:
    """Últimas líneas de ``journalctl -u``."""
    usar = conexion.perfil.sudo_modo != SUDO_NUNCA
    return conexion.ejecutar_sudo(remoto.comando_registro_servicio(nombre, lineas, usar), cancelador=cancelador,
                                  etiqueta="journalctl -u %s" % nombre)


def desinstalar_servicio(conexion: Conexion, nombre: str, directorio: str, borrar_programa: bool,
                         hacer_copia: bool, cancelador: Optional[Cancelador] = None, al_linea=None) -> Resultado:
    """Elimina el servicio (y opcionalmente copia y borra ``/opt/…``)."""
    usar = conexion.perfil.sudo_modo != SUDO_NUNCA
    return conexion.ejecutar_sudo(
        remoto.comando_desinstalar_servicio(nombre, directorio, borrar_programa, hacer_copia, usar),
        cancelador=cancelador, on_salida=al_linea, etiqueta="desinstalar servicio %s" % nombre)

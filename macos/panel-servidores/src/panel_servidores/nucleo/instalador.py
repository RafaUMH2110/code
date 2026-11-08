"""Instalador de aplicaciones: ``instalar-todo.sh`` / ``instalar-todo-isa.sh`` desde la interfaz.

Qué hace la aplicación y qué hace el script
-------------------------------------------
El trabajo pesado (instalar Apache, clonar repos, desplegar con rsync, crear el servicio,
configurar Apache, cron…) lo sigue haciendo **el propio script**, que se sube al servidor y se
ejecuta allí. La aplicación aporta lo que un script no tiene:

* un formulario con validación en lugar de recordar 20 opciones,
* un selector de repos y carpetas (el menú interactivo del script, pero visual),
* el manejo de **sudo sin terminal** (ver ``remoto._SCRIPT_ENVOLTORIO``),
* las credenciales del colector por entorno (nunca por línea de comandos),
* progreso por pasos (1/6 … 6/6) a partir del propio registro del script,
* la confirmación gráfica de «el destino tiene contenido ajeno» (``--forzar``).
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import asdict, dataclass, field, fields
from typing import Callable, Optional

from . import remoto
from .modelos import VARIANTE_ISA, VARIANTE_LOCAL, Resultado
from .recursos import ACOMPANANTES, Recursos
from .ssh import Cancelador, Conexion

DOCROOT_POR_VARIANTE = {VARIANTE_LOCAL: "/var/www/html", VARIANTE_ISA: "/var/www/htdocs"}
URL_POR_VARIANTE = {VARIANTE_LOCAL: "", VARIANTE_ISA: "https://isa.umh.es"}
MODOS_PUBLICACION = ("web", "html", "todo")
SELECCION_GUARDADA = "guardada"   # no pasa nada: el script usa ORIGEN/.seleccion
SELECCION_TODOS = "todos"         # --todos
SELECCION_LISTA = "lista"         # --repos a,b/c
SELECCION_EXCLUIR = "excluir"     # --excluir x,y
DIR_SCRIPT_POR_DEFECTO = "~/panel-servidores/instalar-todo"
#: Destinos que el script rechaza (se reproducen aquí para avisar antes de subir nada).
DESTINOS_PROHIBIDOS = ("", "/", "/var", "/var/www", "/var/www/")


@dataclass
class OpcionesInstalador:
    """Todas las opciones del instalador (ver ``instalar-todo.sh -h``)."""

    variante: str = VARIANTE_LOCAL
    # --- origen y destino
    usuario_gh: str = "RafaUMH2110"        # -u
    origen: str = ""                       # -o   (vacío = ~/RafaUMH2110 en el servidor)
    destino: str = ""                      # -d   (vacío = <docroot>/rafa)
    docroot: str = ""                      # --docroot (vacío = el de la variante)
    forzar: bool = False                   # --forzar
    # --- qué clonar
    seleccion: str = SELECCION_GUARDADA
    repos: list = field(default_factory=list)      # elementos «repo» o «repo/carpeta»
    excluir: list = field(default_factory=list)
    # --- qué se publica
    modo: str = "web"                      # --modo web|html|todo
    sin_indice: bool = False               # --sin-indice
    # --- colector y cron
    colector: bool = False                 # --colector
    cron: str = ""                         # --cron "EXPR"
    # --- solo variante isa
    url: str = ""                          # --url
    entrada_raiz: bool = False             # --entrada-raiz
    json_dir: str = ""                     # --json-dir
    # --- dónde deja la aplicación el script en el servidor (cron guarda esta ruta)
    dir_script: str = DIR_SCRIPT_POR_DEFECTO

    # ------------------------------------------------------------------ valores efectivos
    def docroot_efectivo(self) -> str:
        return (self.docroot or DOCROOT_POR_VARIANTE[self.variante]).rstrip("/") or "/"

    def destino_efectivo(self) -> str:
        return (self.destino or self.docroot_efectivo() + "/rafa").rstrip("/")

    def entrada_web(self) -> str:
        """Ruta pública de la entrada (``/rafa/``), como la calcula el script."""
        d, base = self.destino_efectivo(), self.docroot_efectivo()
        return ("/" + d[len(base):].strip("/") + "/").replace("//", "/") if d.startswith(base + "/") else "/"

    # ------------------------------------------------------------------ validación
    def validar(self) -> list:
        """Errores de configuración que el script también rechazaría (lista vacía = todo bien)."""
        errores = []
        if self.modo not in MODOS_PUBLICACION:
            errores.append("El modo de publicación debe ser web, html o todo.")
        base, dest = self.docroot_efectivo(), self.destino_efectivo()
        if dest in DESTINOS_PROHIBIDOS or dest == base:
            errores.append("Destino no permitido: usa una subcarpeta de %s (por ejemplo %s/rafa)." % (base, base))
        elif not dest.startswith(base + "/"):
            errores.append("El destino debe estar dentro de %s (cambia el DocumentRoot si Apache sirve otra carpeta)." % base)
        if self.cron.strip() and len(self.cron.split()) != 5:
            errores.append("La expresión de cron debe tener 5 campos (minuto hora día mes día-semana), p. ej. «0 3 * * *».")
        for lista, nombre in ((self.repos, "repos"), (self.excluir, "excluidos")):
            for item in lista:
                if re.search(r"[\s,]", item):
                    errores.append("«%s» no es válido en la lista de %s (sin espacios ni comas)." % (item, nombre))
        if self.seleccion == SELECCION_LISTA and not self.repos:
            errores.append("Elige al menos un repo (o usa «Todos» / «Selección guardada»).")
        if self.seleccion == SELECCION_EXCLUIR and not self.excluir:
            errores.append("Indica qué repos excluir.")
        if self.variante == VARIANTE_ISA and self.url and not re.match(r"^https?://[^/\s]+$", self.url.rstrip("/")):
            errores.append("La URL pública debe ser como https://isa.umh.es (sin ruta).")
        if not self.dir_script.strip():
            errores.append("Indica la carpeta del servidor donde dejar el instalador.")
        if not re.match(r"^[A-Za-z0-9-]+$", self.usuario_gh or ""):
            errores.append("El usuario de GitHub solo puede contener letras, cifras y guiones.")
        return errores

    # ------------------------------------------------------------------ traducción a argumentos
    def a_argumentos(self) -> list:
        """Argumentos del script (en el orden de su ayuda)."""
        a: list = []
        if self.usuario_gh:
            a += ["-u", self.usuario_gh]
        if self.origen:
            a += ["-o", self.origen]
        if self.destino:
            a += ["-d", self.destino]
        if self.docroot:
            a += ["--docroot", self.docroot]
        if self.forzar:
            a.append("--forzar")
        if self.seleccion == SELECCION_TODOS:
            a.append("--todos")
        elif self.seleccion == SELECCION_LISTA and self.repos:
            a += ["--repos", ",".join(self.repos)]
        elif self.seleccion == SELECCION_EXCLUIR and self.excluir:
            a += ["--excluir", ",".join(self.excluir)]
        if self.modo != "web":
            a += ["--modo", self.modo]
        if self.sin_indice:
            a.append("--sin-indice")
        if self.colector:
            a.append("--colector")
        if self.cron.strip():
            a += ["--cron", self.cron.strip()]
        if self.variante == VARIANTE_ISA:
            if self.url:
                a += ["--url", self.url.rstrip("/")]
            if self.entrada_raiz:
                a.append("--entrada-raiz")
            if self.json_dir:
                a += ["--json-dir", self.json_dir]
        return a

    def comando_equivalente(self, recursos_nombre: Optional[str] = None) -> str:
        """El comando que ejecutarías a mano en el servidor (para copiarlo o aprender)."""
        nombre = recursos_nombre or Recursos.nombre_instalador(self.variante)
        partes = ["./" + nombre] + [shlex.quote(x) for x in self.a_argumentos()]
        return " ".join(partes)

    # ------------------------------------------------------------------ persistencia en el perfil
    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos: Optional[dict]) -> "OpcionesInstalador":
        validos = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (datos or {}).items() if k in validos})


# ----------------------------------------------------------------------------- análisis del registro
_RE_PASO = re.compile(r"^\[[\d\- :]+\] === (\d)/(\d) (.*) ===$")
_RE_REPOS = re.compile(r"Repos -> nuevos: (\d+) \| actualizados: (\d+) \(con cambios: (\d+), sin cambios: (\d+)\) \| errores: (\d+)")
_RE_DESPLIEGUE = re.compile(r"Resumen despliegue -> nuevos: (\d+) \| modificados: (\d+) \| borrados: (\d+) \| transferido (.+)$")
_RE_FIN = re.compile(r"FIN\. (?:Entrada|Portal): (\S+)\s+\|\s+Errores: (\d+)\s+\|\s+Duración: (\d+)s")
_RE_AJENO = re.compile(r"tiene contenido ajeno y no hay terminal")

PASOS = ("Dependencias", "Selección y clonado", "Despliegue en Apache", "Colector de telemetría",
         "Entrada del servidor", "Comprobación")


@dataclass
class EventoLog:
    """Qué significa una línea del registro del script."""

    tipo: str            # paso | error | aviso | fin | otro
    paso: int = 0
    titulo: str = ""


class AnalizadorLog:
    """Interpreta, línea a línea, el registro que escribe el instalador."""

    def __init__(self) -> None:
        self.paso = 0
        self.total = 6
        self.errores: list = []
        self.avisos: list = []
        self.resumen: dict = {}
        self.necesita_forzar = False

    def alimentar(self, linea: str) -> EventoLog:
        m = _RE_PASO.match(linea)
        if m:
            self.paso, self.total = int(m.group(1)), int(m.group(2))
            return EventoLog("paso", self.paso, m.group(3))
        if _RE_AJENO.search(linea):
            self.necesita_forzar = True
        m = _RE_REPOS.search(linea)
        if m:
            self.resumen.update(nuevos=int(m.group(1)), actualizados=int(m.group(2)),
                                con_cambios=int(m.group(3)), sin_cambios=int(m.group(4)), errores_repos=int(m.group(5)))
        m = _RE_DESPLIEGUE.search(linea)
        if m:
            self.resumen.update(desplegados_nuevos=int(m.group(1)), desplegados_modificados=int(m.group(2)),
                                desplegados_borrados=int(m.group(3)), transferido=m.group(4).strip())
        m = _RE_FIN.search(linea)
        if m:
            self.resumen.update(url=m.group(1), errores=int(m.group(2)), segundos=int(m.group(3)))
            return EventoLog("fin")
        if re.search(r"\bERROR\b", linea):
            self.errores.append(linea)
            return EventoLog("error")
        if re.search(r"\bAVISO\b", linea):
            self.avisos.append(linea)
            return EventoLog("aviso")
        return EventoLog("otro")


@dataclass
class ResultadoInstalacion:
    """Resultado de una ejecución del instalador."""

    codigo: int = 0
    resumen: dict = field(default_factory=dict)
    errores: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    necesita_forzar: bool = False
    mensaje: str = ""
    duracion: float = 0.0
    comando: str = ""

    @property
    def ok(self) -> bool:
        return self.codigo == 0


# ----------------------------------------------------------------------------- sudo
def asegurar_sudo(conexion: Conexion, cancelador: Optional[Cancelador] = None) -> tuple:
    """Comprueba que sudo funcionará sin terminal. Devuelve ``(ok, contraseña | None, mensaje)``.

    * root o ``NOPASSWD``: no hace falta nada.
    * con contraseña: se usa la conocida (SSH reutilizada, Llavero, entorno) o se pide, y **se
      valida con ``sudo -S true``** antes de lanzar una operación larga (hasta 3 intentos).
    """
    r = conexion.ejecutar(remoto.comando_comprobar_sudo(), cancelador=cancelador, etiqueta="comprobar sudo")
    if not r.ok:
        return False, None, r.error.strip() or conexion.explicar_fallo(r)
    estado = r.salida.strip().partition("=")[2]
    if estado in ("root", "nopasswd"):
        return True, None, estado
    if estado == "ausente":
        return False, None, "El servidor no tiene sudo y no entraste como root."
    if conexion.perfil.sudo_modo == "nunca":
        return False, None, "El perfil tiene desactivado sudo, pero el instalador necesita privilegios."
    clave = conexion.secretos.contrasena_sudo()
    for _ in range(3):
        if cancelador is not None and cancelador.cancelado:
            return False, None, "Cancelado."
        if not clave:
            clave = conexion.secretos.preguntar_sudo() if conexion.interactiva else None
        if not clave:
            return False, None, "Falta la contraseña de sudo."
        prueba = conexion.ejecutar(remoto.como_root("true"), entrada=(clave + "\n").encode("utf-8"),
                                   cancelador=cancelador, etiqueta="validar contraseña de sudo")
        if prueba.ok:
            return True, clave, "password"
        clave = None
        conexion.secretos.olvidar_tipo("sudo")
    return False, None, "La contraseña de sudo no es válida."


# ----------------------------------------------------------------------------- ejecución
def preparar_paquete(recursos: Recursos, variante: str) -> tuple:
    """tar.gz con el instalador de la variante y el portal. Devuelve ``(bytes, nombre_script)``."""
    nombre = Recursos.nombre_instalador(variante)
    ficheros = {nombre: recursos.leer(nombre)}
    for extra in ACOMPANANTES:
        if recursos.ruta(extra) is not None:
            ficheros[extra] = recursos.leer(extra)
    return remoto.empaquetar(ficheros), nombre


AlLinea = Callable[[str, bool], None]    # (texto, es_error)


def ejecutar_instalador(conexion: Conexion, recursos: Recursos, opciones: OpcionesInstalador,
                        credenciales: Optional[dict] = None, al_linea: Optional[AlLinea] = None,
                        al_paso: Optional[Callable[[EventoLog], None]] = None,
                        cancelador: Optional[Cancelador] = None, argumentos_extra: Optional[list] = None
                        ) -> ResultadoInstalacion:
    """Sube y ejecuta el instalador. Bloquea hasta que termina (llamar desde un hilo)."""
    errores = opciones.validar()
    if errores:
        return ResultadoInstalacion(codigo=3, mensaje="\n".join(errores))
    ok, clave_sudo, mensaje = asegurar_sudo(conexion, cancelador)
    if not ok:
        return ResultadoInstalacion(codigo=4, mensaje=mensaje)

    variables = {}
    if clave_sudo:
        variables["PANEL_SUDO_PW"] = clave_sudo
    for nombre, valor in (credenciales or {}).items():
        if valor:
            variables[nombre] = valor
    paquete, nombre_script = preparar_paquete(recursos, opciones.variante)
    entrada = remoto.cabecera_entrada(variables) + paquete
    argumentos = opciones.a_argumentos() + list(argumentos_extra or [])
    comando = remoto.comando_instalador(opciones.dir_script, nombre_script, argumentos)

    analizador = AnalizadorLog()

    def recibir(texto: str, es_error: bool) -> None:
        evento = analizador.alimentar(texto)
        if al_linea:
            al_linea(texto, es_error)
        if al_paso and evento.tipo in ("paso", "fin"):
            al_paso(evento)

    r = conexion.ejecutar(comando, entrada=entrada, on_salida=lambda t: recibir(t, False),
                          on_error=lambda t: recibir(t, True), timeout=7200, cancelador=cancelador,
                          etiqueta="instalador %s %s" % (nombre_script, " ".join(argumentos)))
    res = ResultadoInstalacion(codigo=r.codigo, resumen=analizador.resumen, errores=analizador.errores,
                               avisos=analizador.avisos, necesita_forzar=analizador.necesita_forzar,
                               duracion=r.duracion, comando=opciones.comando_equivalente(nombre_script))
    if r.fallo_conexion or r.cancelado:
        res.mensaje = conexion.explicar_fallo(r)
    elif r.codigo in (70, 71, 72, 73, 74, 75, 76):
        res.mensaje = "No se pudo preparar el instalador en el servidor (código %d). %s" % (r.codigo, r.error.strip())
    return res


def listar_en_servidor(conexion: Conexion, recursos: Recursos, opciones: OpcionesInstalador,
                       al_linea: Optional[AlLinea] = None, cancelador: Optional[Cancelador] = None
                       ) -> ResultadoInstalacion:
    """``--listar``: repos y carpetas disponibles y la selección guardada, tal como los ve el servidor."""
    paquete, nombre = preparar_paquete(recursos, opciones.variante)
    args = ["--listar"]
    if opciones.usuario_gh:
        args += ["-u", opciones.usuario_gh]
    if opciones.origen:
        args += ["-o", opciones.origen]
    comando = remoto.comando_instalador(opciones.dir_script, nombre, args)
    r = conexion.ejecutar(comando, entrada=remoto.cabecera_entrada({}) + paquete,
                          on_salida=(lambda t: al_linea(t, False)) if al_linea else None,
                          on_error=(lambda t: al_linea(t, True)) if al_linea else None,
                          timeout=300, cancelador=cancelador, etiqueta="instalador --listar")
    return ResultadoInstalacion(codigo=r.codigo, mensaje=r.error.strip() if not r.ok else "", duracion=r.duracion)


# ----------------------------------------------------------------------------- consultas auxiliares
def ruta_origen(opciones: OpcionesInstalador) -> str:
    return (opciones.origen or "~/RafaUMH2110").rstrip("/")


def leer_seleccion_guardada(conexion: Conexion, opciones: OpcionesInstalador) -> list:
    """Líneas de ``ORIGEN/.seleccion`` (lo que el servidor clonará la próxima vez y en cron)."""
    r = conexion.ejecutar(remoto.comando_leer_fichero(ruta_origen(opciones) + "/.seleccion"), etiqueta="leer .seleccion")
    if r.codigo == 66:
        return []
    if not r.ok:
        raise RuntimeError(r.error.strip() or conexion.explicar_fallo(r))
    return [l.strip() for l in r.salida.splitlines() if l.strip() and not l.startswith("#")]


def leer_registro(conexion: Conexion, opciones: OpcionesInstalador, lineas: int = 300) -> str:
    """Final de ``ORIGEN/instalar-todo.log``."""
    r = conexion.ejecutar(remoto.comando_leer_fichero(ruta_origen(opciones) + "/instalar-todo.log", lineas),
                          etiqueta="leer instalar-todo.log")
    if r.codigo == 66:
        return "(todavía no hay registro: el instalador no se ha ejecutado)"
    if not r.ok:
        raise RuntimeError(r.error.strip() or conexion.explicar_fallo(r))
    return r.salida


def leer_apps(conexion: Conexion, opciones: OpcionesInstalador) -> dict:
    """Catálogo ``apps.json`` desplegado (lo que lista el portal)."""
    r = conexion.ejecutar(remoto.comando_leer_fichero(opciones.destino_efectivo() + "/apps.json"), etiqueta="leer apps.json")
    if r.codigo == 66:
        return {"generated": "", "apps": []}
    if not r.ok:
        raise RuntimeError(r.error.strip() or conexion.explicar_fallo(r))
    return json.loads(r.salida)


def leer_crontab(conexion: Conexion) -> str:
    r = conexion.ejecutar(remoto.sh_c("crontab -l 2>/dev/null; true"), etiqueta="leer crontab")
    if not r.ok:
        raise RuntimeError(r.error.strip() or conexion.explicar_fallo(r))
    return r.salida


def quitar_entradas_cron(crontab: str, patron: str = "instalar-todo") -> tuple:
    """Quita del crontab las líneas que contienen ``patron``. Devuelve ``(nuevo_texto, quitadas)``."""
    mantener, quitadas = [], []
    for linea in crontab.splitlines():
        (quitadas if patron in linea and not linea.lstrip().startswith("#") else mantener).append(linea)
    return ("\n".join(mantener) + "\n") if mantener else "", quitadas


def escribir_crontab(conexion: Conexion, texto: str) -> Resultado:
    """Sustituye el crontab del usuario (``crontab -`` leyendo de la entrada estándar)."""
    return conexion.ejecutar("crontab -", entrada=texto.encode("utf-8"), etiqueta="escribir crontab")


def listar_copias(conexion: Conexion) -> list:
    r = conexion.ejecutar(remoto.comando_listar_copias(), etiqueta="copias de seguridad")
    return [l for l in r.salida.splitlines() if l.strip()] if r.ok else []

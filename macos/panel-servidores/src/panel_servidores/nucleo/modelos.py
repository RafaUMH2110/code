"""Modelos de datos compartidos por el núcleo y la interfaz.

Se usan ``dataclasses`` sencillas y serializables a JSON (sin Qt, sin librerías externas).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Callable, Optional, Protocol

# ----------------------------------------------------------------------------- códigos de salida
# Son los mismos que usa ``telemet-collector-info-ssh.py`` (ver su manual, sección 8).
COD_OK = 0            # todo correcto
COD_DIAGNOSTICO = 1   # el informe se generó y el diagnóstico encontró algún error
COD_SIN_CONFIG = 2    # conectó, pero no se pudo leer config.ini
COD_LOCAL = 3         # problema local: no hay ssh, falta un recurso, destino inválido
COD_CONEXION = 4      # fallo de conexión SSH / autenticación / sudo / python / tiempo agotado
COD_SIN_CLAVE = 5     # --check-key / --install-key: el servidor no acepta solo clave

#: Códigos de proceso especiales que devuelve ``Conexion.ejecutar``.
RC_SSH_FALLO = 255    # ssh no pudo conectar o autenticar
RC_TIMEOUT = 124      # tiempo agotado (mismo convenio que ``timeout(1)``)
RC_CANCELADO = 130    # el usuario canceló la operación (como Ctrl-C)
RC_NO_ENCONTRADO = 127  # comando no encontrado (p. ej. python3 en el servidor)


# ----------------------------------------------------------------------------- secretos
ORIGEN_PREGUNTAR = "preguntar"   # se pide en un diálogo (y se recuerda mientras dure la sesión)
ORIGEN_LLAVERO = "llavero"       # se guarda en el Llavero de macOS
ORIGEN_ENTORNO = "entorno"       # se lee de una variable de entorno (como --password-env)


@dataclass
class FuenteSecreto:
    """Dónde obtener un secreto (contraseña SSH, frase de paso o contraseña de sudo)."""

    origen: str = ORIGEN_PREGUNTAR
    variable: str = ""  # nombre de la variable de entorno si origen == "entorno"


# ----------------------------------------------------------------------------- perfil de servidor
AUTH_AUTO = "auto"              # ssh decide: claves por defecto, ssh-agent, ~/.ssh/config…
AUTH_CLAVE = "clave"            # una clave concreta (-i) con IdentitiesOnly
AUTH_PASSWORD = "password"      # solo contraseña
AUTH_INTERACTIVA = "interactiva"  # keyboard-interactive: contraseña + código 2FA, etc.

SUDO_AUTO = "auto"        # usa sudo si no eres root; reutiliza la contraseña SSH si la hay
SUDO_NUNCA = "nunca"      # no usar sudo (equivale a --no-sudo)
SUDO_SECRETO = "secreto"  # contraseña de sudo propia (preguntar / llavero / entorno)

VARIANTE_LOCAL = "local"  # instalar-todo.sh      (servidor local Debian 13)
VARIANTE_ISA = "isa"      # instalar-todo-isa.sh  (producción isa.umh.es)


@dataclass
class Perfil:
    """Un servidor guardado: cómo conectar, cómo autenticarse y valores por defecto."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    nombre: str = ""
    #: ``[usuario@]host[:puerto]`` o un alias de ``~/.ssh/config``.
    destino: str = ""
    usuario: str = ""            # si no va en el destino (equivale a -u)
    puerto: int = 0              # si no va en el destino (equivale a -p); 0 = el de ssh
    # --- autenticación
    autenticacion: str = AUTH_AUTO
    identidad: str = ""          # ruta de la clave privada (-i)
    password: FuenteSecreto = field(default_factory=FuenteSecreto)
    frase: FuenteSecreto = field(default_factory=FuenteSecreto)
    # --- sudo en el servidor
    sudo_modo: str = SUDO_AUTO
    sudo: FuenteSecreto = field(default_factory=FuenteSecreto)
    reutilizar_password_sudo: bool = True   # (inverso de --no-reuse-password)
    # --- opciones de conexión
    aceptar_huella_nueva: bool = False      # --accept-new-host-key
    salto: str = ""                         # ProxyJump (-J)
    opciones_ssh: list = field(default_factory=list)  # --ssh-arg (una opción por elemento)
    multiplexar: bool = True                # reutilizar la conexión (ControlMaster)
    timeout_conexion: int = 15              # --connect-timeout
    timeout_total: int = 90                 # --timeout
    python_remoto: str = "python3"          # --remote-python
    # --- colector de telemetría
    ruta_config: str = "/opt/telemet-collector/config.ini"   # -c
    servicio: str = "telemet-collector"                      # --service
    # --- despliegue (instalador)
    variante: str = VARIANTE_LOCAL
    url_base: str = ""           # p. ej. http://192.168.0.129 o https://isa.umh.es
    instalador: dict = field(default_factory=dict)   # últimas opciones usadas
    notas: str = ""

    # ------------------------------------------------------------------ serialización
    def a_dict(self) -> dict:
        """Diccionario listo para ``json.dump``."""
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos: dict) -> "Perfil":
        """Reconstruye un perfil ignorando claves desconocidas (compatibilidad hacia delante)."""
        validos = {f.name for f in fields(cls)}
        limpio: dict[str, Any] = {k: v for k, v in datos.items() if k in validos}
        for nombre in ("password", "frase", "sudo"):
            valor = limpio.get(nombre)
            if isinstance(valor, dict):
                limpio[nombre] = FuenteSecreto(**{k: v for k, v in valor.items()
                                                 if k in ("origen", "variable")})
        return cls(**limpio)

    def etiqueta(self) -> str:
        """Texto corto para listas: el nombre si existe, si no el destino."""
        return self.nombre or self.destino or "(sin nombre)"


# ----------------------------------------------------------------------------- ajustes globales
@dataclass
class Ajustes:
    """Preferencias de la aplicación (no dependen de un servidor concreto)."""

    ssh_path: str = ""                 # vacío = autodetectar
    idioma_informe: str = "es"         # idioma del informe del colector (es | en)
    carpeta_scripts: str = ""          # carpeta con scripts propios (sustituye a los incluidos)
    usuario_github: str = "RafaUMH2110"
    rama_github: str = "main"
    mostrar_clave_api: bool = False    # --show-key por defecto
    confirmar_acciones: bool = True    # pedir confirmación antes de acciones que escriben
    max_lineas_consola: int = 20000
    tema: str = "sistema"              # sistema | claro | oscuro
    terminal: str = "Terminal"         # aplicación para «Abrir en Terminal»: Terminal | iTerm
    token_github: str = ""             # opcional: sube el límite de peticiones de la API de GitHub

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos: dict) -> "Ajustes":
        validos = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in datos.items() if k in validos})


# ----------------------------------------------------------------------------- resultado de un comando
@dataclass
class Resultado:
    """Resultado de ejecutar un comando remoto (o local)."""

    codigo: int
    salida: str = ""
    error: str = ""
    duracion: float = 0.0
    comando: str = ""   # versión legible y SIN secretos, para el registro de actividad

    @property
    def ok(self) -> bool:
        return self.codigo == 0

    @property
    def fallo_conexion(self) -> bool:
        """ssh no llegó a ejecutar el comando (conexión, autenticación o tiempo)."""
        return self.codigo in (RC_SSH_FALLO, RC_TIMEOUT)

    @property
    def cancelado(self) -> bool:
        return self.codigo == RC_CANCELADO


# ----------------------------------------------------------------------------- interacción con el usuario
class Interaccion(Protocol):
    """Cómo el núcleo pide datos al usuario sin depender de ninguna interfaz concreta.

    La interfaz gráfica implementa esto con diálogos (``ui/puente.py``); las pruebas, con
    respuestas predefinidas. Los métodos se llaman desde hilos de trabajo y pueden bloquear
    hasta que el usuario responda.
    """

    def pedir_secreto(self, titulo: str, mensaje: str, permitir_recordar: bool = False
                      ) -> Optional[tuple]:
        """Pide un secreto. Devuelve ``(valor, recordar_en_llavero)`` o ``None`` si cancela."""

    def confirmar(self, titulo: str, mensaje: str) -> bool:
        """Pregunta sí/no (por ejemplo, confiar en la huella de un servidor nuevo)."""


class InteraccionNula:
    """Implementación sin usuario: rechaza todo (modo desatendido, ``--batch``)."""

    def pedir_secreto(self, titulo, mensaje, permitir_recordar=False):
        return None

    def confirmar(self, titulo, mensaje):
        return False


#: Tipo de las funciones que reciben cada línea de salida de un comando.
FuncionLinea = Callable[[str], None]

"""Conexión SSH: todas las variantes de autenticación de ``telemet-collector-info-ssh.py``.

Se usa el cliente ``ssh`` del sistema (OpenSSH) y NO una librería de SSH en Python, por las
mismas razones que en el script original:

* respeta ``~/.ssh/config`` (alias, ``ProxyJump``, ``IdentityFile``…), ``known_hosts`` y el
  ``ssh-agent`` / Llavero de macOS,
* sirve cualquier método que soporte tu OpenSSH (claves RSA/ed25519/ecdsa/FIDO, 2FA…),
* no hay que auditar ni mantener ninguna implementación criptográfica propia.

Variantes de autenticación que soporta (perfil → opciones de ``ssh``)
--------------------------------------------------------------------
=============  =====================================================================
auto           ssh decide: claves por defecto, ssh-agent, lo que diga ~/.ssh/config.
clave          ``-i RUTA -o IdentitiesOnly=yes`` (solo esa clave); frase de paso por askpass.
password       solo contraseña (``PubkeyAuthentication=no``); un único intento.
interactiva    keyboard-interactive: contraseña + código 2FA; cada pregunta va al usuario.
=============  =====================================================================

Además: alias de ``~/.ssh/config``, ``ProxyJump``, opciones extra (``--ssh-arg``), puerto,
aceptar huellas nuevas, tiempos de espera y ``sudo`` en el servidor.

Mejoras sobre el script
-----------------------
* **Multiplexado (ControlMaster)**: se autentica UNA vez y las demás órdenes del mismo servidor
  reutilizan la conexión (instantáneo y sin volver a pedir contraseña ni 2FA).
* **Askpass gráfico**: contraseñas, frases de paso, 2FA y huellas se piden en diálogos.
* **Streaming**: la salida llega línea a línea para mostrarla en vivo.
* **Cancelación**: cualquier operación se puede abortar.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .. import rutas
from .askpass import GestorAskpass
from .modelos import (AUTH_CLAVE, AUTH_INTERACTIVA, AUTH_PASSWORD, RC_CANCELADO, RC_SSH_FALLO,
                      RC_TIMEOUT, Ajustes, FuncionLinea, Interaccion, InteraccionNula, Perfil,
                      Resultado, SUDO_NUNCA)
from .secretos import ResolutorSecretos

#: Mensajes de sudo que indican «necesito contraseña / la que diste no vale».
RE_SUDO_FALLO = re.compile(r"sudo: (a password is required|no password was provided|"
                           r"\d+ incorrect password|Sorry, try again|a terminal is required)", re.I)
# Sin espacios ni caracteres de control, y usuario/host no pueden empezar por «-» (ssh lo tomaría por una
# opción: «-oProxyCommand=…» ejecutaría un comando local). Es una defensa contra inyección de opciones.
RE_DESTINO = re.compile(r"^(?:(?P<user>[^@\s\-][^@\s]*)@)?(?P<host>\[[^\]\s]+\]|[^:@\s\-][^:@\s]*)(?::(?P<port>\d+))?$")
RE_HUELLA_CAMBIADA = re.compile(r"REMOTE HOST IDENTIFICATION HAS CHANGED|Host key verification failed", re.I)

#: Tiempo máximo para abrir la conexión principal: incluye el que tarda el usuario en teclear.
ESPERA_AUTENTICACION_S = 600


# ----------------------------------------------------------------------------- destinos
@dataclass
class Destino:
    """``[usuario@]host[:puerto]`` descompuesto."""

    usuario: str
    host: str
    puerto: int


def analizar_destino(texto: str) -> Optional[Destino]:
    """Descompone un destino. Un alias de ``~/.ssh/config`` (solo un nombre) también es válido.

    Devuelve ``None`` si el texto no tiene forma de destino.
    """
    m = RE_DESTINO.match((texto or "").strip())
    if not m:
        return None
    host = m.group("host")
    if host.startswith("[") and host.endswith("]"):     # IPv6 entre corchetes
        host = host[1:-1]
    return Destino(m.group("user") or "", host, int(m.group("port") or 0))


class Cancelador:
    """Señal compartida para abortar una operación larga desde otro hilo."""

    def __init__(self) -> None:
        self._evento = threading.Event()

    def cancelar(self) -> None:
        self._evento.set()

    @property
    def cancelado(self) -> bool:
        return self._evento.is_set()


# ----------------------------------------------------------------------------- proceso con streaming
def _terminar(proceso: subprocess.Popen) -> None:
    """Termina un proceso (y su grupo) con amabilidad primero y a la fuerza después."""
    try:
        os.killpg(proceso.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        proceso.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proceso.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def ejecutar_proceso(args: list, entorno: dict, entrada: bytes = b"", on_salida: Optional[FuncionLinea] = None,
                     on_error: Optional[FuncionLinea] = None, timeout: Optional[float] = None,
                     cancelador: Optional[Cancelador] = None) -> tuple:
    """Ejecuta ``args`` y devuelve ``(codigo, stdout, stderr, segundos)``.

    * La salida se entrega línea a línea mediante los *callbacks* mientras se produce.
    * ``entrada`` se escribe en un hilo aparte (evita interbloqueos con entradas grandes).
    * ``start_new_session=True`` desvincula el proceso del terminal: así ``ssh`` usa el askpass
      en lugar de intentar leer una contraseña de un terminal inexistente.
    """
    inicio = time.monotonic()
    try:
        proceso = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=entorno, start_new_session=True)
    except OSError as exc:
        return 127, "", "No se pudo ejecutar %s: %s\n" % (args[0], exc), 0.0

    salida: list = []
    errores: list = []

    def leer(pipe, acumulado, callback):
        for linea in iter(pipe.readline, b""):
            texto = linea.decode("utf-8", "replace")
            acumulado.append(texto)
            if callback:
                try:
                    callback(texto.rstrip("\r\n"))
                except Exception:       # un fallo al pintar no debe interrumpir la lectura
                    pass

    def escribir():
        try:
            if entrada:
                proceso.stdin.write(entrada)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                proceso.stdin.close()
            except OSError:
                pass

    hilos = [threading.Thread(target=leer, args=(proceso.stdout, salida, on_salida), daemon=True),
             threading.Thread(target=leer, args=(proceso.stderr, errores, on_error), daemon=True),
             threading.Thread(target=escribir, daemon=True)]
    for h in hilos:
        h.start()

    codigo_especial = None
    while True:
        try:
            proceso.wait(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            if cancelador is not None and cancelador.cancelado:
                codigo_especial = RC_CANCELADO
            elif timeout and (time.monotonic() - inicio) > timeout:
                codigo_especial = RC_TIMEOUT
            if codigo_especial is not None:
                _terminar(proceso)
                break
    for h in hilos:
        h.join(timeout=3)
    codigo = codigo_especial if codigo_especial is not None else proceso.returncode
    texto_error = "".join(errores)
    if codigo_especial == RC_TIMEOUT:
        texto_error += "timeout (%d s)\n" % int(timeout or 0)
    return codigo, "".join(salida), texto_error, time.monotonic() - inicio


# ----------------------------------------------------------------------------- conexión
class Conexion:
    """Una conexión (lógica) a un servidor: construye los comandos ``ssh`` y los ejecuta.

    Es segura entre hilos. Con ``perfil.multiplexar`` mantiene una conexión principal abierta
    (``ControlMaster``) que reutilizan todas las órdenes; ``cerrar()`` la termina.
    """

    def __init__(self, perfil: Perfil, ajustes: Ajustes, askpass: GestorAskpass,
                 interaccion: Optional[Interaccion] = None, secretos: Optional[ResolutorSecretos] = None,
                 registro: Optional[FuncionLinea] = None, desatendido: bool = False):
        self.perfil = perfil
        self.ajustes = ajustes
        self.askpass = askpass
        self.interaccion: Interaccion = interaccion or InteraccionNula()
        self.secretos = secretos or ResolutorSecretos(perfil, self.interaccion)
        self.registro = registro
        #: ``True`` = como ``--batch``: nunca pregunta nada (para automatizar).
        self.desatendido = desatendido
        self._token = askpass.registrar(self.secretos.responder_askpass)
        self._dir_control: Optional[Path] = None
        self._maestro = False
        self._cerrojo = threading.Lock()

    # ------------------------------------------------------------------ propiedades
    @property
    def ssh(self) -> str:
        return rutas.buscar_ejecutable("ssh", self.ajustes.ssh_path)

    @property
    def destino(self) -> Optional[Destino]:
        return analizar_destino(self.perfil.destino)

    @property
    def interactiva(self) -> bool:
        """Hay un usuario que pueda contestar preguntas."""
        return not self.desatendido and not isinstance(self.interaccion, InteraccionNula)

    def destino_ssh(self) -> str:
        """Texto ``usuario@host`` que se pasa a ssh (o el alias tal cual)."""
        d = self.destino
        if d is None:
            raise ValueError("Destino no válido: %r (formato: [usuario@]servidor[:puerto] o un alias de ~/.ssh/config)"
                             % self.perfil.destino)
        usuario = d.usuario or self.perfil.usuario
        return "%s@%s" % (usuario, d.host) if usuario else d.host

    def etiqueta(self) -> str:
        return self.perfil.etiqueta()

    # ------------------------------------------------------------------ construcción de opciones
    def _ruta_control(self) -> str:
        if self._dir_control is None:
            # /tmp explícito por el límite de ~104 caracteres de las rutas de socket Unix en macOS.
            self._dir_control = Path(tempfile.mkdtemp(prefix="ps-ctl-", dir="/tmp"))
        return str(self._dir_control / "%C")     # %C = hash de (host, puerto, usuario)

    def opciones(self, solo_clave: bool = False, maestro: bool = False, usar_maestro: bool = True,
                 identidad: str = "") -> list:
        """Opciones de ``ssh`` (sin destino ni comando).

        ``solo_clave`` reproduce la prueba de ``--check-key``: nada de contraseñas, ``-v`` para
        saber qué clave se ofreció y cuál aceptó el servidor. ``identidad`` fuerza una clave
        concreta para esta llamada (si no, se usa la del perfil cuando corresponde).
        """
        p = self.perfil
        d = self.destino
        opts: list = []
        puerto = (d.puerto if d else 0) or p.puerto
        if puerto:
            opts += ["-p", str(puerto)]
        clave = identidad or p.identidad
        if clave and (identidad or p.autenticacion == AUTH_CLAVE or solo_clave):
            opts += ["-i", os.path.expanduser(clave), "-o", "IdentitiesOnly=yes"]
        opts += ["-o", "ConnectTimeout=%d" % p.timeout_conexion, "-o", "ServerAliveInterval=15",
                 "-o", "ForwardAgent=no", "-o", "ForwardX11=no", "-T"]
        if solo_clave:
            # LogLevel no se fija: el primer -o LogLevel ganaría sobre -v.
            opts += ["-v", "-o", "PreferredAuthentications=publickey", "-o", "PubkeyAuthentication=yes",
                     "-o", "PasswordAuthentication=no", "-o", "KbdInteractiveAuthentication=no",
                     "-o", "ControlPath=none"]
        else:
            opts += ["-o", "LogLevel=ERROR", "-o", "NumberOfPasswordPrompts=1"]
            if p.autenticacion in (AUTH_PASSWORD, AUTH_INTERACTIVA):
                opts += ["-o", "PreferredAuthentications=keyboard-interactive,password",
                         "-o", "PubkeyAuthentication=no"]
        if p.aceptar_huella_nueva:
            opts += ["-o", "StrictHostKeyChecking=accept-new"]
        if self.desatendido:
            opts += ["-o", "BatchMode=yes"]
        if p.salto:
            opts += ["-J", p.salto]
        for extra in p.opciones_ssh or []:
            opts += shlex.split(extra)
        if not solo_clave and p.multiplexar:
            if maestro:
                opts += ["-o", "ControlMaster=yes", "-o", "ControlPath=" + self._ruta_control(),
                         "-o", "ControlPersist=900"]
            elif usar_maestro:
                opts += ["-o", "ControlMaster=no", "-o", "ControlPath=" + self._ruta_control()]
        return opts

    def _entorno(self) -> dict:
        entorno = dict(os.environ)
        entorno.update(self.askpass.entorno(self._token))
        return entorno

    def comando_terminal(self, comando_remoto: str = "") -> str:
        """Orden equivalente para pegar en un terminal (sin secretos, sin multiplexado).

        Solo incluye lo que importa a una persona: puerto, clave, salto, huella y opciones extra.
        """
        p, d = self.perfil, self.destino
        partes = ["ssh"]
        puerto = (d.puerto if d else 0) or p.puerto
        if puerto:
            partes += ["-p", str(puerto)]
        if p.identidad and p.autenticacion == AUTH_CLAVE:
            partes += ["-i", p.identidad]
        if p.salto:
            partes += ["-J", p.salto]
        if p.aceptar_huella_nueva:
            partes += ["-o", "StrictHostKeyChecking=accept-new"]
        for extra in p.opciones_ssh or []:
            partes += shlex.split(extra)
        partes.append(self.destino_ssh())
        if comando_remoto:
            partes.append(comando_remoto)
        return " ".join(shlex.quote(x) for x in partes)

    def _anotar(self, etiqueta: str, opciones: list) -> None:
        if self.registro:
            visibles, i = [], 0
            while i < len(opciones):                    # oculta «-o ControlPath=…» (es ruido interno)
                if opciones[i] == "-o" and i + 1 < len(opciones) and opciones[i + 1].startswith("ControlPath="):
                    i += 2
                    continue
                visibles.append(opciones[i])
                i += 1
            self.registro("$ ssh %s %s   # %s" % (" ".join(shlex.quote(x) for x in visibles),
                                                  self.destino_ssh(), etiqueta))

    # ------------------------------------------------------------------ conexión principal (multiplexado)
    def _maestro_vivo(self) -> bool:
        if not self._maestro or self._dir_control is None:
            return False
        # Se pasan las MISMAS opciones que a la conexión principal: %C (el nombre del socket) depende
        # de host, puerto, usuario y salto, y con otro valor ssh buscaría un socket distinto.
        r = subprocess.run([self.ssh, "-O", "check"] + self.opciones() + [self.destino_ssh()],
                           stdin=subprocess.DEVNULL, capture_output=True)
        return r.returncode == 0

    def _asegurar_maestro(self, cancelador: Optional[Cancelador]) -> Optional[Resultado]:
        """Abre la conexión principal si hace falta. Devuelve un ``Resultado`` de error o ``None``."""
        with self._cerrojo:
            if self._maestro_vivo():
                return None
            opts = self.opciones(maestro=True) + ["-N", "-f"]
            self._anotar("abrir conexión principal", opts)
            with tempfile.TemporaryFile() as ficheros_err:
                # stdout/stderr van a ficheros, no a tuberías: el proceso en segundo plano
                # los hereda y, con tuberías, el lector se quedaría esperando eternamente.
                proc = subprocess.Popen([self.ssh] + opts + [self.destino_ssh()], stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=ficheros_err, env=self._entorno(),
                                        start_new_session=True)
                inicio = time.monotonic()
                while True:
                    try:
                        proc.wait(timeout=0.1)
                        break
                    except subprocess.TimeoutExpired:
                        if cancelador is not None and cancelador.cancelado:
                            _terminar(proc)
                            return Resultado(RC_CANCELADO, "", "Cancelado\n", time.monotonic() - inicio)
                        if time.monotonic() - inicio > ESPERA_AUTENTICACION_S:
                            _terminar(proc)
                            return Resultado(RC_TIMEOUT, "", "timeout abriendo la conexión\n",
                                             time.monotonic() - inicio)
                ficheros_err.seek(0)
                texto = ficheros_err.read().decode("utf-8", "replace")
            if proc.returncode == 0:
                self._maestro = True
                return None
            return Resultado(proc.returncode or RC_SSH_FALLO, "", texto, time.monotonic() - inicio,
                             "abrir conexión principal")

    @property
    def abierta(self) -> bool:
        """``True`` si hay una conexión principal viva (solo con multiplexado)."""
        return self._maestro_vivo()

    def conectar(self, cancelador: Optional[Cancelador] = None) -> Resultado:
        """Autentica y deja la conexión lista; devuelve ``ok`` si el servidor responde."""
        r = self.ejecutar('echo "user=$(id -un) uid=$(id -u) host=$(hostname)"', timeout=ESPERA_AUTENTICACION_S,
                          cancelador=cancelador, etiqueta="probar conexión")
        return r

    def cerrar(self) -> None:
        """Cierra la conexión principal y libera todo (se llama al salir o al desconectar)."""
        with self._cerrojo:
            if self._maestro and self._dir_control is not None:
                subprocess.run([self.ssh, "-O", "exit"] + self.opciones() + [self.destino_ssh()],
                               stdin=subprocess.DEVNULL, capture_output=True)
            self._maestro = False
            if self._dir_control is not None:
                shutil.rmtree(self._dir_control, ignore_errors=True)
                self._dir_control = None
            self.secretos.olvidar()

    def destruir(self) -> None:
        """``cerrar()`` y además desregistra el askpass (la conexión ya no se podrá reutilizar)."""
        self.cerrar()
        self.askpass.liberar(self._token)

    # ------------------------------------------------------------------ ejecución de órdenes
    def ejecutar(self, comando: str, *, entrada: bytes = b"", on_salida: Optional[FuncionLinea] = None,
                 on_error: Optional[FuncionLinea] = None, timeout: Optional[float] = None,
                 cancelador: Optional[Cancelador] = None, solo_clave: bool = False,
                 etiqueta: str = "", identidad: str = "") -> Resultado:
        """Ejecuta ``comando`` (cadena para el shell remoto) y devuelve el ``Resultado``."""
        try:
            destino = self.destino_ssh()
        except ValueError as exc:
            return Resultado(3, "", str(exc) + "\n")
        if timeout is None:
            timeout = self.perfil.timeout_total
        if self.perfil.multiplexar and not solo_clave:
            fallo = self._asegurar_maestro(cancelador)
            if fallo is not None:
                return fallo
        opts = self.opciones(solo_clave=solo_clave, identidad=identidad)
        self._anotar(etiqueta or "comando remoto", opts)
        codigo, salida, error, duracion = ejecutar_proceso(
            [self.ssh] + opts + [destino, comando], self._entorno(), entrada, on_salida, on_error,
            timeout, cancelador)
        return Resultado(codigo, salida, error, duracion, etiqueta)

    def ejecutar_sudo(self, comando: str, *, entrada_extra: bytes = b"", **kw) -> Resultado:
        """Como ``ejecutar`` pero para comandos que usan sudo (``remoto.como_root``).

        Pone la contraseña de sudo (si se conoce) en la primera línea de la entrada estándar y,
        si sudo la rechaza y hay usuario delante, la pide y reintenta UNA vez, igual que hacía
        el script original.

        Orden importante: primero se autentica (así la contraseña SSH, si se usó, ya está en
        memoria y puede reutilizarse como contraseña de sudo) y solo después se decide qué enviar.
        """
        usar = self.perfil.sudo_modo != SUDO_NUNCA
        if usar and self.perfil.multiplexar:
            fallo = self._asegurar_maestro(kw.get("cancelador"))
            if fallo is not None:
                return fallo
        clave = self.secretos.contrasena_sudo() if usar else None
        entrada = (clave + "\n").encode("utf-8") if clave else b""
        r = self.ejecutar(comando, entrada=entrada + entrada_extra, **kw)
        if usar and r.codigo != 0 and RE_SUDO_FALLO.search(r.error) and self.interactiva:
            # Sin multiplexado la contraseña SSH solo se conoce tras la primera orden: se reintenta con ella
            # antes de molestar al usuario.
            nueva = self.secretos.contrasena_sudo()
            if not nueva or nueva == clave:
                nueva = self.secretos.preguntar_sudo()
            if nueva:
                r = self.ejecutar(comando, entrada=(nueva + "\n").encode("utf-8") + entrada_extra, **kw)
        return r

    # ------------------------------------------------------------------ utilidades de diagnóstico
    def explicar_fallo(self, r: Resultado) -> str:
        """Traduce un fallo de conexión en un mensaje con pistas (como el script original)."""
        if r.cancelado:
            return "Operación cancelada."
        if r.codigo == RC_TIMEOUT:
            return "Tiempo agotado. Revisa la red o aumenta los tiempos de espera del perfil."
        if r.codigo == RC_SSH_FALLO or r.codigo == 255:
            texto = "No se pudo conectar por SSH con %s. Revisa servidor, puerto, usuario, contraseña o clave." % self.etiqueta()
            if RE_HUELLA_CAMBIADA.search(r.error):
                texto += ("\nLa huella del servidor no coincide con la de known_hosts. Averigua por qué cambió antes de "
                          "borrarla (pestaña «Claves SSH» → «Olvidar huella»).")
            elif "Permission denied" in r.error:
                texto += "\nEl servidor rechazó las credenciales (Permission denied)."
            elif "UNPROTECTED PRIVATE KEY" in r.error:
                texto += "\nLa clave privada tiene permisos demasiado abiertos: chmod 600 en la clave."
            elif "Could not resolve" in r.error or "Name or service not known" in r.error:
                texto += "\nNo se resuelve el nombre del servidor."
            elif "Connection refused" in r.error or "timed out" in r.error:
                texto += "\nEl servidor no responde en ese puerto."
            return texto
        if r.codigo == 127:
            return "El servidor no tiene python3 (o la ruta de «Python remoto» es incorrecta)."
        if RE_SUDO_FALLO.search(r.error):
            return ("sudo necesita contraseña en %s y no se pudo autenticar. Configura la contraseña de sudo en el perfil, "
                    "usa NOPASSWD o desactiva sudo." % self.etiqueta())
        return "Error (código %d)." % r.codigo

#!/usr/bin/env python3
"""
generar_app.py — Generador de apps web de un solo HTML (Anthropic / OpenAI)
===========================================================================

Pensado para trabajar desde VS Code. Se puede usar de tres formas:

1. Pulsando el botón ▶ ("Run Python File") o F5 sin argumentos: entra en un
   menú interactivo que lo pregunta todo por consola.
2. Con "Terminal → Run Task" (si has ejecutado `--init`, que crea las tareas
   de VS Code con desplegables y cuadros de texto nativos).
3. Como script de línea de comandos normal (ver ejemplos abajo).

Ejemplos de línea de comandos
------------------------------
    # Preparar la carpeta actual para VS Code (.vscode, .env.example, plantilla...)
    python generar_app.py --init

    # Modelos: lista curada en el script, o la lista real de tu cuenta
    python generar_app.py --list-models
    python generar_app.py --list-models --remote

    # Generar una app nueva (usa plantilla_base.html si existe)
    python generar_app.py "Conversor de medidas de patronaje cm↔pulgadas" -o conversor.html

    # Elegir plataforma y modelo
    python generar_app.py "..." -o app.html --provider openai --model gpt-6.2-sol

    # Generar y abrir en el navegador con recarga automática en cada cambio
    python generar_app.py "..." -o app.html --serve --chat

    # Modificar una app existente (guarda copia de seguridad y muestra el diff)
    python generar_app.py "Añade exportar a PDF" --base genoutfit.html -o genoutfit.html --chat

    # Varias variantes de diseño + galería comparativa
    python generar_app.py "App de checklist de patrones" -o checklist.html --variantes 3

    # Retomar la última conversación donde la dejaste
    python generar_app.py --resume

Requisitos
----------
    pip install -r requirements.txt
    ANTHROPIC_API_KEY y/o OPENAI_API_KEY en el entorno o en un fichero .env

Autor del script: Rafael Puerto · r.puerto@umh.es
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv es opcional
    def load_dotenv(*_a: Any, **_k: Any) -> bool:  # type: ignore[misc]
        return False

# Tab-completion de rutas en los prompts interactivos (no existe en Windows sin pyreadline3)
try:
    import readline
except ImportError:
    readline = None  # type: ignore[assignment]


# ===========================================================================
# Constantes y configuración
# ===========================================================================

SCRIPT_DIR = Path(__file__).resolve().parent
PLANTILLA_POR_DEFECTO = SCRIPT_DIR / "plantilla_base.html"
FICHERO_CONFIG = SCRIPT_DIR / "generar_app.config.json"
DIR_TRABAJO = SCRIPT_DIR / ".generar_app"
DIR_HISTORIAL = DIR_TRABAJO / "historial"
DIR_SESIONES = DIR_TRABAJO / "sesiones"

FECHA_MARCADOR = "FECHA_HORA"
MAX_TOKENS_POR_DEFECTO = 24000
MAX_TOKENS_TECHO = 64000  # tope al reintentar una respuesta truncada
REINTENTOS_RED = 4        # intentos ante errores transitorios (429, 5xx, sobrecarga)

AUTOR_POR_DEFECTO = {
    "nombre": "Rafael Puerto",
    "departamento": "Departamento de Ingeniería de Sistemas y Automática, UMH",
    "email": "r.puerto@umh.es",
}

# Lista curada de modelos: (id, descripción). Los catálogos cambian cada pocos meses,
# así que esto es solo una ayuda: --model acepta cualquier id, y `--list-models --remote`
# consulta la lista real de tu cuenta contra la API.
MODELOS_CURADOS: dict[str, list[tuple[str, str]]] = {
    "anthropic": [
        ("claude-opus-5-5", "El más capaz; trabajo complejo y de contexto largo"),
        ("claude-sonnet-5-5", "Mejor equilibrio velocidad/inteligencia de la familia 5.5"),
        ("claude-sonnet-5", "Eficiente para uso cotidiano"),
        ("claude-haiku-5-5", "El más rápido y económico"),
        ("claude-fable-5-1", "Razonamiento exigente y tareas de largo recorrido"),
    ],
    "openai": [
        ("gpt-6.2-astra", "El más capaz de OpenAI: razonamiento y código"),
        ("gpt-6.2-sol", "Equilibrio inteligencia/coste para el día a día"),
        ("gpt-6.1-terra", "Rápido, bueno en razonamiento visual y redacción"),
        ("gpt-6-luna", "El más eficiente, para tareas de alto volumen"),
    ],
}

API_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
PROVEEDORES = tuple(API_KEY_ENV)

ENFOQUES_VARIANTES = [
    "una propuesta visual minimalista, con mucho espacio en blanco y tipografía grande",
    "una propuesta colorida y con más personalidad gráfica (iconos, acentos de color)",
    "una propuesta de alta densidad de información, tipo panel de control",
    "una propuesta con la interacción en pasos (wizard) en vez de todo en una pantalla",
    "una propuesta con disposición en dos columnas y vista previa en vivo del resultado",
]


@dataclass
class Config:
    """Configuración efectiva: valores por defecto ← generar_app.config.json ← .env ← argumentos."""

    proveedor: str = "anthropic"
    modelos_defecto: dict[str, str] = field(
        default_factory=lambda: {"anthropic": "claude-sonnet-5", "openai": "gpt-6-luna"}
    )
    max_tokens: int = MAX_TOKENS_POR_DEFECTO
    autor: dict[str, str] = field(default_factory=lambda: dict(AUTOR_POR_DEFECTO))
    # Opcional: {"claude-sonnet-5": {"entrada": 3.0, "salida": 15.0}} en USD por millón de tokens.
    # Si el modelo usado está aquí, se muestra además el coste estimado de cada llamada.
    precios: dict[str, dict[str, float]] = field(default_factory=dict)
    puerto_preview: int = 8000
    color: bool = True

    @classmethod
    def cargar(cls) -> "Config":
        cfg = cls()
        if FICHERO_CONFIG.exists():
            try:
                datos = json.loads(FICHERO_CONFIG.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                aviso(f"{FICHERO_CONFIG.name} no es un JSON válido ({e}); se ignora.")
                datos = {}
            cfg.proveedor = datos.get("proveedor", cfg.proveedor)
            cfg.modelos_defecto.update(datos.get("modelos_defecto", {}))
            cfg.max_tokens = int(datos.get("max_tokens", cfg.max_tokens))
            cfg.autor.update(datos.get("autor", {}))
            cfg.precios = datos.get("precios", cfg.precios)
            cfg.puerto_preview = int(datos.get("puerto_preview", cfg.puerto_preview))
            cfg.color = bool(datos.get("color", cfg.color))
        # Las variables de entorno (.env) tienen prioridad sobre el fichero de configuración
        cfg.proveedor = os.environ.get("AI_PROVIDER", cfg.proveedor)
        if os.environ.get("ANTHROPIC_MODEL"):
            cfg.modelos_defecto["anthropic"] = os.environ["ANTHROPIC_MODEL"]
        if os.environ.get("OPENAI_MODEL"):
            cfg.modelos_defecto["openai"] = os.environ["OPENAI_MODEL"]
        if cfg.proveedor not in PROVEEDORES:
            aviso(f"Proveedor '{cfg.proveedor}' no reconocido; se usa anthropic.")
            cfg.proveedor = "anthropic"
        return cfg


# ===========================================================================
# Salida por consola (colores, avisos, prompts)
# ===========================================================================

class C:
    """Códigos ANSI; se vacían si la salida no es un terminal o se pide NO_COLOR."""

    AZUL = "\033[94m"
    VERDE = "\033[92m"
    AMARILLO = "\033[93m"
    ROJO = "\033[91m"
    GRIS = "\033[90m"
    NEGRITA = "\033[1m"
    FIN = "\033[0m"

    @classmethod
    def desactivar(cls) -> None:
        for nombre in ("AZUL", "VERDE", "AMARILLO", "ROJO", "GRIS", "NEGRITA", "FIN"):
            setattr(cls, nombre, "")


def configurar_color(activo: bool) -> None:
    if not activo or os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        C.desactivar()


def titulo(texto: str) -> None:
    print(f"\n{C.NEGRITA}{C.AZUL}{texto}{C.FIN}")


def ok(texto: str) -> None:
    print(f"{C.VERDE}✓{C.FIN} {texto}")


def aviso(texto: str) -> None:
    print(f"{C.AMARILLO}⚠{C.FIN}  {texto}", file=sys.stderr)


def error(texto: str) -> None:
    print(f"{C.ROJO}✗{C.FIN} {texto}", file=sys.stderr)


def gris(texto: str) -> None:
    print(f"{C.GRIS}{texto}{C.FIN}")


def interactivo() -> bool:
    """True si hay un humano al otro lado al que se le puede preguntar."""
    return sys.stdin.isatty()


def _activar_completado_rutas() -> None:
    """Tab-completion de ficheros en los input() del modo interactivo."""
    if readline is None:
        return
    import glob

    def completar(texto: str, estado: int) -> str | None:
        candidatos = [p + ("/" if Path(p).is_dir() else "") for p in glob.glob(texto + "*")]
        return candidatos[estado] if estado < len(candidatos) else None

    readline.set_completer_delims(" \t\n")
    readline.set_completer(completar)
    try:
        readline.parse_and_bind("tab: complete")
    except Exception:
        pass


def preguntar(texto: str, defecto: str = "") -> str:
    """input() con valor por defecto y tolerante a Ctrl+C / EOF."""
    sufijo = f" [{defecto}]" if defecto else ""
    try:
        respuesta = input(f"{C.NEGRITA}{texto}{sufijo}:{C.FIN} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(130)
    return respuesta or defecto


def preguntar_si_no(texto: str, defecto: bool = False) -> bool:
    marca = "S/n" if defecto else "s/N"
    respuesta = preguntar(f"{texto} ({marca})").lower()
    if not respuesta:
        return defecto
    return respuesta in {"s", "si", "sí", "y", "yes"}


def elegir(texto: str, opciones: Sequence[tuple[str, str]], defecto: str | None = None) -> str:
    """Menú numerado. `opciones` son pares (valor, etiqueta); devuelve el valor elegido."""
    print(f"\n{C.NEGRITA}{texto}{C.FIN}")
    for i, (valor, etiqueta) in enumerate(opciones, 1):
        marca = f" {C.GRIS}← actual{C.FIN}" if valor == defecto else ""
        print(f"  {C.AZUL}[{i}]{C.FIN} {etiqueta}{marca}")
    while True:
        bruto = preguntar("Elige", defecto or "")
        if bruto == defecto:
            return bruto
        if bruto.isdigit() and 1 <= int(bruto) <= len(opciones):
            return opciones[int(bruto) - 1][0]
        for valor, _ in opciones:
            if bruto == valor:
                return valor
        aviso("Opción no válida.")


class Spinner:
    """Indicador de actividad para las llamadas sin streaming."""

    def __init__(self, texto: str = "Generando") -> None:
        self.texto = texto
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None

    def __enter__(self) -> "Spinner":
        if sys.stdout.isatty():
            self._hilo = threading.Thread(target=self._girar, daemon=True)
            self._hilo.start()
        return self

    def _girar(self) -> None:
        for i in iter(int, 1):
            if self._parar.is_set():
                break
            marco = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[i % 10]
            print(f"\r{C.AZUL}{marco}{C.FIN} {self.texto}...", end="", flush=True)
            time.sleep(0.1)

    def __exit__(self, *_exc: Any) -> None:
        self._parar.set()
        if self._hilo:
            self._hilo.join(timeout=0.5)
            print("\r" + " " * (len(self.texto) + 12) + "\r", end="")


# ===========================================================================
# Prompt del sistema
# ===========================================================================

def construir_system_prompt(autor: dict[str, str]) -> str:
    return f"""Eres un generador experto de aplicaciones web de un solo archivo HTML.

Reglas que debes seguir SIEMPRE, salvo que el usuario pida explícitamente lo contrario:

1. La app es un único archivo .html autocontenido: el CSS en un <style> interno y el JavaScript
   en un <script> interno. Sin pasos de compilación ni paquetes npm. Puedes cargar librerías
   desde un CDN (cdnjs, jsdelivr, unpkg) solo si aportan algo que no merece la pena reimplementar.
2. Interfaz en español, limpia, moderna y responsive (debe funcionar bien también en móvil).
   Usa variables CSS para los colores y respeta `prefers-color-scheme` si encaja con la app.
3. Accesibilidad básica: etiquetas <label> asociadas a sus campos, textos alternativos en las
   imágenes, contraste suficiente y foco visible en los elementos interactivos.
4. Si la app necesita una API de IA (Anthropic, OpenAI, Gemini, fal.ai...), pide la clave
   mediante un campo de la propia interfaz, nunca escrita en el código, e indica brevemente
   dónde obtenerla. Guárdala solo en memoria o en localStorage si el usuario lo marca.
5. Gestiona los errores de forma visible para el usuario final (mensajes claros en pantalla,
   no solo console.log) e indica el estado de carga mientras se espera una respuesta.
6. Incluye siempre, al final de la página, un <footer> con este formato exacto:

   <footer>
     <p>{autor['nombre']} · {autor['departamento']} · {autor['email']}</p>
     <p>Última modificación: {FECHA_MARCADOR}</p>
     <p><em>Generado con IA · Revisado por el autor</em></p>
   </footer>

   Escribe literalmente el texto {FECHA_MARCADOR} como marcador: el script que te invoca lo
   sustituirá por la fecha y hora reales, así que no intentes calcularlo tú.
7. Devuelve ÚNICAMENTE el código HTML completo dentro de un único bloque ```html ... ```, sin
   explicaciones antes ni después: el script extrae ese bloque y lo guarda tal cual.
8. Si recibes un HTML existente y una petición de cambios, devuelve el archivo COMPLETO ya
   modificado (nunca un parche ni solo las líneas afectadas) y conserva lo que funcionaba.
"""


# ===========================================================================
# Proveedores de IA
# ===========================================================================

@dataclass
class Resultado:
    """Resultado de una llamada al modelo, uniforme para las dos plataformas."""

    texto: str
    tokens_entrada: int = 0
    tokens_salida: int = 0
    cache_lectura: int = 0
    cache_escritura: int = 0
    truncado: bool = False


Mensajes = list[dict[str, str]]


class ErrorProveedor(RuntimeError):
    """Error de la API ya traducido a algo legible para el usuario."""


class Proveedor:
    """Interfaz común a Anthropic y OpenAI."""

    nombre = ""

    def __init__(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt
        self.client = self._crear_cliente()

    def _crear_cliente(self) -> Any:
        raise NotImplementedError

    def generar(self, modelo: str, mensajes: Mensajes, max_tokens: int, stream: bool) -> Resultado:
        raise NotImplementedError

    def listar_modelos(self) -> list[tuple[str, str]]:
        raise NotImplementedError

    @staticmethod
    def _importar(paquete: str) -> Any:
        try:
            return __import__(paquete)
        except ImportError:
            raise ErrorProveedor(
                f"Falta el paquete '{paquete}'. Instálalo con:\n"
                f"    pip install -r requirements.txt"
            ) from None


class ProveedorAnthropic(Proveedor):
    nombre = "anthropic"

    def _crear_cliente(self) -> Any:
        anthropic = self._importar("anthropic")
        return anthropic.Anthropic()

    def _bloques(self, mensajes: Mensajes) -> list[dict[str, Any]]:
        """Convierte los mensajes a bloques de contenido y marca el último punto cacheable.

        En modo chat la conversación acumula HTML completos (miles de tokens que se reenvían en
        cada vuelta). Marcando el final del penúltimo mensaje con cache_control, Anthropic
        reutiliza ese prefijo en las siguientes llamadas, lo que abarata mucho las iteraciones.
        """
        convertidos: list[dict[str, Any]] = []
        indice_cache = len(mensajes) - 2 if len(mensajes) >= 3 else -1
        for i, m in enumerate(mensajes):
            bloque: dict[str, Any] = {"type": "text", "text": m["content"]}
            if i == indice_cache:
                bloque["cache_control"] = {"type": "ephemeral"}
            convertidos.append({"role": m["role"], "content": [bloque]})
        return convertidos

    def generar(self, modelo: str, mensajes: Mensajes, max_tokens: int, stream: bool) -> Resultado:
        comunes = dict(
            model=modelo,
            max_tokens=max_tokens,
            system=self.system_prompt,
            messages=self._bloques(mensajes),
        )
        if stream:
            partes: list[str] = []
            with self.client.messages.stream(**comunes) as s:
                for trozo in s.text_stream:
                    print(trozo, end="", flush=True)
                    partes.append(trozo)
                final = s.get_final_message()
            print()
            return self._a_resultado("".join(partes), final)
        with Spinner(f"Generando con {modelo}"):
            respuesta = self.client.messages.create(**comunes)
        texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text")
        return self._a_resultado(texto, respuesta)

    @staticmethod
    def _a_resultado(texto: str, mensaje: Any) -> Resultado:
        uso = getattr(mensaje, "usage", None)
        return Resultado(
            texto=texto,
            tokens_entrada=getattr(uso, "input_tokens", 0) or 0,
            tokens_salida=getattr(uso, "output_tokens", 0) or 0,
            cache_lectura=getattr(uso, "cache_read_input_tokens", 0) or 0,
            cache_escritura=getattr(uso, "cache_creation_input_tokens", 0) or 0,
            truncado=getattr(mensaje, "stop_reason", None) == "max_tokens",
        )

    def listar_modelos(self) -> list[tuple[str, str]]:
        return [
            (m.id, getattr(m, "display_name", "") or "")
            for m in self.client.models.list(limit=100).data
        ]


class ProveedorOpenAI(Proveedor):
    nombre = "openai"

    def _crear_cliente(self) -> Any:
        openai = self._importar("openai")
        return openai.OpenAI()

    def _crear(self, modelo: str, mensajes: Mensajes, max_tokens: int, stream: bool) -> Any:
        """Llama a responses.create tolerando modelos que no admiten max_output_tokens."""
        kwargs: dict[str, Any] = dict(
            model=modelo,
            instructions=self.system_prompt,
            input=mensajes,
            max_output_tokens=max_tokens,
        )
        if stream:
            kwargs["stream"] = True
        try:
            return self.client.responses.create(**kwargs)
        except Exception as e:
            texto = str(e).lower()
            no_soportado = "max_output_tokens" in texto and any(
                p in texto for p in ("unsupported", "not supported", "unknown parameter")
            )
            if not no_soportado:
                raise
            aviso(f"El modelo '{modelo}' no admite limitar los tokens de salida; se reintenta sin ese límite.")
            kwargs.pop("max_output_tokens")
            return self.client.responses.create(**kwargs)

    def generar(self, modelo: str, mensajes: Mensajes, max_tokens: int, stream: bool) -> Resultado:
        if stream:
            partes: list[str] = []
            final = None
            for evento in self._crear(modelo, mensajes, max_tokens, stream=True):
                tipo = getattr(evento, "type", "")
                if tipo == "response.output_text.delta":
                    print(evento.delta, end="", flush=True)
                    partes.append(evento.delta)
                elif tipo in ("response.completed", "response.incomplete", "response.failed"):
                    final = getattr(evento, "response", None)
                elif tipo == "error":
                    raise ErrorProveedor(getattr(evento, "message", "error de streaming"))
            print()
            return self._a_resultado("".join(partes), final)
        with Spinner(f"Generando con {modelo}"):
            respuesta = self._crear(modelo, mensajes, max_tokens, stream=False)
        return self._a_resultado(getattr(respuesta, "output_text", "") or "", respuesta)

    @staticmethod
    def _a_resultado(texto: str, respuesta: Any) -> Resultado:
        uso = getattr(respuesta, "usage", None)
        detalles = getattr(respuesta, "incomplete_details", None)
        return Resultado(
            texto=texto,
            tokens_entrada=getattr(uso, "input_tokens", 0) or 0,
            tokens_salida=getattr(uso, "output_tokens", 0) or 0,
            cache_lectura=getattr(getattr(uso, "input_tokens_details", None), "cached_tokens", 0) or 0,
            truncado=getattr(detalles, "reason", None) == "max_output_tokens"
            or getattr(respuesta, "status", None) == "incomplete",
        )

    def listar_modelos(self) -> list[tuple[str, str]]:
        modelos = [m.id for m in self.client.models.list().data]
        # El catálogo incluye embeddings, audio, imagen...: nos quedamos con los de texto
        utiles = [m for m in modelos if re.match(r"^(gpt|o\d|chatgpt)", m) and not
                  re.search(r"(embedding|audio|tts|whisper|image|realtime|moderation|transcribe)", m)]
        return [(m, "") for m in sorted(utiles)]


def crear_proveedor(nombre: str, system_prompt: str) -> Proveedor:
    clases = {"anthropic": ProveedorAnthropic, "openai": ProveedorOpenAI}
    if nombre not in clases:
        raise ErrorProveedor(f"Proveedor desconocido: {nombre}")
    return clases[nombre](system_prompt)


# ===========================================================================
# Llamada con reintentos y diagnóstico de errores
# ===========================================================================

TRANSITORIOS = ("rate limit", "429", "overloaded", "500", "502", "503", "504",
                "timeout", "timed out", "connection", "temporarily")


def _es_transitorio(e: Exception) -> bool:
    texto = f"{type(e).__name__} {e}".lower()
    if "authentication" in texto or "invalid_api_key" in texto or "401" in texto:
        return False
    return any(p in texto for p in TRANSITORIOS)


def _explicar(e: Exception, proveedor: str, modelo: str) -> str:
    texto = str(e)
    bajo = texto.lower()
    clave = API_KEY_ENV.get(proveedor, "la clave de API")
    if "authentication" in bajo or "invalid x-api-key" in bajo or "incorrect api key" in bajo:
        return (f"La clave de {clave} no es válida. Revísala en tu fichero .env "
                f"o en las variables de entorno.")
    if "not_found" in bajo or "does not exist" in bajo or "model" in bajo and "not found" in bajo:
        return (f"El modelo '{modelo}' no existe o tu cuenta no tiene acceso.\n"
                f"   Consulta los disponibles con:  python generar_app.py --list-models --remote "
                f"--provider {proveedor}")
    if "credit" in bajo or "billing" in bajo or "quota" in bajo or "insufficient" in bajo:
        return f"Problema de saldo o cuota en tu cuenta de {proveedor}: {texto}"
    if "rate limit" in bajo or "429" in bajo:
        return "Se ha alcanzado el límite de peticiones por minuto. Prueba de nuevo en un momento."
    return texto


def generar_con_reintentos(
    proveedor: Proveedor,
    modelo: str,
    mensajes: Mensajes,
    max_tokens: int,
    stream: bool,
    auto_ampliar: bool = True,
) -> Resultado:
    """Llama al modelo reintentando errores transitorios y ampliando el límite si la
    respuesta sale truncada (un HTML cortado a medias no sirve de nada)."""
    tokens = max_tokens
    for intento_truncado in range(2):
        ultimo_error: Exception | None = None
        for intento in range(1, REINTENTOS_RED + 1):
            try:
                resultado = proveedor.generar(modelo, mensajes, tokens, stream)
                break
            except ErrorProveedor:
                raise
            except Exception as e:  # errores del SDK / de red
                ultimo_error = e
                if not _es_transitorio(e) or intento == REINTENTOS_RED:
                    raise ErrorProveedor(_explicar(e, proveedor.nombre, modelo)) from e
                espera = 2 ** (intento - 1)
                aviso(f"Error transitorio ({type(e).__name__}); reintento {intento}/{REINTENTOS_RED - 1} en {espera}s...")
                time.sleep(espera)
        else:  # pragma: no cover - el for siempre sale por break o raise
            raise ErrorProveedor(_explicar(ultimo_error or Exception("desconocido"), proveedor.nombre, modelo))

        if not resultado.truncado or not auto_ampliar or intento_truncado == 1:
            return resultado
        nuevo = min(tokens * 2, MAX_TOKENS_TECHO)
        if nuevo <= tokens:
            aviso("La respuesta ha salido truncada y ya se ha alcanzado el tope de tokens.")
            return resultado
        aviso(f"La respuesta ha salido truncada; se reintenta con {nuevo} tokens de salida.")
        tokens = nuevo
    return resultado


# ===========================================================================
# Post-proceso y validación del HTML
# ===========================================================================

PATRON_FECHA = re.compile(r"(Última modificaci[óo]n:\s*)([^<\n]*)")


def extraer_html(respuesta: str) -> str:
    """Saca el bloque de código de la respuesta del modelo.
    Si no hay bloque, asume que toda la respuesta es el HTML."""
    for patron in (r"```html\s*\n(.*?)```", r"```\s*\n(.*?)```"):
        m = re.search(patron, respuesta, re.DOTALL)
        if m:
            return m.group(1).strip() + "\n"
    return respuesta.strip() + "\n"


def footer_html(autor: dict[str, str], fecha: str) -> str:
    return (
        "<footer>\n"
        f"  <p>{autor['nombre']} · {autor['departamento']} · {autor['email']}</p>\n"
        f"  <p>Última modificación: {fecha}</p>\n"
        "  <p><em>Generado con IA · Revisado por el autor</em></p>\n"
        "</footer>\n"
    )


def normalizar_footer(html: str, autor: dict[str, str]) -> tuple[str, list[str]]:
    """Pone la fecha de 'Última modificación' al día y, si el modelo se ha olvidado del pie,
    lo inserta. Devuelve (html, notas de lo que se ha tocado)."""
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    notas: list[str] = []

    if FECHA_MARCADOR in html:
        return html.replace(FECHA_MARCADOR, ahora), notas
    if PATRON_FECHA.search(html):
        return PATRON_FECHA.sub(lambda m: m.group(1) + ahora, html), notas

    pie = footer_html(autor, ahora)
    if "<footer" in html.lower():
        # Hay pie pero sin línea de fecha: la añadimos dentro del footer existente
        html = re.sub(
            r"(</footer>)",
            f"  <p>Última modificación: {ahora}</p>\n\\1",
            html,
            count=1,
            flags=re.IGNORECASE,
        )
        notas.append("se ha añadido la línea de fecha al pie existente")
        return html, notas

    if re.search(r"</body>", html, re.IGNORECASE):
        html = re.sub(r"(\s*</body>)", f"\n{pie}\\1", html, count=1, flags=re.IGNORECASE)
    else:
        html = html.rstrip() + "\n" + pie
    notas.append("faltaba el pie de página y se ha insertado")
    return html, notas


def validar_html(html: str) -> list[str]:
    """Comprobaciones rápidas de sanidad; devuelve la lista de problemas encontrados."""
    problemas: list[str] = []
    bajo = html.lower()
    if "<!doctype" not in bajo:
        problemas.append("no empieza por <!DOCTYPE html>")
    if "<html" not in bajo:
        problemas.append("no contiene la etiqueta <html>")
    if "</html>" not in bajo:
        problemas.append("no se cierra con </html> (la respuesta puede estar cortada)")
    if "<meta name=\"viewport\"" not in bajo and "<meta name='viewport'" not in bajo:
        problemas.append("falta la etiqueta meta viewport (afecta a la vista en móvil)")
    if bajo.count("<script") != bajo.count("</script>"):
        problemas.append("hay etiquetas <script> sin cerrar")
    if bajo.count("<style") != bajo.count("</style>"):
        problemas.append("hay etiquetas <style> sin cerrar")
    for clave in (r"sk-ant-[A-Za-z0-9_\-]{10,}", r"sk-proj-[A-Za-z0-9_\-]{10,}"):
        if re.search(clave, html):
            problemas.append("¡parece contener una clave de API escrita en el código!")
            break
    return problemas


# ===========================================================================
# Historial de versiones y escritura en disco
# ===========================================================================

def guardar_copia(destino: Path) -> Path | None:
    """Antes de sobrescribir, guarda una copia con fecha en .generar_app/historial/."""
    if not destino.exists():
        return None
    DIR_HISTORIAL.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    sufijo = destino.suffix or ".html"
    copia = DIR_HISTORIAL / f"{destino.stem}_{sello}{sufijo}"
    # Dos guardados en el mismo segundo (habitual en modo chat) no deben pisarse la copia
    n = 1
    while copia.exists():
        copia = DIR_HISTORIAL / f"{destino.stem}_{sello}-{n}{sufijo}"
        n += 1
    shutil.copy2(destino, copia)
    return copia


def copias_de(destino: Path) -> list[Path]:
    """Copias guardadas de un fichero, de la más reciente a la más antigua.
    Se ordena por fecha de modificación real, no por nombre."""
    if not DIR_HISTORIAL.exists():
        return []
    patron = f"{destino.stem}_*{destino.suffix or '.html'}"
    return sorted(DIR_HISTORIAL.glob(patron), key=lambda p: p.stat().st_mtime, reverse=True)


def escribir_atomico(destino: Path, contenido: str) -> None:
    """Escribe mediante un temporal + rename, para no dejar el fichero a medias si algo falla."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_text(contenido, encoding="utf-8")
    temporal.replace(destino)


def mostrar_diff(antes: str, despues: str, nombre: str, max_lineas: int = 40) -> None:
    """Resumen de los cambios respecto a la versión anterior del fichero."""
    diff = list(difflib.unified_diff(
        antes.splitlines(), despues.splitlines(),
        fromfile=f"{nombre} (antes)", tofile=f"{nombre} (después)", lineterm="", n=1,
    ))
    if not diff:
        gris("   (el contenido no ha cambiado)")
        return
    añadidas = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    quitadas = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    print(f"   {C.VERDE}+{añadidas}{C.FIN} / {C.ROJO}-{quitadas}{C.FIN} líneas")
    for linea in diff[:max_lineas]:
        if linea.startswith("+") and not linea.startswith("+++"):
            print(f"   {C.VERDE}{linea[:140]}{C.FIN}")
        elif linea.startswith("-") and not linea.startswith("---"):
            print(f"   {C.ROJO}{linea[:140]}{C.FIN}")
        elif linea.startswith("@@"):
            print(f"   {C.GRIS}{linea[:140]}{C.FIN}")
    if len(diff) > max_lineas:
        gris(f"   ... y {len(diff) - max_lineas} líneas más de diferencias")


# ===========================================================================
# Contabilidad de tokens y coste
# ===========================================================================

@dataclass
class Contador:
    """Acumula el gasto de la sesión para poder informar al final."""

    llamadas: int = 0
    entrada: int = 0
    salida: int = 0
    cache_lectura: int = 0
    cache_escritura: int = 0

    def sumar(self, r: Resultado) -> None:
        self.llamadas += 1
        self.entrada += r.tokens_entrada
        self.salida += r.tokens_salida
        self.cache_lectura += r.cache_lectura
        self.cache_escritura += r.cache_escritura

    def coste(self, precios: dict[str, float] | None) -> float | None:
        if not precios:
            return None
        entrada = (self.entrada + self.cache_escritura) * precios.get("entrada", 0.0)
        cache = self.cache_lectura * precios.get("cache_lectura", precios.get("entrada", 0.0) * 0.1)
        salida = self.salida * precios.get("salida", 0.0)
        return (entrada + cache + salida) / 1_000_000


def informar_uso(r: Resultado, cfg: Config, modelo: str) -> None:
    partes = [f"{r.tokens_entrada} tokens de entrada", f"{r.tokens_salida} de salida"]
    if r.cache_lectura:
        partes.append(f"{r.cache_lectura} leídos de caché")
    if r.cache_escritura:
        partes.append(f"{r.cache_escritura} escritos en caché")
    linea = "   " + " · ".join(partes)
    precios = cfg.precios.get(modelo)
    if precios:
        c = Contador()
        c.sumar(r)
        coste = c.coste(precios)
        if coste is not None:
            linea += f" · ≈ {coste:.4f} USD"
    gris(linea)


# ===========================================================================
# Servidor de previsualización con recarga automática
# ===========================================================================

SCRIPT_RECARGA = """
<script>
/* Inyectado solo por el servidor de previsualización de generar_app.py; no está en el fichero. */
(function () {
  let ultimo = null;
  setInterval(async function () {
    try {
      const r = await fetch('/__mtime', { cache: 'no-store' });
      const t = await r.text();
      if (ultimo !== null && t !== ultimo) location.reload();
      ultimo = t;
    } catch (e) { /* el servidor se ha cerrado */ }
  }, 1000);
})();
</script>
"""


class ServidorPreview:
    """Sirve el HTML generado en localhost y recarga el navegador en cada cambio.

    El script de recarga se inyecta al servir la página, nunca en el fichero del disco,
    así que lo que se guarda sigue siendo el HTML limpio que luego puedes subir al servidor.
    """

    def __init__(self, archivo: Path, puerto: int) -> None:
        self.archivo = archivo
        self.puerto = puerto
        self.httpd: HTTPServer | None = None

    def arrancar(self) -> str | None:
        archivo = self.archivo

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (nombre impuesto por la clase base)
                if self.path.startswith("/__mtime"):
                    cuerpo = str(archivo.stat().st_mtime if archivo.exists() else 0).encode()
                    self._responder(cuerpo, "text/plain")
                    return
                if not archivo.exists():
                    self._responder(b"<p>Todavia no se ha generado el fichero.</p>", "text/html")
                    return
                html = archivo.read_text(encoding="utf-8")
                if re.search(r"</body>", html, re.IGNORECASE):
                    html = re.sub(r"(\s*</body>)", SCRIPT_RECARGA + r"\1", html, count=1, flags=re.IGNORECASE)
                else:
                    html += SCRIPT_RECARGA
                self._responder(html.encode("utf-8"), "text/html; charset=utf-8")

            def _responder(self, cuerpo: bytes, tipo: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(cuerpo)
                except BrokenPipeError:
                    pass

            def log_message(self, *_a: Any) -> None:
                pass  # sin ruido en la consola

        for puerto in range(self.puerto, self.puerto + 20):
            try:
                self.httpd = HTTPServer(("127.0.0.1", puerto), Handler)
                break
            except OSError:
                continue
        if self.httpd is None:
            aviso("No se ha podido abrir ningún puerto para la previsualización.")
            return None
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{self.httpd.server_port}/"
        ok(f"Previsualización en {C.AZUL}{url}{C.FIN} (se recarga sola en cada cambio)")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return url

    def parar(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


# ===========================================================================
# Sesiones (guardar y retomar conversaciones)
# ===========================================================================

def ruta_sesion(nombre: str) -> Path:
    seguro = re.sub(r"[^A-Za-z0-9._-]", "_", nombre)
    return DIR_SESIONES / f"{seguro}.json"


def guardar_sesion(nombre: str, datos: dict[str, Any]) -> None:
    DIR_SESIONES.mkdir(parents=True, exist_ok=True)
    datos["actualizada"] = datetime.now().isoformat(timespec="seconds")
    ruta_sesion(nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def listar_sesiones() -> list[tuple[str, dict[str, Any]]]:
    if not DIR_SESIONES.exists():
        return []
    sesiones = []
    for p in DIR_SESIONES.glob("*.json"):
        try:
            sesiones.append((p.stem, json.loads(p.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(sesiones, key=lambda s: s[1].get("actualizada", ""), reverse=True)


def cargar_sesion(nombre: str | None) -> tuple[str, dict[str, Any]] | None:
    sesiones = listar_sesiones()
    if not sesiones:
        return None
    if nombre in (None, "", "ultima", "última"):
        return sesiones[0]
    for n, datos in sesiones:
        if n == re.sub(r"[^A-Za-z0-9._-]", "_", nombre or ""):
            return n, datos
    return None


# ===========================================================================
# Construcción de la petición
# ===========================================================================

def construir_peticion(descripcion: str, base: Path | None, plantilla: Path | None) -> str:
    """Primer mensaje del usuario: la descripción, más el HTML de partida (--base, modo
    edición) o la plantilla de estilo. --base tiene prioridad sobre la plantilla."""
    if base:
        html = base.read_text(encoding="utf-8")
        return (
            f"Este es el HTML existente del que debes partir:\n\n```html\n{html}\n```\n\n"
            f"Cambio pedido: {descripcion}"
        )
    if plantilla and plantilla.exists():
        html = plantilla.read_text(encoding="utf-8")
        return (
            "Usa el siguiente HTML como plantilla de estructura y estilo (cabecera, variables de "
            "color, tipografía, layout y pie de página). Adáptalo y complétalo para construir la "
            "app descrita más abajo: no hace falta conservar literalmente cada elemento si no "
            "encaja, pero mantén el espíritu visual y el formato del pie de página tal cual.\n\n"
            f"```html\n{html}\n```\n\nApp a construir: {descripcion}"
        )
    return descripcion


# ===========================================================================
# Generación: una vuelta completa (llamar, validar, guardar, informar)
# ===========================================================================

@dataclass
class Entorno:
    """Todo lo que necesita una generación, agrupado para no arrastrar diez parámetros."""

    cfg: Config
    proveedor: Proveedor
    modelo: str
    max_tokens: int
    stream: bool
    contador: Contador = field(default_factory=Contador)


def generar_fichero(
    env: Entorno,
    mensajes: Mensajes,
    destino: Path,
    *,
    con_diff: bool = False,
    etiqueta: str | None = None,
) -> str:
    """Llama al modelo, valida y guarda el HTML. Devuelve el texto crudo de la respuesta
    (para añadirlo al historial de la conversación)."""
    anterior = destino.read_text(encoding="utf-8") if (con_diff and destino.exists()) else None

    resultado = generar_con_reintentos(
        env.proveedor, env.modelo, mensajes, env.max_tokens, env.stream
    )
    env.contador.sumar(resultado)

    if not resultado.texto.strip():
        raise ErrorProveedor("El modelo no ha devuelto contenido.")

    html, notas = normalizar_footer(extraer_html(resultado.texto), env.cfg.autor)
    problemas = validar_html(html)

    copia = guardar_copia(destino)
    escribir_atomico(destino, html)

    ok(etiqueta or f"Guardado en {C.NEGRITA}{destino.resolve()}{C.FIN}")
    informar_uso(resultado, env.cfg, env.modelo)
    for nota in notas:
        gris(f"   (corregido: {nota})")
    if copia:
        gris(f"   (copia de la versión anterior en {copia.relative_to(SCRIPT_DIR) if SCRIPT_DIR in copia.parents else copia})")
    for problema in problemas:
        aviso(f"Revisa el HTML generado: {problema}")
    if anterior is not None:
        mostrar_diff(anterior, html, destino.name)

    return resultado.texto


# ===========================================================================
# Variantes y galería comparativa
# ===========================================================================

def generar_variantes(env: Entorno, peticion: str, salida: Path, n: int) -> list[Path]:
    ficheros: list[Path] = []
    for i in range(1, n + 1):
        enfoque = ENFOQUES_VARIANTES[(i - 1) % len(ENFOQUES_VARIANTES)]
        mensajes: Mensajes = [{
            "role": "user",
            "content": peticion + (
                f"\n\n(Variante {i} de {n}. Dale un enfoque de diseño propio y distinto de las "
                f"demás: {enfoque}. La funcionalidad pedida debe ser la misma en todas.)"
            ),
        }]
        destino = salida.with_name(f"{salida.stem}_v{i}{salida.suffix}")
        titulo(f"Variante {i}/{n} → {destino.name}")
        generar_fichero(env, mensajes, destino, etiqueta=f"Variante {i} guardada en {destino.resolve()}")
        ficheros.append(destino)
    return ficheros


def crear_galeria(ficheros: list[Path], salida: Path, autor: dict[str, str]) -> Path:
    """Página con todas las variantes en iframes, una al lado de otra, para compararlas."""
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    tarjetas = "\n".join(
        f"""  <article class="variante">
    <h2>Variante {i}</h2>
    <p class="ruta"><a href="{f.name}" target="_blank" rel="noopener">{f.name}</a> ·
       <a href="{f.name}" target="_blank" rel="noopener">abrir a pantalla completa</a></p>
    <iframe src="{f.name}" title="Variante {i}" loading="lazy"></iframe>
  </article>"""
        for i, f in enumerate(ficheros, 1)
    )
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Variantes generadas</title>
<style>
  :root {{ --borde: #e1e4ea; --fondo: #f5f6fa; --texto: #1f2430; --suave: #666b78; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: "Segoe UI", system-ui, sans-serif; background: var(--fondo);
         color: var(--texto); line-height: 1.5; }}
  header {{ background: #fff; border-bottom: 1px solid var(--borde); padding: 1.25rem 1.5rem; }}
  h1 {{ margin: 0; font-size: 1.3rem; }}
  header p {{ margin: .25rem 0 0; color: var(--suave); font-size: .9rem; }}
  main {{ display: grid; gap: 1.25rem; padding: 1.5rem;
          grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); }}
  .variante {{ background: #fff; border: 1px solid var(--borde); border-radius: 10px;
               overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,.06); }}
  .variante h2 {{ margin: 0; padding: .85rem 1rem .35rem; font-size: 1rem; }}
  .ruta {{ margin: 0; padding: 0 1rem .75rem; font-size: .8rem; color: var(--suave); }}
  .ruta a {{ color: #2d3e8c; }}
  iframe {{ width: 100%; height: 70vh; border: 0; border-top: 1px solid var(--borde);
            background: #fff; }}
  footer {{ padding: 1.5rem; text-align: center; color: var(--suave); font-size: .8rem; }}
  footer p {{ margin: .2rem 0; }}
</style>
</head>
<body>
<header>
  <h1>Variantes generadas</h1>
  <p>{len(ficheros)} propuestas de la misma app. Compáralas y sigue trabajando sobre la que prefieras.</p>
</header>
<main>
{tarjetas}
</main>
<footer>
  <p>{autor['nombre']} · {autor['departamento']} · {autor['email']}</p>
  <p>Última modificación: {ahora}</p>
  <p><em>Generado con IA · Revisado por el autor</em></p>
</footer>
</body>
</html>
"""
    destino = salida.with_name(f"{salida.stem}_variantes.html")
    escribir_atomico(destino, html)
    return destino


# ===========================================================================
# Modo chat con comandos
# ===========================================================================

AYUDA_CHAT = f"""
{C.NEGRITA}Comandos disponibles{C.FIN} (lo que no empiece por / se envía como petición de cambio):
  {C.AZUL}/abrir{C.FIN}       abre el fichero generado en el navegador
  {C.AZUL}/preview{C.FIN}     arranca el servidor local con recarga automática
  {C.AZUL}/deshacer{C.FIN}    recupera la versión anterior del fichero
  {C.AZUL}/historial{C.FIN}   lista las copias guardadas de este fichero
  {C.AZUL}/modelo{C.FIN}      cambia de modelo (o de plataforma) sin perder la conversación
  {C.AZUL}/validar{C.FIN}     vuelve a comprobar el HTML actual
  {C.AZUL}/guardar [n]{C.FIN} guarda la conversación con un nombre para retomarla con --resume
  {C.AZUL}/gasto{C.FIN}       tokens consumidos en esta sesión
  {C.AZUL}/ayuda{C.FIN}       muestra esta ayuda
  {C.AZUL}/salir{C.FIN}       termina (también con Ctrl+D)
"""


def bucle_chat(
    env: Entorno,
    mensajes: Mensajes,
    salida: Path,
    nombre_sesion: str,
    preview: ServidorPreview | None,
) -> None:
    """Conversación para ir refinando la app. Cada vuelta reescribe el fichero."""
    titulo("Modo chat")
    print("Describe los cambios que quieras. Escribe /ayuda para ver los comandos.")

    while True:
        try:
            entrada = input(f"\n{C.NEGRITA}›{C.FIN} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not entrada:
            continue

        if entrada.startswith("/"):
            partes = entrada.split(maxsplit=1)
            comando = partes[0].lower()
            resto = partes[1].strip() if len(partes) > 1 else ""

            if comando in ("/salir", "/exit", "/quit", "/q"):
                break
            if comando in ("/ayuda", "/help", "/h", "/?"):
                print(AYUDA_CHAT)
            elif comando == "/abrir":
                webbrowser.open(salida.resolve().as_uri())
                ok(f"Abierto {salida.name} en el navegador.")
            elif comando == "/preview":
                if preview and preview.httpd:
                    ok("La previsualización ya está en marcha.")
                else:
                    preview = ServidorPreview(salida, env.cfg.puerto_preview)
                    preview.arrancar()
            elif comando in ("/deshacer", "/undo"):
                copias = copias_de(salida)
                if not copias:
                    aviso("No hay ninguna versión anterior guardada de este fichero.")
                else:
                    guardar_copia(salida)  # para poder rehacer
                    shutil.copy2(copias[0], salida)
                    ok(f"Restaurada la versión de {copias[0].name}")
            elif comando == "/historial":
                copias = copias_de(salida)
                if not copias:
                    gris("   (sin copias guardadas todavía)")
                for c in copias[:15]:
                    tam = c.stat().st_size // 1024
                    print(f"   {c.name}  ({tam} KB)")
            elif comando == "/modelo":
                nuevo_prov = elegir("Plataforma", [(p, p) for p in PROVEEDORES], env.proveedor.nombre)
                if not os.environ.get(API_KEY_ENV[nuevo_prov]):
                    aviso(f"No hay {API_KEY_ENV[nuevo_prov]} definida; se mantiene {env.proveedor.nombre}.")
                else:
                    opciones = [(m, f"{m} — {d}") for m, d in MODELOS_CURADOS[nuevo_prov]]
                    nuevo_modelo = elegir("Modelo", opciones, env.cfg.modelos_defecto[nuevo_prov])
                    if nuevo_prov != env.proveedor.nombre:
                        env.proveedor = crear_proveedor(nuevo_prov, env.proveedor.system_prompt)
                    env.modelo = nuevo_modelo
                    ok(f"Ahora se usará {nuevo_prov}/{nuevo_modelo}")
            elif comando == "/validar":
                if not salida.exists():
                    aviso("El fichero todavía no existe.")
                else:
                    problemas = validar_html(salida.read_text(encoding="utf-8"))
                    if problemas:
                        for p in problemas:
                            aviso(p)
                    else:
                        ok("El HTML pasa todas las comprobaciones.")
            elif comando == "/guardar":
                nombre_sesion = resto or nombre_sesion
                guardar_sesion(nombre_sesion, {
                    "proveedor": env.proveedor.nombre, "modelo": env.modelo,
                    "salida": str(salida), "mensajes": mensajes,
                })
                ok(f"Conversación guardada como '{nombre_sesion}' (retómala con --resume {nombre_sesion})")
            elif comando == "/gasto":
                resumen_gasto(env)
            else:
                aviso(f"Comando desconocido: {comando}. Escribe /ayuda.")
            continue

        mensajes.append({
            "role": "user",
            "content": f"Aplica este cambio y devuelve el HTML completo de nuevo: {entrada}",
        })
        print()
        try:
            respuesta = generar_fichero(
                env, mensajes, salida, con_diff=True,
                etiqueta=f"Actualizado {C.NEGRITA}{salida.resolve()}{C.FIN}",
            )
        except ErrorProveedor as e:
            error(str(e))
            mensajes.pop()  # no dejamos la petición fallida en el historial
            continue
        mensajes.append({"role": "assistant", "content": respuesta})
        # Autoguardado: si se cierra VS Code a media sesión, no se pierde el contexto
        guardar_sesion(nombre_sesion, {
            "proveedor": env.proveedor.nombre, "modelo": env.modelo,
            "salida": str(salida), "mensajes": mensajes,
        })


def resumen_gasto(env: Entorno) -> None:
    c = env.contador
    if not c.llamadas:
        return
    total = c.entrada + c.salida + c.cache_lectura + c.cache_escritura
    linea = (f"{c.llamadas} llamada(s) · {c.entrada} tokens de entrada · {c.salida} de salida")
    if c.cache_lectura or c.cache_escritura:
        linea += f" · caché: {c.cache_lectura} leídos / {c.cache_escritura} escritos"
    linea += f" · {total} en total"
    coste = c.coste(env.cfg.precios.get(env.modelo))
    if coste is not None:
        linea += f" · ≈ {coste:.4f} USD"
    gris(f"\n{linea}")


# ===========================================================================
# --init: preparar la carpeta para VS Code
# ===========================================================================

LAUNCH_JSON = """{
  // Configuraciones de F5 para generar_app.py
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Generar app (menú interactivo)",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/generar_app.py",
      "console": "integratedTerminal",
      "justMyCode": true
    },
    {
      "name": "Generar app + previsualización en el navegador",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/generar_app.py",
      "args": ["--serve", "--chat"],
      "console": "integratedTerminal",
      "justMyCode": true
    },
    {
      "name": "Retomar la última conversación",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/generar_app.py",
      "args": ["--resume"],
      "console": "integratedTerminal",
      "justMyCode": true
    },
    {
      "name": "Listar modelos (lista real de mi cuenta)",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/generar_app.py",
      "args": ["--list-models", "--remote"],
      "console": "integratedTerminal",
      "justMyCode": true
    }
  ]
}
"""

TASKS_JSON = """{
  // Terminal → Run Task...  Estas tareas preguntan con desplegables nativos de VS Code.
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Nueva app",
      "type": "shell",
      "command": "${command:python.interpreterPath}",
      "args": [
        "${workspaceFolder}/generar_app.py",
        "${input:descripcion}",
        "-o", "${input:fichero}",
        "--provider", "${input:plataforma}",
        "--serve", "--chat"
      ],
      "problemMatcher": [],
      "presentation": { "reveal": "always", "panel": "dedicated", "clear": true }
    },
    {
      "label": "Modificar la app abierta en el editor",
      "type": "shell",
      "command": "${command:python.interpreterPath}",
      "args": [
        "${workspaceFolder}/generar_app.py",
        "${input:cambio}",
        "--base", "${file}",
        "-o", "${file}",
        "--serve", "--chat"
      ],
      "problemMatcher": [],
      "presentation": { "reveal": "always", "panel": "dedicated", "clear": true }
    },
    {
      "label": "Generar 3 variantes de diseño",
      "type": "shell",
      "command": "${command:python.interpreterPath}",
      "args": [
        "${workspaceFolder}/generar_app.py",
        "${input:descripcion}",
        "-o", "${input:fichero}",
        "--variantes", "3"
      ],
      "problemMatcher": [],
      "presentation": { "reveal": "always", "panel": "dedicated", "clear": true }
    },
    {
      "label": "Listar modelos disponibles",
      "type": "shell",
      "command": "${command:python.interpreterPath}",
      "args": ["${workspaceFolder}/generar_app.py", "--list-models", "--remote"],
      "problemMatcher": [],
      "presentation": { "reveal": "always", "panel": "dedicated", "clear": true }
    },
    {
      "label": "Instalar dependencias",
      "type": "shell",
      "command": "${command:python.interpreterPath}",
      "args": ["-m", "pip", "install", "-r", "${workspaceFolder}/requirements.txt"],
      "problemMatcher": []
    }
  ],
  "inputs": [
    {
      "id": "descripcion",
      "type": "promptString",
      "description": "Describe la app que quieres generar"
    },
    {
      "id": "cambio",
      "type": "promptString",
      "description": "Qué cambio quieres aplicar al fichero abierto"
    },
    {
      "id": "fichero",
      "type": "promptString",
      "description": "Nombre del fichero HTML de salida",
      "default": "mi_app.html"
    },
    {
      "id": "plataforma",
      "type": "pickString",
      "description": "Plataforma de IA",
      "options": ["anthropic", "openai"],
      "default": "anthropic"
    }
  ]
}
"""

SETTINGS_JSON = """{
  // Entorno creado con «python3 -m venv .venv» (ver README). En Windows la extensión
  // de Python detecta igualmente .venv\\Scripts\\python.exe.
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.terminal.activateEnvironment": true,
  "files.exclude": { "**/__pycache__": true },
  "search.exclude": { "**/.venv": true, "**/.generar_app": true },
  "files.watcherExclude": { "**/.venv/**": true, "**/.generar_app/**": true }
}
"""

EXTENSIONS_JSON = """{
  "recommendations": [
    "ms-python.python",
    "ms-python.debugpy"
  ]
}
"""

ENV_EXAMPLE = """# Copia este fichero como ".env" y rellena la clave de la plataforma que uses.
# generar_app.py lo carga solo al arrancar. No subas el .env real a ningún repositorio.

ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...

# Plataforma por defecto si no pasas --provider (anthropic | openai)
AI_PROVIDER=anthropic

# Modelo por defecto de cada plataforma (ver: python generar_app.py --list-models)
ANTHROPIC_MODEL=claude-sonnet-5
OPENAI_MODEL=gpt-6-luna
"""

GITIGNORE = """.env
.venv/
__pycache__/
*.pyc
.DS_Store
*.tmp
# Historial de versiones y conversaciones guardadas (datos locales de trabajo)
.generar_app/
# Apps generadas durante las pruebas (guarda aquí solo las que quieras conservar)
salida*.html
"""

REQUIREMENTS = """anthropic>=0.40.0
openai>=1.50.0
python-dotenv>=1.0.0
"""


def config_json_por_defecto(cfg: Config) -> str:
    return json.dumps(
        {
            "proveedor": cfg.proveedor,
            "modelos_defecto": cfg.modelos_defecto,
            "max_tokens": cfg.max_tokens,
            "autor": cfg.autor,
            "puerto_preview": cfg.puerto_preview,
            "color": cfg.color,
            "_precios": "Opcional. Rellena 'precios' con el coste por millón de tokens de los "
                        "modelos que uses y el script mostrará el gasto estimado de cada llamada.",
            "precios": {},
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def plantilla_base_html(autor: dict[str, str]) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nombre de la app</title>
<style>
  :root {{
    --color-fondo: #f5f6fa;
    --color-superficie: #ffffff;
    --color-primario: #2d3e8c;
    --color-primario-hover: #23316e;
    --color-texto: #1f2430;
    --color-texto-suave: #666b78;
    --color-borde: #e1e4ea;
    --radio: 10px;
    --sombra: 0 2px 10px rgba(0, 0, 0, 0.06);
    font-size: 16px;
  }}

  @media (prefers-color-scheme: dark) {{
    :root {{
      --color-fondo: #16181d;
      --color-superficie: #1f2228;
      --color-texto: #e8eaed;
      --color-texto-suave: #a0a6b0;
      --color-borde: #2f333b;
    }}
  }}

  * {{ box-sizing: border-box; }}

  body {{
    margin: 0;
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    background: var(--color-fondo);
    color: var(--color-texto);
    line-height: 1.5;
  }}

  header {{
    background: var(--color-superficie);
    border-bottom: 1px solid var(--color-borde);
    padding: 1.25rem 1.5rem;
  }}

  header h1 {{ margin: 0; font-size: 1.4rem; }}
  header p {{ margin: .25rem 0 0; color: var(--color-texto-suave); font-size: .95rem; }}

  main {{ max-width: 860px; margin: 0 auto; padding: 1.5rem; }}

  .card {{
    background: var(--color-superficie);
    border: 1px solid var(--color-borde);
    border-radius: var(--radio);
    box-shadow: var(--sombra);
    padding: 1.5rem;
    margin-bottom: 1.25rem;
  }}

  label {{ display: block; font-weight: 600; margin-bottom: .4rem; font-size: .9rem; }}

  input, select, textarea {{
    width: 100%;
    padding: .6rem .75rem;
    border: 1px solid var(--color-borde);
    border-radius: 8px;
    font: inherit;
    font-size: .95rem;
    background: var(--color-superficie);
    color: var(--color-texto);
    margin-bottom: 1rem;
  }}

  button {{
    background: var(--color-primario);
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: .65rem 1.3rem;
    font-size: .95rem;
    font-weight: 600;
    cursor: pointer;
    transition: background .15s ease;
  }}

  button:hover {{ background: var(--color-primario-hover); }}
  :focus-visible {{ outline: 2px solid var(--color-primario); outline-offset: 2px; }}

  footer {{
    max-width: 860px;
    margin: 2rem auto 1.5rem;
    padding: 0 1.5rem;
    color: var(--color-texto-suave);
    font-size: .8rem;
    text-align: center;
  }}

  footer p {{ margin: .2rem 0; }}

  @media (max-width: 600px) {{
    main, footer {{ padding-left: 1rem; padding-right: 1rem; }}
  }}
</style>
</head>
<body>

<header>
  <h1>Nombre de la app</h1>
  <p>Breve descripción de una línea de lo que hace la app.</p>
</header>

<main>
  <div class="card">
    <!-- Contenido principal de la app -->
  </div>
</main>

<footer>
  <p>{autor['nombre']} · {autor['departamento']} · {autor['email']}</p>
  <p>Última modificación: {FECHA_MARCADOR}</p>
  <p><em>Generado con IA · Revisado por el autor</em></p>
</footer>

<script>
  // Lógica de la app
</script>

</body>
</html>
"""


def ejecutar_init(cfg: Config, forzar: bool = False) -> None:
    """Crea en la carpeta del script todo lo necesario para trabajar desde VS Code."""
    titulo("Preparando la carpeta para VS Code")
    ficheros = {
        ".vscode/launch.json": LAUNCH_JSON,
        ".vscode/tasks.json": TASKS_JSON,
        ".vscode/settings.json": SETTINGS_JSON,
        ".vscode/extensions.json": EXTENSIONS_JSON,
        ".env.example": ENV_EXAMPLE,
        ".gitignore": GITIGNORE,
        "requirements.txt": REQUIREMENTS,
        "generar_app.config.json": config_json_por_defecto(cfg),
        "plantilla_base.html": plantilla_base_html(cfg.autor),
    }
    for nombre, contenido in ficheros.items():
        destino = SCRIPT_DIR / nombre
        if destino.exists() and not forzar:
            gris(f"   · {nombre} ya existe, se deja como está")
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
        ok(f"{nombre}")

    print(f"""
{C.NEGRITA}Siguientes pasos{C.FIN}
  1. Crea el entorno e instala las dependencias:
       python3 -m venv .venv && source .venv/bin/activate   {C.GRIS}# Windows: .venv\\Scripts\\activate{C.FIN}
       pip install -r requirements.txt
  2. Copia .env.example como .env y pega tu clave de API.
  3. En VS Code ya tienes:
       · Botón ▶ / F5  →  menú interactivo
       · Terminal → Run Task  →  "Nueva app", "Modificar la app abierta en el editor", "Generar 3 variantes"
""")


# ===========================================================================
# Menú interactivo (botón ▶ de VS Code, sin argumentos)
# ===========================================================================

def pedir_descripcion() -> str:
    """Descripción en una línea o, si se deja vacía, en varias líneas hasta una línea sola con un punto."""
    print(f"\n{C.NEGRITA}Describe la app{C.FIN} {C.GRIS}(Intro vacío para escribir varias líneas){C.FIN}")
    primera = input("› ").strip()
    if primera:
        return primera
    print(f"{C.GRIS}Escribe la descripción; termina con una línea que contenga solo un punto (.){C.FIN}")
    lineas: list[str] = []
    while True:
        try:
            linea = input("  ")
        except (EOFError, KeyboardInterrupt):
            break
        if linea.strip() == ".":
            break
        lineas.append(linea)
    return "\n".join(lineas).strip()


def pedir_fichero(texto: str, defecto: str = "") -> Path:
    while True:
        bruto = preguntar(texto, defecto)
        if not bruto:
            aviso("Hace falta un nombre de fichero.")
            continue
        ruta = Path(bruto).expanduser()
        if not ruta.suffix:
            ruta = ruta.with_suffix(".html")
        return ruta


def pedir_fichero_existente(texto: str) -> Path:
    while True:
        ruta = pedir_fichero(texto)
        if ruta.exists():
            return ruta
        aviso(f"No encuentro '{ruta}'. (Tabulador para autocompletar.)")


def elegir_plataforma_y_modelo(cfg: Config) -> tuple[str, str]:
    disponibles = [p for p in PROVEEDORES if os.environ.get(API_KEY_ENV[p])]
    if not disponibles:
        error("No hay ninguna clave de API definida (ANTHROPIC_API_KEY / OPENAI_API_KEY).\n"
              "   Copia .env.example como .env y pega tu clave, o ejecuta --init si aún no lo tienes.")
        raise SystemExit(1)

    if len(disponibles) == 1:
        proveedor = disponibles[0]
        gris(f"\nPlataforma: {proveedor} (la única con clave configurada)")
    else:
        proveedor = elegir("Plataforma", [(p, p) for p in disponibles], cfg.proveedor)

    defecto = cfg.modelos_defecto[proveedor]
    opciones = [(m, f"{m:<18} {d}") for m, d in MODELOS_CURADOS[proveedor]]
    if defecto not in [m for m, _ in opciones]:
        opciones.insert(0, (defecto, f"{defecto:<18} (de tu configuración)"))
    modelo = elegir("Modelo", opciones, defecto)
    return proveedor, modelo


def menu_interactivo(cfg: Config, args: argparse.Namespace) -> int:
    """Flujo guiado para cuando se lanza sin argumentos (botón ▶ de VS Code)."""
    _activar_completado_rutas()
    print(f"""
{C.NEGRITA}{C.AZUL}╭──────────────────────────────────────────────╮
│  Generador de apps web de un solo HTML       │
╰──────────────────────────────────────────────╯{C.FIN}""")

    accion = elegir("¿Qué quieres hacer?", [
        ("nueva", "Crear una app nueva"),
        ("modificar", "Modificar una app que ya tengo"),
        ("variantes", "Generar varias variantes de una misma idea"),
        ("retomar", "Retomar una conversación anterior"),
        ("modelos", "Ver los modelos disponibles"),
        ("init", "Preparar esta carpeta para VS Code (.vscode, .env.example...)"),
        ("salir", "Salir"),
    ], "nueva")

    if accion == "salir":
        return 0
    if accion == "init":
        ejecutar_init(cfg)
        return 0
    if accion == "modelos":
        remoto = preguntar_si_no("¿Consultar la lista real de tu cuenta (requiere clave de API)?", False)
        mostrar_modelos(cfg, remoto=remoto)
        return 0

    if accion == "retomar":
        sesiones = listar_sesiones()
        if not sesiones:
            aviso("No hay conversaciones guardadas todavía.")
            return 0
        opciones = [
            (n, f"{n:<22} {d.get('salida', '?')}  {C.GRIS}{d.get('actualizada', '')}{C.FIN}")
            for n, d in sesiones[:10]
        ]
        args.resume = elegir("Conversación a retomar", opciones, sesiones[0][0])
        return ejecutar(cfg, args)

    proveedor, modelo = elegir_plataforma_y_modelo(cfg)
    args.provider, args.model = proveedor, modelo

    if accion == "modificar":
        args.base = str(pedir_fichero_existente("Fichero HTML a modificar"))
        args.descripcion = pedir_descripcion()
        sobrescribir = preguntar_si_no(f"¿Guardar los cambios en el mismo fichero ({Path(args.base).name})?", True)
        args.output = args.base if sobrescribir else str(pedir_fichero("Fichero de salida"))
    else:
        args.descripcion = pedir_descripcion()
        args.output = str(pedir_fichero("Fichero de salida", "mi_app.html"))
        if accion == "variantes":
            while True:
                bruto = preguntar("¿Cuántas variantes?", "3")
                if bruto.isdigit() and 2 <= int(bruto) <= 6:
                    args.variantes = int(bruto)
                    break
                aviso("Indica un número entre 2 y 6.")

    if not args.descripcion:
        error("No se ha indicado ninguna descripción.")
        return 1

    if args.variantes <= 1:
        args.serve = preguntar_si_no("¿Abrir una previsualización en el navegador que se recargue sola?", True)
        args.chat = preguntar_si_no("¿Entrar en modo chat para ir pidiendo ajustes?", True)
        args.no_chat = not args.chat  # ya se ha preguntado aquí: que ejecutar() no vuelva a hacerlo

    return ejecutar(cfg, args)


# ===========================================================================
# Listado de modelos
# ===========================================================================

def mostrar_modelos(cfg: Config, remoto: bool = False, solo: str | None = None) -> None:
    proveedores = [solo] if solo else list(PROVEEDORES)

    if not remoto:
        titulo("Modelos (lista incluida en el script)")
        for p in proveedores:
            print(f"\n{C.NEGRITA}{p}{C.FIN}  {C.GRIS}(clave: {API_KEY_ENV[p]}){C.FIN}")
            for id_modelo, desc in MODELOS_CURADOS[p]:
                marca = f"  {C.VERDE}← por defecto{C.FIN}" if id_modelo == cfg.modelos_defecto[p] else ""
                print(f"  {id_modelo:<20} {C.GRIS}{desc}{C.FIN}{marca}")
        print(f"\n{C.GRIS}Los catálogos cambian cada pocos meses. Para la lista real de tu cuenta:\n"
              f"  python generar_app.py --list-models --remote{C.FIN}\n")
        return

    titulo("Modelos disponibles en tu cuenta (consultado a la API)")
    for p in proveedores:
        if not os.environ.get(API_KEY_ENV[p]):
            gris(f"\n{p}: sin {API_KEY_ENV[p]} definida, se omite")
            continue
        print(f"\n{C.NEGRITA}{p}{C.FIN}")
        try:
            with Spinner(f"Consultando {p}"):
                modelos = crear_proveedor(p, "").listar_modelos()
        except Exception as e:
            aviso(f"No se ha podido consultar {p}: {_explicar(e, p, '')}")
            continue
        descripciones = dict(MODELOS_CURADOS[p])
        for id_modelo, nombre in modelos:
            extra = descripciones.get(id_modelo) or nombre
            marca = f"  {C.VERDE}← por defecto{C.FIN}" if id_modelo == cfg.modelos_defecto[p] else ""
            print(f"  {id_modelo:<34} {C.GRIS}{extra}{C.FIN}{marca}")
    print()


# ===========================================================================
# Ejecución principal
# ===========================================================================

def ejecutar(cfg: Config, args: argparse.Namespace) -> int:
    # --- Retomar una sesión guardada -------------------------------------
    mensajes: Mensajes = []
    nombre_sesion = ""
    salida: Path | None = None

    if args.resume is not None:
        encontrada = cargar_sesion(args.resume)
        if not encontrada:
            error("No hay ninguna conversación guardada con ese nombre. "
                  "Las conversaciones se guardan solas al usar el modo chat.")
            return 1
        nombre_sesion, datos = encontrada
        mensajes = datos.get("mensajes", [])
        salida = Path(datos.get("salida", "app.html"))
        args.provider = args.provider or datos.get("proveedor")
        args.model = args.model or datos.get("modelo")
        ok(f"Retomada la conversación '{nombre_sesion}' sobre {salida.name} "
           f"({len(mensajes)} mensajes previos)")
        args.chat = True

    proveedor_nombre = args.provider or cfg.proveedor
    if proveedor_nombre not in PROVEEDORES:
        error(f"Plataforma no reconocida: {proveedor_nombre}")
        return 1

    clave = API_KEY_ENV[proveedor_nombre]
    if not os.environ.get(clave):
        error(f"No se encuentra {clave} en el entorno (necesaria para --provider {proveedor_nombre}).\n"
              f"   Defínela en tu fichero .env o como variable de entorno. "
              f"Si aún no tienes .env, ejecuta:  python generar_app.py --init")
        return 1

    modelo = args.model or cfg.modelos_defecto[proveedor_nombre]

    # --- Descripción ------------------------------------------------------
    descripcion = args.descripcion or ""
    if args.prompt_file:
        ruta = Path(args.prompt_file).expanduser()
        if not ruta.exists():
            error(f"No encuentro el fichero de descripción: {ruta}")
            return 1
        descripcion = ruta.read_text(encoding="utf-8").strip()
    if not descripcion and not mensajes:
        if interactivo():
            descripcion = pedir_descripcion()
        if not descripcion:
            error("No se ha indicado ninguna descripción de la app.")
            return 1

    # --- Fichero de salida ------------------------------------------------
    if args.output:
        salida = Path(args.output).expanduser()
    elif salida is None:
        if interactivo():
            salida = pedir_fichero("Fichero de salida", "mi_app.html")
        else:
            error("Falta -o/--output (el fichero HTML de salida).")
            return 1
    if not salida.suffix:
        salida = salida.with_suffix(".html")

    # --- Base y plantilla -------------------------------------------------
    base: Path | None = None
    if args.base:
        base = Path(args.base).expanduser()
        if not base.exists():
            error(f"No encuentro el fichero base: {base}")
            return 1

    plantilla: Path | None = None
    if not base and not mensajes:
        if args.template:
            plantilla = Path(args.template).expanduser()
            if not plantilla.exists():
                error(f"No encuentro la plantilla: {plantilla}")
                return 1
        elif not args.no_template and PLANTILLA_POR_DEFECTO.exists():
            plantilla = PLANTILLA_POR_DEFECTO

    if args.variantes > 1 and args.chat:
        error("--chat no se puede combinar con --variantes. Genera las variantes, elige una y "
              "continúa sobre ella con:\n"
              f"   python generar_app.py \"ajustes\" --base {salida.stem}_v1.html -o {salida} --chat")
        return 1

    # --- Preparar el entorno de generación --------------------------------
    system_prompt = construir_system_prompt(cfg.autor)
    try:
        proveedor = crear_proveedor(proveedor_nombre, system_prompt)
    except ErrorProveedor as e:
        error(str(e))
        return 1

    env = Entorno(
        cfg=cfg, proveedor=proveedor, modelo=modelo,
        max_tokens=args.max_tokens or cfg.max_tokens, stream=not args.no_stream,
    )

    if not mensajes:
        peticion = construir_peticion(descripcion, base, plantilla)
        if args.dry_run:
            titulo("Petición que se enviaría (--dry-run, no se llama a la API)")
            print(f"{C.GRIS}--- system ---{C.FIN}\n{system_prompt}")
            print(f"{C.GRIS}--- user ({len(peticion)} caracteres) ---{C.FIN}\n{peticion[:4000]}")
            if len(peticion) > 4000:
                gris(f"... y {len(peticion) - 4000} caracteres más")
            print(f"\n{C.GRIS}Destino: {salida}  ·  {proveedor_nombre}/{modelo}  ·  "
                  f"max_tokens={env.max_tokens}{C.FIN}")
            return 0
        mensajes = [{"role": "user", "content": peticion}]

    # --- Variantes --------------------------------------------------------
    if args.variantes > 1:
        titulo(f"Generando {args.variantes} variantes con {proveedor_nombre}/{modelo}")
        try:
            ficheros = generar_variantes(env, mensajes[0]["content"], salida, args.variantes)
        except ErrorProveedor as e:
            error(str(e))
            return 1
        galeria = crear_galeria(ficheros, salida, cfg.autor)
        ok(f"Galería comparativa en {C.NEGRITA}{galeria.resolve()}{C.FIN}")
        resumen_gasto(env)
        if args.serve or args.open:
            webbrowser.open(galeria.resolve().as_uri())
        print(f"\n{C.GRIS}Para seguir trabajando sobre la que más te guste:\n"
              f"   python generar_app.py \"ajustes\" --base {ficheros[0].name} -o {salida.name} "
              f"--chat --serve{C.FIN}")
        return 0

    # --- Generación normal ------------------------------------------------
    es_retomada = bool(args.resume)
    preview: ServidorPreview | None = None

    if not es_retomada:
        titulo(f"Generando {salida.name} con {proveedor_nombre}/{modelo}")
        try:
            respuesta = generar_fichero(env, mensajes, salida, con_diff=bool(base))
        except ErrorProveedor as e:
            error(str(e))
            return 1
        mensajes.append({"role": "assistant", "content": respuesta})

    if args.serve:
        preview = ServidorPreview(salida, cfg.puerto_preview)
        preview.arrancar()
    elif args.open:
        webbrowser.open(salida.resolve().as_uri())

    # --- Chat -------------------------------------------------------------
    continuar = args.chat
    if not continuar and not args.no_chat and interactivo():
        continuar = preguntar_si_no("¿Quieres pedir ajustes sobre esta app ahora?", False)

    if continuar:
        if not nombre_sesion:
            nombre_sesion = f"{salida.stem}-{datetime.now():%Y%m%d-%H%M}"
        _activar_completado_rutas()
        try:
            bucle_chat(env, mensajes, salida, nombre_sesion, preview)
        finally:
            guardar_sesion(nombre_sesion, {
                "proveedor": env.proveedor.nombre, "modelo": env.modelo,
                "salida": str(salida), "mensajes": mensajes,
            })
            gris(f"\nConversación guardada como '{nombre_sesion}'. "
                 f"Retómala con:  python generar_app.py --resume {nombre_sesion}")

    resumen_gasto(env)

    if preview:
        if interactivo() and not continuar:
            try:
                input(f"\n{C.GRIS}Previsualización activa. Pulsa Intro para cerrarla.{C.FIN}")
            except (EOFError, KeyboardInterrupt):
                print()
        preview.parar()

    ok(f"Listo: {salida.resolve()}")
    return 0


def construir_parser(cfg: Config) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="generar_app.py",
        description="Genera o modifica apps web de un solo fichero HTML con la API de Anthropic o de OpenAI.",
        epilog="Sin argumentos entra en modo interactivo (pensado para el botón ▶ de VS Code).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("descripcion", nargs="?", help="Descripción de la app, o del cambio si usas --base")

    g_entrada = p.add_argument_group("entrada")
    g_entrada.add_argument("--prompt-file", metavar="FICHERO",
                           help="Lee la descripción de un fichero de texto (para peticiones largas)")
    g_entrada.add_argument("--base", metavar="HTML",
                           help="HTML existente del que partir (modo edición; ignora la plantilla)")
    g_entrada.add_argument("--template", metavar="HTML",
                           help=f"Plantilla de estilo a usar (por defecto {PLANTILLA_POR_DEFECTO.name} si existe)")
    g_entrada.add_argument("--no-template", action="store_true",
                           help="No usar ninguna plantilla: generar desde cero")

    g_salida = p.add_argument_group("salida")
    g_salida.add_argument("-o", "--output", metavar="HTML", help="Fichero HTML de salida")
    g_salida.add_argument("--variantes", type=int, default=1, metavar="N",
                          help="Genera N variantes de diseño + una galería para compararlas")
    g_salida.add_argument("--serve", action="store_true",
                          help="Abre una previsualización local que se recarga en cada cambio")
    g_salida.add_argument("--open", action="store_true",
                          help="Abre el fichero generado en el navegador (sin servidor)")

    g_modelo = p.add_argument_group("modelo")
    g_modelo.add_argument("--provider", choices=PROVEEDORES, default=None,
                          help=f"Plataforma de IA (por defecto {cfg.proveedor}; también AI_PROVIDER en .env)")
    g_modelo.add_argument("--model", metavar="ID",
                          help="Modelo a usar (por defecto el de tu configuración; ver --list-models)")
    g_modelo.add_argument("--max-tokens", type=int, default=None, metavar="N",
                          help=f"Límite de tokens de salida (por defecto {cfg.max_tokens}; "
                               f"se amplía solo si la respuesta sale truncada)")
    g_modelo.add_argument("--no-stream", action="store_true",
                          help="No mostrar el texto en vivo mientras se genera")

    g_sesion = p.add_argument_group("conversación")
    g_sesion.add_argument("--chat", action="store_true",
                          help="Entra en modo chat tras generar, para ir pidiendo ajustes")
    g_sesion.add_argument("--no-chat", action="store_true",
                          help="No preguntar si quieres entrar en modo chat (útil en scripts)")
    g_sesion.add_argument("--resume", nargs="?", const="ultima", metavar="NOMBRE",
                          help="Retoma una conversación guardada (sin nombre, la última)")

    g_otros = p.add_argument_group("otros")
    g_otros.add_argument("--list-models", action="store_true", help="Lista los modelos y termina")
    g_otros.add_argument("--remote", action="store_true",
                         help="Con --list-models, consulta la lista real de tu cuenta contra la API")
    g_otros.add_argument("--list-sessions", action="store_true",
                         help="Lista las conversaciones guardadas y termina")
    g_otros.add_argument("--init", action="store_true",
                         help="Crea .vscode/, .env.example, plantilla y configuración en esta carpeta")
    g_otros.add_argument("--force", action="store_true", help="Con --init, sobrescribe lo que ya exista")
    g_otros.add_argument("--dry-run", action="store_true",
                         help="Muestra la petición que se enviaría, sin llamar a la API")
    g_otros.add_argument("--no-color", action="store_true", help="Salida sin colores ANSI")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    cfg = Config.cargar()
    parser = construir_parser(cfg)
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)

    configurar_color(cfg.color and not args.no_color)

    if args.init:
        ejecutar_init(cfg, forzar=args.force)
        return 0
    if args.list_models:
        mostrar_modelos(cfg, remoto=args.remote, solo=args.provider)
        return 0
    if args.list_sessions:
        sesiones = listar_sesiones()
        if not sesiones:
            gris("No hay conversaciones guardadas.")
            return 0
        titulo("Conversaciones guardadas")
        for n, d in sesiones:
            print(f"  {n:<26} {d.get('salida', '?'):<28} "
                  f"{C.GRIS}{len(d.get('mensajes', []))} mensajes · {d.get('actualizada', '')}{C.FIN}")
        print(f"\n{C.GRIS}Retoma una con:  python generar_app.py --resume <nombre>{C.FIN}\n")
        return 0

    # Sin argumentos y con un humano delante: menú interactivo (botón ▶ de VS Code)
    if not argv and interactivo():
        return menu_interactivo(cfg, args)

    return ejecutar(cfg, args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        gris("Interrumpido.")
        raise SystemExit(130)

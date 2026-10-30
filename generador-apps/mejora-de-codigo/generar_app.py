#!/usr/bin/env python3
"""
generar_app.py
===============
Generador de apps web (HTML de un solo archivo) usando la API de Anthropic o
la de OpenAI, pensado para ejecutarse desde VS Code.

Se puede lanzar de dos formas:

1. Directamente, sin argumentos (botón ▶ "Run Python File", F5 con la
   configuración "Generar app (interactivo)" de .vscode/launch.json, o
   simplemente `python generar_app.py`): entra en modo interactivo y lo
   pregunta todo por consola (plataforma, fichero de salida, descripción,
   si quieres seguir pidiendo ajustes...).
2. Con argumentos desde la terminal, como cualquier script de línea de
   comandos (ver ejemplos abajo); lo que indiques por argumento no se
   vuelve a preguntar.

Uso rápido (modo línea de comandos)
------------------------------------
    # Ver qué modelos hay disponibles en cada plataforma
    python generar_app.py --list-models

    # Generar una app nueva (usa plantilla_base.html si existe). Por defecto, Anthropic.
    python generar_app.py "App que convierte medidas de patronaje de cm a pulgadas" -o conversor.html

    # Usar OpenAI en vez de Anthropic, y un modelo concreto
    python generar_app.py "..." -o app.html --provider openai --model gpt-6-astra

    # Describir la app en un fichero de texto largo en vez de en la línea de comandos
    python generar_app.py --prompt-file especificacion.txt -o mi_app.html

    # Modo interactivo: te pregunta la descripción y luego permite pedir cambios
    python generar_app.py -o mi_app.html --chat

    # Partir de una app existente tuya y pedirle cambios (ej. una de tu familia GenOutFit)
    python generar_app.py "Añade un botón para exportar a PDF" --base genoutfit.html -o genoutfit.html --chat

    # Generar varias variantes de diseño de golpe, para elegir después
    python generar_app.py "App de checklist para revisión de patrones" -o checklist.html --variantes 3

Requisitos
----------
    pip install -r requirements.txt
    Variable de entorno ANTHROPIC_API_KEY y/o OPENAI_API_KEY (según la plataforma que uses),
    definida en el entorno o en un fichero .env (ver .env.example)
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv es opcional; si no está, se usa el entorno tal cual

# ---------------------------------------------------------------------------
# Configuración por defecto — ajusta esto a tu gusto
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PLANTILLA_POR_DEFECTO = SCRIPT_DIR / "plantilla_base.html"

PROVEEDOR_POR_DEFECTO = os.environ.get("AI_PROVIDER", "anthropic")
MAX_TOKENS_POR_DEFECTO = 20000

# Reintentos automáticos ante errores transitorios de la API (límite de tasa,
# servidor sobrecargado, cortes de conexión...). REINTENTOS_MAX es el número de
# reintentos tras el primer fallo (es decir, hasta REINTENTOS_MAX + 1 intentos en total).
REINTENTOS_MAX = 4
ESPERA_BASE_SEGUNDOS = 2.0

AUTOR = {
    "nombre": "Rafael Puerto",
    "departamento": "Departamento de Ingeniería de Sistemas y Automática, UMH",
    "email": "r.puerto@umh.es",
}

# Modelos disponibles por plataforma: (id_api, descripción breve).
# Esta lista es curada a mano — si Anthropic u OpenAI sacan modelos nuevos y quieres
# usarlos, puedes pasar cualquier id con --model aunque no esté aquí.
MODELOS = {
    "anthropic": [
        ("claude-opus-5-5", "El más capaz; trabajo agéntico y de conocimiento largo/complejo"),
        ("claude-sonnet-5-5", "Mejor equilibrio velocidad/inteligencia de la familia 5.5"),
        ("claude-sonnet-5", "Eficiente para uso cotidiano, anterior a la familia 5.5"),
        ("claude-haiku-5-5", "El más rápido y económico, para tareas de alto volumen"),
        ("claude-fable-5-1", "Razonamiento exigente y tareas agénticas de largo recorrido"),
    ],
    "openai": [
        ("gpt-6-astra", "El más capaz de OpenAI, para el trabajo más exigente"),
        ("gpt-6.1-sol", "Rendimiento cercano a Astra, más económico"),
        ("gpt-6-sol", "Pensado específicamente para código y flujos de trabajo agénticos"),
        ("gpt-6-luna", "El más rápido y económico, para tareas de alto volumen"),
    ],
}

# El marcador "← por defecto" en --list-models se calcula solo, comparando con esto.
MODELO_POR_DEFECTO = {
    "anthropic": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
    "openai": os.environ.get("OPENAI_MODEL", "gpt-6-luna"),
}

API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# Enfoques que se van rotando al generar varias variantes con --variantes,
# para que no salgan todas prácticamente iguales.
ENFOQUES_VARIANTES = [
    "una propuesta visual minimalista, con mucho espacio en blanco y tipografía grande",
    "una propuesta más colorida y con más personalidad gráfica (iconos, acentos de color)",
    "una propuesta centrada en la densidad de información, tipo panel de control",
    "una propuesta con una interacción distinta, por ejemplo en pasos (wizard) en vez de todo en una pantalla",
]

SYSTEM_PROMPT = f"""Eres un generador experto de aplicaciones web de un solo archivo HTML.

Reglas de estilo que debes seguir SIEMPRE, salvo que el usuario pida explícitamente lo contrario:

1. La app es un único archivo .html autocontenido: CSS en un <style> interno y JavaScript en un
   <script> interno. Sin dependencias de build ni paquetes npm. Puedes cargar librerías JS desde un
   CDN (ej. cdnjs, jsdelivr, unpkg) solo si aportan algo que no merece la pena reimplementar.
2. Interfaz en español, limpia, moderna y responsive (debe verse bien también en móvil).
3. Si la app necesita llamar a una API de IA (Anthropic, OpenAI, Gemini, fal.ai, etc.), pide la
   clave de API al usuario mediante un campo de la propia interfaz (nunca la escribas hardcodeada
   en el código) y explica brevemente dónde debe pegarla.
4. Incluye siempre, al final de la página, un <footer> con este formato exacto (ajustando el texto
   a lo que describa la app):

   <footer>
     <p>{AUTOR['nombre']} · {AUTOR['departamento']} · {AUTOR['email']}</p>
     <p>Última modificación: FECHA_HORA</p>
     <p><em>Generado con IA · Revisado por el autor</em></p>
   </footer>

   Para FECHA_HORA escribe un marcador de texto exactamente igual a "FECHA_HORA" (sin comillas);
   el propio script Python que te invoca se encargará de sustituirlo por la fecha y hora reales
   después de recibir tu respuesta, así que no intentes calcularlo tú.
5. Devuelve ÚNICAMENTE el código HTML completo dentro de un único bloque de código ```html ... ```.
   No añadas explicaciones antes ni después del bloque: el script que te invoca extrae solo ese
   bloque y lo guarda tal cual como fichero.
6. Si recibes un HTML existente como punto de partida y una petición de cambios, devuelve el
   archivo COMPLETO ya modificado (no un parche ni solo las líneas que cambian).
"""

FECHA_MARCADOR = "FECHA_HORA"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def mostrar_modelos():
    """Imprime los modelos disponibles de cada plataforma (--list-models)."""
    for proveedor, modelos in MODELOS.items():
        recomendado = MODELO_POR_DEFECTO[proveedor]
        print(f"\n{proveedor}  (clave: {API_KEY_ENV[proveedor]})")
        for id_modelo, descripcion in modelos:
            marca = "  ←  por defecto" if id_modelo == recomendado else ""
            print(f"  {id_modelo:<18} {descripcion}{marca}")
    print(
        "\nUsa --provider {anthropic,openai} --model <id> para elegir. "
        "También puedes pasar cualquier otro id de modelo aunque no esté en esta lista.\n"
    )


def crear_cliente(proveedor: str):
    """Crea el cliente del SDK correspondiente, con un mensaje claro si falta instalar algo."""
    if proveedor == "anthropic":
        try:
            import anthropic
        except ImportError:
            sys.exit(
                "Falta el paquete 'anthropic'. Instala las dependencias con:\n"
                "    pip install -r requirements.txt"
            )
        return anthropic.Anthropic()
    if proveedor == "openai":
        try:
            import openai
        except ImportError:
            sys.exit(
                "Falta el paquete 'openai'. Instala las dependencias con:\n"
                "    pip install -r requirements.txt"
            )
        return openai.OpenAI()
    raise ValueError(f"Proveedor desconocido: {proveedor}")


def extraer_html(respuesta: str) -> str:
    """Extrae el bloque ```html ... ``` de la respuesta del modelo.
    Si no encuentra un bloque de código, asume que la respuesta entera es el HTML."""
    m = re.search(r"```html\s*\n(.*?)```", respuesta, re.DOTALL)
    if m:
        return m.group(1).strip() + "\n"
    m = re.search(r"```\s*\n(.*?)```", respuesta, re.DOTALL)
    if m:
        return m.group(1).strip() + "\n"
    return respuesta.strip() + "\n"


def actualizar_fecha_footer(html: str) -> str:
    """Sustituye el marcador FECHA_HORA (o una fecha previa ya generada) por la fecha/hora actual,
    siguiendo tu convención de mantener 'Última modificación' siempre al día."""
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    if FECHA_MARCADOR in html:
        return html.replace(FECHA_MARCADOR, ahora)
    # Si el modelo ya puso una fecha (o esto es una regeneración), la reemplazamos igualmente
    patron = re.compile(r"(Última modificación:\s*)([^<\n]*)")
    if patron.search(html):
        return patron.sub(lambda m: m.group(1) + ahora, html)
    return html


def _leer_texto(ruta: Path, etiqueta_arg: str) -> str:
    """Lee un fichero de texto en UTF-8 dando un mensaje de error claro (en vez de un
    traceback) si no existe o no se puede decodificar. `etiqueta_arg` identifica el
    argumento de línea de comandos que apunta a ese fichero, para el mensaje de error."""
    try:
        return ruta.read_text(encoding="utf-8")
    except FileNotFoundError:
        sys.exit(f"✗ No se encuentra el fichero indicado en {etiqueta_arg}: {ruta}")
    except UnicodeDecodeError:
        sys.exit(f"✗ No se ha podido leer {ruta} como texto UTF-8 (indicado en {etiqueta_arg}).")
    except OSError as e:
        sys.exit(f"✗ No se ha podido leer {ruta} (indicado en {etiqueta_arg}): {e}")


def construir_peticion_inicial(descripcion: str, base_path: str | None, template_path: Path | None) -> str:
    """Construye el contenido del primer mensaje de usuario, incorporando un HTML de
    partida (--base, modo edición) o una plantilla de estilo (--template / plantilla_base.html),
    si procede. --base tiene prioridad sobre la plantilla."""
    if base_path:
        html_base = _leer_texto(Path(base_path), "--base")
        return (
            f"Este es el HTML existente del que debes partir:\n\n```html\n{html_base}\n```\n\n"
            f"Cambio pedido: {descripcion}"
        )
    if template_path and template_path.exists():
        html_plantilla = _leer_texto(template_path, "--template")
        return (
            "Usa el siguiente HTML como plantilla de estructura y estilo (cabecera, variables de "
            "color, tipografía, layout general y pie de página). Adáptalo y complétalo para "
            "construir la app que se describe a continuación: no hace falta conservar literalmente "
            "cada elemento si no encaja con la app pedida, pero mantén el espíritu visual y el "
            "formato del pie de página tal cual.\n\n"
            f"```html\n{html_plantilla}\n```\n\nApp a construir: {descripcion}"
        )
    return descripcion


def _es_error_transitorio(e: Exception) -> bool:
    """Heurística común a los SDKs de Anthropic y OpenAI para detectar errores que
    merece la pena reintentar: límite de tasa, servidor sobrecargado/caído, o problemas
    de conexión/timeout. No es exacta (se basa en el código de estado HTTP y en el
    nombre de la clase de la excepción), pero en el peor caso solo hace que se reintente
    un error que no lo necesitaba, o que no se reintente uno que sí — nunca oculta el
    fallo final."""
    status = getattr(e, "status_code", None)
    if status in (429, 500, 502, 503, 529):
        return True
    nombre = type(e).__name__
    return any(p in nombre for p in ("RateLimit", "Overloaded", "Connection", "Timeout", "InternalServerError"))


def _responses_create(client, modelo: str, mensajes: list, max_tokens: int, stream: bool):
    """Llama a client.responses.create (OpenAI). Algunos modelos no admiten limitar
    max_output_tokens; si la API lo rechaza por eso, reintenta una vez sin ese límite
    en vez de fallar, avisando por consola."""
    kwargs = dict(model=modelo, instructions=SYSTEM_PROMPT, input=mensajes, max_output_tokens=max_tokens)
    if stream:
        kwargs["stream"] = True
    try:
        return client.responses.create(**kwargs)
    except Exception as e:
        mensaje = str(e).lower()
        rechaza_parametro = "max_output_tokens" in mensaje and (
            "unsupported" in mensaje or "not supported" in mensaje or "unknown parameter" in mensaje
        )
        if not rechaza_parametro:
            raise
        print(
            f"\n[aviso] el modelo '{modelo}' no admite limitar los tokens de salida; "
            "reintentando sin ese límite...",
            file=sys.stderr,
        )
        kwargs.pop("max_output_tokens")
        return client.responses.create(**kwargs)


def llamar_modelo(proveedor: str, client, modelo: str, max_tokens: int, mensajes: list, stream: bool = True) -> str:
    """Envía la conversación al modelo (Anthropic u OpenAI) y devuelve el texto completo de la
    respuesta, mostrándolo en pantalla a medida que llega si stream=True.

    `mensajes` es una lista de dicts {"role": "user"|"assistant", "content": "texto"}; el mismo
    formato sirve para ambas plataformas, así que el resto del script no necesita saber cuál
    está usando."""
    if proveedor == "anthropic":
        if stream:
            texto_completo = []
            with client.messages.stream(
                model=modelo,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=mensajes,
            ) as s:
                for texto in s.text_stream:
                    print(texto, end="", flush=True)
                    texto_completo.append(texto)
            print()
            return "".join(texto_completo)
        respuesta = client.messages.create(
            model=modelo,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=mensajes,
        )
        return "".join(b.text for b in respuesta.content if b.type == "text")

    if proveedor == "openai":
        if stream:
            texto_completo = []
            eventos = _responses_create(client, modelo, mensajes, max_tokens, stream=True)
            for evento in eventos:
                if evento.type == "response.output_text.delta":
                    print(evento.delta, end="", flush=True)
                    texto_completo.append(evento.delta)
                elif evento.type == "error":
                    print(f"\n[error] {evento.message}", file=sys.stderr)
            print()
            return "".join(texto_completo)
        respuesta = _responses_create(client, modelo, mensajes, max_tokens, stream=False)
        return respuesta.output_text

    raise ValueError(f"Proveedor desconocido: {proveedor}")


def generar_y_guardar(proveedor, client, modelo, max_tokens, mensajes, salida_path: Path, stream=True, etiqueta=None) -> str:
    """Llama al modelo (con reintentos automáticos ante errores transitorios: límite de
    tasa, servidor sobrecargado, cortes de conexión...), extrae el HTML, actualiza la
    fecha del pie de página, guarda una copia de seguridad del fichero anterior (si
    existía, en <salida>.bak) y guarda el resultado. Devuelve el texto crudo de la
    respuesta (para añadirlo al historial de conversación).

    Lanza RuntimeError si la llamada falla de forma no recuperable, para que quien la
    invoque decida qué hacer (abortar del todo, saltar esta variante, o dejar seguir
    el modo chat) en vez de terminar el proceso aquí mismo."""
    intento = 0
    while True:
        intento += 1
        try:
            respuesta = llamar_modelo(proveedor, client, modelo, max_tokens, mensajes, stream=stream)
            break
        except Exception as e:
            if intento <= REINTENTOS_MAX and _es_error_transitorio(e):
                espera = ESPERA_BASE_SEGUNDOS * (2 ** (intento - 1)) + random.uniform(0, 1)
                print(
                    f"\n[aviso] error transitorio llamando a {proveedor} ({e}); "
                    f"reintentando en {espera:.0f}s ({intento}/{REINTENTOS_MAX})...",
                    file=sys.stderr,
                )
                time.sleep(espera)
                continue
            raise RuntimeError(f"Error llamando a la API de {proveedor}: {e}") from e

    if salida_path.exists():
        try:
            copia = salida_path.with_name(salida_path.name + ".bak")
            copia.write_text(salida_path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass  # la copia de seguridad es un extra; no debe bloquear el guardado principal

    html = actualizar_fecha_footer(extraer_html(respuesta))
    salida_path.write_text(html, encoding="utf-8")
    print(f"\n✓ {etiqueta or f'Guardado en {salida_path.resolve()}'}")
    return respuesta


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Genera o modifica apps web de un solo HTML usando la API de Anthropic o de OpenAI."
    )
    parser.add_argument("descripcion", nargs="?", help="Descripción de la app o del cambio pedido")
    parser.add_argument("--prompt-file", help="Fichero de texto con la descripción (para peticiones largas)")
    parser.add_argument("--base", help="Fichero HTML existente del que partir (para pedir modificaciones)")
    parser.add_argument("-o", "--output", help="Fichero .html de salida")
    parser.add_argument("--provider", choices=["anthropic", "openai"], default=PROVEEDOR_POR_DEFECTO,
                         help=f"Plataforma de IA a usar (por defecto: {PROVEEDOR_POR_DEFECTO}; también AI_PROVIDER en .env)")
    parser.add_argument("--model", default=None,
                         help="Modelo a usar (por defecto, el recomendado de la plataforma elegida; ver --list-models)")
    parser.add_argument("--list-models", action="store_true", help="Muestra los modelos disponibles de cada plataforma y termina")
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS_POR_DEFECTO)
    parser.add_argument("--no-stream", action="store_true", help="Desactiva la salida en streaming por consola")
    parser.add_argument("--chat", action="store_true", help="Tras generar, entra en modo conversación para pedir ajustes")
    parser.add_argument("--template", help=f"Plantilla HTML de estilo/estructura a usar como base (por defecto: {PLANTILLA_POR_DEFECTO.name} si existe junto al script)")
    parser.add_argument("--no-template", action="store_true", help="No usar ninguna plantilla por defecto, generar desde cero")
    parser.add_argument("--variantes", type=int, default=1, help="Genera N variantes independientes en vez de un único fichero (no compatible con --chat)")
    args = parser.parse_args()

    if args.list_models:
        mostrar_modelos()
        return

    if args.variantes < 1:
        parser.error("--variantes debe ser un entero igual o mayor que 1")
    if args.max_tokens <= 0:
        parser.error("--max-tokens debe ser mayor que 0")

    # Lanzado sin ningún argumento (p. ej. con el botón ▶ "Run Python File" de VS Code, o F5
    # con una configuración sin args): en vez de exigir que lo relances con flags, entra en un
    # modo totalmente guiado por preguntas en la terminal.
    modo_interactivo = len(sys.argv) == 1 and sys.stdin.isatty()
    if modo_interactivo:
        print("=== Generador de apps — modo interactivo ===")
        print(f"Plataforma: [1] anthropic  [2] openai  (Intro = {args.provider})")
        eleccion = input("> ").strip()
        if eleccion == "1":
            args.provider = "anthropic"
        elif eleccion == "2":
            args.provider = "openai"
        print()

    if not args.output:
        if sys.stdin.isatty():
            args.output = input("Fichero de salida (ej. mi_app.html): ").strip()
        if not args.output:
            parser.error("-o/--output es obligatorio (salvo con --list-models; o indícalo cuando se te pida)")

    if not args.output.lower().endswith((".html", ".htm")):
        print(
            f"[aviso] '{args.output}' no termina en .html; se guardará igualmente con ese nombre.",
            file=sys.stderr,
        )

    if args.variantes > 1 and args.chat:
        sys.exit(
            "No se puede combinar --chat con --variantes > 1.\n"
            "Genera primero las variantes, elige la que más te guste y continúa sobre ella con:\n"
            "    python generar_app.py \"ajustes\" --base <variante_elegida>.html -o <salida>.html --chat"
        )

    clave_entorno = API_KEY_ENV[args.provider]
    if not os.environ.get(clave_entorno):
        sys.exit(
            f"No se encuentra {clave_entorno} en el entorno (necesaria para --provider {args.provider}).\n"
            "Defínela como variable de entorno o en tu fichero .env (ver .env.example)."
        )

    modelo = args.model or MODELO_POR_DEFECTO[args.provider]

    # Construir la descripción inicial
    descripcion = args.descripcion
    if args.prompt_file:
        descripcion = _leer_texto(Path(args.prompt_file), "--prompt-file")
    if not descripcion:
        descripcion = input("Describe la app que quieres generar: ").strip()
    if not descripcion:
        sys.exit("No se ha proporcionado ninguna descripción.")

    template_path = None
    if not args.base:  # --base (modo edición) tiene prioridad sobre cualquier plantilla
        if args.template:
            template_path = Path(args.template)
            if not template_path.exists():
                sys.exit(f"✗ No se encuentra la plantilla indicada en --template: {template_path}")
        elif not args.no_template and PLANTILLA_POR_DEFECTO.exists():
            template_path = PLANTILLA_POR_DEFECTO

    contenido_inicial = construir_peticion_inicial(descripcion, args.base, template_path)
    client = crear_cliente(args.provider)
    salida = Path(args.output)
    stream = not args.no_stream

    # --- Modo variantes: N generaciones independientes, cada una a su fichero ---
    if args.variantes > 1:
        fallidas = []
        for i in range(1, args.variantes + 1):
            enfoque = ENFOQUES_VARIANTES[(i - 1) % len(ENFOQUES_VARIANTES)]
            contenido = contenido_inicial + (
                f"\n\n(Esta es la variante {i} de {args.variantes}. Dale un enfoque de diseño "
                f"propio, distinto de otras variantes posibles: {enfoque}. La funcionalidad pedida "
                f"debe seguir siendo la misma.)"
            )
            mensajes = [{"role": "user", "content": contenido}]
            salida_variante = salida.with_name(f"{salida.stem}_v{i}{salida.suffix}")
            print(f"--- Variante {i}/{args.variantes} ({args.provider}/{modelo}) → {salida_variante} ---")
            try:
                generar_y_guardar(
                    args.provider, client, modelo, args.max_tokens, mensajes, salida_variante, stream=stream,
                    etiqueta=f"Guardado en {salida_variante.resolve()}",
                )
            except RuntimeError as e:
                print(f"✗ Variante {i} ha fallado: {e}", file=sys.stderr)
                fallidas.append(i)
            print()

        generadas = args.variantes - len(fallidas)
        print(f"{generadas}/{args.variantes} variantes generadas.")
        if fallidas:
            print(f"Fallaron las variantes: {', '.join(str(i) for i in fallidas)}")
        if generadas:
            print(
                "Para seguir trabajando sobre una de ellas:\n"
                f"    python generar_app.py \"ajustes\" --base {salida.stem}_v1{salida.suffix} -o {salida} --chat"
            )
        if fallidas and not generadas:
            sys.exit(1)
        return

    # --- Modo normal: una generación, con chat opcional ---
    mensajes = [{"role": "user", "content": contenido_inicial}]

    print(f"Generando '{salida}' con {args.provider}/{modelo}...\n")
    try:
        respuesta = generar_y_guardar(args.provider, client, modelo, args.max_tokens, mensajes, salida, stream=stream)
    except RuntimeError as e:
        sys.exit(f"\n✗ {e}")
    mensajes.append({"role": "assistant", "content": respuesta})

    continuar_chat = args.chat
    if not continuar_chat and sys.stdin.isatty():
        resp = input("\n¿Quieres pedir ajustes sobre esta app ahora mismo? [s/N]: ").strip().lower()
        continuar_chat = resp in {"s", "si", "sí", "y", "yes"}

    if continuar_chat:
        print("\nDescribe cambios y pulsa Enter (escribe 'salir' para terminar).")
        while True:
            try:
                peticion = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not peticion or peticion.lower() in {"salir", "exit", "quit"}:
                break
            mensajes.append({
                "role": "user",
                "content": f"Aplica este cambio y devuelve el HTML completo de nuevo: {peticion}",
            })
            print()
            try:
                respuesta = generar_y_guardar(
                    args.provider, client, modelo, args.max_tokens, mensajes, salida, stream=stream,
                    etiqueta=f"Actualizado {salida.resolve()}",
                )
            except RuntimeError as e:
                print(
                    f"\n✗ {e}\nEl cambio no se ha aplicado; el fichero sigue como estaba. "
                    "Puedes reintentar o pedir otra cosa.",
                    file=sys.stderr,
                )
                mensajes.pop()  # descarta la petición fallida para no contaminar el historial
                continue
            mensajes.append({"role": "assistant", "content": respuesta})


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrumpido por el usuario.", file=sys.stderr)
        sys.exit(130)

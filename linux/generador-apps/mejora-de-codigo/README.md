# Generador de apps — versión mejorada (`mejora-de-codigo`)

Versión mejorada de [`../python-app-api-anthropic/`](../python-app-api-anthropic/). Es el **mismo generador** de apps web de un solo HTML (API de **Anthropic** u **OpenAI**, ejecutable desde VS Code), con el mismo CLI, el mismo prompt de sistema, el mismo pie de página y la misma plantilla, pero **más robusto**: reintentos automáticos, copias de seguridad, errores claros y sesiones que no se pierden.

> Las dos carpetas son independientes: cada una tiene su propio script, plantilla, dependencias y `.vscode/`. Si ya usabas la versión base, esta es un reemplazo directo (`generar_app.py`); los demás ficheros son idénticos.

## Qué mejora respecto a la versión base

| Mejora | Antes (base) | Ahora |
|---|---|---|
| **Reintentos automáticos** | Un 429, un 5xx o un corte de red abortaba el proceso | Reintenta con espera creciente (2 s, 4 s, 8 s, 16 s + jitter) hasta 4 veces |
| **Copia de seguridad** | Sobrescribía el fichero sin dejar rastro | Deja la versión anterior en `<salida>.html.bak` antes de escribir |
| **`--chat` resistente** | Un error en mitad de la sesión mataba el proceso y se perdía el historial | Avisa, descarta esa petición y permite seguir |
| **`--variantes` resistente** | Si fallaba una variante se abortaba todo el lote | Continúa con las demás y resume cuántas salieron bien y cuáles fallaron |
| **Errores de ficheros** | Traceback de Python con `--base` / `--prompt-file` inexistentes | Mensaje claro de una línea (también con ficheros no UTF-8) |
| **Bug de `--template`** | Con una plantilla inexistente generaba la app **sin plantilla y sin avisar** | Se detiene con un mensaje explícito |
| **Validación de argumentos** | `--variantes 0` o `--max-tokens 0` daban comportamientos raros | Error de argumentos claro |
| **Ctrl+C** | Solo limpio dentro del bucle de chat | Limpio en cualquier punto (código de salida 130) |
| **Salida sin `.html`** | Sin aviso | Aviso no bloqueante (típico `-o app` en vez de `-o app.html`) |

El detalle técnico de cada cambio está en [`docs/CAMBIOS.md`](docs/CAMBIOS.md).

## Contenido

| Fichero | Para qué sirve |
|---|---|
| `generar_app.py` | El script generador (versión mejorada) |
| `plantilla_base.html` | Estructura y estilo de partida (cabecera, colores, pie de página) |
| `requirements.txt` | Dependencias: `anthropic`, `openai`, `python-dotenv` |
| `.env.example` | Plantilla del `.env` con las claves y modelos por defecto |
| `.vscode/launch.json` | Configuraciones de F5 para VS Code |
| `.gitignore` | Evita subir `.env`, `.venv/`, copias `.bak` y salidas de prueba |
| `docs/CAMBIOS.md` | Registro detallado de cambios respecto a la versión base |
| `docs/ARQUITECTURA.md` | Cómo está construido el script por dentro |

## Puesta en marcha

Abre **esta carpeta** como raíz en VS Code (*File → Open Folder…*):

```bash
python3 -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # y rellena ANTHROPIC_API_KEY y/o OPENAI_API_KEY
```

### Ejecutarlo desde VS Code sin comandos

- **Botón ▶ «Run Python File»** con `generar_app.py` abierto, o
- **F5** con la configuración **«Generar app (interactivo)»**.

Sin argumentos, el script entra en modo interactivo (plataforma → fichero de salida → descripción → ¿quieres pedir ajustes?). Con argumentos funciona como un CLI normal.

## Uso desde la terminal

```bash
python generar_app.py --list-models
python generar_app.py "App que convierte tallas de ropa" -o tallas.html
python generar_app.py "..." -o app.html --provider openai --model gpt-6-astra
python generar_app.py --prompt-file especificacion.txt -o mi_app.html
python generar_app.py "Añade exportar a PDF" --base genoutfit.html -o genoutfit.html --chat
python generar_app.py "App de checklist" -o checklist.html --variantes 3
```

Todos los parámetros, plantillas (`--template`, `--no-template`), modos (`--chat`, `--base`, `--variantes`) y plataformas funcionan exactamente igual que en la versión base; consulta su [README](../python-app-api-anthropic/README.md) para la descripción completa de cada uno.

## Comportamiento nuevo, en la práctica

**Reintentos.** Si la API devuelve un error transitorio verás, por ejemplo:

```
[aviso] error transitorio llamando a anthropic (...); reintentando en 3s (1/4)...
```

Los errores permanentes (clave inválida, petición mal formada…) **no** se reintentan: se muestran enseguida.

**Copias `.bak`.** Al regenerar sobre un fichero existente (típico en `--chat` o con `--base X -o X`), la versión previa queda en `X.html.bak`. Solo se conserva la última copia. Está en `.gitignore`.

**Variantes parcialmente fallidas.**

```
3/5 variantes generadas.
Fallaron las variantes: 2, 4
```

El código de salida es 1 solo si **todas** fallan.

**Chat tras un error.** Si una petición del chat falla definitivamente, el fichero queda como estaba, la petición se descarta del historial y el prompt `>` vuelve a aparecer.

## Ajustes avanzados

En la cabecera de `generar_app.py`:

| Constante | Valor | Efecto |
|---|---|---|
| `REINTENTOS_MAX` | `4` | Reintentos tras el primer fallo (hasta 5 intentos en total) |
| `ESPERA_BASE_SEGUNDOS` | `2.0` | Espera inicial; se duplica en cada reintento |
| `MAX_TOKENS_POR_DEFECTO` | `20000` | Límite de tokens de salida |
| `AUTOR` | tus datos | Nombre, departamento y email del pie de página |

## Estado de verificación

- Compilación, `--help`, `--list-models`, validaciones del CLI y mensajes de error de ficheros inexistentes.
- Reintentos, copia `.bak`, actualización de fecha y propagación de errores no recuperables, con un cliente simulado.
- **No se han hecho llamadas reales a la API** durante el desarrollo: prueba con tu clave antes de depender de él. La heurística de errores transitorios se basa en el código HTTP y el nombre de la excepción de ambos SDKs.

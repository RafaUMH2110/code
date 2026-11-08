# Generador de apps — versión base (`python-app-api-anthropic`)

Script en Python para **generar o modificar apps web de un solo fichero HTML** (estilo GenOutFit, GenImOd, GenPatMod…) directamente desde VS Code, usando la API de **Anthropic** o la de **OpenAI**, a tu elección.

> Esta es la **versión base**. Existe una versión mejorada, con reintentos automáticos, copias de seguridad y manejo de errores más robusto, en [`../mejora-de-codigo/`](../mejora-de-codigo/). Las dos carpetas son independientes.

## Contenido

| Fichero | Para qué sirve |
|---|---|
| `generar_app.py` | El script generador |
| `plantilla_base.html` | Estructura y estilo de partida (cabecera, colores, pie de página) |
| `requirements.txt` | Dependencias: `anthropic`, `openai`, `python-dotenv` |
| `.env.example` | Plantilla del fichero `.env` con las claves y modelos por defecto |
| `.vscode/launch.json` | Configuraciones de F5 para VS Code |
| `.gitignore` | Evita subir `.env`, `.venv/`, copias `.bak` y salidas de prueba |
| `docs/ARQUITECTURA.md` | Cómo está construido el script por dentro |

## 1. Preparar el entorno en VS Code

Abre **esta carpeta** como raíz en VS Code (*File → Open Folder…*) y, en la terminal integrada:

```bash
python3 -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Si VS Code pregunta por el intérprete de Python, elige el de `.venv` (Ctrl/Cmd+Shift+P → *Python: Select Interpreter*).

### Lanzarlo sin usar la terminal (botón ▶ o F5)

No hace falta escribir ningún comando:

- **Botón ▶ «Run Python File»** (arriba a la derecha, con `generar_app.py` abierto), o
- **F5**, eligiendo la configuración **«Generar app (interactivo)»** (incluida en `.vscode/launch.json`, junto con otra para **«Listar modelos disponibles»**).

Al no recibir parámetros, el script entra en **modo interactivo**: pregunta la plataforma, el nombre del fichero de salida y la descripción de la app, y al final si quieres seguir pidiendo ajustes (equivale a `--chat`). Los ejemplos con `python generar_app.py ...` siguen funcionando igual para quien prefiera la terminal.

## 2. Configurar las claves de API

```bash
cp .env.example .env
```

```
ANTHROPIC_API_KEY=sk-ant-tu-clave-real
OPENAI_API_KEY=sk-proj-tu-clave-real
```

Solo hace falta la clave de la plataforma que vayas a usar. El script la carga solo. **Nunca subas el `.env` real al repositorio** (ya está en `.gitignore`).

## 3. Elegir plataforma y modelo

Por defecto se usa Anthropic. Para ver los modelos disponibles:

```bash
python generar_app.py --list-models
```

```
anthropic  (clave: ANTHROPIC_API_KEY)
  claude-opus-5-5    El más capaz; trabajo agéntico y de conocimiento largo/complejo
  claude-sonnet-5-5  Mejor equilibrio velocidad/inteligencia de la familia 5.5
  claude-sonnet-5    Eficiente para uso cotidiano, anterior a la familia 5.5  ←  por defecto
  claude-haiku-5-5   El más rápido y económico, para tareas de alto volumen
  claude-fable-5-1   Razonamiento exigente y tareas agénticas de largo recorrido

openai  (clave: OPENAI_API_KEY)
  gpt-6-astra        El más capaz de OpenAI, para el trabajo más exigente
  gpt-6.1-sol        Rendimiento cercano a Astra, más económico
  gpt-6-sol          Pensado específicamente para código y flujos de trabajo agénticos
  gpt-6-luna         El más rápido y económico, para tareas de alto volumen  ←  por defecto
```

```bash
python generar_app.py "..." -o app.html --provider openai
python generar_app.py "..." -o app.html --provider openai --model gpt-6-astra
```

Para fijar plataforma y modelo por defecto, usa `AI_PROVIDER`, `ANTHROPIC_MODEL` y `OPENAI_MODEL` en `.env`. Con `--model` puedes pasar cualquier id aunque no esté en la lista (por ejemplo, un modelo recién publicado).

## 4. Generar una app nueva

```bash
python generar_app.py "App que convierte tallas de ropa entre sistemas europeo, UK y US" -o conversor_tallas.html
```

Para descripciones largas, mejor en un fichero de texto:

```bash
python generar_app.py --prompt-file especificacion.txt -o mi_app.html
```

## 5. Modo chat (iterar sobre la misma app)

```bash
python generar_app.py "App de checklist para revisión de patrones" -o checklist.html --chat
```

```
> añade un botón para exportar la lista a PDF
> cambia la paleta a tonos verdes
> salir
```

Cada cambio reescribe el mismo fichero.

## 6. Partir de una app existente

```bash
python generar_app.py "Añade selector de complementos" --base genoutfit.html -o genoutfit.html --chat
```

`--base` tiene prioridad: si lo usas, se ignora cualquier plantilla.

## 7. Plantilla base

El script usa automáticamente `plantilla_base.html` en toda generación nueva (sin `--base`):

```bash
python generar_app.py "..." -o app.html                              # plantilla por defecto
python generar_app.py "..." -o app.html --template otra.html         # otra plantilla
python generar_app.py "..." -o app.html --no-template                # desde cero
```

Si editas `plantilla_base.html`, todo lo que generes después hereda el cambio.

## 8. Varias variantes a la vez

```bash
python generar_app.py "App de checklist para revisión de patrones" -o checklist.html --variantes 3
```

Genera `checklist_v1.html`, `checklist_v2.html`, `checklist_v3.html`, cada una con un enfoque de diseño distinto. No es compatible con `--chat`: elige una variante y sigue sobre ella con `--base`.

## Convenciones que aplica automáticamente

- Un único `.html` autocontenido (CSS y JS inline), en español y responsive.
- Si la app usa una API de IA, pide la clave en un campo de la interfaz (nunca hardcodeada).
- Pie de página con nombre, departamento, email y la leyenda «Generado con IA · Revisado por el autor».
- **«Última modificación» se actualiza siempre** a la fecha/hora real al generar o regenerar el fichero.

Tus datos de autor están en el diccionario `AUTOR` al principio de `generar_app.py` (y en el pie de `plantilla_base.html`).

## Parámetros

| Parámetro | Qué hace |
|---|---|
| `-o, --output` | Fichero HTML de salida (obligatorio salvo con `--list-models` o en modo interactivo) |
| `--provider` | `anthropic` u `openai` (por defecto `anthropic`, o `AI_PROVIDER` en `.env`) |
| `--model` | Modelo a usar (por defecto el recomendado de la plataforma; ver `--list-models`) |
| `--list-models` | Muestra los modelos de cada plataforma y termina |
| `--base` | HTML existente del que partir (edición; ignora la plantilla) |
| `--template` | Plantilla de estilo a usar en vez de `plantilla_base.html` |
| `--no-template` | Genera desde cero, sin plantilla |
| `--variantes N` | Genera N variantes independientes |
| `--prompt-file` | Lee la descripción desde un fichero de texto |
| `--max-tokens` | Límite de tokens de salida (por defecto 20000; en OpenAI incluye el razonamiento interno). Si el modelo de OpenAI no admite el límite, el script reintenta solo sin él |
| `--chat` | Entra en modo conversación tras la primera generación |
| `--no-stream` | No muestra el texto en vivo mientras se genera |

## Limitaciones de esta versión

Estas son las diferencias que corrige la versión [`mejora-de-codigo`](../mejora-de-codigo/):

- Un error de la API (límite de tasa, 5xx, corte de red) **termina el proceso** en el primer fallo.
- En `--chat`, un error en mitad de la sesión pierde el historial de la conversación.
- En `--variantes`, si una variante falla se aborta todo el lote.
- Al sobrescribir un fichero no se guarda copia de seguridad.
- `--template` con una ruta inexistente genera la app **sin plantilla y sin avisar**.
- Rutas inexistentes en `--base` / `--prompt-file` producen un traceback de Python.
- No se validan `--variantes ≤ 0` ni `--max-tokens ≤ 0`.

## Estado de verificación

El script se ha comprobado sintácticamente, con `--help`, `--list-models`, los errores de validación del CLI, las funciones auxiliares con clientes simulados y el flujo interactivo en una terminal simulada. **No se han realizado llamadas reales a la API** durante el desarrollo; pruébalo con tu clave antes de usarlo en producción.

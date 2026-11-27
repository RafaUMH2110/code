# Generador de apps — versión optimizada para VS Code (`optimizada-vscode`)

Reescritura de [`../mejora-de-codigo/`](../mejora-de-codigo/). Es el **mismo
generador** de apps web de un solo HTML (API de **Anthropic** u **OpenAI**), con
el mismo CLI, el mismo prompt de sistema y el mismo pie de página, pero con el
código reorganizado en clases y, sobre todo, **pensado para trabajar dentro de
VS Code**: previsualización en vivo, tareas con desplegables nativos, historial
de versiones y conversaciones que se retoman.

> Las tres carpetas de `generador-apps/` son independientes. Si venías de
> `mejora-de-codigo`, esta es un reemplazo directo: todos sus parámetros siguen
> funcionando con el mismo nombre.

El detalle técnico de cada cambio está en [`docs/CAMBIOS.md`](docs/CAMBIOS.md) y
la organización interna en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

## Qué mejora respecto a `mejora-de-codigo`

| Mejora | Antes | Ahora |
|---|---|---|
| **Previsualización en vivo** | Abrir el fichero a mano tras cada cambio | `--serve` abre el navegador y lo recarga solo en cada vuelta del chat |
| **Respuestas truncadas** | Guardaba el HTML cortado como si fuera válido | Lo detecta y reintenta con el doble de límite |
| **Historial** | Un único `.bak`, perdido en la vuelta siguiente | Copia con fecha de cada versión + `/deshacer` |
| **Conversaciones** | Se perdían al cerrar el terminal | Autoguardadas; `--resume` las retoma con todo el contexto |
| **Tareas de VS Code** | No había | 4 tareas con cuadros de diálogo nativos; una usa el fichero abierto |
| **Puesta en marcha** | Copiar ficheros a mano | `--init` crea `.vscode/`, `.env.example`, config y plantilla |
| **Menú al pulsar ▶** | Tres preguntas, solo para crear | Menú de 7 opciones, con autocompletado de rutas |
| **Lista de modelos** | Solo la escrita en el script (se queda obsoleta) | `--list-models --remote` consulta los modelos reales de tu cuenta |
| **Validación del HTML** | No había | DOCTYPE, etiquetas sin cerrar, viewport y **aviso si hay una clave de API en el código** |
| **Pie de página** | Solo actualizaba la fecha | Lo inserta si el modelo se lo olvida |
| **Diff** | Comparar a ojo | Muestra qué líneas han cambiado |
| **Configuración** | Editar el script | `generar_app.config.json` (autoría, modelos, puerto, precios) |
| **Tokens y coste** | No se informaba | Tokens por llamada y total; coste estimado si configuras precios |
| **Caché de prompts** | No se usaba | Caché de Anthropic en modo chat, que abarata las iteraciones largas |
| **Variantes** | N ficheros que abrir uno a uno | Galería que las muestra lado a lado |
| **Errores** | Heurística por código/clase | Además, explicados en una línea con qué hacer |
| **Escritura** | Directa | Atómica (temporal + rename) |

## Inicio rápido

```bash
cd generador-apps/optimizada-vscode
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # rellena ANTHROPIC_API_KEY y/o OPENAI_API_KEY
python generar_app.py                                # menú interactivo (o ▶ / F5 en VS Code)
```

Abre **esta carpeta** como raíz en VS Code (*File → Open Folder…*) para que se
detecten `.vscode/` y la plantilla.

En una carpeta nueva fuera del repositorio, `python generar_app.py --init` crea
todos los ficheros de apoyo de una vez.

## Contenido

| Fichero | Para qué sirve |
|---|---|
| `generar_app.py` | El script generador |
| `plantilla_base.html` | Estructura y estilo de partida, con modo oscuro |
| `generar_app.config.json` | Configuración: autoría, modelos por defecto, puerto, precios |
| `requirements.txt` | Dependencias: `anthropic`, `openai`, `python-dotenv` |
| `.env.example` | Plantilla del `.env` con las claves y modelos por defecto |
| `.vscode/launch.json` | Cuatro configuraciones de F5 |
| `.vscode/tasks.json` | Cuatro tareas con desplegables nativos |
| `.vscode/settings.json` | Intérprete del `.venv` y exclusiones |
| `.vscode/extensions.json` | Extensiones recomendadas |
| `docs/CAMBIOS.md` | Qué cambia respecto a `mejora-de-codigo` y por qué |
| `docs/ARQUITECTURA.md` | Organización interna y decisiones de diseño |

## Las tres formas de usarlo desde VS Code

### 1. Botón ▶ o F5 — menú interactivo

Sin argumentos entra en un menú que lo pregunta todo por consola:

```
¿Qué quieres hacer?
  [1] Crear una app nueva
  [2] Modificar una app que ya tengo
  [3] Generar varias variantes de una misma idea
  [4] Retomar una conversación anterior
  [5] Ver los modelos disponibles
  [6] Preparar esta carpeta para VS Code
  [7] Salir
```

Los prompts de ficheros admiten tabulador para autocompletar rutas. F5 ofrece
además *generar + previsualización*, *retomar la última conversación* y
*listar modelos*.

### 2. Terminal → Run Task

- **Nueva app** — pide descripción, fichero y plataforma en cuadros de diálogo de
  VS Code, y arranca con previsualización y chat.
- **Modificar la app abierta en el editor** — usa `${file}`, así que trabaja
  sobre el fichero abierto sin escribir rutas.
- **Generar 3 variantes de diseño**
- **Listar modelos disponibles** / **Instalar dependencias**

### 3. Línea de comandos

```bash
# App nueva (parte de plantilla_base.html)
python generar_app.py "Conversor de tallas EU/UK/US" -o tallas.html

# Con previsualización que se recarga sola y modo chat
python generar_app.py "..." -o app.html --serve --chat

# Modificar una app existente
python generar_app.py "Añade exportar a PDF" --base genoutfit.html -o genoutfit.html --chat

# Variantes + galería comparativa
python generar_app.py "App de checklist de patrones" -o checklist.html --variantes 3

# Retomar la última conversación
python generar_app.py --resume
```

## Comandos del modo chat

Lo que no empiece por `/` se envía como petición de cambio.

| Comando | Qué hace |
|---|---|
| `/abrir` | Abre el fichero generado en el navegador |
| `/preview` | Arranca el servidor local con recarga automática |
| `/deshacer` | Recupera la versión anterior del fichero |
| `/historial` | Lista las copias guardadas de este fichero |
| `/modelo` | Cambia de modelo o plataforma sin perder la conversación |
| `/validar` | Vuelve a comprobar el HTML actual |
| `/guardar [nombre]` | Guarda la conversación con un nombre |
| `/gasto` | Tokens consumidos en la sesión |
| `/ayuda` | Muestra la ayuda |
| `/salir` | Termina (también Ctrl+D) |

## Parámetros

**Entrada**

| Parámetro | Qué hace |
|---|---|
| `descripcion` | Descripción de la app, o del cambio si usas `--base` |
| `--prompt-file F` | Lee la descripción de un fichero (peticiones largas) |
| `--base HTML` | HTML existente del que partir (modo edición) |
| `--template HTML` | Plantilla de estilo en vez de `plantilla_base.html` |
| `--no-template` | Generar desde cero, sin plantilla |

**Salida**

| Parámetro | Qué hace |
|---|---|
| `-o, --output HTML` | Fichero de salida (se le añade `.html` si no tiene extensión) |
| `--variantes N` | N variantes de diseño + galería comparativa |
| `--serve` | Previsualización local con recarga automática |
| `--open` | Abre el fichero en el navegador (sin servidor) |

**Modelo**

| Parámetro | Qué hace |
|---|---|
| `--provider` | `anthropic` u `openai` |
| `--model ID` | Modelo concreto (acepta cualquier id, esté o no en la lista) |
| `--max-tokens N` | Límite de tokens de salida (se amplía solo si la respuesta sale truncada) |
| `--no-stream` | No mostrar el texto en vivo mientras se genera |

**Conversación**

| Parámetro | Qué hace |
|---|---|
| `--chat` | Entra en modo chat tras generar |
| `--no-chat` | No preguntar por el modo chat (útil en scripts) |
| `--resume [N]` | Retoma una conversación guardada (sin nombre, la última) |

**Otros**

| Parámetro | Qué hace |
|---|---|
| `--list-models` | Lista los modelos (`--remote` consulta tu cuenta real) |
| `--list-sessions` | Lista las conversaciones guardadas |
| `--init` | Prepara la carpeta para VS Code (`--force` sobrescribe) |
| `--dry-run` | Muestra la petición sin llamar a la API |
| `--no-color` | Salida sin colores |

## Configuración (`generar_app.config.json`)

Orden de precedencia: valores por defecto → este fichero → variables de `.env` →
argumentos de la línea de comandos.

```json
{
  "proveedor": "anthropic",
  "modelos_defecto": {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-6-luna"
  },
  "max_tokens": 24000,
  "autor": {
    "nombre": "Rafael Puerto",
    "departamento": "Departamento de Ingeniería de Sistemas y Automática, UMH",
    "email": "r.puerto@umh.es"
  },
  "puerto_preview": 8000,
  "precios": {
    "claude-sonnet-5": { "entrada": 3.0, "salida": 15.0, "cache_lectura": 0.3 }
  }
}
```

`autor` alimenta tanto el prompt del sistema como el pie que inserta el script,
así que basta cambiarlo aquí.

`precios` es opcional (coste en USD por millón de tokens, según la tarifa de cada
plataforma). Si lo dejas vacío solo se muestran los tokens: **el script no
estima costes con precios que no le hayas dado**.

## Datos locales (`.generar_app/`)

| Ruta | Contenido |
|---|---|
| `historial/` | Copia de cada versión anterior; la usa `/deshacer` |
| `sesiones/` | Conversaciones guardadas; las usa `--resume` |

Se puede borrar en cualquier momento; se vuelve a crear solo. Excluido por
`.gitignore`.

## Notas

- La previsualización inyecta el script de recarga **al servir la página**, no en
  el fichero: lo que se guarda en disco es HTML limpio, listo para subir al
  servidor o a GitHub Pages.
- Los catálogos de modelos cambian cada pocos meses (entre octubre y noviembre de
  2026 cambió el de OpenAI por completo). La lista del script es solo una ayuda:
  usa `--list-models --remote` para ver la real de tu cuenta.
- Nunca subas el `.env` real: está excluido por `.gitignore`.

## Estado de verificación

- Post-proceso del HTML (extracción, pie de página en sus cuatro casos,
  validación), flujo de generación, reintentos, detección de respuesta truncada,
  historial sin colisiones, sesiones, configuración y coste, CLI completo y menú
  interactivo en un terminal real.
- Servidor de previsualización: contenido, inyección de la recarga, `/__mtime`,
  puerto ocupado, fichero inexistente y cierre — comprobado además que el fichero
  del disco queda sin el script inyectado.
- Compatibilidad con los SDKs validada contra sus propios tipos
  (`MessageParam` con `cache_control`, `ResponseInputParam`, y los campos de
  `Usage`, `ResponseUsage` e `InputTokensDetails`).
- **No se han hecho llamadas reales a la API** durante el desarrollo: pruébalo
  con tu clave antes de depender de él.

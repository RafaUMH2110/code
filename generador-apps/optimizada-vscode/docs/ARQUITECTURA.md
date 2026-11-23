# Arquitectura de `generar_app.py` (versión optimizada para VS Code)

Un único fichero, organizado en secciones. A diferencia de las versiones
anteriores, la diferencia entre plataformas está encapsulada en una jerarquía de
clases, de forma que el resto del programa no sabe con cuál está hablando.

El estado que sobrevive entre ejecuciones (historial y conversaciones) vive en
`.generar_app/`, fuera del código.

## Flujo

```
main()
  │  carga .env → Config.cargar() → argparse
  ├──► --init / --list-models / --list-sessions         (salidas inmediatas)
  ├──► sin argumentos y con terminal → menu_interactivo()
  ▼
ejecutar()
  │  resuelve: sesión (--resume) · plataforma y clave · modelo · descripción
  │            fichero de salida · base/plantilla · validaciones cruzadas
  ▼
construir_peticion()        --base (edición) │ plantilla │ texto plano
  ▼
Entorno(cfg, proveedor, modelo, max_tokens, stream, contador)
  │
  ├──► --variantes N ──► generar_variantes() ──► crear_galeria()
  │
  ▼
generar_fichero()
  │
  ├─► generar_con_reintentos()
  │     │  reintentos ante errores transitorios (espera 1, 2, 4 s)
  │     │  si truncado: reintenta una vez con el doble de tokens
  │     ▼
  │   Proveedor.generar()
  │     ├─ ProveedorAnthropic → messages.stream() / messages.create()
  │     │                       bloques con cache_control
  │     └─ ProveedorOpenAI    → responses.create(stream=…)
  │                             tolera modelos sin max_output_tokens
  │     ▼
  │   Resultado(texto, tokens, truncado)
  │
  ├─► extraer_html() → normalizar_footer() → validar_html()
  ├─► guardar_copia()      (.generar_app/historial/)
  ├─► escribir_atomico()   (temporal + rename)
  └─► informar_uso() + mostrar_diff()
  ▼
ServidorPreview (--serve)   hilo aparte; inyecta la recarga al servir
  ▼
bucle_chat()                comandos / + peticiones de cambio
  │  autoguarda la conversación en .generar_app/sesiones/ cada vuelta
  ▼
resumen_gasto()
```

## Secciones del fichero

| Sección | Contenido |
|---|---|
| Constantes y configuración | Rutas, límites, `MODELOS_CURADOS`, `ENFOQUES_VARIANTES`, `Config` |
| Salida por consola | `C` (códigos ANSI), `ok/aviso/error/gris`, `preguntar*`, `elegir`, `Spinner` |
| Prompt del sistema | `construir_system_prompt(autor)` |
| Proveedores de IA | `Resultado`, `ErrorProveedor`, `Proveedor` y sus dos implementaciones |
| Reintentos | `_es_transitorio`, `_explicar`, `generar_con_reintentos` |
| Post-proceso del HTML | `extraer_html`, `normalizar_footer`, `footer_html`, `validar_html` |
| Historial y escritura | `guardar_copia`, `copias_de`, `escribir_atomico`, `mostrar_diff` |
| Tokens y coste | `Contador`, `informar_uso` |
| Previsualización | `SCRIPT_RECARGA`, `ServidorPreview` |
| Sesiones | `ruta_sesion`, `guardar_sesion`, `listar_sesiones`, `cargar_sesion` |
| Generación | `Entorno`, `construir_peticion`, `generar_fichero` |
| Variantes | `generar_variantes`, `crear_galeria` |
| Modo chat | `AYUDA_CHAT`, `bucle_chat`, `resumen_gasto` |
| `--init` | Plantillas de `.vscode/`, `.env.example`, `.gitignore`, config y HTML |
| Menú interactivo | `pedir_descripcion`, `pedir_fichero*`, `elegir_plataforma_y_modelo`, `menu_interactivo` |
| Listado de modelos | `mostrar_modelos` |
| Ejecución | `ejecutar`, `construir_parser`, `main` |

## Clases principales

| Clase | Responsabilidad |
|---|---|
| `Config` | Configuración efectiva: defectos → `generar_app.config.json` → `.env` → argumentos |
| `Proveedor` | Interfaz común: `generar()` y `listar_modelos()`; importa su SDK con un error legible si falta |
| `ProveedorAnthropic` | Messages API; convierte los mensajes a bloques y marca el punto cacheable |
| `ProveedorOpenAI` | Responses API; filtra el catálogo de modelos a los de texto |
| `Resultado` | Texto + tokens (entrada, salida, caché) + `truncado`, igual para ambas plataformas |
| `Entorno` | Agrupa configuración, proveedor, modelo, límites y contador |
| `Contador` | Acumula el gasto de la sesión y calcula el coste si hay precios |
| `ServidorPreview` | Servidor local con recarga automática, en un hilo |
| `ErrorProveedor` | Error de API ya traducido a lenguaje llano |

## Decisiones de diseño

**Un solo fichero.** Mantiene la herramienta fácil de copiar a cualquier carpeta;
el precio es un fichero largo, que se compensa con las secciones y el tipado.

**Sin dependencias nuevas.** Solo `anthropic`, `openai` y `python-dotenv`. El
servidor de previsualización usa `http.server`, el diff `difflib`, el
autocompletado `readline` y los colores códigos ANSI directos, todo de la
biblioteca estándar. `readline` no existe en Windows sin `pyreadline3`: su
importación falla de forma controlada y el programa sigue sin autocompletado.

**Mensajes como `list[dict[str, str]]`.** El formato interno es el mismo para las
dos plataformas; cada proveedor hace su conversión dentro de `generar()`. Así
`generar_fichero()`, el chat y las sesiones no dependen de la plataforma, y una
conversación guardada con una se puede retomar con la otra.

**La recarga se inyecta al servir, no en el fichero.** Es la decisión que permite
tener previsualización en vivo sin contaminar el HTML que se publica.

**No se inventan precios.** Las tarifas cambian y codificarlas daría cifras
falsas; se muestran siempre los tokens y el coste solo si el usuario rellena
`precios` en la configuración.

**La lista de modelos es una ayuda, no una restricción.** `--model` acepta
cualquier identificador, y `--list-models --remote` consulta la lista real de la
cuenta, porque los catálogos cambian cada pocos meses.

**Los errores de autenticación no se reintentan.** `_es_transitorio()` los excluye
explícitamente: reintentar cuatro veces una clave mal escrita solo retrasa el
mensaje útil.

## Ficheros que genera `--init`

| Fichero | Para qué |
|---|---|
| `.vscode/launch.json` | Cuatro configuraciones de F5 (menú, previsualización, retomar, modelos) |
| `.vscode/tasks.json` | Cuatro tareas con desplegables nativos; una usa `${file}` |
| `.vscode/settings.json` | Intérprete del `.venv` y exclusiones |
| `.vscode/extensions.json` | Recomienda `ms-python.python` y `ms-python.debugpy` |
| `.env.example` | Claves y modelos por defecto |
| `.gitignore` | `.env`, `.venv/`, `.generar_app/`, cachés |
| `requirements.txt` | Las tres dependencias |
| `generar_app.config.json` | Configuración por defecto, con `precios` vacío |
| `plantilla_base.html` | Estructura y estilo de partida, con modo oscuro |

## Datos locales (`.generar_app/`)

| Ruta | Contenido |
|---|---|
| `historial/<nombre>_<fecha>.html` | Copia previa a cada sobrescritura; la usa `/deshacer` |
| `sesiones/<nombre>.json` | Conversación completa; la usa `--resume` |

Se puede borrar en cualquier momento: se vuelve a crear solo. Está excluido por
`.gitignore`.

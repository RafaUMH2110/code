# Arquitectura de `generar_app.py` (versión base)

Un único fichero sin estado persistente. El flujo es siempre el mismo, con independencia de la plataforma.

```
CLI / modo interactivo
        │
        ▼
 construir_peticion_inicial()   ← --base (edición)  |  plantilla (--template / plantilla_base.html)  |  texto plano
        │
        ▼
 crear_cliente()  ──►  anthropic.Anthropic()  |  openai.OpenAI()
        │
        ▼
 generar_y_guardar()  ──►  llamar_modelo()  ──►  Messages API (Anthropic)
        │                        │               Responses API (OpenAI, vía _responses_create)
        │                        ▼
        │                texto de la respuesta
        ▼
 extraer_html() → actualizar_fecha_footer() → escribir fichero
```

## Funciones

| Función | Responsabilidad |
|---|---|
| `mostrar_modelos()` | Imprime `MODELOS` y marca el modelo por defecto (`--list-models`) |
| `crear_cliente(proveedor)` | Importa el SDK correspondiente y crea el cliente; mensaje claro si falta el paquete |
| `extraer_html(respuesta)` | Extrae el bloque ```` ```html ```` (o cualquier bloque de código; si no hay, toda la respuesta) |
| `actualizar_fecha_footer(html)` | Sustituye `FECHA_HORA` o una fecha previa de «Última modificación» por la actual |
| `construir_peticion_inicial(...)` | Compone el primer mensaje de usuario (base > plantilla > texto) |
| `_responses_create(...)` | Llamada a OpenAI Responses; si el modelo rechaza `max_output_tokens`, reintenta una vez sin él |
| `llamar_modelo(...)` | Llamada a la plataforma elegida, con o sin streaming; mismo formato de mensajes para ambas |
| `generar_y_guardar(...)` | Llama al modelo, extrae el HTML, actualiza la fecha y guarda; ante un error de la API muestra el mensaje y termina el proceso |
| `main()` | CLI, modo interactivo, variantes, generación simple y chat |

## Decisiones de diseño

- **Un solo formato de mensajes** (`{"role", "content"}`) para ambas plataformas.
- **Prompt de sistema con `FECHA_HORA` como marcador**: la fecha de «Última modificación» la inserta el script, no el modelo.
- **Plantilla como contexto, no como molde rígido**: se envía en el primer mensaje para que el modelo mantenga estilo y pie de página.
- **Lista de modelos curada a mano** (`MODELOS`): `--model` acepta cualquier id.
- **Fallback de `max_output_tokens`** detectado en ejecución, sin listas de modelos compatibles.
- **Gestión de errores deliberadamente simple**: un fallo de la API termina el proceso con un mensaje de una línea. La versión [`mejora-de-codigo`](../../mejora-de-codigo/) sustituye esto por reintentos y errores recuperables.

## Cómo extenderlo

- **Nuevo modelo:** añade una tupla a `MODELOS[proveedor]` (opcional; `--model` ya lo acepta).
- **Nuevo proveedor:** añade entradas en `MODELOS`, `MODELO_POR_DEFECTO`, `API_KEY_ENV`, un caso en `crear_cliente()` y otro en `llamar_modelo()`; añade el nombre a `choices` de `--provider`.
- **Otro estilo base:** edita `plantilla_base.html` o pasa `--template`.
- **Otro autor:** edita el diccionario `AUTOR` y el pie de `plantilla_base.html`.

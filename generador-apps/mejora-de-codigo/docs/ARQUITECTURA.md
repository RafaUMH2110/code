# Arquitectura de `generar_app.py` (versión mejorada)

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
 generar_y_guardar()  ── reintentos ──►  llamar_modelo()  ──►  Messages API (Anthropic)
        │                                      │              Responses API (OpenAI, vía _responses_create)
        │                                      ▼
        │                              texto de la respuesta
        ▼
 .bak del fichero previo → extraer_html() → actualizar_fecha_footer() → escribir fichero
```

## Funciones

| Función | Responsabilidad |
|---|---|
| `mostrar_modelos()` | Imprime `MODELOS` y marca el modelo por defecto (`--list-models`) |
| `crear_cliente(proveedor)` | Importa el SDK correspondiente y crea el cliente; mensaje claro si falta el paquete |
| `extraer_html(respuesta)` | Extrae el bloque ```` ```html ```` (o cualquier bloque de código; si no hay, toda la respuesta) |
| `actualizar_fecha_footer(html)` | Sustituye `FECHA_HORA` o una fecha previa de «Última modificación» por la actual |
| `_leer_texto(ruta, etiqueta_arg)` | Lectura UTF-8 con errores legibles |
| `construir_peticion_inicial(...)` | Compone el primer mensaje de usuario (base > plantilla > texto) |
| `_es_error_transitorio(e)` | Decide si un error merece reintento |
| `_responses_create(...)` | Llamada a OpenAI Responses; si el modelo rechaza `max_output_tokens`, reintenta una vez sin él |
| `llamar_modelo(...)` | Llamada a la plataforma elegida, con o sin streaming; mismo formato de mensajes para ambas |
| `generar_y_guardar(...)` | Reintentos, copia `.bak`, extracción, fecha y guardado; lanza `RuntimeError` si el fallo no es recuperable |
| `main()` | CLI, validaciones, modo interactivo, variantes, generación simple y chat |

## Decisiones de diseño

- **Un solo formato de mensajes** (`{"role", "content"}`) para ambas plataformas: el resto del script no sabe qué proveedor usa.
- **`generar_y_guardar` lanza excepciones en vez de terminar el proceso**, de modo que cada llamador decida: abortar (generación simple), saltar (variantes) o continuar (chat).
- **Prompt de sistema con `FECHA_HORA` como marcador**: el modelo no calcula la fecha; la inserta el script, así «Última modificación» siempre es real.
- **Plantilla como contexto, no como molde rígido**: se envía el HTML de `plantilla_base.html` en el primer mensaje para que el modelo mantenga estilo y pie de página.
- **Lista de modelos curada a mano** (`MODELOS`): `--model` acepta cualquier id, así que no hace falta actualizar el código para probar un modelo nuevo.
- **Fallback de `max_output_tokens`** detectado en ejecución, en lugar de mantener una lista de modelos compatibles que quedaría obsoleta.

## Cómo extenderlo

- **Nuevo modelo:** añade una tupla a `MODELOS[proveedor]` (opcional; `--model` ya lo acepta).
- **Nuevo proveedor:** añade entradas en `MODELOS`, `MODELO_POR_DEFECTO`, `API_KEY_ENV`, un caso en `crear_cliente()` y otro en `llamar_modelo()`; añade el nombre a `choices` de `--provider`.
- **Otro estilo base:** edita `plantilla_base.html` o pasa `--template`.
- **Otro autor:** edita el diccionario `AUTOR` y el pie de `plantilla_base.html`.

# Cambios respecto a `python-app-api-anthropic`

Solo cambia `generar_app.py`. `plantilla_base.html`, `requirements.txt`, `.env.example` y `.vscode/launch.json` son idénticos a los de la versión base (se han copiado para que la carpeta sea autocontenida; `.gitignore` solo se amplía con lo ya descrito). No se tocan la lógica de generación, el prompt de sistema, el pie de página, la plantilla por defecto ni los parámetros existentes: el CLI se usa igual.

Ordenados de mayor a menor impacto.

## 1. Reintentos automáticos ante errores transitorios

- **Dónde:** `generar_y_guardar()` y la nueva `_es_error_transitorio()`.
- **Qué hace:** si la llamada falla por límite de tasa (429), error de servidor (500, 502, 503, 529), sobrecarga o problemas de conexión/timeout, reintenta con espera `ESPERA_BASE_SEGUNDOS × 2^(n-1)` más un jitter aleatorio de 0–1 s, hasta `REINTENTOS_MAX` veces.
- **Detección:** común a los dos SDKs; mira `status_code` y, si no existe, el nombre de la clase de la excepción (`RateLimit`, `Overloaded`, `Connection`, `Timeout`, `InternalServerError`).
- **Límite conocido:** es una heurística; en el peor caso reintenta algo innecesario o no reintenta algo que sí lo merecía, pero nunca oculta el fallo final.

## 2. Copia de seguridad antes de sobrescribir

- **Dónde:** `generar_y_guardar()`.
- **Qué hace:** si el fichero de salida ya existe, copia su contenido a `<nombre>.html.bak` antes de escribir el nuevo. Si la copia falla (permisos, disco), se ignora: nunca bloquea el guardado principal.

## 3. `--chat` ya no muere si una petición falla

- **Dónde:** bucle de chat en `main()`.
- **Antes:** `generar_y_guardar()` llamaba a `sys.exit(1)`, perdiendo el historial.
- **Ahora:** `generar_y_guardar()` lanza `RuntimeError`; el chat lo captura, avisa de que el fichero sigue como estaba, hace `mensajes.pop()` para no contaminar el historial con la petición fallida y continúa.

## 4. `--variantes N` continúa aunque una falle

- **Dónde:** modo variantes en `main()`.
- **Ahora:** captura el `RuntimeError` de cada variante, sigue con las demás y al final imprime `X/N variantes generadas` y la lista de fallidas. Sale con código 1 solo si no se generó ninguna.

## 5. Mensajes de error claros para ficheros

- **Dónde:** nueva `_leer_texto(ruta, etiqueta_arg)`, usada para `--base`, `--template` y `--prompt-file`.
- **Cubre:** fichero inexistente, no decodificable como UTF-8 y otros `OSError`, indicando qué argumento apuntaba a él.

## 6. Bug silencioso: `--template` inexistente

- **Antes:** `construir_peticion_inicial()` solo usaba la plantilla si `template_path.exists()`; con una ruta mal escrita generaba la app **sin plantilla y sin avisar**.
- **Ahora:** `main()` comprueba la existencia y se detiene con `✗ No se encuentra la plantilla indicada en --template: …`.

## 7. Validaciones que faltaban

- `--variantes < 1` y `--max-tokens <= 0` producen un error de argumentos (`parser.error`) en lugar de un bucle vacío o una petición inválida a la API.

## 8. Ctrl+C limpio en cualquier punto

- **Antes:** solo estaba cubierto dentro del bucle de chat.
- **Ahora:** `if __name__ == "__main__"` envuelve `main()` en `try/except KeyboardInterrupt`, imprime «Interrumpido por el usuario.» y sale con código 130 (convención de shell para SIGINT).

## 9. Aviso si la salida no termina en `.html`

- Aviso por `stderr` (no bloquea) cuando `-o` no acaba en `.html` ni `.htm`.

## Verificación de los cambios

- `py_compile` y comprobación de que no hay funciones duplicadas.
- `--list-models`, `--variantes 0`, `--max-tokens 0`, `--template`/`--base`/`--prompt-file` inexistentes y aviso de extensión.
- Con cliente simulado: dos fallos 429 seguidos y éxito al tercer intento, creación de `.bak` con el contenido previo, sustitución de `FECHA_HORA`, y conversión de un error no transitorio en `RuntimeError`.

# Cambios respecto a `mejora-de-codigo`

`generar_app.py` está **reescrito por completo** (de ~470 a ~2.070 líneas), con el
código reorganizado en secciones y clases en lugar de funciones sueltas con
cadenas de `if proveedor == …`. El CLI anterior sigue funcionando igual: todos los
parámetros de `mejora-de-codigo` se mantienen con el mismo nombre y significado.

Además del script cambian los ficheros de apoyo: `.vscode/` pasa de 2 a 4 ficheros
(se añaden `tasks.json` y `extensions.json`), aparece `generar_app.config.json` y
`plantilla_base.html` incorpora modo oscuro y foco visible.

Ordenados de mayor a menor impacto.

## 1. Previsualización con recarga automática (`--serve`)

- **Dónde:** clase `ServidorPreview`, constante `SCRIPT_RECARGA`.
- **Qué hace:** levanta un `HTTPServer` en un hilo sobre `127.0.0.1`, abre el
  navegador y lo recarga cada vez que cambia el fichero. La página sondea un
  endpoint `/__mtime` cada segundo y llama a `location.reload()` cuando el
  `mtime` cambia. En modo chat el resultado se ve al instante.
- **Decisión importante:** el script de recarga se inyecta **al servir la
  respuesta**, no en el fichero del disco, así que lo que se guarda sigue siendo
  el HTML limpio que se sube al servidor o a GitHub Pages.
- **Robustez:** si el puerto está ocupado prueba los 20 siguientes; si el fichero
  aún no existe sirve un aviso en lugar de romper; `BrokenPipeError` ignorado.

## 2. Respuestas truncadas: se detectan y se reintentan

- **Dónde:** `generar_con_reintentos()`, campo `Resultado.truncado`.
- **Antes:** si el modelo agotaba `max_tokens` a media app, se guardaba un HTML
  cortado como si fuera válido.
- **Ahora:** se detecta (`stop_reason == "max_tokens"` en Anthropic;
  `status == "incomplete"` / `incomplete_details.reason` en OpenAI) y se reintenta
  una vez con el doble de límite, con tope en `MAX_TOKENS_TECHO` (64.000).

## 3. Historial de versiones en lugar de un solo `.bak`

- **Dónde:** `guardar_copia()`, `copias_de()`, comandos `/deshacer` y `/historial`.
- **Antes:** un único `<nombre>.html.bak`, que se perdía en la siguiente vuelta.
- **Ahora:** cada sobrescritura guarda una copia con fecha en
  `.generar_app/historial/`, y `/deshacer` restaura la anterior. Importa sobre
  todo al trabajar con `--base x.html -o x.html` sobre el mismo fichero.
- **Detalle:** dos guardados en el mismo segundo (habitual en chat) no se pisan;
  se añade un sufijo `-1`, `-2`… El listado se ordena por `mtime` real, no por
  nombre, porque con ese sufijo el orden alfabético sería incorrecto.

## 4. Conversaciones persistentes (`--resume`)

- **Dónde:** `guardar_sesion()`, `cargar_sesion()`, `listar_sesiones()`,
  `--resume`, `--list-sessions`, comando `/guardar`.
- **Qué hace:** el modo chat se autoguarda en JSON en `.generar_app/sesiones/`
  después de cada vuelta. Si se cierra VS Code a media sesión, `--resume` la
  retoma con todo el contexto en lugar de empezar de cero.

## 5. Caché de prompts de Anthropic

- **Dónde:** `ProveedorAnthropic._bloques()`.
- **Por qué:** en modo chat la conversación acumula HTML completos que se
  reenvían en cada vuelta, lo que encarece las iteraciones largas.
- **Qué hace:** convierte los mensajes a bloques de contenido y marca el final
  del penúltimo con `cache_control: {"type": "ephemeral"}`, de forma que
  Anthropic reutiliza ese prefijo en las llamadas siguientes. El script informa
  de los tokens leídos de caché en cada llamada.

## 6. Tareas de VS Code con desplegables nativos

- **Dónde:** `TASKS_JSON`, creado por `--init`.
- **Qué hace:** añade `.vscode/tasks.json` con cuatro tareas que piden los datos
  en cuadros de diálogo de VS Code (`promptString`, `pickString`) en lugar de por
  consola. Una de ellas usa `${file}`, así que «Modificar la app abierta en el
  editor» funciona sobre el fichero abierto sin escribir rutas.
- Usa `${command:python.interpreterPath}` para respetar el intérprete del
  entorno virtual seleccionado en VS Code.

## 7. `--init`: prepara la carpeta de una vez

- **Dónde:** `ejecutar_init()`.
- **Qué hace:** crea `.vscode/` (4 ficheros), `.env.example`, `.gitignore`,
  `requirements.txt`, `plantilla_base.html` y `generar_app.config.json`, y
  explica los siguientes pasos. No sobrescribe nada existente salvo con
  `--force`.

## 8. Menú interactivo en lugar de preguntas encadenadas

- **Dónde:** `menu_interactivo()`.
- **Antes:** lanzar sin argumentos preguntaba plataforma, fichero y descripción,
  siempre en el mismo orden, y solo servía para crear una app nueva.
- **Ahora:** menú de siete opciones (crear, modificar, variantes, retomar
  conversación, ver modelos, preparar la carpeta, salir), con el modelo elegido
  de una lista, descripción en varias líneas opcional y autocompletado de rutas
  con el tabulador (`readline`, omitido si no está disponible).

## 9. Lista de modelos consultada a la API (`--list-models --remote`)

- **Dónde:** `Proveedor.listar_modelos()` en las dos implementaciones.
- **Por qué:** la lista escrita en el script se queda obsoleta; entre octubre y
  noviembre de 2026 cambió el catálogo entero de OpenAI.
- **Qué hace:** `--list-models --remote` consulta `client.models.list()` y
  muestra los modelos reales de la cuenta. En OpenAI filtra el catálogo (que
  incluye *embeddings*, audio e imagen) para dejar solo los de texto.

## 10. Validación del HTML generado

- **Dónde:** `validar_html()`.
- **Comprueba:** `<!DOCTYPE>`, etiqueta `<html>`, cierre `</html>` (señal de
  respuesta cortada), `meta viewport`, y `<script>`/`<style>` sin cerrar.
- **Y lo más útil:** avisa si el HTML contiene una clave de API escrita en el
  código (`sk-ant-…`, `sk-proj-…`), que es justo lo que el prompt del sistema
  prohíbe y conviene detectar antes de publicar.

## 11. Pie de página: se inserta si falta

- **Dónde:** `normalizar_footer()`, `footer_html()`.
- **Antes:** `actualizar_fecha_footer()` solo sustituía la fecha; si el modelo se
  olvidaba del pie, el fichero salía sin él y sin aviso.
- **Ahora:** cuatro casos cubiertos — marcador `FECHA_HORA`, fecha previa que se
  refresca, pie existente sin línea de fecha (se le añade) y pie ausente (se
  inserta antes de `</body>`). Informa de lo que ha corregido.

## 12. Diff de los cambios

- **Dónde:** `mostrar_diff()`.
- **Qué hace:** al modificar una app existente, muestra en consola el recuento de
  líneas añadidas/quitadas y las primeras 40 diferencias con color, en lugar de
  dejar al usuario comparar a ojo.

## 13. Fichero de configuración

- **Dónde:** `Config.cargar()`, `generar_app.config.json`.
- **Qué hace:** evita repetir parámetros. Orden de precedencia: valores por
  defecto → `generar_app.config.json` → variables de entorno (`.env`) →
  argumentos de la línea de comandos.
- **Incluye:** `autor` (que alimenta tanto el prompt del sistema como el pie
  insertado, antes codificado en el script), modelos por defecto, `max_tokens`,
  puerto de previsualización y un apartado `precios` opcional.
- Si el JSON está corrupto, avisa y sigue con los valores por defecto.

## 14. Contabilidad de tokens y coste

- **Dónde:** `Contador`, `informar_uso()`, `resumen_gasto()`, comando `/gasto`.
- **Qué hace:** muestra los tokens de entrada, salida y caché de cada llamada y
  el total de la sesión. Si se rellena `precios` con el coste por millón de
  tokens, añade el gasto estimado. Sin precios configurados **no se inventa un
  coste**: solo se muestran los tokens.

## 15. Errores explicados en lugar de volcados

- **Dónde:** `_explicar()`, `_es_transitorio()`, excepción `ErrorProveedor`.
- **Qué hace:** traduce los errores de los SDKs a una línea con qué hacer: clave
  inválida (indicando qué variable revisar), modelo inexistente (sugiriendo
  `--list-models --remote`), saldo o cuota agotados, y límite de peticiones.
- La detección de errores transitorios excluye explícitamente los de
  autenticación, para no reintentar cuatro veces una clave mal escrita.

## 16. Variantes con galería comparativa

- **Dónde:** `crear_galeria()`.
- **Antes:** `--variantes N` dejaba N ficheros que había que abrir uno a uno.
- **Ahora:** genera además `<nombre>_variantes.html`, que las muestra lado a lado
  en iframes en una rejilla responsive. Los enfoques de diseño pasan de 4 a 5.

## 17. Comandos en el modo chat

- **Dónde:** `bucle_chat()`, `AYUDA_CHAT`.
- **Qué hace:** lo que no empieza por `/` se envía como petición de cambio; los
  comandos son `/abrir`, `/preview`, `/deshacer`, `/historial`, `/modelo`
  (cambia de modelo o plataforma sin perder la conversación), `/validar`,
  `/guardar`, `/gasto`, `/ayuda` y `/salir`.

## 18. Escritura atómica

- **Dónde:** `escribir_atomico()`.
- **Qué hace:** escribe en un fichero temporal y lo renombra, de forma que una
  interrupción a media escritura no deja el HTML a medias. Crea el directorio
  padre si `-o` apunta a una subcarpeta.

## 19. `--dry-run`

- Muestra el prompt del sistema y la petición exacta que se enviaría, con el
  destino, el modelo y el límite de tokens, sin gastar una llamada a la API.

## 20. Detalles menores

- **Streaming:** se recoge el mensaje final del stream para leer el uso de
  tokens y el motivo de parada, que antes se perdían.
- **Spinner** durante las llamadas con `--no-stream`, en lugar de una pausa muda.
- **Color** en la salida, desactivable con `--no-color`, con la variable
  `NO_COLOR` o si la salida no es un terminal.
- **Prompt del sistema** ampliado con accesibilidad básica (etiquetas, contraste,
  foco visible), gestión visible de errores en la app generada y `localStorage`
  para la clave solo si el usuario lo marca.
- **`plantilla_base.html`** con `prefers-color-scheme: dark` y `:focus-visible`.
- **Extensión de salida:** si `-o` no tiene extensión se le añade `.html` en
  lugar de avisar.
- **Tipado** en todo el fichero y agrupación de parámetros en `--help` por
  secciones (entrada, salida, modelo, conversación, otros).

## Verificación de los cambios

Sin llamadas reales a la API; con proveedores simulados y, donde aplica,
validando las estructuras contra los tipos de los propios SDKs.

- **Post-proceso:** `extraer_html()` (bloque `html`, bloque genérico y respuesta
  sin bloque), `normalizar_footer()` (los 4 casos), `validar_html()` (HTML
  correcto, cortado, sin viewport, con etiquetas abiertas y con clave de API).
- **Flujo:** generación y contador de tokens; reintento ante un 503 y éxito al
  segundo intento; error de autenticación sin reintentos; respuesta truncada que
  reintenta con el doble de tokens (1.000 → 2.000).
- **Historial:** tres escrituras en el mismo segundo producen copias distintas y
  bien ordenadas; `/deshacer` restaura el contenido correcto; no quedan `.tmp`.
- **Servidor de previsualización:** sirve el contenido, inyecta la recarga antes
  de `</body>`, **el fichero del disco queda sin el script inyectado**,
  `/__mtime` refleja el cambio, HTML sin `</body>`, puerto ocupado (8111 → 8112),
  fichero inexistente y cierre con `parar()`.
- **Sesiones:** guardar, listar, cargar la última y por nombre, nombre
  inexistente; `--resume` reenvía el contexto acumulado (5 mensajes) y la sesión
  crece a 6.
- **Configuración:** lectura de todos los campos, precedencia del entorno sobre
  el fichero, autor propagado al prompt y al pie, coste calculado a mano
  comprobado, ausencia de precios y JSON corrupto.
- **CLI:** `--help`, `--list-models` (curada y por plataforma),
  `--list-sessions`, `--dry-run`, y los errores de `--base`/`--template`
  inexistentes, falta de clave, falta de `-o` y `--chat` con `--variantes`.
- **Menú interactivo** en un terminal real (pty): las opciones 1, 2, 3, 5 y 7,
  incluido el reintento cuando el fichero indicado no existe.
- **Compatibilidad con los SDKs:** los bloques con `cache_control` validan contra
  `anthropic.types.MessageParam`, el input contra
  `openai.types.responses.ResponseInputParam`, y los campos de uso que lee el
  script existen en `Usage`, `ResponseUsage` e `InputTokensDetails`.

Dos fallos propios encontrados en esas pruebas y corregidos: el historial se
pisaba las copias hechas en el mismo segundo, y el menú preguntaba dos veces por
el modo chat.

# App de macOS con Python + pywebview (interfaz HTML)

Detalles de la variante **Notas Rápidas Web**: la interfaz es HTML/CSS/JS y Python es el motor. Complementa a `GUIA_APP_MACOS.md` (empaquetado, firma y notarización son idénticos; aquí solo se explica lo que cambia).

## Ficheros

| Fichero | Función |
|---|---|
| `notas_web.py` | Backend Python: ventana, API para JS, ficheros, configuración, log |
| `ui/index.html` | Interfaz completa en un solo HTML (CSS y JS incluidos) |
| `setup_web.py` | Configuración de py2app |
| `construir_app_web.sh` | Entorno, icono, build y firma ad-hoc |
| `icono.png` | Icono de ejemplo |

## Inicio rápido

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pywebview
python notas_web.py --debug      # --debug activa el inspector (clic derecho > Inspeccionar)

./construir_app_web.sh           # genera dist/Notas Rápidas Web.app
```

---

# 1. Conceptos básicos

## 1.1 Qué es pywebview

Una librería que abre una **ventana nativa con un navegador embebido** y deja que Python y JavaScript se llamen entre sí. En macOS usa **WKWebView** (el motor de Safari) mediante PyObjC; no incluye Chromium, por lo que el bundle es pequeño.

```
┌────────────── Notas Rápidas Web.app ──────────────┐
│  Ventana nativa (Cocoa)                           │
│  ┌─────────────────────────────────────────────┐  │
│  │ WKWebView  →  ui/index.html (HTML+CSS+JS)   │  │
│  └───────────────▲─────────────────────────────┘  │
│                  │  window.pywebview.api.*        │
│  ┌───────────────┴─────────────────────────────┐  │
│  │ Python: clase Api (ficheros, config, red…)  │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

## 1.2 Cuándo elegirlo (y cuándo no)

| Elige pywebview si… | Elige otra opción si… |
|---|---|
| Ya tienes la interfaz en HTML (por ejemplo, apps de un solo fichero) | Necesitas widgets nativos complejos (tablas, árboles, MDI) → PySide6 / wxPython |
| Quieres un diseño moderno sin aprender un toolkit | Quieres cero dependencias → Tkinter |
| Quieres reutilizar el mismo front-end en web y en escritorio | Necesitas Windows/Linux idéntico al píxel (cada SO usa un motor distinto) |
| Necesitas acceso a disco o a APIs desde Python con interfaz web | La app debe funcionar sin JavaScript |

## 1.3 Comparación con la versión Tkinter

| Aspecto | Tkinter | pywebview |
|---|---|---|
| Interfaz | Widgets de Tk | HTML/CSS/JS |
| Modo oscuro | Manual y limitado | `prefers-color-scheme` en CSS (automático) |
| Dependencias | Ninguna (viene con Python) | `pywebview` + PyObjC (se instalan con pip) |
| Atajos | `bind("<Command-s>")` | `keydown` con `e.metaKey` |
| Menú nativo | `tkAboutDialog`, `::tk::mac::Quit`… | Por defecto estándar; menús propios con `webview.menu` |
| Diálogos de fichero | `tkinter.filedialog` | `window.create_file_dialog()` |
| Aspecto | Sobrio | Libre, tan moderno como tu CSS |

## 1.4 La estructura mínima

```python
import webview

class Api:
    def saludar(self, nombre):
        return f"Hola, {nombre}"

ventana = webview.create_window("Mi app", "ui/index.html", js_api=Api())
webview.start()
```

```html
<script>
window.addEventListener("pywebviewready", async () => {
  const r = await window.pywebview.api.saludar("Rafa");
  console.log(r);
});
</script>
```

Puntos esenciales:

1. `webview.start()` bloquea hasta cerrar la ventana (es el bucle de eventos).
2. **`window.pywebview` no existe hasta que se dispara `pywebviewready`.** Cualquier llamada anterior falla con `undefined`.
3. Todas las llamadas JS → Python **devuelven una promesa** (`await`).
4. Argumentos y retornos deben ser serializables a JSON (números, cadenas, listas, diccionarios, `None`).

---

# 2. Conceptos avanzados

## 2.1 El puente Python ↔ JavaScript

**JS → Python:** métodos públicos de la clase pasada en `js_api`.

```python
class Api:
    def abrir(self): ...            # accesible como pywebview.api.abrir()
    def _interno(self): ...         # NO accesible: empieza por guion bajo
```

**Python → JS:** `window.evaluate_js("codigo")` ejecuta JavaScript y devuelve el valor de la última expresión.

```python
sucio = ventana.evaluate_js("window.hayCambios()")
ventana.evaluate_js("actualizar(%s)" % json.dumps(datos))   # json.dumps evita inyección y errores de comillas
```

**Regla crítica:** en `Api`, todo atributo público es inspeccionado por pywebview de forma recursiva. Guardar `self.window = ventana` como público provoca arranques lentos o errores. En el ejemplo se llama `self._window`.

## 2.2 Seguridad

El puente da a la página la capacidad de ejecutar métodos de Python en tu equipo, así que:

- **Carga solo contenido local o de confianza.** Nunca cargues una URL externa con `js_api` habilitada.
- **Define una Content-Security-Policy** (ya incluida en `index.html`) que impida scripts remotos.
- **No expongas métodos genéricos** del tipo `ejecutar(comando)` o `leer(ruta_cualquiera)`. Expón acciones concretas y valida los argumentos en Python.
- **Escapa lo que insertes en el DOM.** Usa `textContent` en lugar de `innerHTML` con datos externos.
- Los diálogos nativos (`create_file_dialog`) son preferibles a aceptar rutas escritas desde JS: el usuario decide qué fichero se toca.

## 2.3 Diálogos y eventos

```python
# Diálogos nativos
ventana.create_file_dialog(webview.FileDialog.OPEN, file_types=("Texto (*.txt;*.md)",))
ventana.create_file_dialog(webview.FileDialog.SAVE, save_filename="nota.txt")
ventana.create_file_dialog(webview.FileDialog.FOLDER)
ventana.create_confirmation_dialog("Título", "¿Seguro?")     # devuelve bool

# Eventos del ciclo de vida
ventana.events.closing += al_cerrar      # devolver False cancela el cierre
ventana.events.closed  += limpiar
ventana.events.loaded  += cargada
ventana.events.resized += lambda w, h: ...
```

Notas de compatibilidad: en pywebview < 5 las constantes son `webview.OPEN_DIALOG` / `SAVE_DIALOG` / `FOLDER_DIALOG`. El ejemplo detecta ambas. El valor devuelto puede ser `None`, una cadena o una tupla; la función `_primera_ruta()` lo normaliza.

## 2.4 Hilos y tareas largas

- Las llamadas de JS a Python se ejecutan **en hilos aparte**, por lo que la ventana no se congela mientras Python trabaja.
- Aun así, una llamada que tarde mucho deja la promesa JS pendiente: muestra un indicador de carga en la interfaz.
- Para progreso en tiempo real, lanza un hilo en Python y empuja actualizaciones con `evaluate_js`:

```python
import threading, json

def procesar(self):
    def trabajo():
        for i in range(1, 101):
            hacer_paso(i)
            self._window.evaluate_js(f"progreso({i})")
        self._window.evaluate_js("terminado()")
    threading.Thread(target=trabajo, daemon=True).start()
    return {"iniciado": True}
```

- Para cálculo intensivo (CPU), usa `multiprocessing` y llama a `multiprocessing.freeze_support()` al inicio de `main()` si empaquetas.

## 2.5 Persistencia

| Qué | Dónde | Observación |
|---|---|---|
| Configuración y datos de la app | `~/Library/Application Support/<App>/` desde **Python** | Es el método del ejemplo; fiable y visible para el usuario |
| Preferencias ligeras en el front-end | `localStorage` | Requiere `webview.start(private_mode=False, storage_path=...)`; si no, se pierde al cerrar |
| Documentos del usuario | Diálogo de guardado | Nunca dentro del `.app` |
| Registros | `~/Library/Logs/<App>/` | Imprescindible: un `.app` no tiene terminal |

## 2.6 Menús nativos, tamaño y apariencia

```python
import webview.menu as wm

menu = [
    wm.Menu("Archivo", [
        wm.MenuAction("Abrir…", api.abrir),
        wm.Separator(),
        wm.MenuAction("Guardar", lambda: ventana.evaluate_js("guardar()")),
    ]),
]
webview.start(menu=menu)
```

Opciones útiles de `create_window`: `min_size`, `resizable`, `frameless` (sin barra de título), `easy_drag`, `on_top`, `confirm_close`, `text_select`, `background_color`. Con `frameless=True` tendrás que dibujar tú los botones de cerrar/minimizar.

**Modo oscuro:** WKWebView respeta el modo del sistema; con `color-scheme: light dark` y `@media (prefers-color-scheme: dark)` el ejemplo cambia solo.

**Comportamiento de «app»:** desactiva la selección de texto fuera de áreas editables (`user-select: none`) y el menú contextual del navegador si no lo necesitas; si no, la ventana se siente a página web.

## 2.7 Servir los ficheros del front-end

- Si pasas una **ruta a un `.html`**, pywebview lo sirve con un servidor HTTP local interno (puerto aleatorio, solo `127.0.0.1`), de modo que las rutas relativas a CSS, JS e imágenes funcionan.
- Si pasas **HTML en una cadena** (`html=...`), no hay ruta base; los recursos relativos no cargan.
- Puedes servir también una app Flask/FastAPI pasando la instancia como `url`.
- Alternativa de un solo fichero: mantener todo en un único HTML, como en tus apps, y usar `resource_path("ui/index.html")`.

## 2.8 Empaquetado con py2app: particularidades

Respecto a la versión Tkinter (ver `setup_web.py`):

- `"resources": ["ui"]` copia la interfaz a `Contents/Resources/ui`; `resource_path()` la localiza con `RESOURCEPATH`.
- `"packages": ["webview", "bottle", "proxy_tools"]` fuerza la inclusión de pywebview y sus dependencias. Si al ejecutar el `.app` aparece `ModuleNotFoundError`, añade ahí el módulo que falte.
- PyObjC (`objc`, `Foundation`, `AppKit`, `WebKit`, `Quartz`) lo detecta py2app automáticamente, pero es el origen más habitual de fallos de empaquetado: si algo falta, añádelo a `"includes"`.
- El bundle resultante es mucho más pequeño que con PySide6 porque usa el WebKit del sistema.
- Prueba primero con `python setup_web.py py2app -A` (alias) para validar `Info.plist` e icono, y después sin `-A`.

> Estado de la verificación: la interfaz se ha probado en un navegador con un puente simulado, y el código Python se ha comprobado sintácticamente. El empaquetado con py2app no se ha podido ejecutar fuera de macOS, así que es posible que haga falta ajustar `packages`/`includes` en tu equipo.

## 2.9 Depuración

| Necesidad | Cómo |
|---|---|
| Ver errores de JS y la consola | `python notas_web.py --debug`, clic derecho → *Inspeccionar elemento* |
| Ver errores de Python en el `.app` | `~/Library/Logs/NotasRapidasWeb/app.log` |
| Ver la salida estándar del bundle | Ejecutar `"dist/Notas Rápidas Web.app/Contents/MacOS/Notas Rápidas Web"` desde Terminal |
| Recargar la interfaz sin reiniciar | `ventana.load_url(...)` o ⌘R en modo debug |
| Probar la UI sin Python | Abrir `ui/index.html` en el navegador con un `window.pywebview` simulado (como en la prueba automática) |

## 2.10 Errores frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `Cannot read properties of undefined (reading 'api')` | Se llamó a la API antes de `pywebviewready` | Esperar el evento antes de usar `pywebview.api` |
| La app tarda en abrir o falla al iniciar | Atributo público con objeto complejo en `Api` | Prefijar con `_` (`self._window`) |
| `evaluate_js` devuelve `None` | La última expresión no devuelve valor, o la página no ha cargado | Esperar a `events.loaded`; terminar el JS con la expresión deseada |
| El título no cambia | `document.title` no actualiza la ventana nativa | Llamar a `ventana.set_title()` (hecho en `poner_titulo`) |
| Cmd+C / Cmd+V no funcionan | Falta menú Edición en ciertas configuraciones o `frameless` | Usar el menú por defecto o añadir un menú Edición propio |
| `localStorage` vacío en cada arranque | Modo privado por defecto | `webview.start(private_mode=False, storage_path=...)` o guardar desde Python |
| Pantalla en blanco en el `.app` | Ruta de `ui/` mal resuelta | Revisar `resources` en `setup_web.py` y `RESOURCEPATH` |
| `alert()`/`confirm()` no se muestran bien | Diálogos del navegador limitados | Usar `create_confirmation_dialog` desde Python para decisiones importantes |

## 2.11 Lista de verificación

- [ ] La UI espera a `pywebviewready` antes de llamar a la API.
- [ ] Atributos internos de `Api` con guion bajo.
- [ ] Solo contenido local con la API habilitada; CSP definida.
- [ ] Todos los datos que viajan entre capas pasan por JSON.
- [ ] Datos de usuario en `Application Support`; log en `Library/Logs`.
- [ ] `resources` y `packages` correctos en `setup_web.py`; probado el `.app` fuera de tu entorno de desarrollo.
- [ ] `CFBundleIdentifier` propio; firmado (y notarizado si se distribuye).

## Referencias

- pywebview: <https://pywebview.flowrl.com>
- API de la ventana, eventos y menús: <https://pywebview.flowrl.com/guide/api.html>
- py2app: <https://py2app.readthedocs.io>
- WKWebView (Apple): <https://developer.apple.com/documentation/webkit/wkwebview>

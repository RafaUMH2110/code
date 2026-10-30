# App de Windows con Python + pywebview (interfaz HTML)

Detalles de la variante **Notas Rápidas Web**: la interfaz es HTML/CSS/JS y Python es el motor. Complementa a `GUIA_APP_WINDOWS.md` (icono, rutas de datos, antivirus, firma e instaladores son idénticos; aquí solo se explica lo que cambia).

## Ficheros

| Fichero | Función |
|---|---|
| `app_web/notas_web.py` | Backend Python: ventana, API para JS, ficheros, configuración, log |
| `app_web/ui/index.html` | Interfaz completa en un solo HTML (CSS y JS incluidos) |
| `app_web/construir_app_web.ps1` | Entorno, icono y `.exe` con PyInstaller |
| `app_web/construir_app_web.bat` | Lanzador con doble clic |
| `app_web/icono.png`, `icono.ico` | Icono de ejemplo |

## Inicio rápido

```powershell
cd app_web
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install pywebview
python notas_web.py --debug      # --debug activa el inspector (clic derecho > Inspeccionar)

.\construir_app_web.ps1          # genera dist\NotasRapidasWeb\NotasRapidasWeb.exe
```

---

# 1. Conceptos básicos

## 1.1 Qué es pywebview

Una librería que abre una **ventana nativa con un navegador embebido** y deja que Python y JavaScript se llamen entre sí. En Windows usa **Microsoft Edge WebView2** (el motor de Chromium de Edge); no incluye un navegador propio, por lo que el `.exe` es pequeño.

```
┌────────────── NotasRapidasWeb.exe ────────────────┐
│  Ventana nativa (WinForms)                        │
│  ┌─────────────────────────────────────────────┐  │
│  │ WebView2  →  ui/index.html (HTML+CSS+JS)    │  │
│  └───────────────▲─────────────────────────────┘  │
│                  │  window.pywebview.api.*        │
│  ┌───────────────┴─────────────────────────────┐  │
│  │ Python: clase Api (ficheros, config, red…)  │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

## 1.2 Requisito: WebView2 Runtime

- **Windows 11**: viene instalado.
- **Windows 10**: viene con las versiones actualizadas de Microsoft Edge; si falta, descárgalo en <https://developer.microsoft.com/microsoft-edge/webview2/> (*Evergreen Standalone Installer*).
- Si no está, pywebview recurre a un motor antiguo (MSHTML) que no soporta HTML moderno. Para distribuir, incluye en tu instalador la comprobación o el instalador *bootstrapper* de WebView2.

Python 3.9–3.13 es el rango más seguro: pywebview en Windows depende de `pythonnet`, que tarda en admitir las versiones nuevas de Python. Consulta la compatibilidad antes de actualizar Python.

## 1.3 Cuándo elegirlo (y cuándo no)

| Elige pywebview si… | Elige otra opción si… |
|---|---|
| Ya tienes la interfaz en HTML (por ejemplo, apps de un solo fichero) | Necesitas widgets nativos complejos (tablas, árboles, MDI) → PySide6 / wxPython |
| Quieres un diseño moderno sin aprender un toolkit | Quieres cero dependencias → Tkinter |
| Quieres reutilizar el mismo front-end en web y en escritorio | La app debe funcionar en equipos sin WebView2 |
| Necesitas acceso a disco o a APIs desde Python con interfaz web | Necesitas control total de menús y barra de título nativos |

## 1.4 Comparación con la versión Tkinter

| Aspecto | Tkinter | pywebview |
|---|---|---|
| Interfaz | Widgets de Tk | HTML/CSS/JS |
| Modo oscuro | Manual | `prefers-color-scheme` en CSS (sigue al sistema) |
| Dependencias | Ninguna (viene con Python) | `pywebview` + `pythonnet` + WebView2 |
| Atajos | `bind("<Control-s>")` | `keydown` con `e.ctrlKey` |
| Menús | `tk.Menu` | HTML propio o `webview.menu` |
| Diálogos de fichero | `tkinter.filedialog` | `window.create_file_dialog()` |
| DPI alto | Hay que declararlo | Nítido por defecto |
| Tamaño del paquete | Pequeño | Pequeño (usa el motor del sistema) |

## 1.5 La estructura mínima

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
2. **`window.pywebview` no existe hasta que se dispara `pywebviewready`.**
3. Todas las llamadas JS → Python **devuelven una promesa** (`await`).
4. Argumentos y retornos deben ser serializables a JSON.

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

**Regla crítica:** pywebview inspecciona de forma recursiva los atributos públicos de `Api`. Guardar `self.window = ventana` como público causa errores o arranques muy lentos. En el ejemplo se llama `self._window`.

## 2.2 Seguridad

El puente permite a la página ejecutar métodos de Python en el equipo del usuario:

- **Carga solo contenido local o de confianza.** Nunca cargues una URL externa con `js_api` habilitada.
- **Define una Content-Security-Policy** (incluida en `index.html`) que impida scripts remotos.
- **No expongas métodos genéricos** como `ejecutar(comando)` o `leer(ruta_cualquiera)`. Expón acciones concretas y valida los argumentos en Python.
- **Usa `textContent`** en lugar de `innerHTML` con datos externos.
- Prefiere los diálogos nativos (`create_file_dialog`) a aceptar rutas escritas desde JS.

## 2.3 Diálogos y eventos

```python
ventana.create_file_dialog(webview.FileDialog.OPEN, file_types=("Texto (*.txt;*.md)",))
ventana.create_file_dialog(webview.FileDialog.SAVE, save_filename="nota.txt")
ventana.create_file_dialog(webview.FileDialog.FOLDER)
ventana.create_confirmation_dialog("Título", "¿Seguro?")     # devuelve bool

ventana.events.closing += al_cerrar      # devolver False cancela el cierre
ventana.events.closed  += limpiar
ventana.events.loaded  += cargada
ventana.events.resized += lambda w, h: ...
```

En pywebview < 5 las constantes son `webview.OPEN_DIALOG`, `SAVE_DIALOG` y `FOLDER_DIALOG`; el ejemplo detecta ambas. El valor devuelto puede ser `None`, una cadena o una tupla; `_primera_ruta()` lo normaliza.

## 2.4 Hilos y tareas largas

- Las llamadas de JS a Python se ejecutan **en hilos aparte**: la ventana no se congela mientras Python trabaja.
- Una llamada larga deja la promesa JS pendiente: muestra un indicador de carga.
- Para progreso en tiempo real, lanza un hilo y empuja actualizaciones con `evaluate_js`:

```python
import threading

def procesar(self):
    def trabajo():
        for i in range(1, 101):
            hacer_paso(i)
            self._window.evaluate_js(f"progreso({i})")
        self._window.evaluate_js("terminado()")
    threading.Thread(target=trabajo, daemon=True).start()
    return {"iniciado": True}
```

- Para cálculo intensivo usa `multiprocessing`, con `multiprocessing.freeze_support()` al inicio de `main()` (ya incluido en el ejemplo).

## 2.5 Persistencia

| Qué | Dónde | Observación |
|---|---|---|
| Configuración y datos | `%APPDATA%\NotasRapidasWeb\` desde **Python** | Método del ejemplo; fiable y visible |
| Preferencias ligeras en el front-end | `localStorage` | Requiere `webview.start(private_mode=False, storage_path=...)`; si no se pierde al cerrar |
| Documentos del usuario | Diálogo de guardado | Nunca junto al `.exe` |
| Registros | `%LOCALAPPDATA%\NotasRapidasWeb\Logs\` | Imprescindible en una app sin consola |

## 2.6 Menús, tamaño y apariencia

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

Opciones útiles de `create_window`: `min_size`, `resizable`, `frameless` (sin barra de título), `easy_drag`, `on_top`, `confirm_close`, `text_select`, `background_color`.

**Modo oscuro:** WebView2 respeta el tema del sistema; con `color-scheme: light dark` y `@media (prefers-color-scheme: dark)` la interfaz cambia sola. La barra de título nativa sigue el tema que defina Windows.

**Tipografía:** usa `"Segoe UI"` para texto y `Consolas` / `"Cascadia Mono"` para monoespaciado (ya aplicado en `index.html`).

## 2.7 Servir los ficheros del front-end

- Si pasas una **ruta a un `.html`**, pywebview lo sirve con un servidor HTTP local interno (solo `127.0.0.1`, puerto aleatorio), de modo que CSS, JS e imágenes relativos funcionan.
- Si pasas **HTML en una cadena** (`html=...`), no hay ruta base.
- Puedes servir una app Flask/FastAPI pasando la instancia como `url`.
- Con PyInstaller, la carpeta `ui` se incluye con `--add-data "ui;ui"` y se localiza con `resource_path("ui/index.html")`.

## 2.8 Empaquetado con PyInstaller: particularidades

El script `construir_app_web.ps1` ejecuta:

```powershell
pyinstaller --noconfirm --clean --windowed --name NotasRapidasWeb `
  --add-data "ui;ui" --collect-all webview --icon icono.ico notas_web.py
```

- `--add-data "ui;ui"`: copia la interfaz (separador `;` en Windows).
- `--collect-all webview`: incluye los recursos JavaScript y las DLL de pywebview.
- `pythonnet` y `clr_loader` suelen detectarse por los *hooks* de PyInstaller. Si el `.exe` falla con `ModuleNotFoundError: clr` o similar, añade `--hidden-import clr` y `--collect-all clr_loader`.
- Mantén `pyinstaller` y `pyinstaller-hooks-contrib` actualizados: los hooks de pywebview se corrigen con frecuencia.
- Para ver los errores de arranque, construye con `-Consola` y ejecuta el `.exe` desde PowerShell.

> **Estado de la verificación:** la interfaz se probó en un navegador con un puente simulado y el código Python se comprobó sintácticamente. El empaquetado con PyInstaller y la ejecución con WebView2 no se han podido ejecutar fuera de Windows, así que puede hacer falta ajustar las opciones `--hidden-import` / `--collect-all` en tu equipo.

## 2.9 Depuración

| Necesidad | Cómo |
|---|---|
| Ver errores de JS y la consola | `python notas_web.py --debug`, clic derecho → *Inspeccionar* (o `F12`) |
| Ver errores de Python en el `.exe` | `%LOCALAPPDATA%\NotasRapidasWeb\Logs\app.log` |
| Ver la salida estándar del `.exe` | Construir con `-Consola` y ejecutar desde PowerShell |
| Probar la UI sin Python | Abrir `ui\index.html` en el navegador con un `window.pywebview` simulado |
| Fallo de arranque sin mensaje | Comprobar que WebView2 Runtime está instalado |

## 2.10 Errores frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `Cannot read properties of undefined (reading 'api')` | Se llamó a la API antes de `pywebviewready` | Esperar el evento |
| La app tarda en abrir o falla al iniciar | Atributo público con objeto complejo en `Api` | Prefijar con `_` |
| Ventana en blanco | WebView2 ausente o ruta de `ui/` mal resuelta | Instalar WebView2; revisar `--add-data "ui;ui"` |
| `ImportError` de `pythonnet`/`clr` al instalar | Python demasiado nuevo para `pythonnet` | Usar Python 3.11–3.13 |
| `evaluate_js` devuelve `None` | La última expresión no devuelve valor o la página no ha cargado | Esperar a `events.loaded` |
| El título no cambia | `document.title` no actualiza la ventana nativa | Llamar a `ventana.set_title()` (hecho en `poner_titulo`) |
| `localStorage` vacío en cada arranque | Modo privado por defecto | `private_mode=False, storage_path=...` o guardar desde Python |
| El `.exe` es bloqueado por el antivirus | Falso positivo habitual con PyInstaller | `--onedir`, firma de código, exclusión |
| Se abren varias ventanas en bucle | Falta `freeze_support()` | Llamarla al inicio de `main()` |

## 2.11 Lista de verificación

- [ ] La UI espera a `pywebviewready` antes de llamar a la API.
- [ ] Atributos internos de `Api` con guion bajo.
- [ ] Solo contenido local con la API habilitada; CSP definida.
- [ ] Todo lo que viaja entre capas pasa por JSON.
- [ ] Datos de usuario en `%APPDATA%`; log en `%LOCALAPPDATA%`.
- [ ] `--add-data "ui;ui"` y `--collect-all webview` en el empaquetado.
- [ ] Probado en un equipo limpio con WebView2.
- [ ] Firmado si se distribuye fuera de tu entorno.

## Referencias

- pywebview: <https://pywebview.flowrl.com>
- pywebview en Windows y WebView2: <https://pywebview.flowrl.com/guide/installation.html>
- WebView2 Runtime: <https://developer.microsoft.com/microsoft-edge/webview2/>
- PyInstaller: <https://pyinstaller.org>

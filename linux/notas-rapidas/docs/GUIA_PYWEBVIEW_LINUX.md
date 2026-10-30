# App de Linux con Python + pywebview (interfaz HTML)

Detalles de la variante **Notas Rápidas Web** en Debian, Ubuntu y Linux Mint: la interfaz es HTML/CSS/JS y Python es el motor. Complementa a `GUIA_APP_LINUX.md` (lanzadores `.desktop`, rutas XDG, paquetes `.deb`, glibc y diferencias entre distribuciones se explican allí).

## Ficheros

| Fichero | Función |
|---|---|
| `app_web/notas_web.py` | Backend Python: ventana, API para JS, ficheros, configuración, log |
| `app_web/ui/index.html` | Interfaz completa en un solo HTML (CSS y JS incluidos) |
| `app_web/notas-rapidas-web.desktop` | Lanzador del menú de aplicaciones |
| `app_web/crear_deb.sh` | Crea el `.deb` (incluye pywebview; usa GTK y WebKitGTK del sistema) |
| `app_web/instalar_local.sh` | Instala para tu usuario, sin `sudo`, con un venv propio |
| `app_web/construir_app_web.sh` | Binario PyInstaller (**experimental**) |
| `app_web/icono*.png` | Iconos de ejemplo |

## Inicio rápido

```bash
# 1. Paquetes del sistema (Debian 12+, Ubuntu 22.04+, Mint 21+)
sudo apt update
sudo apt install python3-venv python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1

# 2. Entorno de desarrollo (con acceso al «gi» del sistema)
cd app_web
python3 -m venv --system-site-packages .venv
.venv/bin/pip install pywebview
.venv/bin/python notas_web.py --debug       # --debug activa el inspector web

# 3. Instalarla (elige una)
./crear_deb.sh && sudo apt install ./dist/notas-rapidas-web_1.0.0_all.deb
./instalar_local.sh --escritorio
```

---

# 1. Conceptos básicos

## 1.1 Qué es pywebview en Linux

Una librería que abre una **ventana nativa con un navegador embebido** y permite que Python y JavaScript se llamen entre sí. En Linux hay dos *backends*:

| Backend | Motor | Paquetes | Observaciones |
|---|---|---|---|
| **GTK** (por defecto en GNOME, Cinnamon, Xfce) | **WebKitGTK** | `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-webkit2-4.1` | Ligero; usa librerías del sistema |
| **Qt** | QtWebEngine (Chromium) | `pip install "pywebview[qt]"` | Pesado (cientos de MB); no necesita `gi` |

El ejemplo usa el backend GTK. pywebview elige el que encuentre instalado; puedes forzarlo con `webview.start(gui="gtk")` o `gui="qt"`.

```
┌────────────── notas-rapidas-web ──────────────────┐
│  Ventana GTK                                      │
│  ┌─────────────────────────────────────────────┐  │
│  │ WebKitGTK  →  ui/index.html (HTML+CSS+JS)   │  │
│  └───────────────▲─────────────────────────────┘  │
│                  │  window.pywebview.api.*        │
│  ┌───────────────┴─────────────────────────────┐  │
│  │ Python: clase Api (ficheros, config, red…)  │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

## 1.2 Versiones de WebKitGTK

| Paquete (`gir1.2-…`) | Disponible en | Notas |
|---|---|---|
| `webkit2-4.1` | Debian 12 y posteriores, Ubuntu 22.04 y posteriores, Mint 21 y posteriores | Recomendada |
| `webkit2-4.0` | Distros anteriores (Ubuntu 20.04, Mint 20); también en algunas actuales | Misma API para pywebview; el `.deb` acepta cualquiera de las dos (`Depends: … 4.1 \| … 4.0`) |
| `webkit-6.0` | GTK 4 (distros recientes) | pywebview con GTK 3 no la usa |

Comprobar qué hay instalado:

```bash
python3 -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('WebKit2','4.1'); from gi.repository import Gtk, WebKit2; print('OK')"
apt list --installed 2>/dev/null | grep -E "gir1.2-webkit|python3-gi"
```

## 1.3 Cuándo elegirlo (y cuándo no)

| Elige pywebview si… | Elige otra opción si… |
|---|---|
| Ya tienes la interfaz en HTML (por ejemplo, apps de un solo fichero) | Necesitas widgets nativos complejos → GTK o Qt directamente |
| Quieres un diseño moderno sin aprender un toolkit | Quieres cero dependencias → Tkinter |
| Reutilizas el mismo front-end en web y escritorio | No quieres depender de WebKitGTK del sistema |
| Necesitas acceso a disco o APIs desde Python | Necesitas empaquetado portable sin instalar nada (AppImage con Qt) |

## 1.4 Comparación con la versión Tkinter

| Aspecto | Tkinter | pywebview (GTK) |
|---|---|---|
| Interfaz | Widgets de Tk | HTML/CSS/JS |
| Modo oscuro | Manual | `prefers-color-scheme` en CSS (sigue al tema de GTK) |
| Dependencias de apt | `python3-tk` | `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-webkit2-4.1` |
| Dependencias de pip | Ninguna | `pywebview` (Python puro) |
| Atajos | `bind("<Control-s>")` | `keydown` con `e.ctrlKey` |
| Diálogos de fichero | `tkinter.filedialog` | Diálogos nativos de GTK (`create_file_dialog`) |
| Wayland | Vía XWayland (puede verse borroso con escalado fraccionario) | Nativo, nítido |
| Tamaño del `.deb` | ~20 KB | ~0,5 MB (incluye pywebview) |

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

**Python → JS:** `window.evaluate_js("codigo")`.

```python
sucio = ventana.evaluate_js("window.hayCambios()")
ventana.evaluate_js("actualizar(%s)" % json.dumps(datos))   # json.dumps evita inyección
```

**Regla crítica:** pywebview inspecciona de forma recursiva los atributos públicos de `Api`. Guardar `self.window = ventana` como público causa errores o arranques lentos. En el ejemplo se llama `self._window`.

## 2.2 Seguridad

- **Carga solo contenido local o de confianza.** Nunca cargues una URL externa con `js_api` habilitada.
- **Define una Content-Security-Policy** (incluida en `index.html`).
- **No expongas métodos genéricos** como `ejecutar(comando)` o `leer(ruta_cualquiera)`; valida los argumentos en Python.
- **Usa `textContent`** en lugar de `innerHTML` con datos externos.
- Prefiere los diálogos nativos a aceptar rutas escritas desde JS.

## 2.3 Diálogos y eventos

```python
ventana.create_file_dialog(webview.FileDialog.OPEN, file_types=("Texto (*.txt;*.md)",))
ventana.create_file_dialog(webview.FileDialog.SAVE, save_filename="nota.txt")
ventana.create_file_dialog(webview.FileDialog.FOLDER)
ventana.create_confirmation_dialog("Título", "¿Seguro?")     # devuelve bool

ventana.events.closing += al_cerrar      # devolver False cancela el cierre
ventana.events.closed  += limpiar
ventana.events.loaded  += cargada
```

En pywebview < 5 las constantes son `webview.OPEN_DIALOG`, `SAVE_DIALOG` y `FOLDER_DIALOG`; el ejemplo detecta ambas. El valor devuelto puede ser `None`, una cadena o una tupla; `_primera_ruta()` lo normaliza.

## 2.4 Hilos y tareas largas

- Las llamadas de JS a Python se ejecutan **en hilos aparte**: la ventana no se congela.
- Una llamada larga deja la promesa JS pendiente: muestra un indicador de carga.
- Para progreso en tiempo real, lanza un hilo y empuja actualizaciones con `evaluate_js`.
- GTK **no es seguro entre hilos**: modifica la interfaz solo mediante `evaluate_js` o los métodos de `Window` de pywebview, no con llamadas directas a GTK desde hilos secundarios.

## 2.5 Persistencia y rutas

| Qué | Dónde |
|---|---|
| Configuración | `~/.config/notas-rapidas-web/` (`XDG_CONFIG_HOME`) |
| Registros | `~/.local/state/notas-rapidas-web/app.log` (`XDG_STATE_HOME`) |
| Preferencias ligeras en el front-end | `localStorage` requiere `webview.start(private_mode=False, storage_path=...)` |
| Documentos del usuario | Diálogo de guardado |

## 2.6 Icono y nombre de la ventana

- **Icono de ventana:** `webview.start(icon="ruta/icono.png")` (GTK y Qt). El ejemplo lo pasa.
- **Icono en el menú y el dock:** lo da el `.desktop` (`Icon=notas-rapidas-web`) y los PNG en `hicolor`.
- **Nombre del programa:** el ejemplo llama a `GLib.set_prgname("notas-rapidas-web")` para que el entorno asocie la ventana con su lanzador.
- Si el dock muestra un icono genérico adicional, comprueba con `xprop WM_CLASS` (X11) y añade `StartupWMClass=` al `.desktop` con el valor de la segunda cadena.

## 2.7 Empaquetado: por qué el `.deb` ligero es la vía recomendada

Congelar la variante web con PyInstaller es **frágil** porque pywebview necesita GTK, WebKitGTK y sus *typelibs* a través de PyGObject, que dependen del sistema, y WebKit lanza procesos auxiliares. Por eso este proyecto distribuye la variante web así:

| Vía | Qué hace | Ventajas | Inconvenientes |
|---|---|---|---|
| **`.deb`** (`crear_deb.sh`) | Instala el código en `/opt/notas-rapidas-web`, pywebview en `lib/` y usa el Python y GTK del sistema | Un mismo `.deb` para Debian, Ubuntu y Mint, cualquier arquitectura; sin problemas de glibc | Requiere instalar dependencias de apt (las resuelve `apt`) |
| **Instalación local** (`instalar_local.sh`) | venv propio en `~/.local/share` con `--system-site-packages` | Sin `sudo` | Requiere internet; dependencias de apt instaladas antes |
| **PyInstaller** (`construir_app_web.sh`) | Binario con Python incluido | Autocontenido en teoría | Experimental; glibc; GTK/WebKit del sistema |

Cómo funciona el `.deb`:

1. `pip install --target /opt/.../lib pywebview` en el momento de **construir** el paquete (pywebview, `bottle`, `proxy_tools` y `typing_extensions` son Python puro).
2. El lanzador `/usr/bin/notas-rapidas-web` fija `PYTHONPATH` y ejecuta `/usr/bin/python3`.
3. `Depends: python3 (>= 3.9), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1 | gir1.2-webkit2-4.0`.

Si usas el backend Qt, cambia las dependencias por las de Qt y pasa `gui="qt"`.

## 2.8 Depuración

| Necesidad | Cómo |
|---|---|
| Ver errores de JS y la consola | `python3 notas_web.py --debug`, clic derecho → *Inspeccionar elemento* |
| Ver errores de Python | `~/.local/state/notas-rapidas-web/app.log` y la terminal |
| Diagnóstico de GTK/WebKit | Ejecutar desde terminal; revisar `journalctl --user -e` |
| Comprobar dependencias | El fragmento de la sección 1.2 |
| Probar la UI sin Python | Abrir `ui/index.html` en el navegador con un `window.pywebview` simulado |

## 2.9 Errores frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `You must have either QT or GTK with Python extensions installed` | Falta `gi` o WebKitGTK | `sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1` |
| `ModuleNotFoundError: No module named 'gi'` dentro de un venv | El venv no ve los paquetes del sistema | Crearlo con `python3 -m venv --system-site-packages .venv` |
| `ValueError: Namespace WebKit2 not available for version 4.1` | Distro con WebKit 4.0 | `sudo apt install gir1.2-webkit2-4.0` |
| Ventana en blanco o negra | Problema de aceleración gráfica (frecuente en máquinas virtuales y algunas NVIDIA) | Ejecutar con `WEBKIT_DISABLE_COMPOSITING_MODE=1` o `WEBKIT_DISABLE_DMABUF_RENDERER=1` |
| `error: externally-managed-environment` | PEP 668 | Usar un venv (los scripts ya lo hacen) |
| `Cannot read properties of undefined (reading 'api')` | Se llamó a la API antes de `pywebviewready` | Esperar el evento |
| La app tarda en abrir o falla al iniciar | Atributo público con objeto complejo en `Api` | Prefijar con `_` |
| `evaluate_js` devuelve `None` | La página no ha cargado o la expresión no devuelve valor | Esperar a `events.loaded` |
| No aparece el icono en el dock | `WM_CLASS` ≠ `StartupWMClass` | Ver 2.6 |
| `dpkg: dependency problems` | Se usó `dpkg -i` | `sudo apt install ./paquete.deb` |

## 2.10 Diferencias entre Debian, Ubuntu y Linux Mint para esta variante

| Tema | Debian 12 / 13 | Ubuntu 22.04 / 24.04 | Linux Mint 21 / 22 |
|---|---|---|---|
| Paquetes de apt | `python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1` | Igual | Igual (suelen venir `python3-gi` y GTK por defecto) |
| Sesión gráfica | Wayland: ventana nítida, escalado correcto | Wayland | X11 (Cinnamon) |
| Instalar el `.deb` | `sudo apt install ./x.deb` | Igual | Igual |
| Problemas de ventana en blanco en VM | Posible: variable `WEBKIT_DISABLE_*` | Posible | Posible |
| Python del sistema | 3.11 / 3.13 | 3.10 / 3.12 | 3.10 / 3.12 |

El `.deb` y los scripts son idénticos en las tres. Si una distro tiene solo `gir1.2-webkit2-4.0` (versiones anteriores), el `.deb` también se instala porque admite ambas.

## 2.11 Lista de verificación

- [ ] La UI espera a `pywebviewready` antes de llamar a la API.
- [ ] Atributos internos de `Api` con guion bajo.
- [ ] Solo contenido local con la API habilitada; CSP definida.
- [ ] Todo lo que viaja entre capas pasa por JSON.
- [ ] Datos en `~/.config` y logs en `~/.local/state`.
- [ ] `.deb` instalado y probado en Debian, Ubuntu y Mint limpios (o VM).
- [ ] `.desktop` validado y icono en `hicolor`.
- [ ] Probado en Wayland y X11.

## Referencias

- pywebview: <https://pywebview.flowrl.com>
- Instalación y dependencias de pywebview en Linux: <https://pywebview.flowrl.com/guide/installation.html>
- WebKitGTK: <https://webkitgtk.org>
- Desktop Entry Specification: <https://specifications.freedesktop.org/desktop-entry-spec/latest/>

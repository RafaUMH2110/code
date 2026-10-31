# Cuatro toolkits más para macOS: PySide6, wxPython, PyObjC y Toga

Comparación y detalles de las versiones de **Notas Rápidas** hechas con PySide6 (`app_pyside6/`), wxPython (`app_wx/`), PyObjC (`app_pyobjc/`) y Toga (`app_toga/`). Todas hacen lo mismo que las versiones de Tkinter y pywebview, para que puedas comparar el código línea a línea. Los conceptos de empaquetado, firma y notarización se explican en `GUIA_APP_MACOS.md`.

## Funciones comunes de las seis versiones

- Menú Archivo / Edición / Ver con atajos de teclado (Cmd+N, O, S, Shift+S, +, −).
- Abrir, guardar y «guardar como», con indicador de documento modificado.
- Aviso de cambios sin guardar al cerrar la ventana y al salir (Cmd+Q).
- Contador de palabras y caracteres, zoom de la fuente.
- Configuración persistente y registro (`logging`) en las rutas estándar de macOS.
- Reabre el último fichero y acepta ficheros desde Finder.

---

# 1. Panorama

| | Tkinter | pywebview | **PySide6** | **wxPython** | **PyObjC** | **Toga** |
|---|---|---|---|---|---|---|
| Qué es | Tk, en la biblioteca estándar | HTML/JS en WKWebView | Qt 6 | wxWidgets (widgets nativos) | Puente Python → Cocoa | BeeWare: widgets nativos |
| Aspecto en macOS | Propio, algo anticuado | El de tu CSS | Propio de Qt, muy cuidado | Nativo (envuelve AppKit) | **100 % nativo** | Nativo (envuelve AppKit) |
| Plataformas | Todas | Todas | Todas | Todas | **Solo macOS** | macOS, Windows, Linux, iOS, Android |
| Instalación | Viene con Python (Homebrew: `python-tk`) | `pip install pywebview` | `pip install PySide6-Essentials` | `pip install wxPython` | `pip install pyobjc-framework-Cocoa` | `pip install toga` |
| Código para lo mismo | Medio | Medio (Python + JS) | Medio | Medio | **Más largo** | **Más corto** |
| Curva de aprendizaje | Baja | Baja (si sabes web) | Media | Media | Alta (Cocoa) | Baja-media |
| Empaquetado | py2app | py2app | PyInstaller | py2app | py2app | Briefcase |
| Tamaño del `.app` (orden de magnitud) | Decenas de MB | Decenas de MB | Cientos de MB | Decenas de MB | Decenas de MB | Decenas de MB |
| Licencia | PSF | BSD-3 | LGPL | wxWindows Library Licence | MIT | BSD-3 |
| Widgets disponibles | Pocos y básicos | Los de HTML | **Muchísimos** | Muchos | **Todos los de AppKit** | Los básicos y comunes |

---

# 2. Conceptos comunes

Aunque el código parezca distinto, las seis versiones comparten la misma estructura:

| Concepto | Tkinter | PySide6 | wxPython | PyObjC | Toga |
|---|---|---|---|---|---|
| Objeto de aplicación | `tk.Tk()` | `QApplication` | `wx.App` | `NSApplication` + delegado | `toga.App` |
| Ventana | `tk.Tk` | `QMainWindow` | `wx.Frame` | `NSWindow` | `toga.MainWindow` |
| Bucle de eventos | `mainloop()` | `app.exec()` | `app.MainLoop()` | `AppHelper.runEventLoop()` | `app.main_loop()` |
| Conectar un evento | `command=` / `bind()` | señales: `.triggered.connect(f)` | `Bind(wx.EVT_MENU, f, id=…)` | método con selector (`guardar_`) | `on_change=` / `Command(f)` |
| Texto multilínea | `tk.Text` | `QPlainTextEdit` | `wx.TextCtrl` (`TE_MULTILINE`) | `NSTextView` en `NSScrollView` | `toga.MultilineTextInput` |
| Menú y atajo | `Menu` + `bind` | `QAction` + `QKeySequence` | `Menu.Append(id, "…\tCtrl+S")` | `NSMenuItem` + `keyEquivalent` | `toga.Command(shortcut=…)` |
| Diálogo de fichero | `filedialog` | `QFileDialog` | `wx.FileDialog` | `NSOpenPanel` / `NSSavePanel` | `OpenFileDialog` / `SaveFileDialog` |
| Documento modificado | Variable propia | `setWindowModified` | `OSXSetModified` | `setDocumentEdited_` | Variable propia |
| Confirmar al cerrar | `WM_DELETE_WINDOW` | `closeEvent` | `EVT_CLOSE` + `Veto()` | `windowShouldClose_` | `on_close` / `on_exit` |
| Fichero desde Finder | (no soportado) | `QFileOpenEvent` | `MacOpenFiles` | `application:openFile:` | argumentos de línea de comandos |

**Regla común:** todos los toolkits son de un solo hilo para la interfaz. Las tareas largas van a un hilo o proceso aparte y devuelven resultados al hilo principal (Qt: señales; wx: `wx.CallAfter`; Cocoa: `performSelectorOnMainThread`/`AppHelper.callAfter`; Toga: `async`/`await` o `app.loop.run_in_executor`).

---

# 3. PySide6 (Qt for Python)

## 3.1 Idea

Qt es un framework completo (widgets, gráficos, red, multimedia…) escrito en C++. PySide6 es el enlace oficial a Python, mantenido por The Qt Company con licencia LGPL (PyQt6 es otro enlace casi idéntico con licencia GPL/comercial).

## 3.2 Piezas del ejemplo (`notas_pyside6.py`)

```python
app = Aplicacion(sys.argv)          # QApplication (subclase para recibir ficheros de Finder)
ventana = Ventana()                 # QMainWindow con QPlainTextEdit como widget central
ventana.show()
sys.exit(app.exec())
```

- **Señales y ranuras:** `accion.triggered.connect(self.guardar)`. Los widgets emiten señales (`textChanged`, `modificationChanged`) a las que conectas funciones.
- **Atajos estándar:** `QKeySequence.StandardKey.Save` se traduce a **Cmd+S** en macOS y a **Ctrl+S** en el resto; no escribas atajos a mano.
- **Roles de menú:** `QAction.MenuRole.AboutRole` y `QuitRole` hacen que Qt mueva «Acerca de» y «Salir» al menú de la aplicación, como exige macOS.
- **Documento modificado:** el título lleva el marcador `[*]` y `setWindowModified(True)` activa el punto del botón rojo.
- **Ficheros desde Finder:** se sobrescribe `QApplication.event()` y se atiende `QEvent.Type.FileOpen`. El evento puede llegar antes de crear la ventana, por eso se guarda como pendiente.
- **Cierre:** `closeEvent` puede llamar a `evento.ignore()` para cancelar.

## 3.3 Empaquetado: PyInstaller

```bash
./construir_app.sh      # pyinstaller --windowed --name "Notas Rapidas Qt" --icon icono.icns …
```

- py2app tiene soporte limitado para PySide6; **PyInstaller** lo trata mejor (tiene *hooks* específicos).
- Alternativa oficial: `pyside6-deploy` (usa Nuitka); genera un binario compilado.
- El bundle es grande porque incluye las bibliotecas de Qt. `PySide6-Essentials` (en vez de `PySide6`) evita los módulos adicionales y reduce el tamaño.
- Para asociar tipos de fichero («Abrir con…») hay que añadir `CFBundleDocumentTypes` al `Info.plist`: con PyInstaller, mediante `info_plist` en el fichero `.spec`.

## 3.4 Trampas

- `setPlainText()` reinicia el estado de «modificado» y el historial de deshacer; es lo que se quiere al cargar un fichero, pero no al editar.
- No mezcles PySide6 y PyQt6 en el mismo proceso.
- Importa solo los módulos que uses (`QtWidgets`, `QtGui`, `QtCore`) para que el empaquetado no arrastre el resto.

---

# 4. wxPython

## 4.1 Idea

wxWidgets usa los controles nativos de cada sistema (en macOS, AppKit). wxPython («Phoenix») es su enlace a Python. El resultado se ve y se comporta como una app Cocoa normal con una API muy parecida en las tres plataformas.

## 4.2 Piezas del ejemplo (`notas_wx.py`)

```python
app = Aplicacion(False)      # wx.App; OnInit() crea el marco
app.MainLoop()
```

- **IDs estándar:** si usas `wx.ID_ABOUT`, `wx.ID_EXIT` y `wx.ID_PREFERENCES`, wxWidgets coloca esas opciones en el menú de la aplicación automáticamente en macOS.
- **Aceleradores:** `"Guardar\tCtrl+S"`; en macOS «Ctrl» significa **Cmd**.
- **Eventos:** `self.Bind(wx.EVT_MENU, funcion, id=wx.ID_SAVE)`.
- **Cierre:** `EVT_CLOSE`; si el usuario cancela, `evento.Veto()` (solo cuando `evento.CanVeto()` es verdadero, porque un cierre forzado del sistema no se puede vetar).
- **Finder:** se sobrescribe `MacOpenFiles(self, nombres)` en `wx.App`.
- **Punto de modificado:** `OSXSetModified(True)` en el marco.
- **Texto:** `ChangeValue()` cambia el texto **sin** disparar `EVT_TEXT`; `SetValue()` sí lo dispara.

## 4.3 Empaquetado: py2app

```python
OPTIONS = {"argv_emulation": False, "packages": ["wx"], "iconfile": "icono.icns", "plist": {…}}
```

py2app es la herramienta clásica para wxPython en macOS. Si el `.app` falla por módulos que faltan, añádelos a `packages`/`includes`.

## 4.4 Trampas

- Antes de crear cualquier widget hace falta una instancia de `wx.App`.
- `wx.adv` (cuadro «Acerca de») es un submódulo que hay que importar explícitamente.
- La disponibilidad de ruedas (`pip install wxPython`) depende de la versión de Python y de la arquitectura; si `pip` intenta compilar desde el código fuente, tardará mucho o fallará. Comprueba que tu versión de Python tiene rueda para macOS.

---

# 5. PyObjC (AppKit directo)

## 5.1 Idea

PyObjC es un puente entre Python y Objective-C: puedes usar **cualquier API de Apple** (AppKit, Foundation, WebKit, AVFoundation, Vision…) desde Python, con widgets 100 % nativos. No es multiplataforma, y exige entender la forma de pensar de Cocoa.

## 5.2 Conceptos de Cocoa que necesitas

| Concepto | Qué es | En el ejemplo |
|---|---|---|
| **Delegado** | Objeto al que Cocoa «delega» decisiones del ciclo de vida | La clase `Delegado(NSObject)` hace de delegado de la app, de la ventana y del texto |
| **Selector** | Nombre de un método de Objective-C; los `:` marcan argumentos | En Python se escribe con subrayados: `guardar_` ⇄ `guardar:`; `application_openFile_` ⇄ `application:openFile:` |
| **Cadena de respondedores** | Las acciones sin destino (`undo:`, `copy:`) viajan por ventana, vista y aplicación hasta quien las entienda | El menú Edición usa `target=None` y `NSTextView` responde |
| **Target / Action** | Un elemento de menú o botón llama a `acción:` sobre un `target` | `item.setTarget_(self)` y selectors como `"guardar:"` |
| **Autoresizing mask** | Cómo se ajusta una vista al redimensionar la ventana | `NSViewWidthSizable \| NSViewHeightSizable` |
| **Sistema de coordenadas** | El origen está **abajo a la izquierda** | La barra de estado se ancla abajo con `NSViewMaxYMargin` |

## 5.3 Piezas del ejemplo (`notas_pyobjc.py`)

```python
app = NSApplication.sharedApplication()
delegado = Delegado.alloc().init().preparar()   # no se usa __init__ en subclases de NSObject
app.setDelegate_(delegado)
AppHelper.runEventLoop()
```

- **Inicialización:** las subclases de `NSObject` se crean con `alloc().init()`; el estado propio se prepara en un método aparte (`preparar`).
- **Métodos auxiliares:** cualquier método con subrayado en el nombre se interpreta como selector. Los métodos privados de Python deben llevar `@objc.python_method` (si no, PyObjC protesta por no coincidir los argumentos).
- **Menús:** `NSMenu`/`NSMenuItem` se construyen a mano; el primer menú de la barra es el de la aplicación.
- **Texto:** `NSTextView` dentro de `NSScrollView`, con su propio deshacer (`setAllowsUndo_(True)`).
- **Diálogos:** `NSOpenPanel`, `NSSavePanel` y `NSAlert` (los botones devuelven 1000, 1001, 1002…).
- **Documento modificado:** `window.setDocumentEdited_(True)`.
- **Geometría persistente:** `setFrameAutosaveName_(...)` hace que Cocoa guarde y restaure la posición y el tamaño sin código.
- **Salir:** `applicationShouldTerminate_` devuelve 1 (continuar) o 0 (cancelar).

## 5.4 Empaquetado: py2app

Es la herramienta natural. Para PyObjC basta con `pip install pyobjc-framework-Cocoa` (no instales el metapaquete `pyobjc` completo: arrastra cientos de frameworks y alarga la construcción).

## 5.5 Trampas

- No uses `__init__` en subclases de `NSObject`.
- Las actualizaciones de interfaz solo en el hilo principal: `AppHelper.callAfter(función, …)`.
- Mantén una referencia a los delegados (Cocoa no la conserva): en el ejemplo, la variable `delegado` en `main()`.
- Algunas APIs aparecen marcadas como obsoletas en macOS nuevos (por ejemplo `setAllowedFileTypes_`); siguen funcionando, pero conviene migrar a `setAllowedContentTypes_` con `UTType`.

---

# 6. Toga (BeeWare)

## 6.1 Idea

Toga es el toolkit de BeeWare: **un único código Python** que usa widgets nativos en macOS (Cocoa), Windows (WinForms), Linux (GTK), iOS y Android. Se empaqueta con **Briefcase**, la herramienta de BeeWare, que genera `.app`, `.dmg`, instaladores MSI, `.deb`, paquetes para móviles, etc.

## 6.2 Piezas del ejemplo (`src/notas_rapidas_toga/app.py`)

```python
class NotasRapidas(toga.App):
    def startup(self):                       # se llama una vez al arrancar
        self.main_window = toga.MainWindow(title=…)
        self.main_window.content = toga.Box(children=[self.texto, self.estado], style=Pack(direction=COLUMN))
        self.main_window.show()
```

- **Layout con Pack:** `Pack(flex=1, direction=COLUMN, margin=…)` se parece a CSS flexbox.
- **Comandos:** `toga.Command(funcion, text=…, shortcut=toga.Key.MOD_1 + "s", group=toga.Group.FILE)`. `MOD_1` es Cmd en macOS y Ctrl en otros sistemas. Toga añade menús estándar de la aplicación (Acerca de, Salir…); comprueba en tu versión si incluye también los de edición (deshacer, copiar, pegar) y, si no, añádelos como `toga.Command`.
- **Handlers asíncronos:** las acciones pueden ser `async def`. Los diálogos se esperan con `await`: `ruta = await self.main_window.dialog(toga.OpenFileDialog("Abrir", file_types=["txt"]))`.
- **Rutas estándar:** `self.paths.config`, `self.paths.logs`, `self.paths.data`, `self.paths.cache`.
- **Salir con confirmación:** `on_close` (ventana) y `on_exit` (Cmd+Q) son **síncronos** y devuelven `bool`. Como no pueden esperar un diálogo, el ejemplo devuelve `False`, lanza una tarea asíncrona con `self.loop.create_task(...)` y, si el usuario acepta, llama a `self.exit()`.
- **Limitaciones frente a otros toolkits:** no hay diálogo de tres botones (Guardar / No guardar / Cancelar), así que se preguntan dos cosas seguidas; el ejemplo no usa el indicador de documento modificado de macOS y pone un `•` en el título.

## 6.3 Empaquetado: Briefcase

`pyproject.toml` describe el proyecto; `construir_app.sh` encapsula los comandos:

```bash
./construir_app.sh dev         # briefcase dev: ejecuta sin construir
./construir_app.sh             # briefcase create/update macOS + briefcase build macOS
./construir_app.sh package     # además: briefcase package macOS --adhoc-sign  -> .dmg
```

- El proyecto debe tener la estructura `src/<modulo>/` con `__main__.py` y `app.py`; Briefcase la usa al crear la plantilla de Xcode del `.app`.
- `bundle = "com.ejemplo"` + el nombre de la app forman el identificador `com.ejemplo.notas-rapidas-toga`. Cámbialo por el tuyo.
- Briefcase exige un fichero `LICENSE` (el del ejemplo es un marcador).
- Toga **cambia de API con frecuencia** entre versiones menores. El ejemplo está escrito para **Toga 0.5** (`~=0.5.0` en `pyproject.toml`). Con otra versión pueden cambiar `Pack`, los diálogos o los nombres de propiedades.

## 6.4 Trampas

- Las llamadas a diálogos son `await`: el método que las use debe ser `async`.
- Asignar `texto.value = …` desde código dispara `on_change`; el ejemplo usa un indicador `_cargando` para no marcar el documento como modificado al cargar un fichero.
- `briefcase dev` instala las dependencias en tu entorno; `briefcase build` usa un entorno aislado dentro de `build/`.

---

# 7. Cómo elegir

| Si necesitas… | Elige |
|---|---|
| Lo más simple posible y sin dependencias | **Tkinter** |
| Reutilizar una interfaz web | **pywebview** |
| Una aplicación grande y profesional, con muchos widgets, gráficos o tablas | **PySide6** |
| Aspecto nativo y una API estable y madura | **wxPython** |
| Integrarte a fondo con macOS (menús, servicios, sandbox, APIs de Apple) y solo vas a publicar en Mac | **PyObjC** |
| Un único código para escritorio **y móvil** con aspecto nativo | **Toga** |

Notas de decisión:

- **PySide6** es la opción más completa, a costa del tamaño del `.app`.
- **wxPython** y **Toga** se ven nativos porque usan AppKit por debajo; Toga es más moderno, pero su API todavía evoluciona.
- **PyObjC** es la ruta con más control y también la de más trabajo.

---

# 8. Versiones de Python y dependencias

La disponibilidad de ruedas precompiladas para macOS depende de la versión de Python. Si usas una versión muy reciente (por ejemplo la que instala Homebrew) y `pip install` falla o intenta compilar desde fuentes:

1. Comprueba qué versión de Python soporta cada paquete en su página de PyPI.
2. Crea el entorno con una versión anterior: `brew install python@3.13` y `python3.13 -m venv .venv`.
3. Para Tkinter, Homebrew separa Tk: `brew install python-tk@3.13`.

Como orientación, Python 3.12 o 3.13 es lo más seguro para las seis variantes. Verifica siempre en tu equipo.

---

# 9. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| PySide6: la app no abre ficheros desde Finder | Falta `CFBundleDocumentTypes` en el `Info.plist` | Añadir `info_plist` al `.spec` de PyInstaller |
| PySide6: `.app` enorme | Se instaló `PySide6` completo | Usar `PySide6-Essentials` |
| wxPython: `pip` compila durante minutos o falla | No hay rueda para tu versión de Python | Usar una versión de Python con rueda (ver sección 8) |
| wxPython: `AttributeError: module 'wx' has no attribute 'adv'` | Submódulo sin importar | `import wx.adv` |
| PyObjC: `BadPrototypeError` al cargar la clase | Método con subrayados que no es un selector | Decorar con `@objc.python_method` |
| PyObjC: el delegado desaparece y la app no responde | Se perdió la referencia | Guardarlo en una variable viva |
| PyObjC: la interfaz se congela o se cierra al actualizarla desde un hilo | Cocoa no es seguro entre hilos | `AppHelper.callAfter(...)` |
| Toga: `TypeError` al construir `Pack(...)` o los diálogos | API de otra versión de Toga | Fijar `toga~=0.5.0` o adaptar el código |
| Toga: `briefcase create` falla por falta de licencia | No hay `LICENSE` | Sustituir el marcador por tu licencia |
| Toga: la ventana no cierra al pulsar la X con cambios sin guardar | Es el comportamiento: pregunta primero | Aceptar el diálogo; ver §6.2 |
| Cualquiera: `ModuleNotFoundError` solo en el `.app` | El empaquetador no detectó el módulo | `packages`/`includes` (py2app), `--hidden-import` (PyInstaller), `requires` (Briefcase) |

---

# 10. Estado de verificación

| Variante | Qué se ha comprobado | Qué no |
|---|---|---|
| **PySide6** | La lógica de la ventana se ejecutó con Qt sin pantalla (`offscreen`) en Linux: título, contador, marca de modificado, guardar, cargar, zoom, configuración y cierre | El aspecto real en macOS, `QFileOpenEvent` y el empaquetado con PyInstaller |
| **Toga** | La app arranca y su lógica se ejecutó con el backend de pruebas (`toga_dummy`) de Toga 0.5.7: comandos, contador, marca de modificado, guardar, abrir y zoom | El comportamiento real de Cocoa (diálogos, `on_close`/`on_exit`) y Briefcase |
| **wxPython** | Solo la sintaxis | Todo lo demás (wxPython no se instala en el entorno de pruebas) |
| **PyObjC** | Solo la sintaxis y la coherencia de los selectores con el número de argumentos | Todo lo demás (PyObjC solo funciona en macOS) |

Prueba cada variante en tu Mac antes de darla por buena. Si algo falla, el mensaje de error y el fichero `app.log` (ver `MANUAL_VSCODE.md`, §6) indican la causa.

---

## Referencias

- Qt for Python: <https://doc.qt.io/qtforpython-6/>
- wxPython: <https://docs.wxpython.org> · wxWidgets: <https://www.wxwidgets.org>
- PyObjC: <https://pyobjc.readthedocs.io> · Documentación de AppKit: <https://developer.apple.com/documentation/appkit>
- Toga: <https://toga.readthedocs.io> · Briefcase: <https://briefcase.readthedocs.io>
- PyInstaller: <https://pyinstaller.org> · py2app: <https://py2app.readthedocs.io>

# Tres toolkits más para Windows: PySide6, wxPython y Toga

Comparación y detalles de las versiones de **Notas Rápidas** hechas con PySide6 (`app_pyside6/`), wxPython (`app_wx/`) y Toga (`app_toga/`). Todas hacen lo mismo que las versiones de Tkinter y pywebview, para que puedas comparar el código. El empaquetado, el antivirus, la firma y los instaladores se explican en `GUIA_APP_WINDOWS.md`.

## Funciones comunes de las cinco versiones

- Menú Archivo / Edición / Ver / Ayuda con atajos de teclado (Ctrl+N, O, S, Shift+S, +, −).
- Abrir, guardar y «guardar como», con indicador de documento modificado.
- Aviso de cambios sin guardar al cerrar la ventana y al salir.
- Contador de palabras y caracteres, zoom de la fuente.
- Configuración persistente y registro (`logging`) en las rutas estándar del sistema.
- Reabre el último fichero y acepta un fichero como argumento («Abrir con…»).

PyObjC (que sí existe en macOS) **no tiene versión aquí: solo funciona en macOS.**

---

# 1. Panorama

| | Tkinter | pywebview | **PySide6** | **wxPython** | **Toga** |
|---|---|---|---|---|---|
| Qué es | Tk, en la biblioteca estándar | HTML/JS en Edge WebView2 | Qt 6 | wxWidgets (widgets nativos) | BeeWare: widgets nativos |
| Aspecto en Windows | Propio, algo anticuado | El de tu CSS | Propio de Qt, muy cuidado | Nativo (Win32) | Nativo (WinForms) |
| Instalación | Viene con Python | `pip install pywebview` | `pip install PySide6-Essentials` | `pip install wxPython` | `pip install toga` |
| Código para lo mismo | Medio | Medio (Python + JS) | Medio | Medio | **Más corto** |
| Curva de aprendizaje | Baja | Baja (si sabes web) | Media | Media | Baja-media |
| Empaquetado en este proyecto | PyInstaller | PyInstaller | PyInstaller | PyInstaller | Briefcase (`.msi`) |
| Licencia | PSF | BSD-3 | LGPL | wxWindows Library Licence | BSD-3 |
| Widgets disponibles | Pocos y básicos | Los de HTML | **Muchísimos** | Muchos | Los básicos y comunes |

---

# 2. Conceptos comunes

| Concepto | Tkinter | PySide6 | wxPython | Toga |
|---|---|---|---|---|
| Objeto de aplicación | `tk.Tk()` | `QApplication` | `wx.App` | `toga.App` |
| Ventana | `tk.Tk` | `QMainWindow` | `wx.Frame` | `toga.MainWindow` |
| Bucle de eventos | `mainloop()` | `app.exec()` | `app.MainLoop()` | `app.main_loop()` |
| Conectar un evento | `command=` / `bind()` | señales: `.triggered.connect(f)` | `Bind(wx.EVT_MENU, f, id=…)` | `on_change=` / `Command(f)` |
| Texto multilínea | `tk.Text` | `QPlainTextEdit` | `wx.TextCtrl` (`TE_MULTILINE`) | `toga.MultilineTextInput` |
| Menú y atajo | `Menu` + `bind` | `QAction` + `QKeySequence` | `Menu.Append(id, "…\tCtrl+S")` | `toga.Command(shortcut=…)` |
| Diálogo de fichero | `filedialog` | `QFileDialog` | `wx.FileDialog` | `OpenFileDialog` / `SaveFileDialog` |
| Documento modificado | Variable propia | `setWindowModified` | Variable propia (`IsModified`) | Variable propia |
| Confirmar al cerrar | `WM_DELETE_WINDOW` | `closeEvent` | `EVT_CLOSE` + `Veto()` | `on_close` / `on_exit` |
| Fichero como argumento | `sys.argv` | `sys.argv` | `sys.argv` | `sys.argv` |

**Regla común:** todos los toolkits son de un solo hilo para la interfaz. Las tareas largas van a un hilo o proceso aparte y devuelven resultados al hilo principal (Qt: señales; wx: `wx.CallAfter`; Toga: `async`/`await` o `app.loop.run_in_executor`; Tkinter: cola + `after()`).

---
# 3. PySide6 (Qt for Python)

Qt es un framework completo (widgets, gráficos, red, multimedia…) escrito en C++. PySide6 es el enlace oficial a Python, con licencia LGPL (PyQt6 es casi idéntico, con licencia GPL/comercial).

## Piezas del ejemplo (`notas_pyside6.py`)

```python
app = Aplicacion(sys.argv)          # QApplication (subclase)
ventana = Ventana()                 # QMainWindow con QPlainTextEdit como widget central
ventana.show()
sys.exit(app.exec())
```

- **Señales y ranuras:** `accion.triggered.connect(self.guardar)`. Los widgets emiten señales (`textChanged`, `modificationChanged`) a las que conectas funciones.
- **Atajos estándar:** `QKeySequence.StandardKey.Save` da **Ctrl+S** en Windows y Linux (y Cmd+S en macOS). «Salir» lleva `Ctrl+Q` explícito porque Windows no define un atajo estándar.
- **Menú Ayuda:** «Acerca de…» con `QAction.MenuRole.AboutRole` (en macOS Qt lo mueve al menú de la aplicación).
- **Documento modificado:** el título lleva `[*]` y `setWindowModified(True)` lo activa.
- **Cierre:** `closeEvent` puede llamar a `evento.ignore()` para cancelar.
- **Ficheros:** `QFileOpenEvent` solo existe en macOS; aquí el fichero llega por `sys.argv`.

## En Windows

- **Instalación:** `pip install PySide6-Essentials` (ruedas para Windows en PyPI; `Essentials` evita los módulos adicionales y reduce el tamaño).
- **Empaquetado:** `construir_app.ps1` usa **PyInstaller** (`--windowed`, `--icon icono.ico`) y genera `dist\NotasRapidasQt\NotasRapidasQt.exe`. Alternativa oficial: `pyside6-deploy` (usa Nuitka).
- **Icono de la barra de tareas:** `SetCurrentProcessExplicitAppUserModelID` (función `_id_de_aplicacion`) hace que Windows agrupe la ventana bajo el icono correcto.
- **Pantallas de alta densidad:** Qt 6 las gestiona solo; no hace falta `SetProcessDpiAwareness`.
- **Rutas:** configuración en `%APPDATA%\NotasRapidasPySide6\`, registro en `%LOCALAPPDATA%\NotasRapidasPySide6\Logs\app.log`.
- **Trampas:** el `.exe` pesa mucho (incluye Qt); los `.exe` sin firmar pueden dar falsos positivos de antivirus y el aviso de SmartScreen (ver `GUIA_APP_WINDOWS.md`); `setPlainText()` reinicia el estado de «modificado» y el historial de deshacer.

---

# 4. wxPython

wxWidgets usa los controles nativos de cada sistema; wxPython («Phoenix») es su enlace a Python.

## Piezas del ejemplo (`notas_wx.py`)

```python
app = Aplicacion(False)      # wx.App; OnInit() crea el marco
app.MainLoop()
```

- **IDs estándar:** `wx.ID_ABOUT` va al menú Ayuda; `wx.ID_EXIT`, `wx.ID_SAVE`, etc. dan etiquetas y comportamiento coherentes.
- **Aceleradores:** `"Guardar\tCtrl+S"`.
- **Eventos:** `self.Bind(wx.EVT_MENU, funcion, id=wx.ID_SAVE)`.
- **Cierre:** `EVT_CLOSE`; si el usuario cancela, `evento.Veto()` (solo si `evento.CanVeto()`; un cierre forzado del sistema no se puede vetar).
- **Texto:** `ChangeValue()` cambia el texto **sin** disparar `EVT_TEXT`; `SetValue()` sí lo dispara.
- **Antes de crear widgets** hace falta una instancia de `wx.App`; `wx.adv` (cuadro «Acerca de») hay que importarlo explícitamente.

## En Windows

- **Instalación:** `pip install wxPython` (hay ruedas para Windows en PyPI para las versiones habituales de Python; si `pip` intenta compilar desde fuentes, tu versión de Python no tiene rueda y conviene usar otra).
- **Empaquetado:** `construir_app.ps1` usa **PyInstaller** y genera `dist\NotasRapidasWx\NotasRapidasWx.exe`. (py2app, que se usa en macOS, no existe en Windows.)
- **Icono de la barra de tareas:** `_id_de_aplicacion()` fija el AppUserModelID.
- **Rutas:** `%APPDATA%\NotasRapidasWx\` y `%LOCALAPPDATA%\NotasRapidasWx\Logs\app.log`.
- **Trampas:** si la ventana se ve borrosa en pantallas 4K, revisa las propiedades de compatibilidad de DPI del `.exe`; los menús usan etiquetas con `\tCtrl+X` y `wx.ID_ABOUT` en el menú Ayuda.

---

# 5. Toga (BeeWare)

Toga es el toolkit de BeeWare: **un único código Python** con widgets nativos en macOS, Windows, Linux, iOS y Android. Se empaqueta con **Briefcase**.

## Piezas del ejemplo (`src/notas_rapidas_toga/app.py`)

```python
class NotasRapidas(toga.App):
    def startup(self):                       # se llama una vez al arrancar
        self.main_window = toga.MainWindow(title=…)
        self.main_window.content = toga.Box(children=[self.texto, self.estado], style=Pack(direction=COLUMN))
        self.main_window.show()
```

- **Layout con Pack:** `Pack(flex=1, direction=COLUMN, margin=…)`, parecido a CSS flexbox.
- **Comandos:** `toga.Command(funcion, text=…, shortcut=toga.Key.MOD_1 + "s", group=toga.Group.FILE)`. `MOD_1` es **Ctrl** en Windows y Linux (Cmd en macOS).
- **Handlers asíncronos:** las acciones pueden ser `async def`; los diálogos se esperan con `await`: `ruta = await self.main_window.dialog(toga.OpenFileDialog("Abrir", file_types=["txt"]))`.
- **Rutas estándar:** `self.paths.config`, `self.paths.logs`, `self.paths.data`, `self.paths.cache`.
- **Salir con confirmación:** `on_close` y `on_exit` son **síncronos** y devuelven `bool`. Como no pueden esperar un diálogo, el ejemplo devuelve `False`, lanza una tarea con `self.loop.create_task(...)` y, si el usuario acepta, llama a `self.exit()`.
- **Limitaciones frente a otros toolkits:** no hay diálogo de tres botones (Guardar / No guardar / Cancelar), así que se preguntan dos cosas seguidas; el indicador de «modificado» es un `•` en el título.
- Toga **cambia de API con frecuencia** entre versiones menores: el ejemplo está escrito para **Toga 0.5** (`~=0.5.0` en `pyproject.toml`).

## En Windows

- **Backend:** `toga-winforms` (usa Windows Forms de .NET mediante `pythonnet`; el .NET Framework viene con Windows 10 y 11).
- **Empaquetado: Briefcase.** `pyproject.toml` incluye la sección `[tool.briefcase.app.notas-rapidas-toga.windows]`. `construir_app.ps1` encapsula los comandos:

```powershell
.\construir_app.ps1 dev         # briefcase dev: ejecuta sin construir
.\construir_app.ps1             # briefcase create/update windows + build windows
.\construir_app.ps1 run         # briefcase run windows
.\construir_app.ps1 package     # genera un instalador .msi en dist\
```

- La primera vez Briefcase **descarga** Python incrustado y, para el `.msi`, la herramienta WiX: hace falta conexión a internet.
- El instalador se genera sin firma (`--adhoc-sign`); SmartScreen avisará al instalarlo.
- El proyecto debe tener la estructura `src\<modulo>\` con `__main__.py` y `app.py`.
- `bundle = "com.ejemplo"` + el nombre de la app forman el identificador. Cámbialo por el tuyo.
- Briefcase exige un fichero `LICENSE` (el del ejemplo es un marcador).
- **Rutas de datos y log:** las decide Toga (`app.paths`); normalmente cuelgan de `%APPDATA%` y `%LOCALAPPDATA%` con el nombre de la app.

---

# 6. Cómo elegir

| Si necesitas… | Elige |
|---|---|
| Lo más simple posible y sin dependencias | **Tkinter** |
| Reutilizar una interfaz web | **pywebview** |
| Una aplicación grande y profesional (muchos widgets, gráficos, tablas) | **PySide6** |
| Aspecto nativo y una API estable y madura | **wxPython** |
| Un único código para escritorio **y móvil** con aspecto nativo | **Toga** |

---

# 7. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| El `.exe` se abre y se cierra | Error de arranque | Construir con `-Consola` (PySide6, wxPython) y ejecutar desde PowerShell; revisar el log |
| `ModuleNotFoundError` solo en el `.exe` | PyInstaller no detectó el módulo | `--hidden-import` / `--collect-all` y reconstruir |
| PySide6: `.exe` enorme | Se instaló `PySide6` completo | Usar `PySide6-Essentials` |
| wxPython: `pip` compila durante minutos o falla | No hay rueda para tu versión de Python | Usar una versión de Python con rueda |
| wxPython: `AttributeError: module 'wx' has no attribute 'adv'` | Submódulo sin importar | `import wx.adv` |
| Toga: `TypeError` al construir `Pack(...)` o los diálogos | API de otra versión de Toga | Fijar `toga~=0.5.0` o adaptar el código |
| Toga: `briefcase create` falla por falta de licencia | No hay `LICENSE` | Sustituir el marcador por tu licencia |
| Toga: no cierra al pulsar la X con cambios sin guardar | Es el comportamiento: pregunta primero | Aceptar el diálogo |
| Windows Defender elimina el `.exe` | Falso positivo habitual con PyInstaller | Modo carpeta, firma o exclusión |
| «Windows protegió su PC» | SmartScreen | *Más información → Ejecutar de todas formas*, o firmar |
| `ps1` no se ejecuta | Política de PowerShell | Usar el `.bat` o `-ExecutionPolicy Bypass` |

---

# 8. Estado de verificación

| Variante | Qué se ha comprobado | Qué no |
|---|---|---|
| **PySide6** | La lógica de la ventana se ejecutó con Qt sin pantalla (`offscreen`) en Linux: menús, atajos, contador, marca de modificado, guardar, cargar, configuración y cierre | El aspecto real en Windows, el AppUserModelID y el empaquetado con PyInstaller |
| **Toga** | La lógica se ejecutó con el backend de pruebas (`toga_dummy`) de Toga 0.5.7 | El comportamiento real de WinForms (diálogos, `on_close`/`on_exit`) y Briefcase |
| **wxPython** | Solo la sintaxis | Todo lo demás (wxPython no se instala en el entorno de pruebas) |
| **Scripts `.ps1`** | Formato (UTF-8 con BOM, CRLF) | Su ejecución: PowerShell no está disponible en el entorno de pruebas |

Prueba cada variante en tu equipo antes de darla por buena. Si falla, mira el mensaje de error y el fichero `app.log`.

---

## Referencias

- Qt for Python: <https://doc.qt.io/qtforpython-6/> · wxPython: <https://docs.wxpython.org>
- Toga: <https://toga.readthedocs.io> · Briefcase: <https://briefcase.readthedocs.io>
- PyInstaller: <https://pyinstaller.org>

# Tres toolkits más para Linux: PySide6, wxPython y Toga

Comparación y detalles de las versiones de **Notas Rápidas** hechas con PySide6 (`app_pyside6/`), wxPython (`app_wx/`) y Toga (`app_toga/`) en Debian, Ubuntu y Linux Mint. Todas hacen lo mismo que las versiones de Tkinter y pywebview. Los `.desktop`, las rutas XDG, los paquetes `.deb`, glibc y las diferencias generales entre distribuciones se explican en `GUIA_APP_LINUX.md`.

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
| Qué es | Tk, en la biblioteca estándar | HTML/JS en WebKitGTK | Qt 6 | wxWidgets (widgets nativos) | BeeWare: widgets nativos |
| Aspecto en Linux | Propio, algo anticuado | El de tu CSS | Propio de Qt, muy cuidado | Nativo (GTK) | Nativo (GTK 3) |
| Instalación | `sudo apt install python3-tk` | `pip install pywebview` | `pip install PySide6-Essentials` | `sudo apt install python3-wxgtk4.0` | `pip install toga` |
| Código para lo mismo | Medio | Medio (Python + JS) | Medio | Medio | **Más corto** |
| Curva de aprendizaje | Baja | Baja (si sabes web) | Media | Media | Baja-media |
| Empaquetado en este proyecto | PyInstaller / `.deb` | `.deb` / local | PyInstaller / `.deb` / local | PyInstaller / `.deb` / local | Briefcase (`.deb` nativo) |
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

## En Linux (Debian, Ubuntu y Linux Mint)

Hay tres formas de instalarla:

| Vía | Cómo | Cuándo |
|---|---|---|
| **Paquete `.deb`** (`crear_deb.sh`) | Depende del paquete `python3-pyside6.qtwidgets` de la distribución | Debian 12+, Ubuntu 24.04+, Mint 22+ (comprueba `apt-cache policy python3-pyside6.qtwidgets`) |
| **Instalación local** (`instalar_local.sh`) | venv propio en `~/.local/share` con `pip install PySide6-Essentials` | Cualquier versión, incluidas Ubuntu 22.04 / Mint 21; sin `sudo` |
| **Binario PyInstaller** (`construir_app.sh`) | Binario con Qt incluido | Cuando no quieres depender de Python del sistema; construir en la distro más antigua (glibc) |

- **Biblioteca imprescindible con pip:** Qt 6 necesita `libxcb-cursor0` para el plugin `xcb`; sin ella la ventana no abre (`Could not load the Qt platform plugin "xcb"`). `sudo apt install libxcb-cursor0 libegl1 libxkbcommon-x11-0`. El paquete de apt las instala solo.
- **Icono y dock:** `app.setDesktopFileName("notas-rapidas-pyside6")` asocia la ventana con su `.desktop` (Wayland y X11); la ventana usa `icono_256.png`.
- **Wayland:** Qt usa X11 (XWayland) o Wayland según el entorno. Si ves la ventana borrosa en una sesión Wayland, prueba `QT_QPA_PLATFORM=wayland` (puede requerir el paquete `qt6-wayland`).
- **Rutas:** `~/.config/notas-rapidas-pyside6/` y `~/.local/state/notas-rapidas-pyside6/app.log`.

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

## En Linux (Debian, Ubuntu y Linux Mint)

- **Instalación:** `sudo apt install python3-wxgtk4.0`. **PyPI no publica ruedas de wxPython para Linux**, así que `pip install wxPython` compilaría durante mucho tiempo; usa el paquete de la distribución.
- **Vías de instalación:** `.deb` (depende de `python3-wxgtk4.0`), instalación local sin `sudo` (usa el Python del sistema) y binario PyInstaller (**experimental**: wxGTK depende de bibliotecas GTK del sistema).
- **Entorno de desarrollo:** el `.venv` se crea con `--system-site-packages` para que vea el `wx` de apt (la tarea *0b. Crear entorno de desarrollo* ya lo hace). La tarea *Comprobar wxPython en el .venv* lo verifica.
- **Icono y dock:** `SetClassName("NotasRapidasWx")` fija `WM_CLASS`, que debe coincidir con `StartupWMClass=NotasRapidasWx` del `.desktop`; `SetIcon` pone el icono de la ventana.
- **Rutas:** `~/.config/notas-rapidas-wx/` y `~/.local/state/notas-rapidas-wx/app.log`.
- **Versiones:** el paquete de apt trae la versión de wxPython de cada distro (por ejemplo 4.2.x en Debian 12 y 4.0.7 en Ubuntu 22.04); el ejemplo usa solo API disponible en 4.0.7 o posterior.

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

## En Linux (Debian, Ubuntu y Linux Mint)

- **Backend:** `toga-gtk` (GTK 3 mediante PyGObject). Compilar PyGObject y pycairo exige paquetes de desarrollo del sistema:

```bash
sudo apt install build-essential pkg-config python3-dev python3-venv libcairo2-dev \
     libgirepository1.0-dev gir1.2-gtk-3.0 libcanberra-gtk3-module
```

  (En Debian 13 y en Ubuntu 25.04 o posteriores puede hacer falta `libgirepository-2.0-dev` en lugar de `libgirepository1.0-dev`.)
- **Empaquetado: Briefcase con el backend `system`.** Genera un **`.deb`** nativo que usa el Python y GTK del sistema, con las dependencias declaradas en `pyproject.toml` (`system_requires` y `system_runtime_requires`, sección `linux.system.debian`):

```bash
./construir_app.sh dev         # briefcase dev: ejecuta sin construir
./construir_app.sh             # briefcase create/update + build linux system
./construir_app.sh run         # ejecuta la app construida
./construir_app.sh package     # genera el .deb en dist/
sudo apt install ./dist/*.deb
```

- `briefcase create` comprueba los paquetes del sistema y ofrece instalar los que falten.
- Ubuntu y Linux Mint se tratan como derivadas de Debian. Si Briefcase no reconociera tu distribución, puede construir dentro de un contenedor con `--target ubuntu:24.04` (requiere Docker).
- El `.deb` resultante es **específico de la versión de la distribución** en la que se construyó (a diferencia de los `.deb` `Architecture: all` de las demás variantes).
- **Rutas de datos y log:** las decide Toga (`app.paths`), según los directorios estándar de Linux, con el nombre de la app.

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

# 7. Diferencias entre Debian, Ubuntu y Linux Mint para estas variantes

| Tema | Debian 12 / 13 | Ubuntu 22.04 / 24.04 | Linux Mint 21 / 22 |
|---|---|---|---|
| PySide6 de apt (`python3-pyside6.qtwidgets`) | Sí (verifica con `apt-cache policy`) | 24.04 sí; 22.04 no | 22 sí; 21 no |
| wxPython de apt (`python3-wxgtk4.0`) | Sí | Sí | Sí |
| Toga con Briefcase (`linux system`) | Vendor `debian` | Vendor `ubuntu` (derivada de Debian) | Derivada de Ubuntu; si no se reconoce, usar `--target` con Docker |
| `sudo` configurado | Puede faltar: `su -` y `usermod -aG sudo USUARIO` | Sí | Sí |
| Sesión gráfica | Wayland (GNOME) | Wayland (GNOME) | X11 (Cinnamon) |

Los scripts, los `.desktop` y el código son idénticos en las tres; lo que cambia es la disponibilidad de paquetes de apt según la versión de la distribución. Para el resto de diferencias (versiones de Python y glibc, PEP 668, snap, iconos en el Escritorio), consulta la parte 3 de `GUIA_APP_LINUX.md`.

---
# 8. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| PySide6: `Could not load the Qt platform plugin "xcb"` | Falta `libxcb-cursor0` | `sudo apt install libxcb-cursor0` |
| PySide6: `.deb` no instalable (`python3-pyside6.qtwidgets` no existe) | Distribución sin ese paquete (Ubuntu 22.04, Mint 21) | Usar `instalar_local.sh` |
| PySide6: ventana borrosa en Wayland | Escalado fraccionario con XWayland | `QT_QPA_PLATFORM=wayland` o escalado entero |
| wxPython: `pip install wxPython` tarda mucho o falla | No hay ruedas para Linux en PyPI | `sudo apt install python3-wxgtk4.0` |
| wxPython: `Import "wx" could not be resolved` en VS Code | El `.venv` no ve los paquetes del sistema | Recrear con `--system-site-packages` |
| Toga: `pip` falla compilando PyGObject o pycairo | Faltan paquetes de desarrollo | Instalar los de la tarea *0e* (ver sección de Toga) |
| Toga: `briefcase create` no reconoce la distribución | Distribución derivada no contemplada | `--target ubuntu:24.04` (Docker) |
| Toga: `TypeError` al construir `Pack(...)` o los diálogos | API de otra versión de Toga | Fijar `toga~=0.5.0` o adaptar el código |
| Cualquiera: `ModuleNotFoundError` solo en el binario | PyInstaller no detectó el módulo | `--hidden-import` / `--collect-all` y reconstruir |
| Binario: `GLIBC_2.xx not found` | Construido en una distro más nueva | Construir en la más antigua, o usar el `.deb` |
| La app no aparece en el menú | Caché sin actualizar | `update-desktop-database ~/.local/share/applications`; cerrar y abrir sesión |
| Dos iconos en el dock | `WM_CLASS` ≠ `StartupWMClass` | Igualarlos |

---

# 9. Estado de verificación

| Variante | Qué se ha comprobado | Qué no |
|---|---|---|
| **PySide6** | La lógica de la ventana se ejecutó con Qt sin pantalla (`offscreen`) en Ubuntu 24.04: menús, atajos, icono, contador, marca de modificado, guardar, cargar, configuración y cierre | El aspecto real, la sesión Wayland y el empaquetado con PyInstaller |
| **Toga** | La lógica se ejecutó con el backend de pruebas (`toga_dummy`) de Toga 0.5.7 | GTK real (diálogos, `on_close`/`on_exit`) y Briefcase |
| **wxPython** | Solo la sintaxis | Todo lo demás (wxPython no se instala en el entorno de pruebas) |
| **`.deb` PySide6 y wxPython** | Se construyen, y su contenido, metadatos y dependencias son los esperados (`dpkg-deb`) | Su instalación con `apt` en Debian, Ubuntu y Mint |
| **`instalar_local.sh`** | Probados con módulos simulados: copia de ficheros, `.desktop`, lanzador, icono, `--escritorio`, `--desinstalar` y mensajes de error | La instalación real de PySide6 con pip y de wxPython con apt |

Prueba cada variante en tu equipo antes de darla por buena. Si falla, mira el mensaje de error y el fichero `app.log`.

---

## Referencias

- Qt for Python: <https://doc.qt.io/qtforpython-6/> · wxPython: <https://docs.wxpython.org>
- Toga: <https://toga.readthedocs.io> · Briefcase: <https://briefcase.readthedocs.io>
- PyInstaller: <https://pyinstaller.org>

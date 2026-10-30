# Crear una app de macOS con Python (doble clic sobre el icono)

Guía de conceptos básicos y avanzados, con el ejemplo **Notas Rápidas** (`notas_app.py`).

## Contenido del proyecto

| Fichero | Función |
|---|---|
| `notas_app.py` | Código de la aplicación (Tkinter) |
| `setup.py` | Configuración de empaquetado con py2app |
| `construir_app.sh` | Script que automatiza entorno, icono, build y firma |
| `icono.png` | Icono de ejemplo 1024×1024 (opcional) |
| `GUIA_APP_MACOS.md` | Esta guía |

## Inicio rápido

```bash
# 1. Comprueba que tu Python incluye Tk
python3 -c "import tkinter; print(tkinter.TkVersion)"   # debe mostrar 8.6 o superior

# 2. Prueba el script tal cual
python3 notas_app.py

# 3. Constrúyelo como app independiente
chmod +x construir_app.sh
./construir_app.sh          # genera dist/Notas Rápidas.app

# 4. Doble clic en dist/Notas Rápidas.app
```

---

# Parte 1. Conceptos básicos

## 1.1 ¿Qué es una «app» en macOS?

Un `.app` **no es un fichero, es una carpeta** (un *bundle*) que Finder muestra como un único icono. Estructura mínima:

```
Notas Rápidas.app/
└── Contents/
    ├── Info.plist          ← metadatos: nombre, identificador, versión, icono, tipos de documento…
    ├── MacOS/
    │   └── Notas Rápidas   ← ejecutable que lanza macOS al hacer doble clic
    ├── Resources/          ← icono .icns, tu código .py/.pyc, datos, imágenes
    └── Frameworks/         ← intérprete de Python y librerías incluidas
```

Puedes verla con clic derecho → *Mostrar contenido del paquete*.

**Idea clave:** hacer doble clic sobre un `.py` no crea una app. Hace falta un bundle con un ejecutable y un `Info.plist`. Eso es lo que generan las herramientas de empaquetado.

## 1.2 Piezas necesarias

1. **Código Python** con una interfaz gráfica y un bucle de eventos.
2. **Un toolkit de interfaz** (GUI).
3. **Un empaquetador** que construya el bundle e incluya el intérprete.
4. **Un icono** en formato `.icns` (opcional, pero recomendable).
5. **Firma de código** para que macOS no bloquee la app (ver parte 2).

## 1.3 Elegir el toolkit de interfaz

| Toolkit | Ventajas | Inconvenientes |
|---|---|---|
| **Tkinter** | Viene con Python, sin dependencias, ligero | Aspecto más básico |
| **PySide6 / PyQt6** | Muy completo, aspecto profesional | Bundle grande (>100 MB); licencias (LGPL / GPL) |
| **wxPython** | Widgets nativos de macOS | Instalación más pesada |
| **Toga (BeeWare)** | Nativo, multiplataforma, integrado con *Briefcase* | Ecosistema más joven |
| **pywebview / Flet** | Interfaz con HTML/JS dentro de una ventana nativa | Dos mundos que mantener |
| **Kivy** | Táctil, juegos | Aspecto no nativo |

El ejemplo usa Tkinter por ser el más sencillo de reproducir.

> **Aviso sobre Tk en macOS.** Usa Python de [python.org](https://www.python.org/downloads/macos/) (incluye Tk 8.6 reciente) o Homebrew con `brew install python-tk`. El Python que trae Xcode Command Line Tools usa un Tk antiguo con fallos de dibujo y de modo oscuro.

## 1.4 El bucle de eventos

Una app gráfica no «se ejecuta y termina»: construye ventanas, llama a `mainloop()` y se queda esperando eventos (clics, teclas, menús) que despachan a *callbacks*.

```python
root = tk.Tk()
app = NotasApp(root)   # crea widgets y registra callbacks
root.mainloop()        # bloquea aquí hasta cerrar la ventana
```

Consecuencia: **cualquier tarea larga dentro de un callback congela la ventana** (la «bola de colores» de macOS). Ver hilos en la parte 2.

## 1.5 Formas de lograr el «doble clic»

| Método | Cuándo usarlo | Resultado |
|---|---|---|
| **py2app** (recomendado en este ejemplo) | App real, específica de macOS | `.app` independiente, con Python incluido |
| **PyInstaller** | También Windows/Linux con la misma herramienta | `.app` independiente |
| **Briefcase (BeeWare)** | Proyecto multiplataforma con Toga | `.app`, `.dmg`, instaladores |
| **Fichero `.command`** | Uso personal rápido | Abre Terminal, no es una app |
| **Automator / Atajos → «Ejecutar script de shell»** | Lanzador para usarte tú | `.app` ligera que llama a tu Python instalado (no es independiente) |
| **Platypus** | Envolver un script en `.app` con interfaz gráfica | `.app` sencilla |

Ejemplo de `.command` (doble clic, requiere `chmod +x lanzar.command`):

```bash
#!/bin/bash
cd "$(dirname "$0")"
python3 notas_app.py
```

## 1.6 Flujo con py2app

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install py2app
python setup.py py2app -A    # modo alias: rápido, para desarrollo
python setup.py py2app       # modo independiente: para distribuir
```

- **Modo alias (`-A`)**: el `.app` apunta a tu código fuente y a tu entorno. Compila en segundos, pero solo funciona en tu Mac. Útil para probar el icono y el `Info.plist`.
- **Modo independiente**: copia intérprete, librerías y código dentro del bundle. Es el que se distribuye.

El resultado queda en `dist/`. La carpeta `build/` es temporal.

## 1.7 El icono `.icns`

Parte de un PNG de 1024×1024 y se convierte con herramientas de macOS (lo hace `construir_app.sh`):

```bash
mkdir icono.iconset
for s in 16 32 128 256 512; do
  sips -z $s $s icono.png --out icono.iconset/icon_${s}x${s}.png
  sips -z $((s*2)) $((s*2)) icono.png --out icono.iconset/icon_${s}x${s}@2x.png
done
iconutil -c icns icono.iconset
```

Y se indica en `setup.py` con `"iconfile": "icono.icns"`. Si el icono no se actualiza en Finder, ejecuta `touch "dist/Notas Rápidas.app"` o reinicia Finder (`killall Finder`).

## 1.8 Anatomía del código de ejemplo

- **Constantes y rutas** al inicio (`APP_NAME`, `SUPPORT_DIR`, `LOG_FILE`).
- **Clase `NotasApp`**: un método por responsabilidad (`_crear_menus`, `_crear_widgets`, `guardar`, `salir`…).
- **Callbacks** conectados con `command=` y `bind()`.
- **`main()`** como único punto de entrada, protegido con `if __name__ == "__main__":`.

---

# Parte 2. Conceptos avanzados

## 2.1 Integración con el menú nativo de macOS

Tk enlaza ciertos comandos Tcl con el menú de aplicación (el que lleva el nombre de la app junto a la manzana):

```python
root.createcommand("tkAboutDialog", self.acerca_de)       # «Acerca de Notas Rápidas»
root.createcommand("::tk::mac::Quit", self.salir)         # Cmd+Q y «Salir»
root.createcommand("::tk::mac::OpenDocument", self.abrir_desde_finder)
root.createcommand("::tk::mac::ShowPreferences", self.preferencias)  # «Ajustes…» (opcional)
```

Por defecto, **Cmd+Q ignora `WM_DELETE_WINDOW`**; por eso hay que enlazar `::tk::mac::Quit` si quieres preguntar por cambios sin guardar.

## 2.2 Atajos de teclado: Cmd, no Ctrl

En Tk para macOS la tecla Cmd es `Command`. El ejemplo define `MOD = "Command" if IS_MAC else "Control"` y enlaza `<Command-s>`, etc. Los símbolos `+` y `=` se enlazan como `plus` y `equal`.

## 2.3 Dónde guardar datos: nunca dentro del `.app`

El bundle debe tratarse como **solo lectura** (y firmado: modificarlo invalida la firma). Rutas estándar:

| Uso | Ruta |
|---|---|
| Configuración y datos de la app | `~/Library/Application Support/<App>/` |
| Registros | `~/Library/Logs/<App>/` |
| Cachés | `~/Library/Caches/<App>/` |
| Preferencias simples | `~/Library/Preferences/` (con `defaults`/plist) |
| Documentos del usuario | Los elige el usuario con un diálogo de guardado |

```python
SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "NotasRapidas"
```

## 2.4 Recursos dentro del bundle

Al empaquetar, tus ficheros (imágenes, plantillas) viajan en `Contents/Resources`. Con py2app, la variable de entorno `RESOURCEPATH` apunta ahí:

```python
def resource_path(rel):
    base = os.environ.get("RESOURCEPATH") or Path(__file__).resolve().parent
    return Path(base) / rel
```

Para incluirlos: `OPTIONS = {"resources": ["datos/", "logo.png"]}`. No uses rutas relativas al directorio actual (`open("logo.png")`): al lanzar desde Finder el directorio de trabajo es `/`.

## 2.5 Registro y errores: una app no tiene terminal

Sin consola, los fallos son silenciosos: la app «rebota» en el Dock y desaparece. Buenas prácticas, todas presentes en el ejemplo:

- `logging` a fichero en `~/Library/Logs`.
- `sys.excepthook` para excepciones fuera de Tk.
- `root.report_callback_exception` para excepciones dentro de callbacks.
- Mostrar `messagebox.showerror` al usuario cuando proceda.

**Depurar un bundle** que no arranca: ejecútalo desde Terminal para ver la salida estándar:

```bash
"dist/Notas Rápidas.app/Contents/MacOS/Notas Rápidas"
```

También puedes consultar *Console.app* o los informes en `~/Library/Logs/DiagnosticReports/`.

## 2.6 No bloquear la interfaz: hilos y cola

Tkinter **no es seguro entre hilos**: solo el hilo principal puede tocar widgets. Patrón recomendado: el hilo de trabajo escribe en una `queue.Queue` y la interfaz la consulta con `after()`.

```python
import queue, threading

class App:
    def __init__(self, root):
        self.root = root
        self.cola = queue.Queue()
        self.root.after(100, self._sondear)

    def lanzar_tarea(self):
        threading.Thread(target=self._trabajo, daemon=True).start()

    def _trabajo(self):                      # hilo secundario
        resultado = tarea_larga()
        self.cola.put(("fin", resultado))

    def _sondear(self):                      # hilo principal
        try:
            while True:
                tipo, dato = self.cola.get_nowait()
                if tipo == "fin":
                    self.mostrar(dato)
        except queue.Empty:
            pass
        self.root.after(100, self._sondear)
```

Para red o E/S pesada usa hilos; para cálculo intensivo, `multiprocessing` (en apps empaquetadas llama a `multiprocessing.freeze_support()` al inicio de `main()`).

## 2.7 `Info.plist`: lo que se declara en `setup.py`

| Clave | Para qué sirve |
|---|---|
| `CFBundleName` / `CFBundleDisplayName` | Nombre en menú y Finder |
| `CFBundleIdentifier` | Identificador único en notación inversa (`com.tuempresa.app`); lo usan firma, permisos y preferencias |
| `CFBundleShortVersionString` / `CFBundleVersion` | Versión visible / de compilación |
| `LSMinimumSystemVersion` | Versión mínima de macOS |
| `NSHighResolutionCapable` | Renderizado Retina nítido |
| `CFBundleDocumentTypes` | Tipos de fichero que la app sabe abrir («Abrir con…», arrastrar al icono) |
| `LSUIElement` | `True` = app sin icono en el Dock (utilidad de barra de menús) |
| `NSDesktopFolderUsageDescription`, `NSDocumentsFolderUsageDescription`, `NSCameraUsageDescription`, `NSMicrophoneUsageDescription` | Texto del aviso de privacidad (TCC) cuando la app accede a esos recursos |

Si usas cámara, micrófono o carpetas protegidas y no declaras la clave `...UsageDescription`, macOS puede cerrar la app o denegar el acceso sin avisar.

## 2.8 Arquitecturas: Apple Silicon e Intel

- Un Python **arm64** produce una app solo para Apple Silicon; uno **x86_64** (Rosetta) solo Intel.
- Para una app **universal2** necesitas un intérprete y dependencias universal2. El instalador de python.org lo es. Comprueba con:

```bash
file "dist/Notas Rápidas.app/Contents/MacOS/Notas Rápidas"
lipo -archs "dist/Notas Rápidas.app/Contents/MacOS/Notas Rápidas"
```

- Las librerías con extensiones en C (NumPy, Pillow…) deben tener ruedas universal2 o compilarse por separado.

## 2.9 Firma, Gatekeeper y notarización

macOS comprueba el origen de cualquier app descargada (**Gatekeeper**).

| Situación | Qué hacer |
|---|---|
| App para ti, construida en tu Mac | Firma ad-hoc: `codesign --force --deep --sign - "App.app"` |
| App enviada a otras personas, sin cuenta de desarrollador | El usuario debe hacer clic derecho → *Abrir* (o *Ajustes → Privacidad y seguridad → Abrir igualmente*) la primera vez |
| Distribución profesional | Firmar con *Developer ID Application* (Apple Developer Program), activar *Hardened Runtime* y **notarizar** |

Flujo de distribución profesional:

```bash
# 1. Firmar con hardened runtime
codesign --force --deep --options runtime \
  --entitlements entitlements.plist \
  --sign "Developer ID Application: Tu Nombre (TEAMID)" "dist/Notas Rápidas.app"

# 2. Comprimir y enviar a notarizar
ditto -c -k --keepParent "dist/Notas Rápidas.app" NotasRapidas.zip
xcrun notarytool submit NotasRapidas.zip \
  --apple-id tu@correo --team-id TEAMID --password "<contraseña de app>" --wait

# 3. Grapar el ticket al bundle y verificar
xcrun stapler staple "dist/Notas Rápidas.app"
spctl --assess --type execute --verbose "dist/Notas Rápidas.app"
```

Con *Hardened Runtime*, los intérpretes de Python suelen necesitar un `entitlements.plist` con claves como `com.apple.security.cs.allow-unsigned-executable-memory` y `com.apple.security.cs.disable-library-validation`. Pruébalo siempre en un Mac limpio.

## 2.10 Distribución: `.zip` o `.dmg`

```bash
# ZIP conservando atributos del bundle
ditto -c -k --keepParent "dist/Notas Rápidas.app" NotasRapidas.zip

# DMG sencillo
hdiutil create -volname "Notas Rápidas" -srcfolder dist \
  -ov -format UDZO NotasRapidas.dmg
```

Para un DMG con fondo y acceso directo a *Aplicaciones* existe la herramienta `create-dmg` (`brew install create-dmg`).

## 2.11 Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| El icono rebota en el Dock y la app se cierra | Excepción al arrancar | Ejecutar el binario del bundle desde Terminal; revisar `~/Library/Logs/<App>/app.log` |
| `ModuleNotFoundError` solo en el `.app` | py2app no detectó una importación dinámica | Añadir a `"packages"` o `"includes"` en `setup.py` |
| Ventana vacía o dibujo defectuoso | Tk 8.5 del Python de Xcode | Usar Python de python.org |
| «No se puede abrir porque no se puede verificar el desarrollador» | Gatekeeper | Firmar/notarizar, o clic derecho → Abrir |
| «App dañada» tras copiarla por red | Atributo de cuarentena | `xattr -dr com.apple.quarantine "App.app"` (solo si confías en la app) |
| No encuentra ficheros de datos | Rutas relativas | Usar `resource_path()` y `Application Support` |
| El `.app` pesa cientos de MB | Dependencias grandes (Qt, NumPy…) | Excluir con `"excludes"`, usar entorno virtual limpio |
| Cmd+Q cierra sin preguntar | Falta `::tk::mac::Quit` | Enlazarlo (ver 2.1) |
| El icono no cambia | Caché de iconos | `touch` al `.app` o `killall Finder` |
| El diálogo de Ayuda/Acerca no aparece | `tkAboutDialog` no registrado | Registrar el comando antes de `mainloop()` |

## 2.12 Lista de verificación antes de entregar

- [ ] Funciona como script y como `.app` independiente.
- [ ] Probado en un Mac distinto (o usuario limpio) sin Python instalado.
- [ ] `CFBundleIdentifier`, versión y copyright actualizados.
- [ ] Icono `.icns` incluido.
- [ ] Datos de usuario fuera del bundle.
- [ ] Registro en `~/Library/Logs` y manejo de excepciones.
- [ ] Firmado (ad-hoc, o Developer ID + notarizado si se distribuye).
- [ ] Comprobada la arquitectura (`lipo -archs`).

---

## Referencias

- py2app: <https://py2app.readthedocs.io>
- Tkinter (documentación de Python): <https://docs.python.org/3/library/tkinter.html>
- Notas sobre Tk en macOS: <https://www.tcl-lang.org/man/tcl8.6/TkCmd/tk_mac.htm>
- Briefcase (BeeWare): <https://briefcase.readthedocs.io>
- PyInstaller: <https://pyinstaller.org>
- Firma y notarización: <https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution>

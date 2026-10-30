# Crear una app de Windows con Python (doble clic sobre el icono)

Guía de conceptos básicos y avanzados, con el ejemplo **Notas Rápidas** (`notas-rapidas/app_tk/notas_app.py`).

## Contenido del proyecto

| Fichero | Función |
|---|---|
| `notas-rapidas/app_tk/notas_app.py` | Código de la aplicación (Tkinter) |
| `notas-rapidas/app_tk/construir_app.ps1` | Script que crea el entorno, el icono y el `.exe` con PyInstaller |
| `notas-rapidas/app_tk/construir_app.bat` | Lanzador con doble clic para el script anterior |
| `notas-rapidas/app_tk/icono.png`, `icono.ico` | Icono de ejemplo |
| `docs/GUIA_APP_WINDOWS.md` | Esta guía |

## Inicio rápido

```powershell
# 1. Comprueba que tu Python incluye Tk
py -3 -c "import tkinter; print(tkinter.TkVersion)"   # debe mostrar 8.6 o superior

# 2. Prueba el script tal cual
py -3 notas-rapidas\app_tk\notas_app.py

# 3. Constrúyelo como app independiente
cd notas-rapidas/app_tk
.\construir_app.ps1          # o doble clic en construir_app.bat

# 4. Doble clic en dist\NotasRapidas\NotasRapidas.exe
```

---

# Parte 1. Conceptos básicos

## 1.1 ¿Qué es una «app» en Windows?

En Windows, una aplicación es un **ejecutable `.exe`** (formato PE) que el sistema lanza al hacer doble clic. A diferencia de macOS no hay «bundle»: el `.exe` va acompañado de las librerías (`.dll`) y datos que necesita.

Con PyInstaller obtienes dos formatos:

| Formato | Resultado | Ventajas | Inconvenientes |
|---|---|---|---|
| **Carpeta** (`--onedir`, por defecto en el ejemplo) | `dist\NotasRapidas\NotasRapidas.exe` + carpeta `_internal` con DLL y recursos | Arranque rápido; menos falsos positivos de antivirus; fácil de depurar | Hay que distribuir la carpeta completa (zip o instalador) |
| **Un solo `.exe`** (`--onefile`) | `dist\NotasRapidas.exe` | Cómodo de enviar | Se descomprime en una carpeta temporal en cada arranque (más lento); más falsos positivos |

Estructura del modo carpeta:

```
dist\NotasRapidas\
├── NotasRapidas.exe      ← lo que se ejecuta con doble clic
└── _internal\            ← intérprete de Python, DLL, librerías, icono.ico, datos
```

**Idea clave:** hacer doble clic sobre un `.py` ejecuta el script con el Python instalado y abre una consola negra. Una «app» necesita un `.exe` independiente, sin consola y con icono propio.

## 1.2 Piezas necesarias

1. **Código Python** con una interfaz gráfica y un bucle de eventos.
2. **Un toolkit de interfaz** (GUI).
3. **Un empaquetador** que construya el `.exe` e incluya el intérprete (PyInstaller).
4. **Un icono** en formato `.ico` (con varios tamaños: 16 a 256 px).
5. **Firma de código** para evitar el aviso de SmartScreen (ver parte 2).

## 1.3 Elegir el toolkit de interfaz

| Toolkit | Ventajas | Inconvenientes |
|---|---|---|
| **Tkinter** | Viene con Python, sin dependencias, ligero | Aspecto algo anticuado |
| **PySide6 / PyQt6** | Muy completo, aspecto profesional | Tamaño grande; licencias (LGPL / GPL) |
| **wxPython** | Widgets nativos de Windows | Instalación más pesada |
| **customtkinter** | Tkinter con aspecto moderno | Dependencia adicional |
| **pywebview / Flet** | Interfaz HTML/JS o Flutter en ventana nativa | Dos mundos que mantener |
| **Toga (BeeWare)** | Nativo y multiplataforma | Ecosistema más joven |

El ejemplo usa Tkinter por ser el más sencillo de reproducir. La variante con HTML está en `GUIA_PYWEBVIEW_WINDOWS.md`.

> **Python en Windows:** instala Python desde [python.org](https://www.python.org/downloads/windows/) y deja marcada la casilla *tcl/tk and IDLE*. Evita la versión de Microsoft Store para desarrollar: redirige las escrituras en `AppData` a una carpeta privada y puede confundirte al buscar el log y la configuración.

## 1.4 El bucle de eventos

Una app gráfica no «se ejecuta y termina»: construye ventanas, llama a `mainloop()` y se queda esperando eventos (clics, teclas, menús) que despachan a *callbacks*.

```python
root = tk.Tk()
app = NotasApp(root)   # crea widgets y registra callbacks
root.mainloop()        # bloquea aquí hasta cerrar la ventana
```

Consecuencia: **una tarea larga dentro de un callback congela la ventana** («No responde» en la barra de título). Ver hilos en la parte 2.

## 1.5 Formas de lograr el «doble clic»

| Método | Cuándo usarlo | Resultado |
|---|---|---|
| **PyInstaller** (usado en este ejemplo) | App real y distribuible | `.exe` independiente con Python incluido |
| **Nuitka** | Más rendimiento y menos falsos positivos | `.exe` compilado a C |
| **cx_Freeze** | Alternativa a PyInstaller, genera también MSI | `.exe` + instalador MSI |
| **Briefcase (BeeWare)** | Proyecto multiplataforma con Toga | `.exe` + instalador MSI |
| **Fichero `.pyw`** | Uso personal rápido | Se ejecuta sin consola con tu Python instalado; no es independiente |
| **Fichero `.bat` / acceso directo** | Lanzador para ti | Llama a `pythonw.exe script.py`; requiere Python instalado |

Ejemplo de acceso directo sin consola (propiedades → *Destino*):

```
"C:\Users\tu_usuario\AppData\Local\Programs\Python\Python313\pythonw.exe" "C:\ruta\notas_app.py"
```

`pythonw.exe` es el intérprete «sin consola»; renombrar el script a `notas_app.pyw` consigue lo mismo con doble clic.

## 1.6 Flujo con PyInstaller

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name NotasRapidas --icon icono.ico --add-data "icono.ico;." notas_app.py
```

Opciones esenciales:

| Opción | Significado |
|---|---|
| `--windowed` (`-w`) | Sin ventana de consola (app gráfica) |
| `--console` | Con consola: útil para ver errores al depurar |
| `--onedir` / `--onefile` | Carpeta / un solo `.exe` |
| `--icon icono.ico` | Icono del `.exe` |
| `--add-data "origen;destino"` | Incluye ficheros (**en Windows el separador es `;`**) |
| `--hidden-import modulo` | Fuerza un módulo que PyInstaller no detecta |
| `--collect-all paquete` | Incluye todo un paquete (código, datos, binarios) |
| `--name` | Nombre del `.exe` (evita tildes y espacios) |
| `--version-file` | Metadatos (versión, copyright) visibles en *Propiedades* |
| `--clean` | Limpia cachés antes de construir |

Genera además un `NotasRapidas.spec` que puedes editar y reutilizar (`pyinstaller NotasRapidas.spec`).

## 1.7 El icono `.ico`

Un `.ico` contiene varios tamaños. Con Pillow:

```python
from PIL import Image
Image.open("icono.png").convert("RGBA").save(
    "icono.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
```

Si Windows no actualiza el icono del `.exe` o del acceso directo, es la caché de iconos: reinicia el Explorador de archivos, o ejecuta `ie4uinit.exe -show`.

## 1.8 Anatomía del código de ejemplo

- **Constantes y rutas** al inicio (`APP_NAME`, `SUPPORT_DIR`, `LOG_FILE`).
- **Clase `NotasApp`**: un método por responsabilidad (`_crear_menus`, `_crear_widgets`, `guardar`, `salir`…).
- **Callbacks** conectados con `command=` y `bind()`.
- **`main()`** como único punto de entrada, protegido con `if __name__ == "__main__":`.

---

# Parte 2. Conceptos avanzados

## 2.1 Atajos de teclado y menús

En Windows la tecla modificadora es **Ctrl**: `<Control-s>`, `<Control-o>`… Los símbolos `+` y `=` se enlazan como `plus` y `equal`. Convenciones del sistema que conviene respetar:

| Acción | Atajo |
|---|---|
| Rehacer | `Ctrl+Y` (en Tk para Windows; algunas apps usan también `Ctrl+Shift+Z`) |
| Salir | `Alt+F4` (lo gestiona el sistema; enlázalo con `WM_DELETE_WINDOW`) |
| Menú «Ayuda → Acerca de» | Va en el menú Ayuda, no en un menú de aplicación como en macOS |

`root.protocol("WM_DELETE_WINDOW", self.salir)` intercepta el botón X y `Alt+F4` para preguntar por cambios sin guardar.

## 2.2 Pantallas de alta densidad (DPI)

Sin declarar compatibilidad, Windows escala la ventana como un bitmap y se ve borrosa en pantallas 4K o con escala del 125 % o más. El ejemplo lo resuelve al arrancar:

```python
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
```

Hazlo **antes** de crear `tk.Tk()`. Con PySide6 y pywebview no hace falta.

## 2.3 Dónde guardar datos: nunca junto al `.exe`

La carpeta de instalación (`C:\Program Files\...`) es de solo lectura para usuarios normales. Rutas estándar:

| Uso | Ruta | Variable |
|---|---|---|
| Configuración que acompaña al perfil | `C:\Users\<u>\AppData\Roaming\<App>\` | `%APPDATA%` |
| Datos locales, logs, cachés | `C:\Users\<u>\AppData\Local\<App>\` | `%LOCALAPPDATA%` |
| Datos compartidos por todos los usuarios | `C:\ProgramData\<App>\` | `%PROGRAMDATA%` |
| Documentos del usuario | Los elige el usuario con un diálogo | — |

```python
SUPPORT_DIR = Path(os.environ["APPDATA"]) / "NotasRapidas"
LOG_DIR = Path(os.environ["LOCALAPPDATA"]) / "NotasRapidas" / "Logs"
```

Para abrir la carpeta: `Win+R` → `%APPDATA%`.

## 2.4 Recursos dentro del `.exe`

PyInstaller extrae los datos añadidos con `--add-data` en `sys._MEIPASS` (en modo carpeta, la subcarpeta `_internal`):

```python
def resource_path(rel):
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return Path(base) / rel
```

Nunca uses rutas relativas al directorio actual (`open("logo.png")`): al lanzar con doble clic o desde un acceso directo, el directorio de trabajo puede ser cualquiera. Tampoco uses `__file__` sin esta función.

## 2.5 Registro y errores: una app «windowed» no tiene consola

Con `--windowed`, `sys.stdout` y `sys.stderr` valen `None`: un `print()` puede incluso lanzar una excepción. Por eso el ejemplo:

- Escribe con `logging` a `%LOCALAPPDATA%\NotasRapidas\Logs\app.log`.
- Instala `sys.excepthook` para excepciones fuera de Tk.
- Usa `root.report_callback_exception` para excepciones dentro de callbacks.
- Muestra `messagebox.showerror` cuando procede.

**Depurar un `.exe` que no arranca:** construye con `-Consola` (`.\construir_app.ps1 -Consola`) y ejecútalo desde PowerShell: verás el traceback en pantalla.

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
        self.cola.put(("fin", tarea_larga()))

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

**`multiprocessing` en un `.exe`:** en Windows usa *spawn*, que relanza el ejecutable. Sin `multiprocessing.freeze_support()` al principio de `main()`, la app se abre en bucle infinito de ventanas. El ejemplo ya lo incluye.

## 2.7 Metadatos del `.exe` y manifiesto

Para que *Propiedades → Detalles* muestre versión, empresa y copyright, usa un fichero de versión:

```powershell
pip install pyinstaller-versionfile
create-version-file metadata.yml --outfile version.txt
pyinstaller --version-file version.txt ...
```

PyInstaller incluye un manifiesto con `asInvoker` (se ejecuta con los permisos del usuario). Solo pide administrador (`--uac-admin`) si es imprescindible: dispara el aviso UAC y complica los accesos directos y «Abrir con».

## 2.8 «Abrir con…» y asociación de ficheros

Cuando el usuario arrastra un fichero sobre el `.exe` o usa *Abrir con*, Windows lo pasa como **argumento**: `sys.argv[1]`. El ejemplo lo gestiona en `main()`.

Para que `.txt`/`.md` ofrezcan tu app por defecto hay que registrar la asociación en el **registro de Windows** (lo hace el instalador, ver 2.10) o el usuario la elige una vez en *Abrir con → Elegir otra aplicación*.

## 2.9 Antivirus, SmartScreen y firma de código

Los `.exe` creados con PyInstaller sin firmar suelen provocar:

- **Falsos positivos** en antivirus (especialmente con `--onefile`).
- **Windows SmartScreen:** «Windows protegió su PC» al ejecutar un `.exe` descargado.

Mitigaciones, de menor a mayor esfuerzo:

| Medida | Efecto |
|---|---|
| Preferir `--onedir` a `--onefile` | Reduce falsos positivos |
| Construir PyInstaller desde fuente (con *bootloader* propio) o usar Nuitka | Menos coincidencias con firmas conocidas |
| Enviar el `.exe` a Microsoft Defender como falso positivo | Soluciona casos concretos |
| **Firmar con certificado de firma de código** (`signtool`) | Identifica al editor; SmartScreen gana reputación con el tiempo |
| Certificado EV o servicio de firma en la nube (por ejemplo, Azure Trusted Signing) | Reputación inmediata en SmartScreen |

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  /f certificado.pfx /p "<contraseña>" dist\NotasRapidas\NotasRapidas.exe
signtool verify /pa dist\NotasRapidas\NotasRapidas.exe
```

Para uso personal o dentro de tu centro, el usuario puede pulsar *Más información → Ejecutar de todas formas*. Los ficheros descargados llevan una marca (*Mark of the Web*); la opción *Desbloquear* en las propiedades del `.zip` la elimina.

## 2.10 Distribución: zip o instalador

**ZIP:**

```powershell
Compress-Archive -Path dist\NotasRapidas -DestinationPath NotasRapidas-1.0.0.zip
```

El usuario descomprime y ejecuta. Sencillo, pero sin acceso directo ni desinstalación.

**Instalador con Inno Setup** (gratuito, <https://jrsoftware.org/isinfo.php>): genera `NotasRapidas-Setup.exe`, crea accesos directos, asociación de ficheros y desinstalador. Fragmento de `instalador.iss`:

```ini
[Setup]
AppName=Notas Rápidas
AppVersion=1.0.0
DefaultDirName={autopf}\NotasRapidas
DefaultGroupName=Notas Rápidas
OutputBaseFilename=NotasRapidas-Setup
SetupIconFile=icono.ico
PrivilegesRequired=lowest

[Files]
Source: "dist\NotasRapidas\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Notas Rápidas"; Filename: "{app}\NotasRapidas.exe"
Name: "{autodesktop}\Notas Rápidas"; Filename: "{app}\NotasRapidas.exe"; Tasks: icono

[Tasks]
Name: "icono"; Description: "Crear acceso directo en el Escritorio"

[Run]
Filename: "{app}\NotasRapidas.exe"; Description: "Ejecutar Notas Rápidas"; Flags: postinstall nowait
```

Otras vías: **MSIX** (Microsoft Store, requiere firma), **WiX/MSI** (entornos corporativos), **winget** (publicar en el gestor de paquetes).

## 2.11 Arquitectura y versiones de Windows

- Un Python **64 bits** genera un `.exe` de 64 bits (lo habitual hoy). Para equipos de 32 bits hay que construir con Python de 32 bits.
- Windows on ARM ejecuta x64 mediante emulación; para código nativo ARM64 se necesita Python ARM64 y dependencias compatibles.
- Compila siempre en la **versión más antigua de Windows** que quieras soportar y prueba en un equipo limpio o máquina virtual sin Python instalado.
- Python 3.9 y posteriores no funcionan en Windows 7/8.

## 2.12 Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| La app se abre y se cierra | Excepción al arrancar | Construir con `-Consola`; revisar `%LOCALAPPDATA%\NotasRapidas\Logs\app.log` |
| `ModuleNotFoundError` solo en el `.exe` | PyInstaller no detectó una importación dinámica | `--hidden-import` o `--collect-all` |
| No encuentra imágenes o datos | Ruta relativa o falta `--add-data` | Usar `resource_path()` y revisar el separador `;` |
| Ventana borrosa en pantalla 4K | Falta declarar DPI | `SetProcessDpiAwareness(1)` antes de `tk.Tk()` |
| Se abren ventanas sin parar | Falta `freeze_support()` con `multiprocessing` | Llamarla al inicio de `main()` |
| `AttributeError: 'NoneType'... write` | `print()` con `--windowed` | Usar `logging` |
| Windows Defender bloquea o elimina el `.exe` | Falso positivo | `--onedir`, firma, exclusión o envío a Microsoft |
| «Windows protegió su PC» | SmartScreen | Firmar o *Más información → Ejecutar de todas formas* |
| El script `.ps1` no se ejecuta | Política de ejecución | Usar el `.bat` o `powershell -ExecutionPolicy Bypass -File ...` |
| El icono no cambia | Caché de iconos | Reiniciar el Explorador o `ie4uinit.exe -show` |
| Error al escribir en `Program Files` | Sin permisos | Guardar datos en `%APPDATA%` / `%LOCALAPPDATA%` |
| `.exe` muy grande | Dependencias pesadas | Entorno virtual limpio, `--exclude-module`, UPX con cautela |
| No aparece `tkinter` | Python sin Tk | Reinstalar Python marcando *tcl/tk and IDLE* |

## 2.13 Lista de verificación antes de entregar

- [ ] Funciona como script y como `.exe` independiente.
- [ ] Probado en un equipo o máquina virtual sin Python instalado.
- [ ] Versión, nombre y copyright actualizados.
- [ ] Icono `.ico` con varios tamaños.
- [ ] Datos de usuario en `%APPDATA%` / `%LOCALAPPDATA%`, nunca junto al `.exe`.
- [ ] `logging` a fichero; sin `print()` en la versión `--windowed`.
- [ ] `multiprocessing.freeze_support()` si usas procesos.
- [ ] Revisado con Windows Defender; firmado si se distribuye fuera de tu entorno.
- [ ] Zip o instalador probado en un usuario limpio.

---

## Referencias

- PyInstaller: <https://pyinstaller.org>
- Tkinter (documentación de Python): <https://docs.python.org/3/library/tkinter.html>
- Python en Windows: <https://docs.python.org/3/using/windows.html>
- Inno Setup: <https://jrsoftware.org/isinfo.php>
- Firma de código con SignTool: <https://learn.microsoft.com/windows/win32/seccrypto/signtool>
- Nuitka: <https://nuitka.net>

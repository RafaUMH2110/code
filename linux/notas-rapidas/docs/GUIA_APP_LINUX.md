# Crear una app de Linux con Python (Debian, Ubuntu y Linux Mint)

Guía de conceptos básicos y avanzados, con el ejemplo **Notas Rápidas** (`app_tk/notas_app.py`). Incluye, en la parte 3, las diferencias entre **Debian**, **Ubuntu** y **Linux Mint**.

## Contenido del proyecto

| Fichero | Función |
|---|---|
| `app_tk/notas_app.py` | Código de la aplicación (Tkinter) |
| `app_tk/notas-rapidas.desktop` | Lanzador: entrada del menú de aplicaciones, icono y tipos de fichero |
| `app_tk/crear_deb.sh` | Crea el paquete `.deb` (recomendado) |
| `app_tk/instalar_local.sh` | Instala solo para tu usuario, sin `sudo` |
| `app_tk/construir_app.sh` | Binario independiente con PyInstaller |
| `app_tk/icono.png`, `icono_256.png`, `icono_48.png` | Iconos de ejemplo |
| `docs/GUIA_APP_LINUX.md` | Esta guía |

## Inicio rápido

```bash
# 1. Paquetes del sistema (Debian, Ubuntu y Mint)
sudo apt update
sudo apt install python3-tk python3-venv python3-pip

# 2. Prueba el script tal cual
python3 app_tk/notas_app.py

# 3. Elige UNA forma de «instalarla»
cd app_tk
./crear_deb.sh && sudo apt install ./dist/notas-rapidas_1.0.0_all.deb   # paquete .deb
./instalar_local.sh --escritorio                                        # solo tu usuario, sin sudo
./construir_app.sh                                                      # binario PyInstaller

# 4. Búscala en el menú de aplicaciones como «Notas Rápidas» o ejecuta: notas-rapidas
```

---

# Parte 1. Conceptos básicos

## 1.1 ¿Qué es una «app» en Linux?

En Linux no existe el concepto de *bundle* de macOS ni un único formato como el `.exe`. Una aplicación de escritorio es la suma de:

1. **Un ejecutable** (un binario ELF o un script con *shebang*, como `#!/bin/sh`).
2. **Un fichero `.desktop`** (*Desktop Entry*): texto que dice al entorno gráfico el nombre, el icono, el comando y los tipos de fichero de la app. Es lo que hace que aparezca en el menú, en el lanzador y en «Abrir con…».
3. **Iconos** en el tema `hicolor` (`/usr/share/icons/hicolor/<tamaño>/apps/`).
4. **Una forma de distribuirla**: normalmente un paquete (`.deb` en Debian y derivadas).

```
/usr/bin/notas-rapidas                                      ← comando (lanzador)
/opt/notas-rapidas/notas_app.py, icono.png                  ← código y recursos
/usr/share/applications/notas-rapidas.desktop               ← entrada de menú
/usr/share/icons/hicolor/256x256/apps/notas-rapidas.png     ← icono
```

**Idea clave:** hacer doble clic sobre un `.py` no crea una app. En Linux, una app «de verdad» se reconoce porque tiene un `.desktop` instalado, y es ese fichero (no el ejecutable) el que se lanza desde el menú.

## 1.2 Piezas necesarias

1. **Código Python** con una interfaz gráfica y un bucle de eventos.
2. **Un toolkit de interfaz** (GUI).
3. **Un lanzador `.desktop`** y un icono.
4. **Un modo de instalación**: paquete `.deb`, instalación local o binario independiente.
5. **Dependencias del sistema** declaradas (en el `.deb`, con `Depends:`).

## 1.3 Elegir el toolkit de interfaz

| Toolkit | Paquete apt | Ventajas | Inconvenientes |
|---|---|---|---|
| **Tkinter** | `python3-tk` | Ligero, estándar, sin dependencias de pip | Aspecto algo anticuado |
| **PyGObject (GTK 4 / GTK 3)** | `python3-gi` | Nativo en GNOME, Cinnamon, Xfce | Más código; API extensa |
| **PySide6 / PyQt6** | `python3-pyside6.*`, `python3-pyqt6` | Muy completo, aspecto profesional | Más dependencias; versiones según la distro |
| **pywebview** | pip + `python3-gi` + WebKitGTK | Interfaz HTML/CSS/JS reutilizable | Dos mundos que mantener |
| **customtkinter** | pip | Tkinter con aspecto moderno | Dependencia adicional |
| **Kivy / Flet** | pip | Táctil o multiplataforma | Aspecto no nativo |

El ejemplo usa Tkinter por ser el más sencillo de reproducir. La variante con HTML está en `GUIA_PYWEBVIEW_LINUX.md`.

> **Importante:** en Debian, Ubuntu y Mint, **`tkinter` no se instala con Python**. Es un paquete aparte: `sudo apt install python3-tk`. Si falta, `import tkinter` da `ModuleNotFoundError`.

## 1.4 El bucle de eventos

Una app gráfica no «se ejecuta y termina»: construye ventanas, llama a `mainloop()` y se queda esperando eventos (clics, teclas, menús) que despachan a *callbacks*.

```python
root = tk.Tk(className="NotasRapidas")
app = NotasApp(root)   # crea widgets y registra callbacks
root.mainloop()        # bloquea aquí hasta cerrar la ventana
```

Consecuencia: **una tarea larga dentro de un callback congela la ventana** y el escritorio ofrecerá «forzar salida». Ver hilos en la parte 2.

## 1.5 Formas de lograr el «doble clic»

| Método | Cuándo usarlo | Resultado |
|---|---|---|
| **Paquete `.deb`** (`crear_deb.sh`) | Distribuir en Debian, Ubuntu y Mint | Se instala con un clic o con `apt`; aparece en el menú; se desinstala limpiamente |
| **Instalación local** (`instalar_local.sh`) | Uso propio, sin permisos de administrador | Entrada de menú y comando en `~/.local` |
| **Binario PyInstaller** (`construir_app.sh`) | App sin depender del Python ni de `python3-tk` del sistema | Carpeta `dist/notas-rapidas/` |
| **Lanzador `.desktop` apuntando a un script** | Prototipo rápido | Icono que ejecuta `python3 /ruta/notas_app.py` |
| **AppImage** | Un solo fichero ejecutable para cualquier distro | Fichero `.AppImage` (requiere herramientas extra) |
| **Flatpak / Snap** | Distribución con aislamiento (sandbox) | Paquete universal; manifiesto y tiendas |

Ejemplo del lanzador más sencillo (guárdalo como `~/.local/share/applications/mi-app.desktop`):

```ini
[Desktop Entry]
Type=Application
Name=Mi App
Exec=/usr/bin/python3 /home/usuario/proyectos/notas_app.py
Icon=/home/usuario/proyectos/icono.png
Terminal=false
```

### Por qué el doble clic sobre un binario no siempre funciona

- Los **binarios ELF** modernos son ejecutables *PIE*, y algunos gestores de archivos los identifican como «biblioteca compartida» en lugar de «programa»: al hacer doble clic se abre el visor de archivos comprimidos o no ocurre nada.
- Por eso en Linux se recomienda **lanzar la app desde el `.desktop`** (menú o icono del Escritorio), no desde el binario suelto.
- Los `.desktop` fuera del menú (por ejemplo en el Escritorio) necesitan **permiso de ejecución** y, según el gestor, marcarse como de confianza (ver parte 3).

## 1.6 Los tres flujos de instalación

### A. Paquete `.deb` (recomendado)

```bash
cd app_tk
./crear_deb.sh
sudo apt install ./dist/notas-rapidas_1.0.0_all.deb
sudo apt remove notas-rapidas          # desinstalar
```

- El paquete es `Architecture: all`: **un mismo `.deb` sirve en `amd64`, `arm64`, etc.** porque el código es Python.
- Usa el Python del sistema, así que no depende de la `glibc` del equipo de construcción.
- `Depends: python3 (>= 3.9), python3-tk`: `apt` instala automáticamente lo que falte.
- Usa `sudo apt install ./fichero.deb` en lugar de `sudo dpkg -i`: `apt` resuelve las dependencias, `dpkg` no.
- Al hacer doble clic sobre un `.deb`, el instalador gráfico de la distribución (Gestor de software de Mint, centro de aplicaciones de Ubuntu o GNOME Software en Debian) lo abre.

### B. Instalación local, sin sudo

```bash
cd app_tk
./instalar_local.sh --escritorio       # --escritorio crea además un icono en el Escritorio
./instalar_local.sh --desinstalar
```

Copia la app a `~/.local/share/notas-rapidas/`, crea el comando en `~/.local/bin/` y el `.desktop` en `~/.local/share/applications/`.

### C. Binario con PyInstaller

```bash
cd app_tk
./construir_app.sh                     # carpeta dist/notas-rapidas/
./construir_app.sh --onefile           # un solo fichero (arranque más lento)
```

Incluye el intérprete de Python dentro del binario. **Depende de la `glibc` del equipo donde se construye** (ver 2.7).

## 1.7 Iconos

- Formato: **PNG** (o SVG). No existe `.ico` ni `.icns`.
- Se instalan en el tema `hicolor`: `/usr/share/icons/hicolor/256x256/apps/<id>.png` (y `48x48`, `128x128`…). El `.desktop` los referencia **por nombre, sin ruta ni extensión**: `Icon=notas-rapidas`.
- Para instalaciones locales: `~/.local/share/icons/hicolor/...`.
- Si el icono no aparece tras instalar: `gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor` (el `.deb` lo gestiona automáticamente mediante *triggers* de `dpkg`).
- Para la ventana: `root.iconphoto(True, tk.PhotoImage(file="icono.png"))` (hecho en el ejemplo).

## 1.8 El fichero `.desktop`

```ini
[Desktop Entry]
Type=Application
Version=1.0
Name=Notas Rápidas
GenericName=Bloc de notas
Comment=Bloc de notas sencillo
Exec=notas-rapidas %F
Icon=notas-rapidas
Terminal=false
Categories=Utility;TextEditor;
MimeType=text/plain;text/markdown;
StartupNotify=true
StartupWMClass=NotasRapidas
```

| Clave | Para qué sirve |
|---|---|
| `Name`, `Comment`, `GenericName` | Texto visible en el menú (admite traducciones: `Name[en]=...`) |
| `Exec` | Comando. `%F` = lista de ficheros, `%f` = uno, `%U`/`%u` = URL |
| `Icon` | Nombre del icono del tema, o ruta absoluta |
| `Terminal` | `true` si es una app de consola |
| `Categories` | Carpeta del menú (Utility, Office, Graphics, Development…) |
| `MimeType` | Tipos de fichero con los que aparece en «Abrir con…» |
| `StartupWMClass` | Debe coincidir con la clase de ventana (`WM_CLASS`) para que el dock agrupe la ventana con su icono |
| `NoDisplay=true` | Oculta la entrada del menú |

Valida un `.desktop` con `desktop-file-validate fichero.desktop` (paquete `desktop-file-utils`).

## 1.9 Anatomía del código de ejemplo

- **Constantes y rutas** al inicio (`APP_NAME`, `APP_ID`, `SUPPORT_DIR`, `LOG_FILE`).
- **Clase `NotasApp`**: un método por responsabilidad (`_crear_menus`, `_crear_widgets`, `guardar`, `salir`…).
- **Callbacks** conectados con `command=` y `bind()`.
- **`main()`** como único punto de entrada, protegido con `if __name__ == "__main__":`.

---

# Parte 2. Conceptos avanzados

## 2.1 Atajos de teclado y menús

En Linux la tecla modificadora es **Ctrl**: `<Control-s>`, `<Control-o>`… Convenciones:

| Acción | Atajo |
|---|---|
| Salir | `Ctrl+Q` (los menús de aplicación de GNOME lo usan; en Tkinter hay que enlazarlo) |
| Rehacer | `Ctrl+Shift+Z` en Tk/X11; muchas apps aceptan también `Ctrl+Y` (ambos están en el ejemplo) |
| Símbolos `+` y `=` | Se enlazan como `plus` y `equal` |

`root.protocol("WM_DELETE_WINDOW", self.salir)` intercepta el botón X y `Alt+F4`.

## 2.2 Dónde guardar datos: especificación XDG

Linux sigue la *XDG Base Directory Specification*. Usa estas rutas, nunca la carpeta de la app:

| Uso | Ruta por defecto | Variable |
|---|---|---|
| Configuración | `~/.config/<app>/` | `XDG_CONFIG_HOME` |
| Datos de la app | `~/.local/share/<app>/` | `XDG_DATA_HOME` |
| Registros y estado | `~/.local/state/<app>/` | `XDG_STATE_HOME` |
| Cachés | `~/.cache/<app>/` | `XDG_CACHE_HOME` |
| Documentos del usuario | Los elige el usuario con un diálogo | — |

```python
def _xdg(variable, por_defecto):
    return Path(os.environ.get(variable) or Path.home() / por_defecto)

SUPPORT_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "notas-rapidas"
LOG_DIR = _xdg("XDG_STATE_HOME", ".local/state") / "notas-rapidas"
```

`/opt/<app>` y `/usr` son de solo lectura para el usuario normal: no escribas ahí.

## 2.3 Recursos junto al código

```python
def resource_path(rel):
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return Path(base) / rel
```

Funciona como script, instalada por el `.deb` (`/opt/notas-rapidas/`) y dentro de PyInstaller. Nunca uses rutas relativas al directorio actual: al lanzar desde el menú el directorio de trabajo es `$HOME`.

## 2.4 Registro y errores: lanzada desde el menú no hay terminal

Si la app arranca desde el menú, `stdout` y `stderr` van a ninguna parte (o al registro de la sesión). El ejemplo:

- Escribe con `logging` a `~/.local/state/notas-rapidas/app.log`.
- Instala `sys.excepthook` y `root.report_callback_exception`.
- Muestra `messagebox.showerror` cuando procede.

**Depurar una app que no arranca:** ejecútala desde un terminal (`notas-rapidas`) para ver el traceback. También puedes consultar el registro de la sesión:

```bash
journalctl --user -e                   # entorno systemd de usuario (GNOME)
tail -f ~/.local/state/notas-rapidas/app.log
```

## 2.5 No bloquear la interfaz: hilos y cola

Tkinter **no es seguro entre hilos**: solo el hilo principal toca widgets. Patrón recomendado: el hilo de trabajo escribe en una `queue.Queue` y la interfaz la consulta con `after()`.

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

En Linux `multiprocessing` usa `fork` por defecto en Python ≤ 3.13 y `forkserver` desde 3.14: no mezcles `fork` con hilos ni con Tk ya inicializado; crea los procesos antes de abrir la ventana o usa `multiprocessing.get_context("spawn")`.

## 2.6 Dependencias de Python: el entorno «externally managed» (PEP 668)

Debian 12 o posterior, Ubuntu 23.04 o posterior y Linux Mint 22 marcan el Python del sistema como *externally managed*: `pip install paquete` fuera de un entorno virtual falla con `error: externally-managed-environment`.

Soluciones, por orden de preferencia:

1. **Paquete de apt**, si existe (`sudo apt install python3-requests`).
2. **Entorno virtual** (lo que hacen los scripts del proyecto): `python3 -m venv .venv`.
3. `pipx` para herramientas de línea de comandos (`sudo apt install pipx`).
4. `--break-system-packages`: **evítalo**, puede romper herramientas del sistema.

Para usar módulos instalados con apt (como `gi`) dentro de un venv: `python3 -m venv --system-site-packages .venv`.

## 2.7 Portabilidad de binarios: glibc

Un binario PyInstaller se enlaza con la `glibc` del equipo de construcción y **solo funciona con esa versión o superior**.

| Se construye en… | Funciona en… |
|---|---|
| Ubuntu 22.04 / Mint 21 (glibc 2.35) | Todas las de la tabla de la parte 3 |
| Debian 12 (glibc 2.36) | Debian 12+, Ubuntu 24.04+, Mint 22+; **no** Ubuntu 22.04 / Mint 21 |
| Ubuntu 24.04 / Mint 22 (glibc 2.39) | Ubuntu 24.04+, Mint 22+, Debian 13; **no** Debian 12 |

**Regla:** construye en la distro más antigua que quieras soportar (un contenedor o una máquina virtual sirve). Comprueba la versión con `ldd --version`. El paquete `.deb` de este proyecto **no tiene este problema** porque no incluye binarios.

Otras diferencias de los binarios: son específicos de arquitectura (`amd64` ≠ `arm64`) y deben construirse en cada una.

## 2.8 X11, Wayland, HiDPI y asociación con el icono

- **GNOME** (Debian, Ubuntu) usa **Wayland** por defecto; **Cinnamon** (Mint) usa **X11**. Tkinter funciona en ambos (en Wayland a través de XWayland).
- Con **escalado fraccionario** en Wayland (125 %, 150 %), las apps Tk (XWayland) pueden verse algo borrosas. Es una limitación conocida de Tk; soluciones: escalado entero, o un toolkit nativo (GTK, Qt).
- Para texto nítido en pantallas de alta densidad en X11: `root.tk.call("tk", "scaling", 2.0)`.
- **Agrupación en el dock:** la ventana se asocia al `.desktop` por su clase `WM_CLASS`. En Tkinter se fija con `tk.Tk(className="NotasRapidas")` y debe coincidir con `StartupWMClass=NotasRapidas`. Sin esto, el dock muestra un icono genérico adicional.
- En Wayland, GNOME identifica las apps por su *app-id* (nombre del `.desktop`); `StartupWMClass` ayuda a que ambos coincidan.

## 2.9 `.desktop` avanzado

- **Acciones adicionales** (menú contextual del icono):

```ini
Actions=nueva;

[Desktop Action nueva]
Name=Nueva nota
Exec=notas-rapidas
```

- **Traducciones:** `Name[en]=Quick Notes`, `Comment[en]=Simple notepad`.
- **Tipos de fichero y predeterminada:** `MimeType=` solo ofrece la app en «Abrir con…». Para hacerla predeterminada: `xdg-mime default notas-rapidas.desktop text/markdown`.
- **Apps de consola:** `Terminal=true`.
- Tras editar un `.desktop` local: `update-desktop-database ~/.local/share/applications`.

## 2.10 Distribución

| Vía | Descripción |
|---|---|
| **Fichero `.deb` suelto** | Lo que genera `crear_deb.sh`; se instala con `apt install ./`. Sin actualizaciones automáticas |
| **Repositorio APT propio** | `reprepro` o `aptly` publican un repositorio; los usuarios reciben actualizaciones con `apt upgrade`. El repositorio se firma con una clave GPG |
| **PPA (Ubuntu / Mint)** | Repositorio en Launchpad con paquetes fuente; solo para Ubuntu y derivadas |
| **AppImage** | Un fichero único autoejecutable; para Python se usa `python-appimage` o `appimage-builder` |
| **Flatpak** | Sandbox y tienda Flathub; manifiesto YAML/JSON; Linux Mint lo trae configurado |
| **Snap** | Tienda Snap Store; viene por defecto en Ubuntu, **bloqueado en Mint** y opcional en Debian |

Para empezar, el `.deb` es lo más simple. Para llegar a usuarios de cualquier distro, Flatpak es la opción más habitual.

**Mejoras del `.deb`** cuando crezca el proyecto: `postinst`/`postrm` para tareas de instalación, `Recommends`/`Suggests`, página de manual (`/usr/share/man/man1/`), `lintian` para revisar el paquete y un empaquetado completo con `debhelper` y `dh-python` si quieres incluirlo en Debian.

## 2.11 Seguridad y firma

- Los `.deb` sueltos **no se firman uno a uno** en la práctica. La confianza viene del **repositorio APT**, firmado con GPG (`Release`/`InRelease`).
- Instalar un `.deb` ejecuta scripts como `root` (`postinst`): instala solo paquetes de fuentes de confianza y revisa su contenido con `dpkg-deb -c` y `dpkg-deb -e`.
- Una app de usuario no necesita permisos especiales. Evita `sudo`/`pkexec` dentro de la app; si necesitas privilegios, usa `polkit`.
- En Flatpak y Snap, los permisos (red, ficheros) se declaran en el manifiesto.

## 2.12 Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'tkinter'` | Falta el paquete de apt | `sudo apt install python3-tk` |
| `error: externally-managed-environment` al usar pip | PEP 668 | Usar `python3 -m venv .venv` |
| `The virtual environment was not created successfully` | Falta `python3-venv` | `sudo apt install python3-venv` |
| `python: command not found` | Solo existe `python3` | Usar `python3`, o `sudo apt install python-is-python3` |
| `sudo: command not found` o «usuario no está en sudoers» (Debian) | Debian no configura sudo si se puso contraseña de root | `su -` y `apt install sudo; usermod -aG sudo USUARIO`; reiniciar sesión |
| La app no aparece en el menú | Entrada sin actualizar | `update-desktop-database ~/.local/share/applications`; cerrar y abrir sesión |
| El icono es genérico | Nombre mal escrito o caché | `Icon=` sin extensión; `gtk-update-icon-cache -f -t …/hicolor` |
| Doble clic sobre el binario no hace nada | El gestor lo ve como «biblioteca compartida» | Lanzar desde el `.desktop` o la terminal |
| El `.desktop` del Escritorio muestra «No es de confianza» | Falta permiso de ejecución | `chmod +x`; clic derecho → *Permitir lanzar* (GNOME); *Propiedades → Permisos* (Nemo) |
| `version 'GLIBC_2.38' not found` | Binario construido en una distro más nueva | Construir en la distro más antigua o usar el `.deb` |
| Ventana de Tk borrosa en Wayland | Escalado fraccionario con XWayland | Escalado entero o toolkit nativo |
| Dos iconos en el dock | `WM_CLASS` ≠ `StartupWMClass` | Igualarlos (`className=` en `tk.Tk`) |
| `dpkg: dependency problems` | Se usó `dpkg -i` | `sudo apt install -f` o instalar con `apt install ./paquete.deb` |
| `PyInstaller: objdump not found` | Falta binutils | `sudo apt install binutils` |

## 2.13 Lista de verificación antes de entregar

- [ ] Funciona como script y desde el `.deb` (instalado en un sistema limpio).
- [ ] `Depends:` correcto: instalado en una VM mínima de Debian, Ubuntu y Mint.
- [ ] `.desktop` validado (`desktop-file-validate`), icono en `hicolor`, `StartupWMClass` coherente.
- [ ] Versión, mantenedor y descripción actualizados en `crear_deb.sh`.
- [ ] Datos en `~/.config`, `~/.local/share`, `~/.local/state`; nunca junto al código.
- [ ] `logging` a fichero.
- [ ] Probado con Wayland y X11.
- [ ] Binarios PyInstaller construidos en la distro más antigua soportada.
- [ ] `lintian` revisado y `sudo apt remove` deja el sistema limpio.

---

# Parte 3. Diferencias entre Debian, Ubuntu y Linux Mint

## 3.1 Resumen

**El mismo código, los mismos scripts y el mismo `.deb` sirven en las tres distribuciones.** Ubuntu y Mint son derivadas de Debian (Mint, de Ubuntu; la edición LMDE, directamente de Debian), usan `apt` y `dpkg`, y comparten los nombres de paquetes relevantes (`python3-tk`, `python3-venv`, `python3-gi`…). Las diferencias están en las **versiones**, en lo que viene **preinstalado**, en la **configuración inicial** y en el **escritorio**.

## 3.2 Versiones relevantes

Valores habituales a fecha de esta guía; compruébalos en tu equipo con `python3 --version` y `ldd --version`.

| Distribución | Base | Python | glibc | PEP 668 | Escritorio por defecto |
|---|---|---|---|---|---|
| **Debian 12** «bookworm» | — | 3.11 | 2.36 | Sí | GNOME (Wayland) |
| **Debian 13** «trixie» | — | 3.13 | 2.41 | Sí | GNOME (Wayland) |
| **Ubuntu 22.04 LTS** | Debian | 3.10 | 2.35 | No | GNOME (Wayland) |
| **Ubuntu 24.04 LTS** | Debian | 3.12 | 2.39 | Sí | GNOME (Wayland) |
| **Linux Mint 21.x** | Ubuntu 22.04 | 3.10 | 2.35 | No | Cinnamon (X11) |
| **Linux Mint 22.x** | Ubuntu 24.04 | 3.12 | 2.39 | Sí | Cinnamon (X11) |
| **LMDE** | Debian | Según versión base | Según versión base | Sí | Cinnamon (X11) |

Consecuencias:

- El código del proyecto funciona con **Python ≥ 3.9** (usa `from __future__ import annotations`), por lo que cubre todas las filas.
- Para **binarios PyInstaller**, la referencia más antigua es **Ubuntu 22.04 / Mint 21 (glibc 2.35)**; un binario construido allí funciona en el resto.
- Las versiones de Ubuntu o Debian posteriores a las de la tabla siguen el mismo patrón: comprueba `python3 --version` y las dependencias con `apt-cache policy`.

## 3.3 Paquetes y comandos

| Tema | Debian | Ubuntu | Linux Mint |
|---|---|---|---|
| Gestor de paquetes | `apt` | `apt` | `apt` |
| Tkinter | `python3-tk` | `python3-tk` | `python3-tk` |
| Entornos virtuales | `python3-venv` | `python3-venv` | `python3-venv` |
| PyGObject (para pywebview) | `python3-gi` | `python3-gi` | `python3-gi` (suele venir preinstalado) |
| WebKitGTK | `gir1.2-webkit2-4.1` | `gir1.2-webkit2-4.1` (22.04 o posterior; 20.04: 4.0) | `gir1.2-webkit2-4.1` (21 o posterior; 20: 4.0) |
| Comando `python` | No existe (usa `python3`) | No existe (instala `python-is-python3`) | No existe |
| Instalar un `.deb` local | `sudo apt install ./x.deb` | `sudo apt install ./x.deb` | `sudo apt install ./x.deb` |

## 3.4 Configuración inicial y herramientas

| Tema | Debian | Ubuntu | Linux Mint |
|---|---|---|---|
| **`sudo`** | Puede **no estar configurado**: si durante la instalación se puso contraseña de root, el usuario no está en `sudo`. Solución: `su -` y `usermod -aG sudo USUARIO` | Viene configurado para el usuario creado en la instalación | Viene configurado |
| **Snap** | No viene instalado | Instalado por defecto | **Bloqueado** (`/etc/apt/preferences.d/nosnap.pref`); no uses instrucciones basadas en `snap` |
| **Flatpak** | Opcional (`apt install flatpak`) | Opcional | Preconfigurado, con Flathub |
| **Gestor gráfico de `.deb`** | GNOME Software | App Center / GNOME Software | Gestor de software / GDebi |
| **Repositorios** | `main` por defecto; `contrib`, `non-free` y `non-free-firmware` opcionales | `main`, `universe`, `restricted`, `multiverse` | Los de Ubuntu más los de Mint |
| **Paquetes preinstalados** | Mínimos | Intermedios | Muchos (códecs, herramientas gráficas) |
| **Fuente por defecto** | DejaVu / Noto | Ubuntu | Ubuntu / Noto |

## 3.5 Doble clic, lanzadores y escritorio

| Tema | Debian (GNOME) | Ubuntu (GNOME) | Linux Mint (Cinnamon) |
|---|---|---|---|
| Gestor de archivos | Nautilus (Archivos) | Nautilus (Archivos) | Nemo |
| **Menú de aplicaciones** | Actividades → buscar «Notas» | Actividades / cuadrícula | Menú de Mint |
| **Iconos en el Escritorio** | No se muestran por defecto | Sí (extensión incluida) | Sí |
| `.desktop` en el Escritorio | Clic derecho → *Permitir lanzar* | Clic derecho → *Permitir lanzar* | Debe tener permiso de ejecución; `Propiedades → Permisos` |
| Doble clic sobre un `.deb` | Abre GNOME Software | Abre el instalador de la distro | Abre el Gestor de software |
| Sesión gráfica | Wayland | Wayland | X11 |
| Terminal | GNOME Terminal / Consola | GNOME Terminal | Terminal de Mint |

Las opciones `--escritorio` de `instalar_local.sh` hacen `chmod +x` y marcan el `.desktop` como de confianza con `gio`; funciona en GNOME y es suficiente en Nemo. En **Debian GNOME**, que no muestra iconos en el Escritorio, usa la entrada de menú.

## 3.6 VS Code en cada distro

VS Code **no está en los repositorios** de ninguna de las tres. Opciones:

| Vía | Debian | Ubuntu | Linux Mint |
|---|---|---|---|
| **`.deb` oficial** de <https://code.visualstudio.com> (`sudo apt install ./code_*.deb`) | Sí | Sí | Sí |
| Repositorio APT de Microsoft | Sí (lo añade el `.deb`) | Sí | Sí |
| Snap (`sudo snap install code --classic`) | Opcional | Sí | **No** (snap bloqueado) |
| Flatpak (`com.visualstudio.code`) | Opcional | Opcional | Sí |

Recomendación: el **`.deb` oficial** funciona igual en las tres y se actualiza con `apt upgrade`. La variante Flatpak queda aislada del sistema y puede no ver tu `python3`, `tkinter` ni `gi`.

## 3.7 Qué cambia en este proyecto, en concreto

| Elemento | ¿Cambia entre Debian, Ubuntu y Mint? |
|---|---|
| `notas_app.py`, `notas_web.py`, `index.html` | No |
| `.desktop` e iconos | No |
| `crear_deb.sh` y el `.deb` resultante | No (un único `.deb`, `Architecture: all`) |
| `instalar_local.sh` | No |
| `construir_app.sh` (PyInstaller) | El binario depende de la glibc: construir en la distro más antigua |
| Paquetes de apt a instalar | Mismos nombres. En distros anteriores a Debian 12 / Ubuntu 22.04 usar `gir1.2-webkit2-4.0` |
| Instalación de VS Code | Sí (snap no disponible en Mint) |
| Primer uso de `sudo` | Sí, en Debian puede requerir configurarlo |
| Mostrar iconos en el Escritorio | Sí (Debian GNOME no los muestra) |

---

## Referencias

- Desktop Entry Specification: <https://specifications.freedesktop.org/desktop-entry-spec/latest/>
- XDG Base Directory Specification: <https://specifications.freedesktop.org/basedir-spec/latest/>
- Icon Theme Specification: <https://specifications.freedesktop.org/icon-theme-spec/latest/>
- Guía del mantenedor de Debian: <https://www.debian.org/doc/manuals/maint-guide/>
- Python y PEP 668: <https://peps.python.org/pep-0668/>
- PyInstaller: <https://pyinstaller.org>
- Tkinter (documentación de Python): <https://docs.python.org/3/library/tkinter.html>
- Flatpak: <https://docs.flatpak.org> · AppImage: <https://appimage.org>

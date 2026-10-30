# Manual: programar, ejecutar y empaquetar apps de Linux desde VS Code

Válido para **Debian**, **Ubuntu** y **Linux Mint**. Proyecto de ejemplo con dos versiones de la misma app («Notas Rápidas»):

- **`app_tk/`**: interfaz con Tkinter.
- **`app_web/`**: interfaz HTML dentro de una ventana nativa (pywebview + GTK/WebKitGTK).

La app es **autocontenida**: esta carpeta (`linux/notas-rapidas/`) lleva su propio `.vscode/`, sus guías, su manual y su `.gitignore`. Se abre como proyecto independiente en VS Code.

> **Requisito:** todo se hace en Linux, con VS Code instalado en el mismo equipo. Para ver ventanas necesitas una sesión gráfica (no sirve SSH sin reenvío gráfico). Los paquetes `.deb` se crean en Debian, Ubuntu, Mint o derivadas (necesitan `dpkg-deb`).

---

## 1. Estructura de la carpeta

```
notas-rapidas/                     ← raíz del proyecto de VS Code (se abre esta carpeta)
├── .vscode/
│   ├── launch.json                ← ejecución y depuración (F5)
│   ├── tasks.json                 ← tareas: paquetes, instalación, binarios, logs, limpiar
│   ├── settings.json              ← intérprete, formato, exclusiones
│   └── extensions.json            ← extensiones recomendadas
├── app_tk/                        ← versión Tkinter
│   ├── notas_app.py
│   ├── notas-rapidas.desktop      ← lanzador del menú
│   ├── crear_deb.sh               ← paquete .deb
│   ├── instalar_local.sh          ← instalación sin sudo
│   ├── construir_app.sh           ← binario PyInstaller
│   └── icono.png / icono_256.png / icono_48.png
├── app_web/                       ← versión pywebview
│   ├── notas_web.py
│   ├── ui/index.html              ← la interfaz
│   ├── notas-rapidas-web.desktop
│   ├── crear_deb.sh
│   ├── instalar_local.sh
│   ├── construir_app_web.sh       ← binario PyInstaller (experimental)
│   └── icono.png / icono_256.png / icono_48.png
├── docs/
│   ├── GUIA_APP_LINUX.md          ← conceptos básicos y avanzados + diferencias Debian/Ubuntu/Mint
│   └── GUIA_PYWEBVIEW_LINUX.md    ← detalles de la variante pywebview
├── .gitignore
└── MANUAL_VSCODE_LINUX.md         ← este manual
```

Dentro de la app, las variantes se llaman `app_tk` y `app_web` a propósito: **nunca nombres una carpeta `tkinter` o `webview`**, porque taparía el módulo real y provocaría errores de importación.

### Convención: una carpeta autocontenida por app

En el repositorio, cada app es una carpeta de primer nivel dentro de `linux/` (nombre en minúsculas y guiones) que contiene **todo lo suyo**: código, `.vscode/`, `docs/`, manual y `.gitignore`.

Para añadir una app nueva:

1. Copia la carpeta `notas-rapidas/` como plantilla y renómbrala (`linux/<mi-app>/`).
2. Sustituye el código de `app_tk/` y `app_web/` (o crea las variantes que necesites).
3. Cambia los nombres del paquete, del comando, del `.desktop` y de los iconos en los scripts `crear_deb.sh` e `instalar_local.sh` (`PAQUETE=`, `APP=`).
4. Ajusta `.vscode/launch.json` y `.vscode/tasks.json` con los ficheros de la nueva app.
5. Edita el manual y las guías para que hablen de la nueva app.
6. En VS Code, abre `linux/<mi-app>/` como carpeta raíz.

---

## 2. Preparación (una sola vez)

### 2.1 Comprobar tu distribución

```bash
cat /etc/os-release | head -3
python3 --version
```

Cualquier Debian 12 o posterior, Ubuntu 22.04 o posterior y Linux Mint 21 o posterior sirve (Python 3.9 o superior). La parte 3 de `docs/GUIA_APP_LINUX.md` detalla las diferencias entre distribuciones.

### 2.2 Instalar paquetes del sistema

Con una tarea: `Ctrl+Shift+P` → *Tasks: Run Task* → **0a. Instalar paquetes del sistema (apt)**.
O desde el terminal:

```bash
sudo apt update
sudo apt install python3-tk python3-venv python3-pip python3-gi python3-gi-cairo \
                  gir1.2-gtk-3.0 gir1.2-webkit2-4.1 binutils dpkg-dev
```

| Paquete | Para qué |
|---|---|
| `python3-tk` | Tkinter (**no viene con Python** en Debian/Ubuntu/Mint) |
| `python3-venv` | Entornos virtuales |
| `python3-pip` | pip |
| `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-3.0`, `gir1.2-webkit2-4.1` | pywebview (GTK + WebKitGTK) |
| `binutils` | Lo necesita PyInstaller (`objdump`) |
| `dpkg-dev` | Herramientas de empaquetado `.deb` |

> En Ubuntu 20.04 y Mint 20 usa `gir1.2-webkit2-4.0` en lugar de `4.1`.
> **En Debian**, si `sudo` no existe o te dice que no estás en `sudoers`, abre un terminal de root con `su -`, ejecuta `apt install sudo && usermod -aG sudo TU_USUARIO` y reinicia la sesión.

### 2.3 Instalar VS Code

VS Code no está en los repositorios de Debian, Ubuntu ni Mint. Lo más sencillo, igual en las tres:

1. Descarga el `.deb` desde <https://code.visualstudio.com/Download>.
2. Instálalo: `sudo apt install ./code_*.deb` (también añade el repositorio de Microsoft para recibir actualizaciones con `apt upgrade`).

Alternativas: `sudo snap install code --classic` (Ubuntu; **no en Mint**, que bloquea snap) o Flatpak (puede quedar aislado del sistema y no ver `tkinter` ni `gi`). Recomendamos el `.deb`.

### 2.4 Abrir la carpeta y las extensiones

1. *File → Open Folder…* y elige `linux/notas-rapidas`.
2. VS Code propondrá instalar las extensiones recomendadas (`.vscode/extensions.json`). Acepta. Las importantes son **Python** y **Python Debugger**; **ShellCheck** revisa los `.sh`.
3. Si te lo pide, confía en el autor de la carpeta (*Trust*).

### 2.5 Crear el entorno de desarrollo

**A. Con una tarea:** `Ctrl+Shift+P` → *Tasks: Run Task* → **0b. Crear entorno de desarrollo (.venv)**.

**B. Desde el terminal integrado** (``Ctrl+` ``):

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install --upgrade pip pyinstaller pywebview
```

`--system-site-packages` permite que el venv vea `gi` (instalado con apt), necesario para pywebview. Después selecciona el intérprete: `Ctrl+Shift+P` → *Python: Select Interpreter* → `./.venv/bin/python`. En la barra inferior debe aparecer `.venv` (`settings.json` ya lo configura).

> Debian 12 o posterior, Ubuntu 24.04 y Mint 22 no permiten `pip install` fuera de un venv (error `externally-managed-environment`). Por eso siempre se usa `.venv`.

---

## 3. Programar

| Qué | Cómo |
|---|---|
| Abrir un fichero | `Ctrl+P` y escribir el nombre |
| Buscar en todo el proyecto | `Ctrl+Shift+F` |
| Ir a la definición | `F12` o `Ctrl+clic` |
| Ver todos los usos | `Shift+F12` |
| Renombrar un símbolo en todo el proyecto | `F2` |
| Paleta de comandos | `Ctrl+Shift+P` |
| Terminal integrado | ``Ctrl+` `` |
| Panel de problemas | `Ctrl+Shift+M` |
| Formatear el fichero | `Ctrl+Shift+I` (también al guardar) |

**Consejos**

- Edita la interfaz web en `app_web/ui/index.html`; la lógica de Python en `notas_web.py`.
- Los métodos de la clase `Api` sin guion bajo son los que llama JavaScript. Los que empiezan por `_` son internos.
- Los scripts `.sh` necesitan permiso de ejecución: `chmod +x app_tk/*.sh app_web/*.sh`.

---

## 4. Ejecutar y depurar (sin instalar)

Abre la vista de ejecución (`Ctrl+Shift+D`), elige una configuración y pulsa **F5**.

| Configuración | Qué hace |
|---|---|
| **Tkinter: ejecutar / depurar** | Lanza `app_tk/notas_app.py` |
| **pywebview: ejecutar / depurar (con inspector web)** | Lanza `app_web/notas_web.py --debug` |
| **pywebview: ejecutar sin inspector** | Igual, sin herramientas de desarrollo |
| **Fichero actual** | Ejecuta el `.py` abierto |

**Atajos de depuración**

| Tecla | Acción |
|---|---|
| `F5` | Iniciar / continuar |
| `Ctrl+F5` | Ejecutar sin depurar |
| `F9` | Poner o quitar un punto de interrupción |
| `F10` | Paso por encima (siguiente línea) |
| `F11` | Paso al interior de una función |
| `Shift+F11` | Salir de la función |
| `Shift+F5` | Detener |

**Flujo típico para depurar un botón**

1. Pon un punto de interrupción (clic a la izquierda del número de línea) dentro de `guardar()`.
2. Pulsa `F5` y usa la app. Al ejecutar esa línea, VS Code se detiene.
3. Mira las variables en el panel *Variables*; evalúa expresiones en la *Debug Console*.

**Depurar la parte web (pywebview)**

VS Code depura Python, no el JavaScript de la ventana. Para JavaScript:

1. Ejecuta con la configuración *con inspector web*.
2. Haz clic derecho en la ventana → **Inspeccionar elemento** (inspector de WebKit).
3. En *Consola*, *Red* y *Elementos* verás lo habitual de un navegador.

Para probar solo el diseño, abre `app_web/ui/index.html` en el navegador (los botones que llaman a Python no funcionarán).

---

## 5. Instalar y empaquetar

Tienes tres vías, todas disponibles como tareas (`Ctrl+Shift+P` → *Tasks: Run Task*). `Ctrl+Shift+B` lanza la predeterminada (**Crear .deb Tkinter**).

### 5.1 Paquete `.deb` (recomendado)

| Tarea | Resultado |
|---|---|
| **Crear .deb Tkinter** | `app_tk/dist/notas-rapidas_1.0.0_all.deb` |
| **Crear .deb pywebview** | `app_web/dist/notas-rapidas-web_1.0.0_all.deb` |

Instalar y quitar:

```bash
sudo apt install ./app_tk/dist/notas-rapidas_1.0.0_all.deb
sudo apt remove notas-rapidas
```

- El paquete es `Architecture: all`: **el mismo `.deb` sirve en Debian, Ubuntu y Mint y en cualquier arquitectura.**
- Usa `apt install ./…`, no `dpkg -i`: `apt` instala las dependencias.
- Cambia versión y mantenedor al crearlo: `VERSION=1.1.0 MANTENEDOR="Nombre <correo>" ./crear_deb.sh`.
- Revisa el paquete con `dpkg-deb -I fichero.deb` (metadatos) y `dpkg-deb -c fichero.deb` (contenido); si tienes `lintian`, el script lo ejecuta.

### 5.2 Instalación local, sin `sudo`

| Tarea | Resultado |
|---|---|
| **Instalar en local Tkinter (sin sudo)** | App en `~/.local/share/notas-rapidas`, comando en `~/.local/bin`, entrada de menú |
| **Instalar en local pywebview (sin sudo)** | Igual, con un venv propio |
| **Desinstalar local …** | Elimina lo instalado |

Para crear además un icono en el Escritorio: `./instalar_local.sh --escritorio`.

### 5.3 Binario con PyInstaller

| Tarea | Resultado |
|---|---|
| **Construir binario Tkinter (PyInstaller, carpeta)** | `app_tk/dist/notas-rapidas/notas-rapidas` |
| **Construir binario Tkinter (PyInstaller, un solo fichero)** | `app_tk/dist/notas-rapidas` |
| **Construir binario pywebview (PyInstaller, experimental)** | `app_web/dist/notas-rapidas-web/notas-rapidas-web` |

> **Atención:** un binario PyInstaller solo funciona en distribuciones con una `glibc` igual o más reciente que la del equipo donde se construyó. Construye en la distro más antigua que quieras soportar (Ubuntu 22.04 / Mint 21 cubre las de la tabla de la guía). El `.deb` no tiene esta limitación. La variante pywebview con PyInstaller es experimental: usa mejor el `.deb`.

### 5.4 Qué elegir

| Quieres… | Usa |
|---|---|
| Distribuir a usuarios de Debian, Ubuntu o Mint | `.deb` |
| Probar la app tal cual la verá el usuario, sin permisos de administrador | Instalación local |
| Una app que no dependa de `python3-tk` ni del Python del sistema | Binario PyInstaller (Tkinter) |
| Cubrir también Fedora, Arch, openSUSE… | Flatpak o AppImage (ver guía, §2.10) |

---

## 6. Probar y depurar lo ya instalado

Una app instalada **no se depura con F5**. Usa estas vías:

1. **Desde el terminal:** ejecuta el comando (`notas-rapidas` o `notas-rapidas-web`) y verás los errores en pantalla.
2. **Registro:** tarea *Ver log de la app …*. Lee `~/.local/state/notas-rapidas/app.log` o `~/.local/state/notas-rapidas-web/app.log`.
3. **Binario:** tarea *Ejecutar binario … con salida en terminal*.
4. **Registro de la sesión:** `journalctl --user -e` (GNOME y otras sesiones con systemd).
5. **Probar el paquete en un sistema limpio:** una máquina virtual o un contenedor con Debian, Ubuntu o Mint **sin** las herramientas de desarrollo instaladas.

---

## 7. Lanzador, icono y «doble clic»

La app se abre desde el **menú de aplicaciones** (busca «Notas Rápidas») o desde un icono del Escritorio. En Linux el doble clic sobre el binario no es fiable (algunos gestores lo tratan como biblioteca compartida); lo correcto es lanzar desde el `.desktop`.

| Escritorio | Menú | Icono en el Escritorio |
|---|---|---|
| **Debian (GNOME)** | Actividades → escribir «Notas» | GNOME de Debian no muestra iconos en el Escritorio por defecto |
| **Ubuntu (GNOME)** | Actividades / cuadrícula | Sí; clic derecho sobre el icono → *Permitir lanzar* |
| **Linux Mint (Cinnamon)** | Menú de Mint | Sí; debe tener permiso de ejecución (*Propiedades → Permisos*) |

`instalar_local.sh --escritorio` hace el `chmod +x` y marca el lanzador como de confianza.

---

## 8. Flujo de trabajo recomendado

```
 1. Editar código                     →  VS Code
 2. Probar rápido y depurar           →  F5 (sin instalar)
 3. Probar la instalación             →  Tarea «Instalar en local …»
 4. Crear el paquete                  →  Ctrl+Shift+B (.deb)
 5. Probar en una VM limpia           →  sudo apt install ./….deb
 6. Distribuir                        →  .deb suelto, repositorio APT o Flatpak (guía §2.10)
```

---

## 9. Personalizar el proyecto

| Quiero… | Dónde |
|---|---|
| Cambiar el nombre mostrado | `Name=` en el `.desktop` y `APP_NAME` en el `.py` |
| Cambiar el nombre del paquete y del comando | `PAQUETE=` en `crear_deb.sh`, `APP=` en `instalar_local.sh`, nombre del `.desktop` |
| Cambiar versión, mantenedor y descripción | `VERSION`, `MANTENEDOR`, `DESCRIPCION` en `crear_deb.sh` |
| Cambiar el icono | Reemplazar `icono.png` y regenerar `icono_256.png` e `icono_48.png` |
| Añadir una librería de Python | Con apt si existe (`python3-xxx`) o en el `.venv`; si va en el `.deb`, vendorizarla como hace `app_web/crear_deb.sh` |
| Añadir una dependencia de apt | Línea `Depends:` en `crear_deb.sh` |
| Cambiar los tipos de fichero asociados | `MimeType=` en el `.desktop` |
| Cambiar la carpeta de datos | `APP_ID` en el `.py` |

Tras cambiar opciones, usa la tarea **Limpiar build/ y dist/** antes de construir de nuevo.

---

## 10. Problemas frecuentes en VS Code y Linux

| Síntoma | Causa | Solución |
|---|---|---|
| `ModuleNotFoundError: tkinter` | Falta el paquete de apt | `sudo apt install python3-tk` |
| `Import "gi" could not be resolved` | El venv no ve los paquetes del sistema | Recrear con `python3 -m venv --system-site-packages .venv` |
| `error: externally-managed-environment` | PEP 668 | Usar siempre `.venv` |
| `The virtual environment was not created…` | Falta `python3-venv` | `sudo apt install python3-venv` |
| `python: command not found` | Solo existe `python3` | Usar `python3`, o `sudo apt install python-is-python3` |
| `sudo: command not found` / no estás en sudoers (Debian) | Debian no configura sudo con contraseña de root | `su -` → `apt install sudo; usermod -aG sudo USUARIO` y reiniciar sesión |
| F5 no hace nada o «Debugger not found» | Falta la extensión | Instalar *Python Debugger* (`ms-python.debugpy`) |
| `Permission denied: ./crear_deb.sh` | Sin permiso de ejecución | `chmod +x app_tk/*.sh app_web/*.sh` |
| `dpkg-deb: command not found` | Falta `dpkg-dev` o no es una distro Debian | `sudo apt install dpkg-dev` |
| `dpkg: dependency problems` al instalar | Se usó `dpkg -i` | `sudo apt install -f`, o `apt install ./paquete.deb` |
| La app no aparece en el menú | Caché sin actualizar | `update-desktop-database ~/.local/share/applications`; cerrar y abrir sesión |
| El icono es genérico | Nombre/caché | `Icon=` sin extensión; `gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor` |
| `You must have either QT or GTK…` | Faltan paquetes de pywebview | Ver sección 2.2 |
| Ventana de pywebview en blanco (VM, algunas NVIDIA) | Aceleración gráfica | Ejecutar con `WEBKIT_DISABLE_COMPOSITING_MODE=1` |
| `GLIBC_2.xx not found` | Binario construido en una distro más nueva | Construir en la más antigua, o usar el `.deb` |
| VS Code (Flatpak o snap) no ve `tkinter`/`gi` | Entorno aislado | Instalar VS Code con el `.deb` oficial |
| `.desktop` del Escritorio «no es de confianza» | Falta permiso o confianza | `chmod +x`, *Permitir lanzar* (GNOME), *Propiedades → Permisos* (Nemo) |
| Tk borroso en Wayland | Escalado fraccionario (XWayland) | Escalado entero o toolkit nativo |
| Dos iconos en el dock | `WM_CLASS` ≠ `StartupWMClass` | Igualarlos (guía, §2.8) |

---

## 11. Control de versiones (opcional)

```bash
git init
git add .
git commit -m "Notas Rápidas: versiones Tkinter y pywebview para Linux"
```

`.gitignore` ya excluye `.venv`, `build`, `dist`, `*.spec` y `*.deb`. VS Code incluye el panel *Source Control* (`Ctrl+Shift+G`).

---

## 12. Referencias

- VS Code, depuración de Python: <https://code.visualstudio.com/docs/python/debugging>
- VS Code, tareas: <https://code.visualstudio.com/docs/editor/tasks>
- VS Code en Linux: <https://code.visualstudio.com/docs/setup/linux>
- Desktop Entry Specification: <https://specifications.freedesktop.org/desktop-entry-spec/latest/>
- Guía del mantenedor de Debian: <https://www.debian.org/doc/manuals/maint-guide/>
- pywebview: <https://pywebview.flowrl.com>
- Guías del proyecto: `docs/GUIA_APP_LINUX.md` y `docs/GUIA_PYWEBVIEW_LINUX.md`

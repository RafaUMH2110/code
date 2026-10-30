# Manual: programar, ejecutar y construir apps de macOS desde VS Code

Proyecto de ejemplo con dos versiones de la misma app («Notas Rápidas»):

- **`app_tk/`**: interfaz con Tkinter.
- **`app_web/`**: interfaz HTML dentro de una ventana nativa (pywebview).

La app es **autocontenida**: esta carpeta (`macos/notas-rapidas/` en el repositorio) lleva su propio `.vscode/`, sus guías, su manual y su `.gitignore`. Se abre como proyecto independiente en VS Code, sin depender de otras apps del repositorio.

> **Requisito:** todo se hace en un **Mac**, con VS Code instalado en ese mismo Mac. El `.app` solo se puede construir en macOS (no vale Codespaces, WSL ni SSH a Linux).

---

## 1. Estructura de la carpeta

```
notas-rapidas/                     ← raíz del proyecto de VS Code (se abre esta carpeta)
├── .vscode/
│   ├── launch.json                ← ejecución y depuración (F5)
│   ├── tasks.json                 ← tareas: construir, abrir, ver logs, limpiar
│   ├── settings.json              ← intérprete, formato, exclusiones
│   └── extensions.json            ← extensiones recomendadas
├── app_tk/                        ← versión Tkinter
│   ├── notas_app.py
│   ├── setup.py                   ← configuración de py2app
│   ├── construir_app.sh
│   └── icono.png
├── app_web/                       ← versión pywebview
│   ├── notas_web.py
│   ├── ui/index.html              ← la interfaz
│   ├── setup_web.py
│   ├── construir_app_web.sh
│   └── icono.png
├── docs/
│   ├── GUIA_APP_MACOS.md          ← conceptos básicos y avanzados (Tkinter, empaquetado, firma)
│   └── GUIA_PYWEBVIEW.md          ← detalles de la variante pywebview
├── .gitignore
└── MANUAL_VSCODE.md               ← este manual
```

Dentro de la app, las variantes se llaman `app_tk` y `app_web` a propósito: **nunca nombres una carpeta `tkinter` o `webview`**, porque taparía el módulo real y provocaría errores de importación.

### Convención: una carpeta autocontenida por app

En el repositorio, cada app es una carpeta de primer nivel dentro de `macos/` (nombre en minúsculas y guiones: `notas-rapidas`, `conversor-unidades`…) que contiene **todo lo suyo**: código, `.vscode/`, `docs/`, manual y `.gitignore`. Así las apps no comparten ficheros y se pueden abrir, copiar o eliminar de forma independiente.

Para añadir una app nueva:

1. Copia la carpeta `notas-rapidas/` como plantilla y renómbrala (`macos/<mi-app>/`).
2. Sustituye el código de `app_tk/` y `app_web/` (o crea las variantes que necesites).
3. Ajusta `.vscode/launch.json` y `.vscode/tasks.json` con los nombres de los ficheros y de los `.exe`/`.app` de la nueva app.
4. Edita el manual y las guías para que hablen de la nueva app.
5. En VS Code, abre `macos/<mi-app>/` como carpeta raíz.

---

## 2. Preparación (una sola vez)

### 2.1 Instalar Python con Tk

Descarga Python desde <https://www.python.org/downloads/macos/>. Comprueba en el Terminal:

```bash
python3 --version
python3 -c "import tkinter; print(tkinter.TkVersion)"   # debe mostrar 8.6 o superior
```

> Si usas Homebrew: `brew install python-tk`. Evita el Python de las *Command Line Tools* de Xcode: su Tk es antiguo y falla.

### 2.2 Instalar VS Code y abrir la carpeta

1. Instala VS Code desde <https://code.visualstudio.com>.
2. *File → Open Folder…* y elige `macos/notas-rapidas`.
3. VS Code propondrá instalar las extensiones recomendadas (`.vscode/extensions.json`). Acepta. Las importantes son **Python** y **Debugpy** (Microsoft).
4. Si te lo pide, confía en el autor de la carpeta (*Trust*).

### 2.3 Crear el entorno de desarrollo

Tienes dos formas:

**A. Con una tarea:** `Cmd+Shift+P` → *Tasks: Run Task* → **0. Crear entorno de desarrollo (.venv)**.

**B. Desde el terminal integrado** (`Ctrl+\``):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip py2app pywebview
```

Después, selecciona el intérprete: `Cmd+Shift+P` → *Python: Select Interpreter* → `./.venv/bin/python`. En la barra inferior debe aparecer `.venv`. (`settings.json` ya lo configura por defecto.)

---

## 3. Programar

| Qué | Cómo |
|---|---|
| Abrir un fichero | `Cmd+P` y escribir el nombre |
| Buscar en todo el proyecto | `Cmd+Shift+F` |
| Ir a la definición de una función | `F12` o `Cmd+clic` |
| Ver todos los usos | `Shift+F12` |
| Renombrar un símbolo en todo el proyecto | `F2` |
| Paleta de comandos | `Cmd+Shift+P` |
| Terminal integrado | `Ctrl+\`` |
| Formatear el fichero | `Shift+Option+F` (también al guardar) |

**Consejos**

- Edita la interfaz web en `app_web/ui/index.html`; la lógica de Python en `notas_web.py`.
- Pylance marca en la barra lateral errores y avisos (pestaña *Problems*, `Cmd+Shift+M`).
- Los métodos de la clase `Api` sin guion bajo son los que llama JavaScript. Los que empiezan por `_` son internos.

---

## 4. Ejecutar y depurar (sin construir el .app)

Abre la vista de ejecución (`Cmd+Shift+D`), elige una configuración en el desplegable y pulsa **F5**.

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
2. Haz clic derecho en la ventana → **Inspeccionar elemento**.
3. En la pestaña *Consola* verás los errores; en *Red* y *Elementos*, lo habitual de Safari.

Para probar la interfaz sin Python, abre `app_web/ui/index.html` en el navegador (los botones que llaman a Python no funcionarán, pero verás diseño y estilos).

---

## 5. Construir el `.app`

### 5.1 Con una tarea (recomendado)

`Cmd+Shift+B` ejecuta la tarea de construcción predeterminada (**Construir .app Tkinter**). Para elegir otra: `Cmd+Shift+P` → *Tasks: Run Task*.

| Tarea | Resultado |
|---|---|
| **Construir .app Tkinter (independiente)** | `app_tk/dist/Notas Rápidas.app` |
| **Construir .app pywebview (independiente)** | `app_web/dist/Notas Rápidas Web.app` |
| **Alias .app … (desarrollo rápido)** | `.app` ligero que apunta a tu código fuente |
| **Abrir .app …** | Lo abre como si hicieras doble clic |
| **Ejecutar .app … con salida en terminal** | Lo lanza desde el terminal para ver errores |
| **Ver log de la app …** | Sigue en directo el fichero de registro |
| **Limpiar build/ y dist/** | Borra los resultados de compilación |

Los scripts `construir_app*.sh` hacen, en orden: crean un `.venv` propio dentro de la carpeta de la app, instalan `py2app` (y `pywebview`), convierten `icono.png` en `icono.icns`, construyen y firman con firma *ad-hoc*.

La primera vez, macOS puede pedir permiso para ejecutar el script: `chmod +x` ya está aplicado; si da *Permission denied*, ejecuta en el terminal `chmod +x app_tk/construir_app.sh app_web/construir_app_web.sh`.

### 5.2 Desde el terminal integrado

```bash
cd app_tk && ./construir_app.sh
# o
cd app_web && ./construir_app_web.sh
```

### 5.3 Dos modos de construcción

| Modo | Comando | Tarda | Para qué |
|---|---|---|---|
| **Alias** | `python setup.py py2app -A` | Segundos | Probar el icono, el `Info.plist` y el doble clic mientras desarrollas. Solo funciona en tu Mac |
| **Independiente** | `./construir_app.sh` | Un minuto o más | La versión que puedes copiar a otro Mac |

En modo alias el `.app` ejecuta el código fuente actual: cambias el `.py`, guardas y reabres la app **sin reconstruir**.

---

## 6. Probar y depurar el `.app` ya construido

Un `.app` **no se depura con F5**. Usa estas vías:

1. **Terminal integrado:** tarea *Ejecutar .app … con salida en terminal*. Se ve cualquier error de arranque.
2. **Registro:** tarea *Ver log de la app …*. Lee `~/Library/Logs/NotasRapidas/app.log` (Tkinter) o `~/Library/Logs/NotasRapidasWeb/app.log` (pywebview).
3. **Informes de fallo del sistema:** `~/Library/Logs/DiagnosticReports/` o la aplicación *Consola*.
4. **Inspeccionar el contenido:** clic derecho sobre el `.app` en Finder → *Mostrar contenido del paquete*.

---

## 7. Flujo de trabajo recomendado

```
 1. Editar código                    →  VS Code
 2. Probar rápido y depurar          →  F5 (sin .app)
 3. Probar icono y doble clic        →  Tarea «Alias .app»
 4. Construir versión final          →  Cmd+Shift+B
 5. Probar en otro Mac / usuario     →  Copiar el .app (zip) y abrirlo
 6. Distribuir                       →  Firmar y notarizar (ver docs/GUIA_APP_MACOS.md, §2.9)
```

---

## 8. Personalizar el proyecto

| Quiero… | Dónde |
|---|---|
| Cambiar el nombre de la app | `CFBundleName` y `CFBundleDisplayName` en `setup.py` / `setup_web.py` |
| Poner mi identificador | `CFBundleIdentifier` (por ejemplo `es.midominio.notas`) |
| Cambiar el icono | Reemplazar `icono.png` (1024×1024) y borrar `icono.icns` si existe |
| Cambiar versión | `CFBundleVersion` y `CFBundleShortVersionString` |
| Incluir ficheros extra (imágenes, plantillas) | Clave `"resources"` en `setup*.py` |
| Añadir una librería | `pip install librería` en el entorno y, si el `.app` no la encuentra, añadirla a `"packages"` o `"includes"` |
| Cambiar el nombre de la carpeta de datos | `APP_ID` en `notas_app.py` / `notas_web.py` |

Tras cambiar `setup*.py` o el icono, usa la tarea **Limpiar build/ y dist/** antes de construir de nuevo.

---

## 9. Problemas frecuentes en VS Code

| Síntoma | Causa | Solución |
|---|---|---|
| `Import "webview" could not be resolved` | Intérprete equivocado | `Python: Select Interpreter` → `.venv` y comprobar que `pip install pywebview` se hizo en ese entorno |
| `ModuleNotFoundError: tkinter` | Python sin Tk | Instalar Python de python.org o `brew install python-tk` |
| F5 no hace nada o aparece «Debugger not found» | Falta la extensión | Instalar *Python Debugger* (`ms-python.debugpy`) |
| La ventana de Tkinter se ve vacía o rara | Tk antiguo | Usar Python de python.org |
| `Permission denied: ./construir_app.sh` | Sin permiso de ejecución | `chmod +x app_tk/construir_app.sh app_web/construir_app_web.sh` |
| El script falla en `codesign` o `iconutil` | Faltan *Command Line Tools* | `xcode-select --install` |
| El `.app` se abre y se cierra | Error de arranque | Tarea *Ejecutar .app … con salida en terminal* y revisar el log |
| `ModuleNotFoundError` solo en el `.app` | py2app no detectó el módulo | Añadirlo a `"packages"` / `"includes"` y reconstruir |
| El icono no cambia | Caché de iconos de Finder | `touch` al `.app` o `killall Finder` |
| Las tareas no aparecen | Carpeta mal abierta | Abrir `macos/notas-rapidas` (la raíz que contiene `.vscode`) |
| El formateador no actúa | Falta la extensión Black | Instalarla o quitar `editor.defaultFormatter` de `settings.json` |
| «App dañada» al copiarla a otro Mac | Cuarentena de macOS | Clic derecho → Abrir; o firmar y notarizar |

---

## 10. Control de versiones (opcional)

```bash
git init
git add .
git commit -m "Notas Rápidas: versiones Tkinter y pywebview"
```

`.gitignore` ya excluye `.venv`, `build`, `dist` e iconos generados. VS Code incluye el panel *Source Control* (`Ctrl+Shift+G`) para hacer commits sin usar el terminal.

---

## 11. Referencias

- VS Code, depuración de Python: <https://code.visualstudio.com/docs/python/debugging>
- VS Code, tareas: <https://code.visualstudio.com/docs/editor/tasks>
- VS Code, entornos Python: <https://code.visualstudio.com/docs/python/environments>
- py2app: <https://py2app.readthedocs.io>
- pywebview: <https://pywebview.flowrl.com>
- Guías del proyecto: `docs/GUIA_APP_MACOS.md` y `docs/GUIA_PYWEBVIEW.md`

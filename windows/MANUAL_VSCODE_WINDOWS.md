# Manual: programar, ejecutar y construir apps de Windows desde VS Code

Proyecto de ejemplo con dos versiones de la misma app («Notas Rápidas»):

- **`notas-rapidas/`** (carpeta de la app) con dos variantes:
  - **`app_tk/`**: interfaz con Tkinter.
  - **`app_web/`**: interfaz HTML dentro de una ventana nativa (pywebview + Edge WebView2).

> **Requisito:** todo se hace en un equipo con **Windows 10 u 11**, con VS Code instalado en ese mismo equipo. PyInstaller construye ejecutables para el sistema en el que se ejecuta: un `.exe` de Windows solo se puede construir en Windows.

---

## 1. Estructura de la carpeta

```
windows/
├── .vscode/                       ← configuración COMÚN a todas las apps
│   ├── launch.json                ← ejecución y depuración (F5)
│   ├── tasks.json                 ← tareas: construir, abrir, ver logs, limpiar
│   ├── settings.json              ← intérprete, formato, exclusiones
│   └── extensions.json            ← extensiones recomendadas
├── notas-rapidas/                 ← UNA CARPETA POR APP
│   ├── app_tk/                    ← versión Tkinter
│   │   ├── notas_app.py
│   │   ├── construir_app.ps1      ← construye el .exe (PyInstaller)
│   │   ├── construir_app.bat      ← lo mismo con doble clic
│   │   └── icono.png / icono.ico
│   └── app_web/                   ← versión pywebview
│       ├── notas_web.py
│       ├── ui/index.html          ← la interfaz
│       ├── construir_app_web.ps1
│       ├── construir_app_web.bat
│       └── icono.png / icono.ico
├── docs/                          ← guías generales, válidas para cualquier app
│   ├── GUIA_APP_WINDOWS.md        ← conceptos básicos y avanzados
│   └── GUIA_PYWEBVIEW_WINDOWS.md  ← detalles de la variante pywebview
├── .gitignore
└── MANUAL_VSCODE_WINDOWS.md       ← este manual
```

Dentro de cada app, las variantes se llaman `app_tk` y `app_web` a propósito: **nunca nombres una carpeta `tkinter` o `webview`**, porque taparía el módulo real y provocaría errores de importación.

### Convención: una carpeta por app

Cada app nueva va en su **propia carpeta** de primer nivel, con nombre en minúsculas y guiones (`notas-rapidas`, `conversor-unidades`…). Dentro, una subcarpeta por variante o tecnología. Lo que es común (`.vscode/`, `docs/`, `.gitignore`, el manual) se queda en la raíz del proyecto.

Para añadir una app:

1. Crea `<mi-app>/` con sus subcarpetas (por ejemplo `<mi-app>/app_tk/`) y copia ahí los ficheros de la app y su script de construcción.
2. En `.vscode/launch.json` añade una configuración con `program` y `cwd` apuntando a `${workspaceFolder}/<mi-app>/...`.
3. En `.vscode/tasks.json` añade las tareas de construir y abrir, con `options.cwd` apuntando a la misma carpeta.
4. Si la app tiene una guía propia, ponla en `docs/` o dentro de `<mi-app>/`.

---

## 2. Preparación (una sola vez)

### 2.1 Instalar Python con Tk

1. Descarga Python desde <https://www.python.org/downloads/windows/> (recomendado 3.11–3.13).
2. En el instalador marca **«Add python.exe to PATH»** y deja activada la opción *tcl/tk and IDLE* y el *py launcher*.
3. Comprueba en PowerShell:

```powershell
py -3 --version
py -3 -c "import tkinter; print(tkinter.TkVersion)"   # debe mostrar 8.6 o superior
```

> Evita la versión de **Microsoft Store**: redirige `AppData` a una carpeta privada y mezcla rutas de logs y configuración.

### 2.2 Instalar VS Code y abrir la carpeta

1. Instala VS Code desde <https://code.visualstudio.com>.
2. *File → Open Folder…* y elige `windows`.
3. VS Code propondrá instalar las extensiones recomendadas (`.vscode/extensions.json`). Acepta. Las importantes son **Python** y **Python Debugger** (Microsoft); **PowerShell** ayuda a editar los `.ps1`.
4. Si te lo pide, confía en el autor de la carpeta (*Trust*).

### 2.3 Crear el entorno de desarrollo

**A. Con una tarea:** `Ctrl+Shift+P` → *Tasks: Run Task* → **0. Crear entorno de desarrollo (.venv)**.

**B. Desde el terminal integrado** (``Ctrl+` ``):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip pyinstaller pywebview pillow
```

Después selecciona el intérprete: `Ctrl+Shift+P` → *Python: Select Interpreter* → `.\.venv\Scripts\python.exe`. En la barra inferior debe aparecer `.venv`. (`settings.json` ya lo configura por defecto.)

> **Si PowerShell dice «la ejecución de scripts está deshabilitada»** al activar el entorno, ejecuta una sola vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
> Los scripts de construcción no lo necesitan: se lanzan con `-ExecutionPolicy Bypass`.

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
| Formatear el fichero | `Shift+Alt+F` (también al guardar) |

**Consejos**

- Edita la interfaz web en `notas-rapidas\app_web\ui\index.html`; la lógica de Python en `notas_web.py`.
- Los métodos de la clase `Api` sin guion bajo son los que llama JavaScript. Los que empiezan por `_` son internos.
- Los `.ps1` deben guardarse como **UTF-8 con BOM** y fin de línea CRLF para que Windows PowerShell 5.1 lea bien las tildes; `settings.json` ya lo aplica a esos ficheros.

---

## 4. Ejecutar y depurar (sin construir el .exe)

Abre la vista de ejecución (`Ctrl+Shift+D`), elige una configuración y pulsa **F5**.

| Configuración | Qué hace |
|---|---|
| **Tkinter: ejecutar / depurar** | Lanza `notas-rapidas\app_tk\notas_app.py` |
| **pywebview: ejecutar / depurar (con inspector web)** | Lanza `notas-rapidas\app_web\notas_web.py --debug` |
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
2. Pulsa `F12` o haz clic derecho → **Inspeccionar** (herramientas de Edge).
3. En *Consola*, *Red* y *Elementos* verás lo habitual de un navegador.

Para probar solo el diseño, abre `notas-rapidas\app_web\ui\index.html` en el navegador (los botones que llaman a Python no funcionarán).

---

## 5. Construir el `.exe`

### 5.1 Con una tarea (recomendado)

`Ctrl+Shift+B` ejecuta la tarea de construcción predeterminada (**Construir .exe Tkinter (carpeta)**). Para elegir otra: `Ctrl+Shift+P` → *Tasks: Run Task*.

| Tarea | Resultado |
|---|---|
| **Construir .exe Tkinter (carpeta)** | `notas-rapidas\app_tk\dist\NotasRapidas\NotasRapidas.exe` |
| **Construir .exe pywebview (carpeta)** | `notas-rapidas\app_web\dist\NotasRapidasWeb\NotasRapidasWeb.exe` |
| **… (un solo .exe)** | `dist\NotasRapidas.exe` / `dist\NotasRapidasWeb.exe` |
| **… con consola (depuración)** | `.exe` que abre una consola con trazas y errores |
| **Abrir .exe …** | Lo ejecuta como si hicieras doble clic |
| **Ejecutar .exe … con salida en terminal** | Lo lanza desde el terminal |
| **Ver log de la app …** | Sigue en directo el fichero de registro |
| **Abrir carpeta de datos de usuario** | Abre `%APPDATA%` |
| **Limpiar build/ y dist/** | Borra los resultados de compilación |

Los scripts `construir_app*.ps1` hacen, en orden: crean un `.venv` propio dentro de la carpeta de la app, instalan `pyinstaller` (y `pywebview`), generan `icono.ico` si falta, construyen con PyInstaller y abren la carpeta `dist` en el Explorador.

### 5.2 Con doble clic

Abre `notas-rapidas/app_tk` o `notas-rapidas/app_web` en el Explorador y haz doble clic en `construir_app.bat` / `construir_app_web.bat`. Argumentos opcionales desde terminal: `construir_app.bat -UnSoloExe` o `-Consola`.

### 5.3 Desde el terminal integrado

```powershell
cd notas-rapidas/app_tk
.\construir_app.ps1                 # carpeta
.\construir_app.ps1 -UnSoloExe      # un solo .exe
.\construir_app.ps1 -Consola        # con consola para depurar

cd ..\app_web
.\construir_app_web.ps1
```

### 5.4 Carpeta frente a un solo `.exe`

| Modo | Tarda en arrancar | Antivirus | Distribución |
|---|---|---|---|
| **Carpeta** (por defecto) | Rápido | Menos falsos positivos | Comprimir en `.zip` o crear instalador |
| **Un solo `.exe`** | Más lento (se descomprime cada vez) | Más falsos positivos | Un único fichero |

---

## 6. Probar y depurar el `.exe` ya construido

Un `.exe` **no se depura con F5**. Usa estas vías:

1. **Construir con consola:** tarea *Construir … con consola (depuración)* y ejecutar el `.exe` desde PowerShell: el traceback aparece en pantalla.
2. **Registro:** tarea *Ver log de la app …*. Lee `%LOCALAPPDATA%\NotasRapidas\Logs\app.log` (Tkinter) o `%LOCALAPPDATA%\NotasRapidasWeb\Logs\app.log` (pywebview).
3. **Visor de eventos:** *Registros de Windows → Aplicación* muestra cierres inesperados.
4. **Equipo limpio:** copia la carpeta `dist\…` a otro PC o máquina virtual **sin Python** para confirmar que es realmente independiente.

---

## 7. Flujo de trabajo recomendado

```
 1. Editar código                    →  VS Code
 2. Probar rápido y depurar          →  F5 (sin .exe)
 3. Construir versión de prueba      →  Ctrl+Shift+B
 4. Si falla: construir con consola  →  Tarea «… con consola»
 5. Probar en otro PC / usuario      →  Copiar la carpeta dist\… (zip)
 6. Distribuir                       →  Instalador y firma (ver docs\GUIA_APP_WINDOWS.md, §2.9–2.10)
```

---

## 8. Personalizar el proyecto

| Quiero… | Dónde |
|---|---|
| Cambiar el nombre del `.exe` | Opción `--name` en el `.ps1` correspondiente |
| Cambiar el nombre mostrado | `APP_NAME` en `notas_app.py` / `notas_web.py` |
| Cambiar el icono | Reemplazar `icono.png` (1024×1024) y borrar `icono.ico` para que se regenere |
| Cambiar la versión | `VERSION` en el `.py`; para las propiedades del `.exe`, `--version-file` |
| Incluir ficheros extra (imágenes, plantillas) | Otra opción `--add-data "origen;destino"` |
| Añadir una librería | `pip install librería` en el entorno; si el `.exe` no la encuentra, `--hidden-import` o `--collect-all` |
| Cambiar la carpeta de datos | `APP_ID` en el `.py` |
| Pedir permisos de administrador | `--uac-admin` (solo si es imprescindible) |

Tras cambiar opciones o el icono, usa la tarea **Limpiar build/ y dist/** antes de construir de nuevo.

---

## 9. Problemas frecuentes en VS Code y Windows

| Síntoma | Causa | Solución |
|---|---|---|
| `Import "webview" could not be resolved` | Intérprete equivocado | `Python: Select Interpreter` → `.venv` y `pip install pywebview` en ese entorno |
| `ModuleNotFoundError: tkinter` | Python sin Tk | Reinstalar Python marcando *tcl/tk and IDLE* |
| `py` no se reconoce | Falta el *py launcher* | Reinstalar Python con esa opción, o usar `python` |
| F5 no hace nada o «Debugger not found» | Falta la extensión | Instalar *Python Debugger* (`ms-python.debugpy`) |
| «La ejecución de scripts está deshabilitada» | Política de PowerShell | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, o usar el `.bat` |
| Los textos con tildes salen mal en el terminal | `.ps1` sin BOM | Guardar como UTF-8 con BOM (ya configurado en `settings.json`) |
| El `.exe` se abre y se cierra | Error de arranque | Construir con consola y revisar el log |
| `ModuleNotFoundError` solo en el `.exe` | PyInstaller no detectó el módulo | `--hidden-import` / `--collect-all` y reconstruir |
| Ventana en blanco en pywebview | Falta WebView2 o `ui` | Instalar WebView2 Runtime; revisar `--add-data "ui;ui"` |
| Windows Defender elimina el `.exe` | Falso positivo | Usar modo carpeta; firmar; enviar a Microsoft para análisis |
| «Windows protegió su PC» | SmartScreen | *Más información → Ejecutar de todas formas*, o firmar el `.exe` |
| `Permission denied` al reconstruir | El `.exe` sigue abierto | Cerrar la app y reintentar; limpiar `dist` |
| El icono no cambia | Caché de iconos | Reiniciar el Explorador o `ie4uinit.exe -show` |
| Las tareas no aparecen | Carpeta mal abierta | Abrir `windows` (la raíz que contiene `.vscode`) |
| Se abren ventanas sin parar | Falta `freeze_support()` | Ya incluido; mantenerlo si cambias `main()` |

---

## 10. Control de versiones (opcional)

```powershell
git init
git add .
git commit -m "Notas Rápidas: versiones Tkinter y pywebview para Windows"
```

`.gitignore` ya excluye `.venv`, `build`, `dist` y `*.spec`. VS Code incluye el panel *Source Control* (`Ctrl+Shift+G`) para hacer commits sin usar el terminal.

---

## 11. Referencias

- VS Code, depuración de Python: <https://code.visualstudio.com/docs/python/debugging>
- VS Code, tareas: <https://code.visualstudio.com/docs/editor/tasks>
- VS Code, entornos Python: <https://code.visualstudio.com/docs/python/environments>
- PyInstaller: <https://pyinstaller.org>
- pywebview: <https://pywebview.flowrl.com>
- Guías del proyecto: `docs\GUIA_APP_WINDOWS.md` y `docs\GUIA_PYWEBVIEW_WINDOWS.md`

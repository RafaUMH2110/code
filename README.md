# code

Ejemplos de código y aplicaciones en Python, organizados por sistema operativo. Cada app es un proyecto autocontenido (código, `.vscode/`, guías, manual y `.gitignore`) que se abre como carpeta raíz en VS Code.

## Organización

En la raíz del repositorio solo hay tres carpetas, una por sistema operativo. Dentro de cada una hay **un directorio por app**, con el nombre de la app, y dentro de éste está todo el contenido generado para ella.

```
code/
├── macos/
│   ├── notas-rapidas/          ← app «Notas Rápidas» (.app con py2app)
│   └── generador-apps/         ← generador de apps web con IA
├── windows/
│   ├── notas-rapidas/          ← app «Notas Rápidas» (.exe con PyInstaller)
│   └── generador-apps/
└── linux/
    ├── notas-rapidas/          ← app «Notas Rápidas» (.deb para Debian, Ubuntu y Mint)
    └── generador-apps/
```

Contenido de cada app (ejemplo con `notas-rapidas`):

```
notas-rapidas/
├── .vscode/            ← ejecución, depuración y tareas de VS Code
├── app_tk/             ← versión Tkinter
├── app_web/            ← versión pywebview (interfaz HTML)
├── app_pyside6/        ← versión PySide6
├── app_wx/             ← versión wxPython
├── app_toga/           ← versión Toga (BeeWare)
├── …                   (app_pyobjc/, solo en macos/: PyObjC existe únicamente en macOS)
├── docs/               ← guías (conceptos básicos y avanzados)
├── .gitignore
└── MANUAL_VSCODE_<SISTEMA>.md
```

### Reglas

- La raíz solo contiene `macos/`, `windows/` y `linux/` (más este README y `.gitattributes`).
- Cada app va en su propio directorio dentro de cada sistema operativo. Nombres en minúsculas y guiones (`notas-rapidas`, `generador-apps`…).
- Cada app lleva dentro todo lo suyo; no se comparten ficheros entre apps.
- Una app multiplataforma se añade en las tres carpetas (cada una adaptada a su sistema, o idéntica si no depende de él).
- Para trabajar con una app, abre su carpeta (por ejemplo `macos/notas-rapidas/`) en VS Code (*File → Open Folder…*).

### Añadir una app nueva

1. Crea `macos/<mi-app>/`, `windows/<mi-app>/` y/o `linux/<mi-app>/`.
2. Copia como plantilla la estructura de `notas-rapidas/` (o de `generador-apps/`) y sustituye el código.
3. Ajusta `.vscode/launch.json`, `.vscode/tasks.json`, el manual y las guías.
4. Añade la app a la tabla de abajo.

## Apps

| App | Descripción | macOS | Windows | Linux |
|---|---|---|---|---|
| **notas-rapidas** | Bloc de notas de escritorio. Se ejecuta con doble clic. Versiones por toolkit en macOS, Windows y Linux: Tkinter (`app_tk/`), pywebview con interfaz HTML (`app_web/`), PySide6 (`app_pyside6/`), wxPython (`app_wx/`) y Toga (`app_toga/`); solo en macOS, además, PyObjC (`app_pyobjc/`) | [manual](macos/notas-rapidas/MANUAL_VSCODE.md) | [manual](windows/notas-rapidas/MANUAL_VSCODE_WINDOWS.md) | [manual](linux/notas-rapidas/MANUAL_VSCODE_LINUX.md) |
| **generador-apps** | Script en Python que genera o modifica apps web de un solo HTML con la API de Anthropic u OpenAI. Dos versiones: `python-app-api-anthropic/` y `mejora-de-codigo/` | [README](macos/generador-apps/README.md) | [README](windows/generador-apps/README.md) | [README](linux/generador-apps/README.md) |

## Notas Rápidas: diferencias entre plataformas

| | macOS | Windows | Linux (Debian / Ubuntu / Mint) |
|---|---|---|---|
| Empaquetador | py2app | PyInstaller | `.deb` (`dpkg-deb`); PyInstaller opcional |
| Resultado | `.app` | `.exe` | Paquete `.deb` + lanzador `.desktop` |
| Icono | `.icns` | `.ico` | PNG en el tema `hicolor` |
| Motor web (pywebview) | WKWebView | Edge WebView2 | GTK + WebKitGTK |
| Datos de usuario | `~/Library/Application Support` | `%APPDATA%` | `~/.config` (XDG) |
| Registro | `~/Library/Logs` | `%LOCALAPPDATA%` | `~/.local/state` (XDG) |
| Firma | Developer ID + notarización | Certificado de firma + SmartScreen | Repositorio APT firmado con GPG |

En Linux el mismo `.deb` sirve en Debian, Ubuntu y Linux Mint; las diferencias entre ellas están en la parte 3 de [`GUIA_APP_LINUX.md`](linux/notas-rapidas/docs/GUIA_APP_LINUX.md).

## Estado de verificación

- El código Python se ha comprobado sintácticamente y la interfaz HTML de Notas Rápidas se ha probado en un navegador con el puente a Python simulado.
- El empaquetado (py2app / PyInstaller / `.deb`) y la ejecución real con Tkinter y pywebview **deben probarse en cada sistema**. Si el ejecutable no encuentra algún módulo, las guías explican cómo añadirlo.
- El generador de apps se probó solo con clientes de API simulados; pruébalo con tu clave.

## Requisitos

- Python 3.11–3.13 de [python.org](https://www.python.org/downloads/) (incluye Tk).
- VS Code con las extensiones *Python* y *Python Debugger*.
- Construir un `.app` requiere macOS; construir un `.exe` requiere Windows; los `.deb` se crean en Debian, Ubuntu, Mint o derivadas.

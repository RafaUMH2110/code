# code

Ejemplos de código y aplicaciones en Python, organizados por sistema operativo. Cada app es un proyecto autocontenido (código, `.vscode/`, guías, manual y `.gitignore`) que se abre como carpeta raíz en VS Code.

## Organización

En la raíz hay tres carpetas por sistema operativo (las apps de escritorio), una carpeta para lo que es idéntico en los tres (`generador-apps/`) y las carpetas de herramientas (`scripts/`, `telemetria/`).

```
code/
├── macos/
│   └── notas-rapidas/          ← app «Notas Rápidas» (.app con py2app)
├── windows/
│   └── notas-rapidas/          ← app «Notas Rápidas» (.exe con PyInstaller)
├── linux/
│   └── notas-rapidas/          ← app «Notas Rápidas» (.deb para Debian, Ubuntu y Mint)
├── generador-apps/             ← generador de apps web con IA (el mismo en los tres sistemas)
├── scripts/                    ← instaladores, informes del colector, mantenimiento de repos, iTerm2
├── docs/                       ← guías y documentos generales (parches en git, traspasos…)
└── telemetria/                 ← scripts Python de telemetría
    ├── meteo/                  ← estación meteorológica Vevor YT60234 (Weather Underground)
    │   ├── telemeteo-consulta/ ← consulta puntual y cliente síncrono (+ GUI)
    │   ├── telemeteo-monitor/  ← monitor asíncrono (+ GUI)
    │   └── telemeteo-puente/   ← puente HTTP → MQTT
    └── home/                   ← TeleHome (telemetría y control del hogar; enchufes Tuya)
        ├── telehome-servicio/  ← servicio Python: interfaz web, modo local y nube, programaciones, macOS y Linux
        └── telehome-pruebas/   ← pruebas por línea de órdenes (VS Code)
```

Contenido de cada app de escritorio (ejemplo con `notas-rapidas`):

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

- Una app que **cambia según el sistema operativo** va en `macos/`, `windows/` y `linux/`, cada una adaptada, en su propio directorio y autocontenida (con `.vscode/`, guías, manual y `.gitignore`).
- Una app que es **idéntica en los tres sistemas** va una sola vez en la raíz (como `generador-apps/`), también autocontenida. Si más adelante necesita diferir por sistema, se separa en las tres carpetas.
- Nombres de directorio en minúsculas y con guiones (`notas-rapidas`, `generador-apps`…). Los módulos y ficheros del programa Python conservan `_` (`generar_app.py`); `macos/`, `windows/` y `linux/` no se renombran.
- Cada app lleva dentro todo lo suyo; no se comparten ficheros entre apps.
- **El colector TeleMet no está aquí**: su única fuente es el repositorio [`apps`](https://github.com/RafaUMH2110/apps/tree/main/telemetria) (`telemetria/meteo/telemetcolector` y `telemetcollector`).
- Para trabajar con una app, abre su carpeta (por ejemplo `macos/notas-rapidas/`) en VS Code (*File → Open Folder…*).

### Añadir una app nueva

1. Crea `macos/<mi-app>/`, `windows/<mi-app>/` y/o `linux/<mi-app>/` (o `<mi-app>/` en la raíz si es idéntica en los tres).
2. Copia como plantilla la estructura de `notas-rapidas/` (o de `generador-apps/`) y sustituye el código.
3. Ajusta `.vscode/launch.json`, `.vscode/tasks.json`, el manual y las guías.
4. Añade la app a la tabla de abajo.

## VS Code
Abre `code.code-workspace` (menú *Archivo → Abrir workspace desde archivo*): reúne cada app como carpeta raíz, de modo que se aplica su `.vscode/` (intérprete `.venv`, depuración y tareas). También puedes abrir una app suelta como carpeta.

## Apps

| App | Descripción | macOS | Windows | Linux |
|---|---|---|---|---|
| **notas-rapidas** | Bloc de notas de escritorio. Se ejecuta con doble clic. Versiones por toolkit en macOS, Windows y Linux: Tkinter (`app_tk/`), pywebview con interfaz HTML (`app_web/`), PySide6 (`app_pyside6/`), wxPython (`app_wx/`) y Toga (`app_toga/`); solo en macOS, además, PyObjC (`app_pyobjc/`) | [manual](macos/notas-rapidas/MANUAL_VSCODE.md) | [manual](windows/notas-rapidas/MANUAL_VSCODE_WINDOWS.md) | [manual](linux/notas-rapidas/MANUAL_VSCODE_LINUX.md) |
| **generador-apps** | Script en Python que genera o modifica apps web de un solo HTML con la API de Anthropic u OpenAI. Tres versiones: `python-app-api-anthropic/`, `mejora-de-codigo/` y `optimizada-vscode/` (la recomendada) | [README](generador-apps/README.md) (igual en los tres sistemas) | ← | ← |

## Otras carpetas

| Carpeta | Contenido |
|---|---|
| [`telemetria/`](telemetria/) | Telemetría en Python, en dos carpetas: [`meteo/`](telemetria/meteo/) y [`home/`](telemetria/home/). Ver su [README](telemetria/README.md). |
| [`telemetria/meteo/`](telemetria/meteo/) | Scripts Python para leer la estación meteorológica Vevor YT60234 (Weather Underground / Earth Network): en tres carpetas `telemeteo-consulta/`, `telemeteo-monitor/` y `telemeteo-puente/` (consulta y cliente síncrono, monitor asíncrono, GUIs Tkinter y puente MQTT). Antes era el repo `RafaUMH2110/telemetria`. Ver su [README](telemetria/meteo/README.md). |
| [`telemetria/home/`](telemetria/home/) | **TeleHome**: telemetría y control del hogar (enchufes inteligentes Energeeks/Tuya), en dos carpetas (siguientes filas); los clientes web, iPhone e iPad, están en el repo `apps`. Ver su [README](telemetria/home/README.md). |
| [`telemetria/home/telehome-servicio/`](telemetria/home/telehome-servicio/) | **TeleHome** (servicio, 0.14.0): telemetría y control de hasta 7 dispositivos Wi-Fi Tuya (enchufes Energeeks EG-EW008MC / EG-EW009MC y luces regulables, de blanco y color, con escenas, grupos, transiciones, temporizadores y estancias), con interfaz web, histórico SQLite, **modo local** (red local) y **modo nube** (API de Tuya IoT, para leer los enchufes desde fuera de su red, p. ej. una VM de Azure), instaladores para macOS y Linux (systemd) y contraseña opcional. Ver su [README](telemetria/home/telehome-servicio/README.md). |
| [`telemetria/home/telehome-pruebas/`](telemetria/home/telehome-pruebas/) | **TeleHome · vscode**: herramienta de pruebas preliminares por línea de órdenes (estado, encender, apagar, vigilar a CSV, datos crudos), configurable por JSON y por variables del código, con `.vscode/` listo. Ver su [README](telemetria/home/telehome-pruebas/README.md) y su [manual](telemetria/home/telehome-pruebas/MANUAL.md). |
| [`scripts/`](scripts/) | Instaladores para clonar los repos y desplegar las apps en Apache (con opción de instalar el colector TeleMet), informes del colector por SSH, auditoría de los repos de `RafaUMH2110`, la guía para mover repos y la configuración de iTerm2 con perfiles por servidor y SSH por clave. Ver su [README](scripts/README.md). |

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

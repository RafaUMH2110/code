# code

Ejemplos de aplicaciones de escritorio en Python que se ejecutan con **doble clic** sobre su icono, con guías y proyecto de VS Code para programarlas, ejecutarlas y construirlas.

## Organización

El repositorio tiene una carpeta por sistema operativo (macOS, Windows y Linux). Dentro, **cada app es una carpeta completamente autocontenida**: lleva su propio código, su `.vscode/`, sus guías (`docs/`), su manual y su `.gitignore`. El código de apps distintas nunca se mezcla.

```
code/
├── macos/                              ← apps para macOS (.app con py2app)
│   └── notas-rapidas/                  ← app «Notas Rápidas» (proyecto de VS Code completo)
│       ├── .vscode/
│       ├── app_tk/                     ← versión Tkinter
│       ├── app_web/                    ← versión pywebview (HTML)
│       ├── docs/
│       │   ├── GUIA_APP_MACOS.md
│       │   └── GUIA_PYWEBVIEW.md
│       ├── .gitignore
│       └── MANUAL_VSCODE.md
└── windows/                            ← apps para Windows (.exe con PyInstaller)
    └── notas-rapidas/
        ├── .vscode/
        ├── app_tk/
        ├── app_web/
        ├── docs/
        │   ├── GUIA_APP_WINDOWS.md
        │   └── GUIA_PYWEBVIEW_WINDOWS.md
        ├── .gitignore
        └── MANUAL_VSCODE_WINDOWS.md
└── linux/                              ← apps para Debian, Ubuntu y Linux Mint (.deb)
    └── notas-rapidas/
        ├── .vscode/
        ├── app_tk/
        ├── app_web/
        ├── docs/
        │   ├── GUIA_APP_LINUX.md       ← incluye las diferencias Debian / Ubuntu / Mint
        │   └── GUIA_PYWEBVIEW_LINUX.md
        ├── .gitignore
        └── MANUAL_VSCODE_LINUX.md
```

Además, `generador-apps/` agrupa herramientas de línea de comandos multiplataforma (no son apps de escritorio): el generador de apps web con IA, en dos versiones separadas. Ver [`generador-apps/README.md`](generador-apps/README.md).

```
generador-apps/
├── python-app-api-anthropic/   ← versión base
└── mejora-de-codigo/           ← versión mejorada (reintentos, copias .bak, errores claros)
```

- Para trabajar con una app, abre su carpeta (por ejemplo `macos/notas-rapidas/`) como raíz en VS Code (*File → Open Folder…*).
- Una app nueva se crea copiando una carpeta existente como plantilla y renombrándola (`macos/<mi-app>/`, `windows/<mi-app>/`, `linux/<mi-app>/`). Los pasos están en la sección «Convención» del manual de cada app.
- Nombres de carpeta en minúsculas y guiones.

## App de ejemplo: Notas Rápidas

Un bloc de notas en dos versiones:

| Versión | Interfaz | Para qué sirve |
|---|---|---|
| `app_tk/` | Tkinter | Sin dependencias; la más sencilla de reproducir |
| `app_web/` | HTML/CSS/JS en ventana nativa (pywebview) | Reutilizar interfaces web; aspecto moderno |

## Por dónde empezar

| Plataforma | Manual | Construir (desde la carpeta de la variante) |
|---|---|---|
| macOS | [`macos/notas-rapidas/MANUAL_VSCODE.md`](macos/notas-rapidas/MANUAL_VSCODE.md) | `./construir_app.sh` → `dist/Notas Rápidas.app` |
| Windows | [`windows/notas-rapidas/MANUAL_VSCODE_WINDOWS.md`](windows/notas-rapidas/MANUAL_VSCODE_WINDOWS.md) | `.\construir_app.ps1` → `dist\NotasRapidas\NotasRapidas.exe` |
| Linux (Debian, Ubuntu, Mint) | [`linux/notas-rapidas/MANUAL_VSCODE_LINUX.md`](linux/notas-rapidas/MANUAL_VSCODE_LINUX.md) | `./crear_deb.sh` → `dist/notas-rapidas_1.0.0_all.deb` |

En VS Code, `Cmd/Ctrl+Shift+B` lanza la construcción desde cualquier punto del proyecto.

## Diferencias entre plataformas

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

- El código Python se ha comprobado sintácticamente y la interfaz HTML se ha probado en un navegador con el puente a Python simulado.
- El empaquetado (py2app / PyInstaller / `.deb`) y la ejecución real con Tkinter y pywebview **deben probarse en cada sistema**. Si el ejecutable no encuentra algún módulo, las guías explican cómo añadirlo.

## Requisitos

- Python 3.11–3.13 de [python.org](https://www.python.org/downloads/) (incluye Tk).
- VS Code con las extensiones *Python* y *Python Debugger*.
- Construir un `.app` requiere macOS; construir un `.exe` requiere Windows; los `.deb` se crean en Debian, Ubuntu, Mint o derivadas.

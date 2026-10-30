# code

Ejemplos de aplicaciones de escritorio en Python que se ejecutan con **doble clic** sobre su icono, con guías y proyecto de VS Code para programarlas, ejecutarlas y construirlas.

## Organización

El repositorio tiene una carpeta por sistema operativo. Dentro, **cada app es una carpeta completamente autocontenida**: lleva su propio código, su `.vscode/`, sus guías (`docs/`), su manual y su `.gitignore`. El código de apps distintas nunca se mezcla.

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
```

- Para trabajar con una app, abre su carpeta (por ejemplo `macos/notas-rapidas/`) como raíz en VS Code (*File → Open Folder…*).
- Una app nueva se crea copiando una carpeta existente como plantilla y renombrándola (`macos/<mi-app>/`, `windows/<mi-app>/`). Los pasos están en la sección «Convención» del manual de cada app.
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

En VS Code, `Cmd/Ctrl+Shift+B` lanza la construcción desde cualquier punto del proyecto.

## Diferencias entre plataformas

| | macOS | Windows |
|---|---|---|
| Empaquetador | py2app | PyInstaller |
| Resultado | `.app` | `.exe` |
| Icono | `.icns` | `.ico` |
| Motor web (pywebview) | WKWebView | Edge WebView2 |
| Datos de usuario | `~/Library/Application Support` | `%APPDATA%` |
| Registro | `~/Library/Logs` | `%LOCALAPPDATA%` |
| Firma | Developer ID + notarización | Certificado de firma + SmartScreen |

## Estado de verificación

- El código Python se ha comprobado sintácticamente y la interfaz HTML se ha probado en un navegador con el puente a Python simulado.
- El empaquetado (py2app / PyInstaller) y la ejecución real con Tkinter y pywebview **deben probarse en cada sistema**. Si el ejecutable no encuentra algún módulo, las guías explican cómo añadirlo.

## Requisitos

- Python 3.11–3.13 de [python.org](https://www.python.org/downloads/) (incluye Tk).
- VS Code con las extensiones *Python* y *Python Debugger*.
- Construir un `.app` requiere macOS; construir un `.exe` requiere Windows.

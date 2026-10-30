# code

Ejemplos de aplicaciones de escritorio en Python que se ejecutan con **doble clic** sobre su icono, con guías y proyecto de VS Code para programarlas, ejecutarlas y construirlas.

La aplicación de ejemplo es **Notas Rápidas**, un bloc de notas, en dos versiones:

| Versión | Interfaz | Para qué sirve |
|---|---|---|
| `app_tk/` | Tkinter | Sin dependencias; la más sencilla de reproducir |
| `app_web/` | HTML/CSS/JS en ventana nativa (pywebview) | Reutilizar interfaces web; aspecto moderno |

## Estructura

```
code/
├── macos/                          ← proyecto completo para macOS (.app con py2app)
│   ├── .vscode/                    ← launch, tasks, settings, extensions
│   ├── app_tk/                     ← Tkinter  (notas_app.py, setup.py, construir_app.sh)
│   ├── app_web/                    ← pywebview (notas_web.py, ui/index.html, setup_web.py, construir_app_web.sh)
│   ├── docs/
│   │   ├── GUIA_APP_MACOS.md       ← conceptos básicos y avanzados
│   │   └── GUIA_PYWEBVIEW.md       ← detalles de la variante pywebview
│   └── MANUAL_VSCODE.md            ← manual de uso con VS Code
└── windows/                        ← proyecto completo para Windows (.exe con PyInstaller)
    ├── .vscode/
    ├── app_tk/                     ← notas_app.py, construir_app.ps1 / .bat
    ├── app_web/                    ← notas_web.py, ui/index.html, construir_app_web.ps1 / .bat
    ├── docs/
    │   ├── GUIA_APP_WINDOWS.md
    │   └── GUIA_PYWEBVIEW_WINDOWS.md
    └── MANUAL_VSCODE_WINDOWS.md
```

Cada carpeta (`macos/`, `windows/`) es un **proyecto independiente**: ábrela como carpeta raíz en VS Code (*File → Open Folder…*).

## Por dónde empezar

| Plataforma | Manual | Construir |
|---|---|---|
| macOS | [`macos/MANUAL_VSCODE.md`](macos/MANUAL_VSCODE.md) | `./construir_app.sh` → `dist/Notas Rápidas.app` |
| Windows | [`windows/MANUAL_VSCODE_WINDOWS.md`](windows/MANUAL_VSCODE_WINDOWS.md) | `.\construir_app.ps1` → `dist\NotasRapidas\NotasRapidas.exe` |

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

# code

Ejemplos de aplicaciones de escritorio en Python que se ejecutan con **doble clic** sobre su icono, con guías y proyecto de VS Code para programarlas, ejecutarlas y construirlas.

## Organización

El repositorio tiene un proyecto por sistema operativo. Dentro de cada uno, **cada app vive en su propia carpeta**, de modo que el código de apps distintas nunca se mezcla.

```
code/
├── macos/                              ← proyecto de VS Code para macOS (.app con py2app)
│   ├── .vscode/                        ← configuración común (launch, tasks, settings, extensions)
│   ├── docs/                           ← guías generales
│   │   ├── GUIA_APP_MACOS.md
│   │   └── GUIA_PYWEBVIEW.md
│   ├── MANUAL_VSCODE.md
│   └── notas-rapidas/                  ← app «Notas Rápidas»
│       ├── app_tk/                     ← versión Tkinter
│       └── app_web/                    ← versión pywebview (HTML)
└── windows/                            ← proyecto de VS Code para Windows (.exe con PyInstaller)
    ├── .vscode/
    ├── docs/
    │   ├── GUIA_APP_WINDOWS.md
    │   └── GUIA_PYWEBVIEW_WINDOWS.md
    ├── MANUAL_VSCODE_WINDOWS.md
    └── notas-rapidas/
        ├── app_tk/
        └── app_web/
```

- Abre `macos/` o `windows/` como carpeta raíz en VS Code (*File → Open Folder…*).
- Lo común a todas las apps (`.vscode/`, `docs/`, manual) está en la raíz de cada proyecto.
- Cada app tiene su carpeta, con nombre en minúsculas y guiones, y una subcarpeta por variante.

### Añadir una app nueva

1. Crea `macos/<mi-app>/` y/o `windows/<mi-app>/` con sus variantes dentro.
2. Añade su configuración en `.vscode/launch.json` y sus tareas en `.vscode/tasks.json`, apuntando a `${workspaceFolder}/<mi-app>/...`.
3. Si necesita documentación propia, ponla en `<mi-app>/` o en `docs/`.

## App de ejemplo: Notas Rápidas

Un bloc de notas en dos versiones:

| Versión | Interfaz | Para qué sirve |
|---|---|---|
| `app_tk/` | Tkinter | Sin dependencias; la más sencilla de reproducir |
| `app_web/` | HTML/CSS/JS en ventana nativa (pywebview) | Reutilizar interfaces web; aspecto moderno |

## Por dónde empezar

| Plataforma | Manual | Construir (desde la carpeta de la variante) |
|---|---|---|
| macOS | [`macos/MANUAL_VSCODE.md`](macos/MANUAL_VSCODE.md) | `./construir_app.sh` → `dist/Notas Rápidas.app` |
| Windows | [`windows/MANUAL_VSCODE_WINDOWS.md`](windows/MANUAL_VSCODE_WINDOWS.md) | `.\construir_app.ps1` → `dist\NotasRapidas\NotasRapidas.exe` |

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

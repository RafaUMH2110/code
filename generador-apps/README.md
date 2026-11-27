# Generador de apps con IA

Script en Python que, desde VS Code, genera o modifica **apps web de un solo fichero HTML** usando la API de Anthropic o la de OpenAI. Sigue las convenciones habituales: HTML autocontenido, interfaz en español y responsive, clave de API pedida en la interfaz, y pie de página con autoría, «Última modificación» siempre actualizada y la leyenda «Generado con IA · Revisado por el autor».

Esta carpeta contiene **tres versiones del mismo proyecto, en directorios separados**. Cada una es autocontenida (script, plantilla, dependencias, `.vscode/`, `.gitignore` y documentación).

```
generador-apps/
├── python-app-api-anthropic/   ← versión base (primera entrega)
│   ├── generar_app.py
│   ├── plantilla_base.html
│   ├── requirements.txt
│   ├── .env.example
│   ├── .gitignore
│   ├── .vscode/launch.json
│   ├── docs/ARQUITECTURA.md
│   └── README.md
├── mejora-de-codigo/           ← versión mejorada de la anterior
│   ├── generar_app.py          ← único fichero con código distinto
│   ├── plantilla_base.html
│   ├── requirements.txt
│   ├── .env.example
│   ├── .gitignore
│   ├── .vscode/launch.json
│   ├── docs/
│   │   ├── ARQUITECTURA.md
│   │   └── CAMBIOS.md          ← qué cambia y por qué
│   └── README.md
└── optimizada-vscode/          ← reescritura centrada en trabajar desde VS Code
    ├── generar_app.py          ← reescrito por completo
    ├── plantilla_base.html     ← con modo oscuro
    ├── generar_app.config.json ← configuración (autoría, modelos, precios)
    ├── requirements.txt
    ├── .env.example
    ├── .gitignore
    ├── .vscode/                ← launch.json, tasks.json, settings.json, extensions.json
    ├── docs/
    │   ├── ARQUITECTURA.md
    │   └── CAMBIOS.md          ← qué cambia y por qué
    └── README.md
```

## ¿Cuál usar?

| | `python-app-api-anthropic` | `mejora-de-codigo` | `optimizada-vscode` |
|---|---|---|---|
| Anthropic y OpenAI, `--list-models` | ✅ | ✅ | ✅ |
| Plantilla, `--base`, `--chat`, `--variantes` | ✅ | ✅ | ✅ |
| Modo interactivo y F5 en VS Code | ✅ | ✅ | ✅ |
| Reintentos ante 429 / 5xx / red | ❌ | ✅ | ✅ |
| Copia antes de sobrescribir | ❌ | ✅ (`.bak`) | ✅ (historial con fecha) |
| `--chat` y `--variantes` sobreviven a un fallo | ❌ | ✅ | ✅ |
| Errores de fichero sin traceback | ❌ | ✅ | ✅ |
| Validación de argumentos | ❌ | ✅ | ✅ |
| Previsualización en vivo (`--serve`) | ❌ | ❌ | ✅ |
| Detecta respuestas truncadas | ❌ | ❌ | ✅ |
| `/deshacer` y historial de versiones | ❌ | ❌ | ✅ |
| Conversaciones persistentes (`--resume`) | ❌ | ❌ | ✅ |
| Tareas de VS Code con desplegables | ❌ | ❌ | ✅ |
| `--init` (prepara la carpeta) | ❌ | ❌ | ✅ |
| Modelos reales de tu cuenta (`--remote`) | ❌ | ❌ | ✅ |
| Validación del HTML generado | ❌ | ❌ | ✅ |
| Inserta el pie si falta | ❌ | ❌ | ✅ |
| Diff de los cambios | ❌ | ❌ | ✅ |
| Fichero de configuración | ❌ | ❌ | ✅ |
| Tokens, coste y caché de prompts | ❌ | ❌ | ✅ |
| Galería comparativa de variantes | ❌ | ❌ | ✅ |

**Recomendación:** usa `optimizada-vscode`. Las dos anteriores se conservan como historia del proyecto, referencia más sencilla de leer y para poder comparar las tres.

## Inicio rápido

```bash
cd generador-apps/optimizada-vscode      # o mejora-de-codigo / python-app-api-anthropic
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                       # rellena ANTHROPIC_API_KEY y/o OPENAI_API_KEY
python generar_app.py                      # modo interactivo (o ▶ / F5 en VS Code)
```

Para trabajar en VS Code, abre la carpeta de la versión elegida como raíz (*File → Open Folder…*) para que `.vscode/launch.json` y la plantilla se detecten.

## Notas

- Estas herramientas son **cross-platform** (macOS, Windows y Linux). Para que cada carpeta de sistema operativo sea independiente, el repositorio mantiene una copia idéntica en `macos/`, `windows/` y `linux/`: si cambias una, replica el cambio en las otras. Solo cambia la activación del entorno virtual (`source .venv/bin/activate` en macOS/Linux, `.venv\Scripts\activate` en Windows).
- Nunca subas el `.env` real: está excluido por `.gitignore`.
- Durante el desarrollo no se hicieron llamadas reales a la API (solo pruebas con clientes simulados); prueba con tu clave antes de usarlo en producción.

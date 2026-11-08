# Panel de Servidores

Aplicación gráfica para **macOS** (Python + **PySide6/Qt 6**) que reúne en una sola ventana todo lo que hacían los scripts del repositorio `code`:

| Script | En la aplicación |
|---|---|
| `instalar-todo.sh` · `instalar-todo-isa.sh` | Pestaña **Instalador** (formulario, selector de repos/carpetas de GitHub, progreso por pasos, cron) |
| `telemet-collector-info.py` | Pestañas **Informe** y **Servicio** |
| `telemet-collector-info-ssh.py` | Conexión SSH de todo el programa + pestaña **Claves SSH** |

Todas las operaciones remotas usan **sesiones SSH** con todas las variantes de autenticación: clave, `ssh-agent`, clave con frase, contraseña, 2FA, bastión (`-J`), alias de `~/.ssh/config`, huellas de servidor y sudo con o sin contraseña. Las contraseñas **nunca** van en la línea de comandos ni se guardan en disco (opcionalmente, en el Llavero de macOS).

Además de lo que hacían los scripts: varios servidores guardados, conexión única reutilizada (una contraseña por sesión), informe de varios servidores a la vez con exportación CSV, gestor de claves SSH (generar, agente, instalar, revocar, auditar), control del servicio systemd con registro, desinstalación guiada, visor del catálogo de aplicaciones, copia del comando equivalente, «Abrir en Terminal», importación de `~/.ssh/config` y actualización de los scripts desde GitHub.

## Arranque rápido (VS Code)

```bash
cd panel-servidores
code .                       # abre VS Code
./scripts/ejecutar.sh        # crea .venv la primera vez y arranca la app
./scripts/ejecutar.sh --pruebas
```

En VS Code: *Ejecutar y depurar* → **Panel de Servidores**. Tareas (⇧⌘B): pruebas, sincronizar scripts, construir `.app`.

## Crear la `.app`

```bash
./scripts/construir-app.sh --dmg      # dist/Panel de Servidores.app y .dmg (solo en macOS)
```

## Documentación

* [`docs/manual-usuario.md`](docs/manual-usuario.md) — cómo usar la aplicación, pestaña por pestaña, con equivalencias con los scripts.
* [`docs/manual-tecnico.md`](docs/manual-tecnico.md) — arquitectura, flujos SSH, askpass, envoltorio del instalador, seguridad, pruebas, empaquetado y cómo extender.

## Estructura

```
src/panel_servidores/
  nucleo/   lógica sin Qt (SSH, comandos remotos, claves, instalador, colector, GitHub…)
  ui/       interfaz Qt (ventana, pestañas, diálogos)
  recursos/ scripts del repo incluidos + portal
tests/      unitarias · integración con sshd real · interfaz sin pantalla
```

*Autor: Rafa · Dpto. de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es — Generado con IA · Revisado por el autor.*

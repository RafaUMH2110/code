# Panel de Servidores — instrucciones para Claude

App de escritorio para macOS (Python + PySide6/Qt 6) que sustituye a `instalar-todo(-isa).sh`, `telemet-collector-info.py` y `telemet-collector-info-ssh.py`. Autor: Rafa (Dpto. de Ingeniería de Sistemas y Automática, UMH, r.puerto@umh.es). Lee `docs/manual-tecnico.md` antes de cambios grandes.

## Idioma y estilo
- Todo en **español** (comentarios, docstrings, mensajes de la interfaz, documentación). Los identificadores ya están en español: mantén esa convención.
- Código elegante, estructurado y **muy comentado**: explica el *porqué*, no solo el *qué*.
- Las cabeceras de documentos llevan autor, departamento, email y la leyenda «Generado con IA · Revisado por el autor».

## Arquitectura (regla de oro)
- `src/panel_servidores/nucleo/`: lógica **sin Qt**. Se prueba con pytest.
- `src/panel_servidores/ui/`: solo interfaz. Cada botón llama a una función de `nucleo/` dentro de un `Trabajo` (hilo) y pinta el resultado. **No pongas lógica de negocio en `ui/`.**
- Los scripts del repo **no se reimplementan**: se suben al servidor y se ejecutan allí (`nucleo/remoto.py`, `nucleo/instalador.py`).
- SSH = el `ssh` del sistema (no Paramiko). Preguntas interactivas por el puente askpass.

## Reglas de seguridad (no negociables)
- **Ningún secreto** en la línea de comandos, en el registro de actividad ni en disco (salvo Llavero si el usuario lo pide).
- Todo texto externo en comandos remotos va con `shlex.quote` y parámetros posicionales (`remoto.sh_c`). Nunca concatenes texto del usuario.
- Los destinos no pueden empezar por `-` ni contener espacios (`ssh.RE_DESTINO`).
- Borrados remotos solo bajo `/opt/`. `--forzar` nunca se recuerda.
- No sobrescribir claves SSH existentes.

## Cómo trabajar
- Ejecutar: `./scripts/ejecutar.sh`. Pruebas: `./scripts/ejecutar.sh --pruebas` (o `python -m pytest -q`).
- Las pruebas de integración y de UI necesitan root y OpenSSH (sshd real); si no, se saltan solas. En el Mac corren las unitarias.
- Tras cambiar código: ejecuta las pruebas y no des la tarea por terminada si falla alguna. Añade una prueba por cada fallo corregido o función nueva.
- Qt: nunca toques widgets desde un hilo; usa `ui.hilos.en_gui()`. No conectes señales a lambdas esperando que corran en el hilo de la interfaz.
- Interfaz: **nunca** pongas colores fijos ni `setStyleSheet("color:…")`; usa `estilo.poner_rol` / `estilo.color` (ver «Aspecto y temas» en el manual técnico). Tablas y árboles con `widgets.tabla` / `preparar_arbol`. Tras tocar la interfaz ejecuta `PSV_CAPTURAS=/tmp/capturas python -m pytest tests/test_visual.py` y mira las imágenes (claro y oscuro).
- Antes de cada commit que cambie la app, ejecuta `./scripts/marcar-modificacion.sh`: actualiza la fecha y hora de «Última modificación» que muestra *Ayuda ▸ Acerca de* (`ULTIMA_MODIFICACION` en `__init__.py`). No la dejes desfasada.
- Cambios en `nucleo/remoto.py`: la función debe ser pura y tener prueba ejecutándola con `sh` local.

## Recursos incluidos
- `src/panel_servidores/recursos/` contiene copias de los scripts del repo. **No ejecutes `scripts/sincronizar-recursos.sh` sin comprobar la rama activa del repo `code`**: sobrescribe los incluidos (los instaladores llevan el filtro de repos archivados de `mantenimiento-2026-11`).

## Git
- Trabaja en una rama (nunca directo a `main`) y abre pull request. Mensajes de commit en español, descriptivos.

## No verificado aún en un Mac real
Llavero (`keyring`), `ssh-add --apple-use-keychain`, AppleScript de Terminal/iTerm, `construir-app.sh` (PyInstaller/codesign) y 2FA reales. Si algo de eso falla, pide el panel *Actividad* y el error.

# clonar-code.sh — clonar el repo `code` completo

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Clona (o actualiza) el repositorio **completo** `RafaUMH2110/code` con **todos** sus directorios, incluidos los nuevos (`telemetria/`, `telemetria/home/`, `telemetria/telemet-enchufes-*/`, `generador-apps/`…). No usa clonado parcial: si ya tenías un clon parcial (sparse-checkout), lo completa.

Versión inglesa: [`../en/clone-code/`](../en/clone-code/clone-code-guide.md).

## Uso rápido

```bash
chmod +x clonar-code.sh
./clonar-code.sh                       # clona en ~/RafaUMH2110/code (o actualiza)
./clonar-code.sh -o /srv/repos         # otra carpeta contenedora
./clonar-code.sh --arbol               # añade el segundo nivel en el resumen
./clonar-code.sh --cron "0 3 * * *"    # y lo programa cada día a las 03:00
```

## Qué hace (4 pasos)

1. **Clonado.** Si no existe `ORIGEN/code`, hace un `git clone` completo. Si existe: desactiva el sparse-checkout si lo tenía, avisa de cambios locales, hace `fetch` y avanza con `merge --ff-only`. Informa de commits, ficheros nuevos/modificados/borrados, líneas, descarga aproximada y **directorios nuevos**.
2. **Comprobación.** Verifica que existen (y tienen ficheros) los directorios exigidos. Por defecto: `telemetria/home`, `telemetria/telemet-enchufes-local`, `telemetria/telemet-enchufes-nube`, `telemetria/telemet-enchufes-vscode`, `generador-apps`, `linux`, `macos`, `windows`, `scripts`.
3. **Contenido.** Tabla de ficheros y tamaño por directorio de primer nivel (`--arbol`: también el segundo).
4. **Programación.** Con `--cron` sustituye la línea de cron de este script por la nueva.

## Opciones

| Opción | Significado | Por defecto |
|---|---|---|
| `-u USUARIO` | Cuenta de GitHub | `RafaUMH2110` |
| `-r REPO` | Repositorio | `code` |
| `-o ORIGEN` | Carpeta que contendrá el clon (queda en `ORIGEN/REPO`) | `~/RafaUMH2110` |
| `-b RAMA` | Rama a seguir | rama por defecto del repo |
| `--exigir LISTA` | Directorios obligatorios, separados por comas | los 9 indicados arriba |
| `--sin-comprobar` | No comprueba directorios | — |
| `--arbol` | Muestra también subdirectorios de segundo nivel | — |
| `--forzar` | Si hay cambios locales o no se puede avanzar: guarda copia y iguala al remoto | — |
| `--cron "EXPR"` | Programa la actualización en cron | — |
| `-h`, `--help` | Ayuda | — |

## `--forzar`: qué se conserva

- Cambios locales sin commitear → `ORIGEN/copias-clonar-code/<repo>-<fecha>.patch`.
- Commits locales que no están en el remoto → rama `copia-antes-de-forzar-<fecha>`.

Sin `--forzar`, si no se puede avanzar el script termina con error y no toca nada.

## Códigos de salida

`0` correcto · `1` error (sin red, clon no actualizable, falta un directorio exigido, opción desconocida). El registro queda en `ORIGEN/clonar-code.log`.

## Notas

- **`telemetria/home/`** contiene ahora solo un `README.md` provisional; el script lo da por válido porque tiene un fichero. Cuando se añada contenido, se descargará con la siguiente ejecución.
- El **modo web** de `instalar-todo.sh` publica las apps, no el repo `code` completo: este script es para tener el código fuente en el servidor, no para desplegarlo en Apache.
- Una selección guardada de `instalar-todo` (sparse) no afecta a este clon: viven en carpetas distintas salvo que uses el mismo `-o`; en ese caso `clonar-code.sh` completará el clon parcial.
- Para añadir un directorio nuevo a la comprobación: `--exigir "…,nuevo-dir"` (o edita `EXIGIR_DEF` en el script).

# Guía rápida: parches en git (y GitHub)

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

## 1. Qué es un parche

Un parche es un **fichero de texto que describe cambios**: qué líneas se quitan (`-`), cuáles se añaden (`+`) y en qué
ficheros, con unas líneas de contexto alrededor para saber dónde van. Puede incluir también ficheros nuevos, borrados,
renombrados y (con `--binary`) binarios como imágenes.

```diff
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -3,2 +3,2 @@
 Texto de contexto sin cambios
-línea antigua
+línea nueva
```

Sirve para **pasar cambios sin tener acceso de escritura** al repo (o a la máquina donde se prepararon): se envía el
fichero, quien lo recibe lo aplica en su copia, lo revisa y lo sube él mismo.

Un parche solo funciona si el repo está en el **estado del que partió**. Si el código ya cambió (o ya contiene esos
mismos cambios), `git apply` se niega.

## 2. Crear un parche

| Qué quieres | Orden |
|---|---|
| Cambios sin confirmar (working tree) | `git diff > cambios.patch` |
| Cambios ya preparados con `git add` | `git diff --cached > cambios.patch` |
| Incluir ficheros nuevos | primero `git add -A` y luego `git diff --cached` (un `git diff` normal **no** ve ficheros sin añadir) |
| Con binarios (imágenes…) y renombrados | `git diff --cached -M --binary > cambios.patch` |
| Entre dos ramas o commits | `git diff main..mi-rama > cambios.patch` |
| **Uno o varios commits, con autor y mensaje** | `git format-patch -1` (el último) · `git format-patch main..mi-rama` (uno por commit) |

Hay **dos formatos**:
- **Diff simple** (`git diff`): solo los cambios. No guarda autor ni mensaje.
- **mbox** (`git format-patch`): cada commit es un correo con autor, fecha, mensaje y diff. Es el formato para `git am`.

## 3. Aplicar un parche

### `git apply` (solo los cambios)

```bash
git apply --check cambios.patch     # prueba en seco: no modifica nada
git apply --stat cambios.patch      # resumen: ficheros y líneas que tocaría
git apply cambios.patch             # aplica en el directorio de trabajo
git add -A && git commit -m "…"     # el commit lo haces tú
```

Es **atómico**: si una sola parte falla, no se aplica nada. Por eso un error no deja el repo a medias.

### `git am` (con autor y mensaje del commit)

```bash
git am 0001-mi-cambio.patch         # aplica y crea el commit con su autor y mensaje
git am --abort                      # cancela si algo sale mal
```

Solo vale con parches de `git format-patch`.

### Opciones útiles

| Opción | Para qué |
|---|---|
| `-R` | Aplicar **al revés** (deshacer un parche) |
| `--3way` | Si el repo ha cambiado un poco, intenta una fusión a tres bandas y deja marcas de conflicto, en vez de rechazarlo |
| `--reject` | Aplica lo que puede y guarda lo que no en ficheros `.rej` para resolverlo a mano |
| `--index` | Aplica y deja los cambios ya en el índice (listo para commit) |
| `-p N` | Quita N niveles de carpeta de las rutas (por defecto 1: el `a/` y `b/`) |
| `--ignore-whitespace` | Tolera diferencias de espacios o saltos de línea |

## 4. Errores típicos y qué significan

| Mensaje | Causa | Solución |
|---|---|---|
| `patch does not apply` | El fichero no tiene el contenido esperado: ha cambiado desde que se hizo el parche, **o ya está aplicado** | `git log` y `git diff` para ver si ya está; si no, `git pull` y reintenta, o `--3way` |
| `already exists in working directory` | El parche crea un fichero que ya existe (p. ej. porque ya lo subiste) | Pide un parche solo con las diferencias respecto al estado actual |
| `No such file or directory` | El parche modifica un fichero que no está (otra rama, clon parcial o ya movido) | `git pull`, comprueba la rama; si el clon es parcial, `git sparse-checkout disable` |
| `corrupt patch at line N` | El fichero se cortó o se alteró al descargarlo o copiarlo | Descárgalo de nuevo; no lo abras y lo guardes con un editor que cambie saltos de línea |
| `trailing whitespace` (aviso) | El parche añade espacios al final de línea | Es solo un aviso |

Regla práctica: **antes de aplicar, `git pull` y `git status` limpios**, y siempre `git apply --check` primero.

## 5. Parches y GitHub

- **Pull request = parche con interfaz.** Es la forma habitual de proponer cambios en GitHub: rama → push → PR → revisión → merge.
- GitHub genera el parche de cualquier PR o commit si añades `.patch` o `.diff` a su URL:
  - `https://github.com/USUARIO/REPO/pull/12.patch` (formato mbox, con commits)
  - `https://github.com/USUARIO/REPO/commit/ABC1234.diff` (diff simple)
  - `https://github.com/USUARIO/REPO/compare/main...rama.patch`
- Así puedes aplicar a mano un PR: `curl -L URL.patch | git am` (o `| git apply`).
- Un parche **no se «sube» a GitHub**: se aplica en un clon local, se hace commit y se hace `git push`.

## 6. Flujo recomendado cuando recibes un parche

```bash
cd ~/RafaUMH2110/mi-repo
git pull                                   # parte del último estado
git status -sb                             # debe estar limpio
git apply --check ~/Downloads/cambios.patch   # prueba en seco
git apply --stat  ~/Downloads/cambios.patch   # qué toca
git apply ~/Downloads/cambios.patch
git diff --stat                            # revisa lo aplicado
git add -A                                 # -A: incluye ficheros nuevos y borrados
git commit -m "Descripción del cambio"
git push
```

Trucos:
- **`git commit -am` no añade ficheros nuevos**: usa `git add -A` antes.
- Para probar sin riesgo, aplica el parche en una rama: `git switch -c prueba-parche`.
- Para deshacer un parche ya aplicado y sin commitear: `git apply -R cambios.patch` (o `git restore .`, que descarta **todos** los cambios sin confirmar).
- Si ya hiciste commit y no has hecho push: `git reset --hard HEAD~1`; si ya hiciste push: `git revert HEAD`.

## 7. Resumen en una línea cada uno

- **Crear:** `git add -A && git diff --cached --binary > x.patch`
- **Comprobar:** `git apply --check x.patch`
- **Aplicar:** `git apply x.patch` (cambios) · `git am x.patch` (commit completo)
- **Subir:** `git add -A && git commit -m "…" && git push`
- **Deshacer:** `git apply -R x.patch`

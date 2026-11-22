# Publicar apps nuevas cuando Claude no tiene push directo

> Copia, tal cual, del documento del proyecto «Telemetría» (`claude/publicar-apps-rpuertoumh.md`), redactado el **2026-10-16**. Las rutas dentro del repo `apps` y los nombres de las cuentas (`rpuertoumh`, `rafapumh`) pueden haber cambiado desde entonces.

Cuando una sesión de Claude no tiene acceso de escritura a `RafaUMH2110/apps` (la app de GitHub de Claude no está vinculada a esa cuenta en esa sesión concreta), la vía más fiable es subir el archivo tú mismo desde tu terminal.

## 1. Comprobar qué cuenta de GitHub tienes activa localmente

```bash
gh auth status
```

## 2. Cambiar a RafaUMH2110 si hace falta

Si la cuenta ya está en la lista de `gh auth status` (por ejemplo porque sueles trabajar con `rpuertoumh` y necesitas cambiar):

```bash
gh auth switch --hostname github.com --user RafaUMH2110
```

Si RafaUMH2110 no aparece nunca en esa lista, autentícala primero (abre el navegador):

```bash
gh auth login --hostname github.com --git-protocol https --web
# Elegir iniciar sesión con la cuenta RafaUMH2110 cuando se abra GitHub
```

Verificación rápida de qué cuenta quedó activa:

```bash
gh api user --jq .login
```

## 3. Clonar/actualizar el repo y añadir la app

```bash
git clone https://github.com/RafaUMH2110/apps.git   # o 'git -C apps pull' si ya lo tienes clonado
cd apps
mkdir -p apps/<categoria>/<nombre-app>
cp /ruta/local/index.html apps/<categoria>/<nombre-app>/index.html
git add apps/<categoria>/<nombre-app>/index.html
git commit -m "Añade <nombre-app>"
git push origin main
```

La app queda publicada en `https://rafaumh2110.github.io/apps/<categoria>/<nombre-app>/` (GitHub Pages ya está activo en ese repo).

## Nota

Las credenciales de GitHub App de Claude para `RafaUMH2110` y para `rpuertoumh` son instalaciones independientes; reautorizar una de ellas en `claude.ai/customize/connectors` a mitad de una sesión no garantiza que esa misma sesión recoja el cambio — a veces hace falta una sesión nueva. Mientras tanto, este flujo local con `gh auth switch` es la alternativa que siempre funciona.

## Crear un repo NUEVO (no solo añadir a uno existente)

Aunque la sesión de Claude tenga push confirmado a `RafaUMH2110/apps` (vía `gh api user` devolviendo `RafaUMH2110` y pushes que funcionan), **crear un repositorio nuevo** (`gh repo create ...`, público o privado) falla siempre con:

```
HTTP 403: This GitHub API path is not available: sessions are bound to their configured repositories.
```

Esto es porque el token de la GitHub App está limitado a los repos ya configurados en la instalación (p. ej. `apps`), y `/user` y "crear repo" son endpoints fuera de ese ámbito. No hay forma de rodear esto desde la sesión: hace falta que Rafa cree el repo él mismo (web o su propio `gh` autenticado) y, si quiere que una sesión de Claude futura pueda hacerle push directo, añadirlo a la instalación de la GitHub App de Claude para esa cuenta (Settings → Applications → Claude → Repository access) — posiblemente necesitando una sesión nueva para que se refleje, como ya pasaba con `rpuertoumh`/`rafapumh`.

Mientras tanto, el flujo que sí funciona en la sesión actual: Claude dedica los ficheros ya listos (p. ej. en el scratchpad) y se los pasa a Rafa, y Rafa ejecuta localmente:

```bash
gh repo create RafaUMH2110/<nombre-repo> --public --description "<descripción corta>"
git clone https://github.com/RafaUMH2110/<nombre-repo>.git
cd <nombre-repo>
cp /ruta/a/index.html .
cp /ruta/a/apple-touch-icon.png .   # si aplica
git add -A
git commit -m "Primera versión"
git push origin main
# Activar Pages: Settings → Pages → Deploy from a branch → main → / (root)
# o por API:
gh api repos/RafaUMH2110/<nombre-repo>/pages -X POST -f "source[branch]=main" -f "source[path]=/"
```

La app queda en `https://rafaumh2110.github.io/<nombre-repo>/`.

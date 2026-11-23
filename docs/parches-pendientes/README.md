# Parches pendientes de aplicar

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Parches generados en una sesión de Claude y **todavía no aplicados**, guardados aquí para poder aplicarlos desde
cualquier equipo con un `git pull`. Cuando se aplican y se suben, **esta carpeta se borra** (ver el paso 4).

Cómo funcionan los parches en general: [`../guia-parches-git.md`](../guia-parches-git.md).

---

## Qué hay ahora (23 de noviembre de 2026)

**Seleccionar todos los días de golpe** en *Ajustes → Programaciones → Añadir programación*. Hasta ahora había que
marcar los siete días uno a uno. Ahora, encima de las casillas L M X J V S D:

- **Todos los días**: casilla que marca o desmarca los siete. Refleja el estado: queda *a medias* si hay algunos
  marcados y se marca sola cuando los siete lo están.
- **Lunes a viernes** y **Fin de semana**: atajos para los dos grupos más habituales.

No cambia el comportamiento de fondo: sin ningún día marcado la programación sigue siendo de **una sola vez**, y el
formulario lo sigue avisando. Una programación nueva sigue empezando sin días marcados.

El formulario existe en dos sitios con el mismo código, así que hay un parche para cada repo:

| Parche | Repo | Qué toca |
|---|---|---|
| `telehome-todos-los-dias-code.patch` | `code` (este mismo) | Interfaz del propio servicio (`telehome/static/index.html`), README y versión **0.9.3** |
| `telehome-todos-los-dias-apps.patch` | `apps` | App genérica (`telemetria/home/telehome/index.html`) y su manual (apartado 16) |

Comprobado en el navegador (claro y oscuro), en las dos interfaces: marcar todos, quitar uno (la casilla queda a
medias), los dos atajos, guardar, verlo en la lista como «todos los días» y reabrirlo con los siete marcados. Los 107
tests del servicio pasan. No se ha probado en un iPhone o iPad reales; las apps de iPhone y iPad no editan
programaciones, así que no cambian.

---

## Cómo aplicarlos

### 1. Repo `code`

```bash
cd ~/ruta/a/code
git pull
git apply --check docs/parches-pendientes/telehome-todos-los-dias-code.patch   # no cambia nada: solo comprueba
git apply docs/parches-pendientes/telehome-todos-los-dias-code.patch
git add -A
git commit -m "TeleHome 0.9.3: seleccionar todos los días de una programación de golpe"
git push
```

### 2. Repo `apps`

```bash
cd ~/ruta/a/apps
git pull
git apply --check ~/ruta/a/code/docs/parches-pendientes/telehome-todos-los-dias-apps.patch
git apply ~/ruta/a/code/docs/parches-pendientes/telehome-todos-los-dias-apps.patch
git add -A
git commit -m "TeleHome: seleccionar todos los días de una programación de golpe"
git push
```

### 3. Desplegar en lorca

```bash
sudo ./scripts/instalar-todo/instalar-todo-lorca.sh --telehome
```

### 4. Borrar esta carpeta

Una vez aplicados y subidos, los parches ya no sirven para nada (el cambio está en el historial):

```bash
cd ~/ruta/a/code
git rm -r docs/parches-pendientes
git commit -m "docs: quitados los parches ya aplicados"
git push
```

Y quitar la fila de `docs/README.md` que apunta a esta carpeta.

### Si `git apply` falla

Lo normal es que el parche **ya esté aplicado**. Para comprobarlo:

```bash
grep -c "schDaysQuick" telemetria/home/telehome-servicio/telehome/static/index.html   # en code
grep -c "schDaysQuick" telemetria/home/telehome/index.html                            # en apps
```

Si devuelve algo distinto de `0`, no hay nada que hacer en ese repo. Si no, mira
[`../guia-parches-git.md`](../guia-parches-git.md), apartado de errores típicos.

---

## Hecho recientemente (ya aplicado, solo como referencia)

- **TeleHome 0.9.2**: mensajes de error de red legibles, con el detalle técnico plegado bajo «Detalle técnico»
  (`code`: commit `ecc764e`; `apps`: commit `7e4a441`).
- **DNS de lorca**: el fallo que motivó lo anterior fue puntual. Desde lorca, `openapi.tuyaeu.com` resuelve y
  responde (200) y no hay proxy; solo tiene direcciones IPv6, así que un tropiezo de esa ruta deja el modo nube fuera
  unos segundos. Pendiente de decidir: reintentar una vez antes de dar el fallo por bueno.

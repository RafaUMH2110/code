# Parches pendientes de aplicar

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Parches generados en una sesión de Claude y **todavía no aplicados**, guardados aquí para poder aplicarlos desde
cualquier equipo con un `git pull`. Cuando se aplican y se suben, **esta carpeta se borra** (ver el paso 4).

Cómo funcionan los parches en general: [`../guia-parches-git.md`](../guia-parches-git.md).

---

## Qué hay ahora (23 de noviembre de 2026)

Mensajes de error legibles en TeleHome. Hasta ahora, un fallo de red con la nube de Tuya se enseñaba tal como lo
suelta la librería:

> Error de comunicación con la nube: HTTPSConnectionPool(host='openapi.tuyaeu.com', port=443): Max retries exceeded
> with url: /v1.0/devices/factory-infos?device_ids=… (Caused by NameResolutionError("… Failed to resolve
> 'openapi.tuyaeu.com' ([Errno -2] Name or service not known)"))

Ahora se lee así, con el texto técnico plegado debajo bajo «Detalle técnico»:

> No se pudo conectar con la nube de Tuya (openapi.tuyaeu.com): no se pudo averiguar su dirección. Comprueba que el
> servidor tiene salida a internet y un DNS que funcione.

| Parche | Repo | Estado | Qué toca |
|---|---|---|---|
| (ya aplicado: commit `ecc764e`) | `code` (este mismo) | **Hecho** | Servicio **0.9.2**: traducción de los fallos de red (nube y red local), ayuda para el inicio de sesión fallido, detalle técnico aparte en la API y en el registro, interfaz del servicio, README y 13 pruebas nuevas (107 en total) |
| `telehome-errores-legibles-apps.patch` | `apps` | **Pendiente** | App genérica (`telemetria/home/telehome`): el detalle técnico se pliega bajo el mensaje; manual e instalación al día |

Detalle de lo que cambia:

- **Seis fallos distinguidos**, cada uno con su frase y qué mirar: DNS, salida bloqueada por el puerto 443, proxy,
  certificado o reloj del servidor, tiempo agotado y conexión cortada. El mensaje nombra el servidor de Tuya al que
  no se llegó.
- **Inicio de sesión fallido**: distingue credenciales mal copiadas de centro de datos equivocado, en vez de soltar
  el código de Tuya a secas.
- **Enchufes en modo local**: tenían el mismo problema (`[Errno 113] No route to host`); ahora dicen «No se llega al
  enchufe: ¿está encendido y en la misma red que el servidor?» y similares.
- **Registro del servicio**: cada fallo queda con mensaje y detalle en una línea de aviso (`journalctl -u telehome`).

Comprobado en el navegador (claro y oscuro) con un fallo de red real contra `openapi.tuyaeu.com`, en la app genérica
y en la interfaz del servicio. No se ha probado en un iPhone o iPad reales.

---

## Cómo aplicar lo que queda

### 1. Repo `apps`

```bash
cd ~/ruta/a/apps
git pull
git apply --check ~/ruta/a/code/docs/parches-pendientes/telehome-errores-legibles-apps.patch   # no cambia nada: solo comprueba
git apply ~/ruta/a/code/docs/parches-pendientes/telehome-errores-legibles-apps.patch
git add -A
git commit -m "TeleHome: el detalle técnico de los errores se pliega bajo el mensaje"
git push
```

El parche del repo `code` ya está aplicado y subido (commit `ecc764e`, servicio 0.9.2): no hay que hacer nada con él.

### 2. Desplegar en lorca

```bash
sudo ./scripts/instalar-todo/instalar-todo-lorca.sh --telehome
```

### 3. Borrar esta carpeta

Una vez aplicados y subidos, los parches ya no sirven para nada (el cambio está en el historial):

```bash
cd ~/ruta/a/code
git rm -r docs/parches-pendientes
git commit -m "docs: quitados los parches ya aplicados"
git push
```

Y quitar la fila de `docs/README.md` que apunta a esta carpeta.

### Si `git apply` falla

Lo normal es que el parche **ya esté aplicado** (por ejemplo, porque se aplicó desde el chat). Para comprobarlo:

```bash
grep -c "Detalle técnico" telemetria/home/telehome/index.html
```

Si devuelve algo distinto de `0`, no hay nada que hacer: pasa al paso 3. Si no, mira
[`../guia-parches-git.md`](../guia-parches-git.md), apartado de errores típicos.

---

## Pendiente aparte: el DNS de lorca

El error que motivó estos parches era real: lorca no pudo resolver `openapi.tuyaeu.com`. Para saber si es permanente
o fue un corte pasajero, desde el propio servidor:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://openapi.tuyaeu.com/v1.0/token
```

Si falla también ahí, el modo nube no funcionará desde lorca hasta que ese servidor tenga salida a internet (o un
proxy configurado). El modo local no se ve afectado.

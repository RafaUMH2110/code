# TeleHome Enchufes · iPad

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Versión para **iPad** de [`telehome-enchufes`](../telehome-enchufes/README.md): consulta y control de hasta 7 enchufes
Wi-Fi Energeeks EG-EW008MC / EG-EW009MC (Tuya) desde el navegador del dispositivo. Vista dividida: a la izquierda la lista de enchufes con sus interruptores y a la derecha el detalle (valores, gráfica y resumen). Funciona en vertical, en horizontal y en Split View / Slide Over (en anchos pequeños pasa a una columna), con modo oscuro automático.

Es **una sola página** (`index.html`, sin dependencias ni ficheros externos) que habla con el servicio TeleHome Enchufes
ya instalado. Solo **consulta y controla** (ver potencia, tensión, corriente y energía; encender y apagar; gráficas,
resumen y CSV). **Añadir o editar enchufes, el modo nube y la contraseña se siguen haciendo en la interfaz completa.**

## Despliegue en Apache (como el resto de apps)

1. El servicio `telehome-enchufes` debe estar instalado y publicado en Apache en `/rafa/telehome/`
   (lo hace `instalar-todo-isa.sh`; ver el [README del servicio](../telehome-enchufes/README.md)).
2. `instalar-todo` copia esta carpeta junto con el resto del repo `code` a `/var/www/htdocs/rafa/code/telemetria/home/telehome-enchufes-ipad/`
   (selecciona `code/telemetria/home` en el portal). No hay nada más que configurar.
3. Abre la página desde iPad y úsala con *Compartir → Añadir a pantalla de inicio*: se abre a pantalla completa, como una app.

Como la página y la API salen del mismo servidor, no hay CORS ni cabeceras que tocar. Si el servicio pide contraseña,
el navegador la pide al conectar; si no puede, la app muestra un aviso con un botón que abre la interfaz completa para iniciar sesión.

## Cómo encuentra la API

1. La URL guardada en *Ajustes → URL de la API* (opcional; debe ser del mismo servidor).
2. `/rafa/telehome/api/` (la ruta del Apache de isa.umh.es).
3. `api/` relativa a la página (por si el servicio sirve esta carpeta directamente).

## Probar en local

```bash
cd telemetria/home/telehome-enchufes && python3 -m telehome_enchufes serve --simulate 3 --no-browser   # servicio simulado en :8765
cd ../telehome-enchufes-ipad && python3 servir.py                                                     # app en http://127.0.0.1:8080/
python3 servir.py --host 0.0.0.0                                                                     # visible desde el ipad de tu Wi-Fi (solo para probar)
```

[`servir.py`](servir.py) solo usa la biblioteca estándar: sirve esta carpeta y reenvía `/rafa/telehome/*` al servicio
(`--api`), igual que hace Apache. En VS Code, F5 lo arranca y abre Chrome (`.vscode/`).

## Contenido

| Fichero | Para qué |
|---|---|
| `index.html` | La app completa (HTML, CSS y JavaScript en un fichero); el pie muestra la última modificación |
| `apple-touch-icon.png` | Icono de 180×180 para la pantalla de inicio |
| `servir.py` | Servidor de pruebas (ver arriba) |
| `.vscode/` | Tarea y configuraciones para servir y abrir la app desde VS Code |

Probada con navegador emulado (iPad, claro y oscuro) contra el servicio en **simulación**; no se ha probado con enchufes reales ni en un ipad físico.

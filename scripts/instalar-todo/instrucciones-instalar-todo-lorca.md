# Despliegue en http://lorca.umh.es con `instalar-todo-lorca.sh`

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
**Fecha:** 20/11/2026
*Generado con IA · Revisado por el autor*

---

## 1. Qué es

Variante de [`instalar-todo-isa.sh`](instrucciones-instalar-todo-isa.md) para **http://lorca.umh.es** (Debian 13), con acceso **solo por http** (puerto 80). Publica el contenido en `/var/www/htdocs/rafa` y deja el portal en **http://lorca.umh.es/rafa/**.

Como la variante isa, **no modifica** `apache2.conf` ni las reglas existentes del servidor, y solo recarga Apache si añade configuración nueva (con `configtest` y reversión si falla).

## 2. Diferencias respecto a la variante isa

| Aspecto | isa | lorca |
|---|---|---|
| URL por defecto | `https://isa.umh.es` | `http://lorca.umh.es` |
| `--url` | Admite http o https | **Debe empezar por `http://`** (si no, el script se detiene) |
| Comprobación final | Prueba el puerto 443 y, si falla, `http://localhost` | Prueba el puerto 80 y, si falla, `http://localhost` |
| Portal | Plantilla `index.html` | La misma plantilla; rotula la página con el nombre del servidor (`lorca.umh.es`) |

## 3. Uso

```bash
unzip instalar-todo-azure.zip && cd instalar-todo   # o clona el repo code
chmod +x instalar-todo-lorca.sh
./instalar-todo-lorca.sh -h                  # ayuda
./instalar-todo-lorca.sh --todos             # todos los repos públicos
./instalar-todo-lorca.sh --repos "apps,code" # solo algunos
```

- El resto de opciones (`-u`, `-o`, `-d`, `--docroot`, `--repos`, `--excluir`, `--listar`, `--sin-indice`, `--colector`, `--cron`, `--forzar`) funcionan como en la variante isa.
- **TeleHome Enchufes** se instala por defecto si `code/telemetria/home` está entre los repos clonados (`--sin-telehome` para omitirlo) y queda en `http://lorca.umh.es/rafa/telehome/enchufes/`.
- La plantilla `index.html` (y los iconos) deben estar junto al script; si no, se usa la del repo `code` ya clonado y, en último caso, se genera un índice simple.
- Las apps meteorológicas de `apps` están en `telemetria/meteo/` y aparecen en la categoría **Meteo** del portal.

## 4. Comprobación

```bash
curl -I http://lorca.umh.es/rafa/
curl -s http://lorca.umh.es/rafa/apps.json | jq '.apps | length'
```

---
*Última modificación: 20/11/2026*

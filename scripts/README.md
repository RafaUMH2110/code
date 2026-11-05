# scripts

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Scripts para clonar los repos públicos de `RafaUMH2110`, desplegar sus apps web en Apache y, opcionalmente, instalar el colector de telemetría.

## Contenido

| Carpeta | Fichero | Para qué sirve |
|---|---|---|
| `clonar-actualizar/` | `actualizar_repos.sh` | Clona o actualiza los repos públicos (primera versión) |
| | `desplegar_apache.sh` | Copia las apps HTML al directorio de Apache (primera versión) |
| | `clonar_actualizar_repos.md` | Guía de las dos anteriores |
| `instalar-todo/` | `instalar_todo.sh` | Todo en uno para el servidor local (selección de repos, despliegue, colector, entrada `/rafa/`) |
| | `instalar_todo_isa.sh` | Variante para https://isa.umh.es (DocumentRoot `/var/www/htdocs`; no toca la configuración existente) |
| | `index.html` | Portal de entrada; debe estar junto a los scripts |
| | `instrucciones_instalar_todo.md` | Guía de `instalar_todo.sh` |
| | `instrucciones_instalar_todo_isa.md` | Guía de `instalar_todo_isa.sh` |
| | `apache_docroot_htdocs.md` | Por qué `/rafa/` da 404 si Apache sirve otro DocumentRoot |
| | `anteriores/instalar_todo_anterior.sh` | Versión previa de `instalar_todo.sh`, solo como histórico |
| `telemet-colector/` | `telemet_colector.py` | TeleMet Colector: lee de forma continua la estación meteorológica y guarda un histórico (24 h por defecto; `duracion_horas`, `--horas` o `TELEMET_HORAS`) en SQLite y como JSON para las apps TeleMet. Admite varias estaciones, cada una con su API Key (`[estacion:ID]`). |
| | `MANUAL.md`, `README.md` | Manual detallado (instalación, configuración y funcionamiento) y guía rápida |
| | `config.example.ini`, `telemet-colector.service` | Plantilla de configuración y servicio systemd |

Los scripts `instalar_todo*.sh` sustituyen a los de `clonar-actualizar/`.

## Uso rápido

```bash
cd instalar-todo
chmod +x instalar_todo.sh instalar_todo_isa.sh
./instalar_todo.sh -h        # servidor local
./instalar_todo_isa.sh -h    # isa.umh.es
```

## English version

See [`en/`](en/README.md) for the English versions of all the scripts and guides.

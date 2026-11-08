# mantenimiento-repos

Herramienta de **solo lectura** para revisar el estado de los repositorios de `RafaUMH2110`: no cambia ficheros, ramas ni commits de tus clones ni nada en GitHub. Con `--clonar` solo crea clones superficiales nuevos o hace `git fetch` en los existentes, dentro de la carpeta que indiques.

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

## Qué comprueba

| Categoría | Qué busca |
|---|---|
| `secretos` | Claves de API y tokens (Anthropic, OpenAI, GitHub, AWS, Google, fal.ai) y claves privadas en el árbol de trabajo; con `--historial`, también en todo el historial. Ignora marcadores del tipo `sk-ant-xxxx`. **Nunca imprime la clave**: solo el fichero y el tipo. |
| `ramas` | Ramas remotas con commits sin integrar en la rama por defecto, ramas ya integradas (borrables, también si sus commits están aplicados con *cherry-pick* o *rebase*) y ramas sin actividad (`--dias`). |
| `ficheros` | Ficheros grandes (`--mb`), `.pyc`, `__pycache__`, `.DS_Store`, `.env`, nombres tipo «archivo (1)» (descargas duplicadas) y nombres con espacios. |
| `duplicados` | Ficheros idénticos (mismo SHA-1, desde 20 KB) repetidos en el árbol. |
| `higiene` | Falta de `README`, `.gitignore` o `LICENSE` en la raíz. |
| `ruido` | Porcentaje de commits de bots entre los últimos commits. |
| `workflows` | Sintaxis de `.github/workflows/*.yml` (con PyYAML instalado; sin él solo los cuenta). |
| `enlaces` | Enlaces relativos de `.md` y `.html` que no apuntan a nada (se ignora el código). |

Cada hallazgo es **CRÍTICO** (hay que actuar ya, por ejemplo una clave), **AVISO** (conviene revisarlo) o **INFO** (a tu criterio).

## Uso

Requiere Python 3.7+ y `git` (solo biblioteca estándar; PyYAML es opcional). Para `--clonar` hace falta además acceso a internet.

```bash
# Un repo concreto (por defecto, el directorio actual)
python3 scripts/mantenimiento-repos/auditar-repos.py -d ~/repos/apps

# Una carpeta con varios clones: se revisa cada repo que contenga
python3 scripts/mantenimiento-repos/auditar-repos.py -d ~/repos

# Clonar o actualizar los repos públicos no archivados y revisarlos
python3 scripts/mantenimiento-repos/auditar-repos.py --clonar RafaUMH2110 -d ~/repos

# Con el historial completo (más lento) y salida en JSON
python3 scripts/mantenimiento-repos/auditar-repos.py -d ~/repos --historial --json
```

Opciones: `--dias N` (60 por defecto), `--mb N` (5 por defecto), `--json`, `--no-color`.

`--clonar` solo ve los repos **públicos**. Los privados (`programas`, `IA`…) hay que clonarlos a mano en la carpeta indicada con `-d`.

Códigos de salida: `0` todo bien · `1` hay avisos · `2` hay hallazgos críticos · `3` no se pudo trabajar (sin `git`, directorio vacío…). Sirve, por tanto, para un `cron` o un `pre-push`.

## Cuándo ejecutarlo

- Antes de publicar un cambio grande en un repo.
- Una vez al mes, con `--historial` cada trimestre.
- Si encuentra una clave: **revócala en el proveedor primero** y después límpiala del repo. Borrarla del árbol no la saca del historial de Git.

El artifact de mantenimiento recoge además la lista de comprobaciones manuales que esta herramienta no puede hacer (ajustes de GitHub Pages, protección de ramas, archivar repos).

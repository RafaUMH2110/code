# Mover un repositorio de GitHub a una subcarpeta de otro repositorio

**Autor:** Rafa · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche · r.puerto@umh.es
*Generado con IA · Revisado por el autor*

Guía para llevar el contenido de un repositorio a una **subcarpeta de otro**, **conservando el historial de commits**, y retirar después el repositorio de origen sin perder nada.

Ejemplo real de esta guía: **`RafaUMH2110/telemetria` → `RafaUMH2110/code`** (carpeta `telemetria/`), porque todo el contenido es código Python. Cambia los nombres por los tuyos en otros casos.

---

## 1. Resumen

GitHub **no permite fusionar dos repositorios** desde su interfaz. Lo que sí se puede hacer es:

1. Traer el repo de origen dentro del de destino, como subcarpeta, con `git subtree add` (conserva todos los commits).
2. Subir el resultado al destino.
3. Corregir los enlaces y las guías que apuntaban al repo viejo.
4. Dejar un aviso en el repo viejo y **archivarlo** (o borrarlo cuando estés seguro).

| Paso | Qué haces | Dónde |
|---|---|---|
| 1 | Clonar origen y destino | Terminal |
| 2 | `git subtree add` | Terminal (repo destino) |
| 3 | Revisar y `git push` | Terminal |
| 4 | Buscar y corregir referencias | Terminal / editor |
| 5 | Aviso + archivar el repo viejo | GitHub (web) |

---

## 2. Requisitos

- Tener `git` (2.20 o superior; `git subtree` viene incluido en las instalaciones habituales).
- Permiso de escritura en el repo **destino**. Del repo de origen solo hace falta leerlo (si es público no hace falta nada); para archivarlo después sí necesitas ser su propietario.
- Autenticación contra GitHub ya configurada (`gh auth login`, clave SSH o token).

Comprobaciones previas:

```bash
git --version
git subtree 2>&1 | head -2          # debe mostrar la ayuda de subtree, no "not a git command"
gh auth status                      # opcional: comprueba la sesión de GitHub
```

---

## 3. Decisiones previas

| Decisión | Valor en el ejemplo | Cómo elegir |
|---|---|---|
| Repo de origen | `RafaUMH2110/telemetria` | El que se va a mover |
| Repo de destino | `RafaUMH2110/code` | Debe existir ya |
| Subcarpeta destino | `telemetria` | Sin barra inicial ni final. Elige una ruta que no exista aún en el destino |
| Rama del origen | `main` | Compruébala: `git -C telemetria branch -a` (puede ser `master`) |
| ¿Conservar historial? | Sí | Si no importa, usa la variante sin historial (sección 9) |

---

## 4. Paso a paso (con historial)

### 4.1. Clonar los dos repositorios

Clona el origen **completo** (no uses `--depth`: un clon superficial pierde historial).

```bash
cd ~
git clone https://github.com/RafaUMH2110/telemetria.git
git clone https://github.com/RafaUMH2110/code.git
```

Comprueba qué vas a mover:

```bash
cd ~/telemetria
git branch -a                 # ramas (anota el nombre de la principal)
git log --oneline | wc -l     # nº de commits que se conservarán
git ls-files                  # ficheros que se llevará
```

### 4.2. Preparar el destino

```bash
cd ~/code
git checkout main
git pull --rebase origin main        # parte de lo último que hay en GitHub
git status                           # debe estar limpio
ls telemetria 2>/dev/null    # no debe existir ya (si existe, elige otra ruta)
```

### 4.3. Traer el repo de origen como subcarpeta

```bash
cd ~/code
git subtree add --prefix=telemetria ~/telemetria main
```

- `--prefix` es la subcarpeta de destino.
- El segundo argumento es el repositorio de origen (ruta local o URL) y el tercero, su rama.
- **No** uses `--squash` si quieres conservar los commits uno a uno.

Resultado: un commit de fusión `Add 'telemetria/' from commit '…'` y la carpeta `telemetria/` con todos los ficheros. El historial original queda enlazado, así que `git log -- telemetria` muestra los commits antiguos.

### 4.4. Revisar antes de subir

```bash
git log --oneline -5
ls telemetria
git log --oneline -- telemetria | head     # historial del origen
git diff --stat HEAD~1 HEAD | tail -3
```

Comprueba que están todos los ficheros del origen y que no ha entrado nada que no debía (claves, `config.ini`, datos).

### 4.5. Subir al destino

```bash
git push origin main
```

Si te lo rechaza porque alguien subió algo entre medias: `git pull --rebase origin main` y repite `git push origin main`.

---

## 5. Corregir referencias al repo viejo

Busca en tus repos cualquier mención al origen:

```bash
cd ~/code
grep -rn "RafaUMH2110/telemetria" . --include=*.md --include=*.html --include=*.sh --include=*.py --include=*.json
grep -rn -i "repos \"[^\"]*telemetria" . --include=*.md --include=*.sh   # listas de repos en guías y scripts
cd ~/apps && grep -rn "RafaUMH2110/telemetria" . --include=*.md --include=*.html --include=*.json
```

Qué suele haber que tocar:

| Dónde | Qué cambiar |
|---|---|
| README de `code` / `apps` | Enlaces `github.com/RafaUMH2110/telemetria` → `github.com/RafaUMH2110/code/tree/main/telemetria` |
| Guías de los scripts `instalar_todo*.sh` | Ejemplos con `--repos "…,telemetria"` → `…,code/telemetria`; quitar el repo de los menús de ejemplo |
| Portales / índices | Las entradas que apunten al repo viejo |
| Documentos que citen la ruta de los ficheros | La ruta nueva es `telemetria/<fichero>` |

Cada cambio se sube con su commit habitual:

```bash
git add -A
git commit -m "Actualiza referencias tras mover telemetria a telemetria"
git pull --rebase origin main && git push origin main
```

Añade también una fila en el README de la carpeta (`scripts/README.md`) que explique qué es `telemetria/` y que antes era un repo independiente.

---

## 6. Retirar el repositorio de origen

Hazlo **solo cuando** hayas comprobado que todo está en el destino.

### 6.1. Dejar un aviso

En el repo viejo, sustituye el README por un aviso:

```bash
cd ~/telemetria
cat > README.md <<'EOF'
# telemetria — MOVIDO

Este repositorio se ha integrado en
**[RafaUMH2110/code](https://github.com/RafaUMH2110/code/tree/main/telemetria)**
(carpeta `telemetria/`). Este repo queda archivado solo como referencia.
EOF
git add README.md && git commit -m "Aviso: repositorio movido a RafaUMH2110/code" && git push origin main
```

### 6.2. Archivarlo (recomendado)

En GitHub: repo `telemetria` → **Settings → General → Danger Zone → Archive this repository**.

El repo queda de solo lectura: los enlaces antiguos siguen funcionando, nadie puede subir cambios y puedes desarchivarlo si hace falta.

### 6.3. O borrarlo (solo si no lo necesitas)

**Settings → General → Danger Zone → Delete this repository.** Es **irreversible** y rompe todos los enlaces, forks y estrellas. Mejor archivar, y borrar más adelante si realmente sobra.

Con la CLI de GitHub, equivalentes:

```bash
gh repo archive RafaUMH2110/telemetria --yes
# gh repo delete RafaUMH2110/telemetria --yes        # irreversible
```

---

## 7. Comprobaciones finales

```bash
cd ~/code && git status                     # limpio
git log --oneline -3                        # tu último commit está arriba
git ls-remote origin main                   # el hash coincide con el local
git log --oneline -- telemetria | wc -l   # nº de commits del historial conservado
```

Y en la web: abre `https://github.com/RafaUMH2110/code/tree/main/telemetria` y comprueba que está todo.

Si el repo de origen tenía **GitHub Pages**, **Actions**, **Issues**, **releases** o **webhooks**, esas cosas **no** se mueven con el código: revísalas en *Settings* del repo viejo antes de archivarlo.

---

## 8. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `git: 'subtree' is not a git command` | Instalación sin `git subtree` | Instala el paquete completo (`apt install git`) o usa la variante sin historial (sección 9) |
| `Working tree has modifications. Cannot add.` | Cambios sin confirmar en el destino | `git status`; haz commit o `git stash` y repite |
| `prefix 'telemetria' already exists.` | La carpeta destino ya existe | Elige otro `--prefix` o bórrala si estaba vacía |
| `fatal: couldn't find remote ref main` | La rama del origen no se llama `main` | Mira `git -C ~/telemetria branch -a` y usa su nombre (p. ej. `master`) |
| Solo aparecen 1 o 2 commits | El origen se clonó con `--depth` | Clona de nuevo sin `--depth` (o `git fetch --unshallow`) |
| `git push` rechazado (non-fast-forward) | Cambios nuevos en el destino | `git pull --rebase origin main` y vuelve a subir |
| Ya hay rutas o enlaces rotos | Quedan referencias al repo viejo | Repite la búsqueda de la sección 5 |

---

## 9. Variante sin historial (más simple)

Si el historial no importa:

```bash
cd ~/code
mkdir -p telemetria
rsync -a --exclude='.git' ~/telemetria/ telemetria/
git add telemetria
git commit -m "Añade telemetria (movido desde RafaUMH2110/telemetria)"
git push origin main
```

Se pierde el historial de commits (queda solo en el repo archivado).

---

## 10. Variante: sin clonar antes el origen

Si prefieres no clonar el origen antes:

```bash
cd ~/code
git subtree add --prefix=telemetria https://github.com/RafaUMH2110/telemetria.git main
```

Trae el historial directamente desde GitHub (necesita conexión y permiso de lectura).

---

## 11. Plantilla para reutilizar

Sustituye los cuatro valores y ejecuta:

```bash
ORIGEN=RafaUMH2110/telemetria      # usuario/repo a mover
DESTINO=RafaUMH2110/code           # usuario/repo que lo recibe
CARPETA=telemetria         # subcarpeta dentro del destino
RAMA=main                          # rama del origen

git clone "https://github.com/$ORIGEN.git" /tmp/origen
git clone "https://github.com/$DESTINO.git" /tmp/destino
cd /tmp/destino
test ! -e "$CARPETA" || { echo "La carpeta $CARPETA ya existe"; exit 1; }
git subtree add --prefix="$CARPETA" /tmp/origen "$RAMA"
git log --oneline -3
git push origin HEAD
```

Después, sigue con las secciones 5 a 7.

---

*Autor: Rafael Puerto (r.puerto@umh.es) · Departamento de Ingeniería de Sistemas y Automática · Universidad Miguel Hernández de Elche.*

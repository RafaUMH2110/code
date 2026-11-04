# Clonar y actualizar los repositorios públicos de RafaUMH2110

Guía para un servidor local **Debian 13** (IP `192.168.0.129`).

Autor: Rafa Puerto · Departamento de Ingeniería de Sistemas y Automática · UMH · r.puerto@umh.es
_Generado con IA · Revisado por el autor_

---

## 1. Requisitos

```bash
sudo apt update && sudo apt install -y git curl jq
```

| Paquete | Uso |
|---------|-----|
| `git`   | Clonar y actualizar repositorios |
| `curl`  | Consultar la API de GitHub |
| `jq`    | Procesar la respuesta JSON de la API |

El servidor necesita salida a Internet (HTTPS, puerto 443) hacia `github.com` y `api.github.com`.

## 2. Clonar todos los repos públicos (primera vez)

```bash
mkdir -p ~/RafaUMH2110 && cd ~/RafaUMH2110

page=1
while :; do
  repos=$(curl -s "https://api.github.com/users/RafaUMH2110/repos?type=public&per_page=100&page=$page" \
    | jq -r '.[].name')
  [ -z "$repos" ] && break
  for r in $repos; do
    if [ -d "$r/.git" ]; then
      echo ">> Actualizando $r"; git -C "$r" pull --ff-only
    else
      echo ">> Clonando $r"
      git clone "https://github.com/RafaUMH2110/$r.git"
    fi
  done
  page=$((page+1))
done
```

Resultado: un directorio por repositorio dentro de `~/RafaUMH2110/`.

## 3. Script de actualización (`actualizar_repos.sh`)

Hace `git pull --ff-only` en los repos ya clonados, clona los públicos nuevos y guarda un registro en `actualizar.log`.

```bash
#!/usr/bin/env bash
# Actualiza (git pull) los repos públicos de RafaUMH2110 y clona los nuevos.
# Uso: ./actualizar_repos.sh [directorio_destino]
set -euo pipefail

USUARIO="RafaUMH2110"
DESTINO="${1:-$HOME/$USUARIO}"
LOG="$DESTINO/actualizar.log"

for cmd in git curl jq; do
  command -v "$cmd" >/dev/null || { echo "Falta '$cmd'. Instala con: sudo apt install -y git curl jq" >&2; exit 1; }
done

mkdir -p "$DESTINO"
cd "$DESTINO"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "Inicio de sincronización de $USUARIO en $DESTINO"
nuevos=0; actualizados=0; errores=0
page=1

while :; do
  respuesta=$(curl -sf "https://api.github.com/users/$USUARIO/repos?type=public&per_page=100&page=$page") \
    || { log "ERROR: fallo al consultar la API de GitHub (¿límite de peticiones?)"; exit 1; }
  repos=$(echo "$respuesta" | jq -r '.[].name')
  [ -z "$repos" ] && break

  for r in $repos; do
    if [ -d "$r/.git" ]; then
      if git -C "$r" pull --ff-only --quiet; then
        log "Actualizado: $r"; actualizados=$((actualizados+1))
      else
        log "ERROR actualizando: $r"; errores=$((errores+1))
      fi
    else
      if git clone --quiet "https://github.com/$USUARIO/$r.git"; then
        log "Clonado (nuevo): $r"; nuevos=$((nuevos+1))
      else
        log "ERROR clonando: $r"; errores=$((errores+1))
      fi
    fi
  done
  page=$((page+1))
done

log "Fin. Nuevos: $nuevos | Actualizados: $actualizados | Errores: $errores"
```

### Instalación y uso

```bash
nano ~/actualizar_repos.sh        # pegar el contenido anterior
chmod +x ~/actualizar_repos.sh

~/actualizar_repos.sh             # destino por defecto: ~/RafaUMH2110
~/actualizar_repos.sh /srv/repos  # destino personalizado
```

## 4. Automatizar con cron

```bash
crontab -e
```

Añadir (ejecución diaria a las 3:00):

```
0 3 * * * /home/usuario/actualizar_repos.sh >/dev/null 2>&1
```

Sustituye `usuario` por el usuario real del servidor. Revisa el resultado en `~/RafaUMH2110/actualizar.log`.

## 5. Clonar o actualizar un único repositorio

```bash
# Clonar
git clone https://github.com/RafaUMH2110/<repo>.git

# Actualizar
git -C ~/RafaUMH2110/<repo> pull --ff-only
```

## 6. Repositorios privados (opcional)

Con un _Personal Access Token_ (permiso `repo`) se pueden incluir los privados:

```bash
export GITHUB_TOKEN="ghp_XXXXXXXXXXXX"
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/user/repos?affiliation=owner&per_page=100&page=1" | jq -r '.[].name'
```

Recomendaciones:
- No dejes el token escrito en el script ni en la URL de clonado (queda guardado en `.git/config`).
- Alternativa más limpia: instalar `gh` (`sudo apt install gh`), ejecutar `gh auth login` y usar `gh repo clone RafaUMH2110/<repo>`.

## 7. Copia exacta tipo backup (opcional)

Para conservar todas las ramas y referencias, clona con `--mirror` y actualiza con `remote update`:

```bash
git clone --mirror https://github.com/RafaUMH2110/<repo>.git
git -C <repo>.git remote update --prune
```

Un repositorio `--mirror` no tiene árbol de trabajo (es solo la base de datos de Git).

## 8. Solución de problemas

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| `jq: parse error` o el script falla al consultar la API | Límite de la API sin autenticar (60 peticiones/hora por IP) | Esperar una hora o usar un token |
| `fatal: Not possible to fast-forward` | Hay cambios locales o historia reescrita en el remoto | Revisar con `git status`; si no hay nada local que conservar: `git fetch && git reset --hard origin/<rama>` |
| `Could not resolve host: github.com` | Sin DNS o sin salida a Internet | Comprobar `ping 8.8.8.8` y `/etc/resolv.conf`; revisar proxy o cortafuegos |
| `Permission denied` al crear el directorio | Permisos del destino | Usar un destino dentro de `$HOME` o ajustar propietario con `chown` |
| El cron no se ejecuta | Ruta relativa o falta de permisos de ejecución | Usar ruta absoluta y `chmod +x` |

## 9. Comprobaciones rápidas

```bash
ls ~/RafaUMH2110                       # repos clonados
tail -n 20 ~/RafaUMH2110/actualizar.log  # último resultado
git -C ~/RafaUMH2110/<repo> log -1     # último commit descargado
```

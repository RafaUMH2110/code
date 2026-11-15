#!/usr/bin/env bash
# =====================================================================
#  instalar-iterm2.sh · Instala tema y perfiles de iTerm2 (macOS)
#
#  Uso:  bash instalar-iterm2.sh [-m NOMBRE] [--colores]
#
#    -m, --maquina NOMBRE   nombre de ESTA máquina («iMac despacho»,
#                           «MacBook»). Se guarda en datos/maquina.txt y lo
#                           usan los generadores: aparece como distintivo en
#                           las sesiones locales y como comentario de las
#                           claves SSH que se creen aquí, para distinguirlas
#                           en el authorized_keys de los servidores.
#                           Si no se indica, se pregunta, proponiendo el
#                           nombre que macOS tiene configurado.
#    --colores              importa además los presets de color
#                           (colores/*.itermcolors) en Ajustes > Colores.
#                           NO hace falta: los perfiles ya llevan sus colores.
#                           iTerm2 pregunta «¿Añadir preset duplicado?» si ya
#                           los tenías, por eso solo se hace cuando se pide.
#    -h, --ayuda            esta ayuda
#
#  El shebang hace que se ejecute con bash aunque tu shell sea zsh (el de
#  Darwin). Está escrito para funcionar igual si lo lanzas con «zsh
#  instalar-iterm2.sh»: nada de «read -p» ni de globs sin resultado, que
#  zsh trata de otra manera.
# =====================================================================
set -euo pipefail

ESTE="${BASH_SOURCE[0]:-$0}"      # bash da BASH_SOURCE; zsh, $0

uso() { awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$ESTE"; }

# read -p no es portable: zsh lo usa para leer del coproceso
pregunta() {                      # pregunta "texto" NOMBRE_DE_VARIABLE
  printf '%s' "$1" >&2
  IFS= read -r "$2" || true
}

MAQUINA=""
COLORES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--maquina)
      [[ -n "${2:-}" ]] || { echo "Falta el nombre después de $1"; exit 1; }
      MAQUINA="$2"; shift 2 ;;
    --colores) COLORES=1; shift ;;
    -h|--ayuda|--help) uso; exit 0 ;;
    *) echo "Opción desconocida: $1"; echo; uso; exit 1 ;;
  esac
done

AQUI="$(cd "$(dirname "$ESTE")" && pwd)"
if [[ -d "$AQUI/colores" ]]; then BASE="$AQUI"; else BASE="$(cd "$AQUI/.." && pwd)"; fi
DYN="$HOME/Library/Application Support/iTerm2/DynamicProfiles"
# Las copias de seguridad NUNCA van dentro de DynamicProfiles: iTerm2 carga
# todos los archivos de esa carpeta, así que una copia del mismo archivo son
# perfiles repetidos y avisos al abrir cada ventana.
COPIAS="$HOME/.iterm2-umh-copias"
STAMP="$(date +%Y%m%d-%H%M%S)"

[[ "$(uname)" == "Darwin" ]] || { echo "Este script es para macOS."; exit 1; }

echo "==> 1/8 Nombre de esta máquina"
POR_DEFECTO="$(scutil --get ComputerName 2>/dev/null || hostname -s)"
if [[ -z "$MAQUINA" ]]; then
  if [[ -t 0 ]]; then
    R=""
    pregunta "    ¿Cómo llamas a este equipo? [$POR_DEFECTO] " R
    MAQUINA="${R:-$POR_DEFECTO}"
  else
    MAQUINA="$POR_DEFECTO"       # sin terminal interactiva: el de macOS
  fi
fi
# Se guarda sin espacios al principio ni al final y en una sola línea
MAQUINA="$(printf '%s' "${MAQUINA}" | tr -d '\r\n' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
[[ -n "${MAQUINA}" ]] || { echo "    El nombre no puede quedar vacío."; exit 1; }
mkdir -p "$BASE/datos"
printf '%s\n' "${MAQUINA}" > "$BASE/datos/maquina.txt"
echo "    -> '${MAQUINA}' guardado en datos/maquina.txt"
echo "       (distintivo de las sesiones locales y comentario de las claves)"

echo "==> 2/8 Fuente: Menlo Regular 12 (viene con macOS)"
if [[ -e /System/Library/Fonts/Menlo.ttc ]]; then
  echo "    OK, no hay que instalar nada."
else
  echo "    AVISO: no encuentro Menlo en /System/Library/Fonts."
fi

echo "==> 3/8 Perfiles dinámicos de iTerm2"
mkdir -p "$DYN" "$COPIAS"

# Copias de seguridad antiguas que quedaron dentro de la carpeta: iTerm2 las
# carga como perfiles más, con los mismos GUID, y de ahí los avisos repetidos.
SOBRAN="$(find "$DYN" -maxdepth 1 -type f -name 'UMH-Perfiles.json.bak-*' 2>/dev/null)"
if [[ -n "$SOBRAN" ]]; then
  printf '%s\n' "$SOBRAN" | while IFS= read -r f; do
    [[ -n "$f" ]] && mv "$f" "$COPIAS/" && echo "    Aparto $(basename "$f") (iTerm2 lo cargaba como perfiles duplicados)"
  done
fi
AJENOS="$(find "$DYN" -maxdepth 1 -type f ! -name 'UMH-Perfiles.json' 2>/dev/null | sort)"
if [[ -n "$AJENOS" ]]; then
  echo "    AVISO: hay más archivos en DynamicProfiles, y iTerm2 también los carga."
  echo "    Si ves perfiles repetidos, míralos; no los toco porque pueden no ser míos:"
  printf '%s\n' "$AJENOS" | while IFS= read -r f; do [[ -n "$f" ]] && echo "      $(basename "$f")"; done
fi

if [[ -f "$BASE/datos/servidores.csv" ]] && command -v python3 >/dev/null 2>&1; then
  echo "    Hay inventario: regenero los perfiles para que lleven el nombre nuevo"
  [[ -f "$DYN/UMH-Perfiles.json" ]] && cp "$DYN/UMH-Perfiles.json" "$COPIAS/UMH-Perfiles.json.bak-$STAMP"
  python3 "$BASE/generar_perfiles.py" --instalar \
    || echo "    El inventario tiene errores: corrígelos y repite generar_perfiles.py"
elif [[ -f "$BASE/perfiles/UMH-Perfiles.json" ]]; then
  [[ -f "$DYN/UMH-Perfiles.json" ]] && cp "$DYN/UMH-Perfiles.json" "$COPIAS/UMH-Perfiles.json.bak-$STAMP"
  cp "$BASE/perfiles/UMH-Perfiles.json" "$DYN/UMH-Perfiles.json"
  echo "    -> $DYN/UMH-Perfiles.json  (iTerm2 lo recarga al instante)"
  echo "    OJO: el distintivo con el nombre de la máquina sale al regenerar:"
  echo "      python3 generar_perfiles.py --instalar"
else
  echo "    Todavía no hay perfiles generados. Cuando tengas tu inventario:"
  echo "      python3 generar_perfiles.py --instalar"
fi

echo "==> 4/8 Comprobar la fuente de los perfiles instalados"
if [[ -f "$DYN/UMH-Perfiles.json" ]]; then
  grep -m1 '"Normal Font"' "$DYN/UMH-Perfiles.json" | sed 's/^[[:space:]]*/    /'
  if grep -q '"Normal Font": "null' "$DYN/UMH-Perfiles.json"; then
    echo "    AVISO: la fuente quedó en «null». Repite: python3 generar_perfiles.py --instalar"
  fi
  if grep -q 'JetBrainsMono' "$DYN/UMH-Perfiles.json"; then
    echo "    AVISO: el JSON instalado aún usa JetBrainsMono (versión antigua)."
    echo "    Regenéralo con: python3 generar_perfiles.py --instalar"
  fi
else
  echo "    (aún no hay perfiles instalados)"
fi

echo "==> 5/8 Presets de color"
if [[ "$COLORES" == "1" ]]; then
  echo "    Se abren para que iTerm2 los importe (si ya estaban, te preguntará)."
  open "$BASE/colores/UMH-Elegante-Oscuro.itermcolors" || true
  open "$BASE/colores/UMH-Elegante-Claro.itermcolors"  || true
else
  echo "    No se importan: los perfiles ya llevan sus colores."
  echo "    (Si los quieres en Ajustes > Colores: bash instalar-iterm2.sh --colores)"
fi

echo "==> 6/8 Carpetas y permisos de SSH"
mkdir -p "$HOME/.ssh/cm" "$HOME/.ssh/config.d"
chmod 700 "$HOME/.ssh" "$HOME/.ssh/cm" "$HOME/.ssh/config.d"
[[ -f "$HOME/.ssh/config" ]] && chmod 600 "$HOME/.ssh/config"
echo "    Carpetas listas. La configuración SSH de cada servidor la escribe"
echo "    el generador, que respeta tu ~/.ssh/config y solo le añade un Include:"
echo "      python3 generar_perfiles.py --instalar"

echo "==> 7/8 Shell integration de iTerm2 (opcional)"
# Marcas de prompt (⌘↑/⌘↓ salta entre comandos), historial y descargas con clic
# derecho. Es un archivo que se descarga y se carga desde ~/.zshrc.
SI_ARCHIVO="$HOME/.iterm2_shell_integration.zsh"
SI_LINEA='test -e "${HOME}/.iterm2_shell_integration.zsh" && source "${HOME}/.iterm2_shell_integration.zsh"'
if [[ -f "$SI_ARCHIVO" ]] && grep -qs 'iterm2_shell_integration' "$HOME/.zshrc" 2>/dev/null; then
  echo "    Ya está instalada: no toco nada."
elif [[ ! -t 0 ]]; then
  echo "    Omitido (sin terminal interactiva). Se puede repetir este script."
else
  Q=""
  pregunta "    ¿Instalarla? Descarga un archivo de iterm2.com y añade una línea a ~/.zshrc [s/N] " Q
  if [[ "${Q:-N}" =~ ^[sSyY]$ ]]; then
    if ! command -v curl >/dev/null 2>&1; then
      echo "    No hay curl: omitido."
    elif curl -fsSL --max-time 30 https://iterm2.com/shell_integration/zsh -o "$SI_ARCHIVO.tmp" \
         && [[ -s "$SI_ARCHIVO.tmp" ]] && grep -q 'iTerm2' "$SI_ARCHIVO.tmp"; then
      mv "$SI_ARCHIVO.tmp" "$SI_ARCHIVO"
      if ! grep -qs 'iterm2_shell_integration' "$HOME/.zshrc" 2>/dev/null; then
        [[ -f "$HOME/.zshrc" ]] && cp "$HOME/.zshrc" "$COPIAS/.zshrc.bak-$STAMP"
        printf '\n# iTerm2 shell integration (añadido por instalar-iterm2.sh)\n%s\n' "$SI_LINEA" >> "$HOME/.zshrc"
        echo "    Línea añadida a ~/.zshrc (copia previa en $COPIAS)."
      fi
      echo "    Instalada. Abre una pestaña nueva para activarla."
    else
      rm -f "$SI_ARCHIVO.tmp"
      echo "    No se pudo descargar (¿sin conexión?). No he cambiado nada."
      echo "    Puedes hacerlo a mano: está en MANUAL.md, apartado 4."
    fi
  else
    echo "    Omitida."
  fi
fi

echo "==> 8/8 Fijar UMH · Base como perfil predeterminado"
GUID_BASE="415d01c5-71c8-5639-bd7e-0d90e99b4a0f"   # uuid5 de "UMH · Base"
ACTUAL="$(defaults read com.googlecode.iterm2 "Default Bookmark Guid" 2>/dev/null || true)"
if [[ "$ACTUAL" == "$GUID_BASE" ]]; then
  echo "    Ya era el predeterminado."
else
  echo "    Esto REQUIERE cerrar iTerm2 (perderás las sesiones abiertas)."
  Q=""
  pregunta "    ¿Cerrar iTerm2 y fijarlo ahora? [s/N] " Q
  if [[ "${Q:-N}" =~ ^[sSyY]$ ]]; then
    osascript -e 'quit app "iTerm"' 2>/dev/null || true
    sleep 3
    defaults write com.googlecode.iterm2 "Default Bookmark Guid" -string "$GUID_BASE"
    echo "    Hecho. Vuelve a abrir iTerm2."
  else
    echo "    Omitido. Hazlo en Ajustes > Perfiles > UMH · Base"
    echo "    > Other Actions... > Set as Default."
  fi
fi

cat <<'FIN'


Listo. Siguiente paso (desde esta carpeta):
  python3 generar_perfiles.py --instalar     # perfiles + ~/.ssh/config.d/umh.conf
  python3 generar_claves.py --dry-run        # ver qué claves se crearían
En iTerm2: Ajustes > Perfiles  ->  verás los perfiles "UMH · ...".
«UMH · Base» es el predeterminado: ⌘N abre una ventana del tamaño de la hoja.
Si ya tenías ventanas abiertas, ciérralas y abre una nueva con ⌘N: el tamaño
solo se aplica a ventanas nuevas.
FIN

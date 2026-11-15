#!/usr/bin/env bash
# =====================================================================
#  instalar-iterm2.sh · Instala tema y perfiles de iTerm2 (macOS)
#
#  Uso:  bash instalar-iterm2.sh [-m NOMBRE]
#
#    -m, --maquina NOMBRE   nombre de ESTA máquina («iMac despacho»,
#                           «MacBook»). Se guarda en datos/maquina.txt y lo
#                           usan los generadores: aparece como distintivo en
#                           las sesiones locales y como comentario de las
#                           claves SSH que se creen aquí, para distinguirlas
#                           en el authorized_keys de los servidores.
#                           Si no se indica, se pregunta, proponiendo el
#                           nombre que macOS tiene configurado.
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
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--maquina)
      [[ -n "${2:-}" ]] || { echo "Falta el nombre después de $1"; exit 1; }
      MAQUINA="$2"; shift 2 ;;
    -h|--ayuda|--help) uso; exit 0 ;;
    *) echo "Opción desconocida: $1"; echo; uso; exit 1 ;;
  esac
done

AQUI="$(cd "$(dirname "$ESTE")" && pwd)"
if [[ -d "$AQUI/colores" ]]; then BASE="$AQUI"; else BASE="$(cd "$AQUI/.." && pwd)"; fi
DYN="$HOME/Library/Application Support/iTerm2/DynamicProfiles"
STAMP="$(date +%Y%m%d-%H%M%S)"

[[ "$(uname)" == "Darwin" ]] || { echo "Este script es para macOS."; exit 1; }

echo "==> 1/7 Nombre de esta máquina"
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

echo "==> 2/7 Fuente monoespaciada (JetBrainsMono Nerd Font)"
if command -v brew >/dev/null 2>&1; then
  brew list --cask font-jetbrains-mono-nerd-font >/dev/null 2>&1 \
    || brew install --cask font-jetbrains-mono-nerd-font
else
  echo "    Homebrew no encontrado. Instala la fuente a mano desde"
  echo "    https://www.nerdfonts.com  (variante 'Nerd Font Mono')"
fi

echo "==> 3/7 Perfiles dinámicos de iTerm2"
mkdir -p "$DYN"
if [[ -f "$BASE/perfiles/UMH-Perfiles.json" ]]; then
  [[ -f "$DYN/UMH-Perfiles.json" ]] && cp "$DYN/UMH-Perfiles.json" "$DYN/UMH-Perfiles.json.bak-$STAMP"
  cp "$BASE/perfiles/UMH-Perfiles.json" "$DYN/UMH-Perfiles.json"
  echo "    -> $DYN/UMH-Perfiles.json  (iTerm2 lo recarga al instante)"
else
  echo "    Todavía no hay perfiles generados. Cuando tengas tu inventario:"
  echo "      python3 generar_perfiles.py --instalar"
fi

echo "==> 4/7 Comprobar el nombre PostScript real de la fuente"
# Devuelve el nombre PostScript, o nada si no se puede determinar.
# OJO: mdls devuelve "(null)" si Spotlight aún no ha indexado el archivo;
# ese valor NUNCA debe escribirse en el perfil.
ps_name_of() {
  mdls -raw -name com_apple_ats_name_postscript "$1" 2>/dev/null \
    | tr -d '()"' | tr -s ' \t\n,' '\n' \
    | grep -E '^[A-Za-z0-9][A-Za-z0-9._-]+$' \
    | grep -vix 'null' | head -1
}
FONT_TTF="$HOME/Library/Fonts/JetBrainsMonoNerdFontMono-Regular.ttf"
ESPERADO="JetBrainsMonoNFM-Regular"
PS_NAME=""
if [[ -f "$FONT_TTF" ]]; then
  mdimport -i "$FONT_TTF" >/dev/null 2>&1 || true   # fuerza el indexado
  for _ in 1 2 3; do
    PS_NAME="$(ps_name_of "$FONT_TTF")"
    [[ -n "$PS_NAME" ]] && break
    sleep 1
  done
fi
if [[ -z "$PS_NAME" ]]; then
  echo "    No se pudo leer el nombre PostScript (Spotlight aún indexando)."
  echo "    Se deja '$ESPERADO', que es el correcto para esta fuente."
  echo "    Verifícalo luego con: bash scripts/diagnostico.sh"
elif [[ "$PS_NAME" == "$ESPERADO" ]]; then
  echo "    OK ($ESPERADO)"
else
  echo "    Tu versión usa otro nombre: $PS_NAME -> ajustando el perfil instalado"
  /usr/bin/sed -i '' "s/$ESPERADO/$PS_NAME/g" "$DYN/UMH-Perfiles.json"
fi

echo "==> 5/7 Presets de color (se abren para que iTerm2 los importe)"
open "$BASE/colores/UMH-Elegante-Oscuro.itermcolors" || true
open "$BASE/colores/UMH-Elegante-Claro.itermcolors"  || true

echo "==> 6/7 Carpetas y permisos de SSH"
mkdir -p "$HOME/.ssh/cm" "$HOME/.ssh/config.d"
chmod 700 "$HOME/.ssh" "$HOME/.ssh/cm" "$HOME/.ssh/config.d"
[[ -f "$HOME/.ssh/config" ]] && chmod 600 "$HOME/.ssh/config"
echo "    Carpetas listas. La configuración SSH de cada servidor la escribe"
echo "    el generador, que respeta tu ~/.ssh/config y solo le añade un Include:"
echo "      python3 scripts/generar_perfiles.py --instalar"

echo "==> 7/7: fijar UMH · Base como perfil predeterminado"
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


Listo. Siguiente paso:
  python3 scripts/generar_perfiles.py --instalar
  python3 scripts/generar_claves.py --dry-run
En iTerm2: Ajustes > Perfiles  ->  verás los perfiles "UMH · ...".
Marca "UMH · Local (iMac)" como predeterminado si no lo está.
FIN

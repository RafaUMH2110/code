#!/usr/bin/env bash
# =====================================================================
#  instalar-iterm2.sh · Instala tema, perfiles y config SSH (macOS)
#  Uso:  bash scripts/instalar-iterm2.sh
# =====================================================================
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$AQUI/colores" ]]; then BASE="$AQUI"; else BASE="$(cd "$AQUI/.." && pwd)"; fi
DYN="$HOME/Library/Application Support/iTerm2/DynamicProfiles"
STAMP="$(date +%Y%m%d-%H%M%S)"

[[ "$(uname)" == "Darwin" ]] || { echo "Este script es para macOS."; exit 1; }

echo "==> 1/6 Fuente monoespaciada (JetBrainsMono Nerd Font)"
if command -v brew >/dev/null 2>&1; then
  brew list --cask font-jetbrains-mono-nerd-font >/dev/null 2>&1 \
    || brew install --cask font-jetbrains-mono-nerd-font
else
  echo "    Homebrew no encontrado. Instala la fuente a mano desde"
  echo "    https://www.nerdfonts.com  (variante 'Nerd Font Mono')"
fi

echo "==> 2/6 Perfiles dinámicos de iTerm2"
mkdir -p "$DYN"
[[ -f "$DYN/UMH-Perfiles.json" ]] && cp "$DYN/UMH-Perfiles.json" "$DYN/UMH-Perfiles.json.bak-$STAMP"
cp "$BASE/perfiles/UMH-Perfiles.json" "$DYN/UMH-Perfiles.json"
echo "    -> $DYN/UMH-Perfiles.json  (iTerm2 lo recarga al instante)"

echo "==> 3/6 Comprobar el nombre PostScript real de la fuente"
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

echo "==> 4/6 Presets de color (se abren para que iTerm2 los importe)"
open "$BASE/colores/UMH-Elegante-Oscuro.itermcolors" || true
open "$BASE/colores/UMH-Elegante-Claro.itermcolors"  || true

echo "==> 5/6 Carpetas y permisos de SSH"
mkdir -p "$HOME/.ssh/cm" "$HOME/.ssh/config.d"
chmod 700 "$HOME/.ssh" "$HOME/.ssh/cm" "$HOME/.ssh/config.d"
[[ -f "$HOME/.ssh/config" ]] && chmod 600 "$HOME/.ssh/config"
echo "    Carpetas listas. La configuración SSH de cada servidor la escribe"
echo "    el generador, que respeta tu ~/.ssh/config y solo le añade un Include:"
echo "      python3 scripts/generar_perfiles.py --instalar"

echo "==> 6/6: fijar UMH · Base como perfil predeterminado"
GUID_BASE="415d01c5-71c8-5639-bd7e-0d90e99b4a0f"   # uuid5 de "UMH · Base"
ACTUAL="$(defaults read com.googlecode.iterm2 "Default Bookmark Guid" 2>/dev/null || true)"
if [[ "$ACTUAL" == "$GUID_BASE" ]]; then
  echo "    Ya era el predeterminado."
else
  echo "    Esto REQUIERE cerrar iTerm2 (perderás las sesiones abiertas)."
  read -r -p "    ¿Cerrar iTerm2 y fijarlo ahora? [s/N] " Q || true
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

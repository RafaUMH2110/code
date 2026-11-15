#!/usr/bin/env bash
# =====================================================================
#  diagnostico.sh · ¿Por qué iTerm2 no aplica fuente/tamaño?
#  Uso:  bash scripts/diagnostico.sh
# =====================================================================
DYN="$HOME/Library/Application Support/iTerm2/DynamicProfiles/UMH-Perfiles.json"

echo "=============================================================="
echo " 1. ¿Están cargados los perfiles?"
echo "=============================================================="
if [[ -f "$DYN" ]]; then
  echo "Archivo: OK"
  grep -nE '"(Name|Normal Font|Columns|Rows)"' "$DYN" | sed 's/^/  /'
else
  echo "NO EXISTE -> $DYN"
  echo "   (vuelve a ejecutar scripts/instalar-iterm2.sh)"
fi

echo
echo "=============================================================="
echo " 2. ¿Qué perfil usa iTerm2 al abrir una ventana nueva?"
echo "=============================================================="
ACTUAL="$(defaults read com.googlecode.iterm2 "Default Bookmark Guid" 2>/dev/null)"
echo "GUID predeterminado actual : ${ACTUAL:-(ninguno: usa el perfil 'Default')}"
echo "GUID de UMH · Local (iMac) : 14fbd8df-11a4-519f-9afa-243dbdd6083b"
if [[ "$ACTUAL" == "14fbd8df-11a4-519f-9afa-243dbdd6083b" ]]; then
  echo ">> CORRECTO"
else
  echo ">> ESTA ES LA CAUSA MÁS PROBABLE: el predeterminado NO es el perfil UMH."
  echo "   Arreglo (cierra iTerm2 antes):"
  echo "     osascript -e 'quit app \"iTerm\"'; sleep 3"
  echo "     defaults write com.googlecode.iterm2 \"Default Bookmark Guid\" \\"
  echo "       -string \"14fbd8df-11a4-519f-9afa-243dbdd6083b\""
fi

echo
echo "=============================================================="
echo " 3. Nombre PostScript REAL de las fuentes instaladas"
echo "=============================================================="
N=0
for f in "$HOME/Library/Fonts"/JetBrainsMono*Mono-Regular.ttf \
         "$HOME/Library/Fonts"/JetBrainsMono*.ttf; do
  [[ -f "$f" ]] || continue
  PS="$(mdls -raw -name com_apple_ats_name_postscript "$f" 2>/dev/null)"
  printf '  %-45s -> %s\n' "$(basename "$f")" "${PS:-?}"
  N=$((N+1))
  [[ $N -ge 6 ]] && { echo "  (...)"; break; }
done
[[ $N -eq 0 ]] && echo "  No hay ninguna JetBrainsMono instalada en ~/Library/Fonts"
echo
echo "  El JSON debe llevar EXACTAMENTE ese nombre + espacio + tamaño,"
echo "  p.ej.  \"Normal Font\": \"JetBrainsMonoNFM-Regular 14\""
echo "  Si no coincide, iTerm2 cae en silencio a Monaco 12. Para corregirlo:"
echo "     sed -i '' 's/JetBrainsMonoNFM-Regular/<NOMBRE_REAL>/g' \"$DYN\""

echo
echo "=============================================================="
echo " 4. Ajustes que pisan el tamaño de ventana"
echo "=============================================================="
for k in OpenArrangementAtStartup OpenNoWindowsAtStartup AdjustWindowForFontSizeChange; do
  printf '  %-32s = %s\n' "$k" "$(defaults read com.googlecode.iterm2 $k 2>/dev/null || echo '(no definido)')"
done
printf '  %-32s = %s\n' "NSQuitAlwaysKeepsWindows (macOS)" \
  "$(defaults read -g NSQuitAlwaysKeepsWindows 2>/dev/null || echo '(no definido)')"
echo
echo "  OpenArrangementAtStartup = 1  -> se restaura una composición guardada"
echo "     y Columns/Rows se ignoran. Desactívalo en"
echo "     Settings > General > Startup."
echo "  NSQuitAlwaysKeepsWindows = 1  -> macOS restaura la geometría anterior."
echo "     Arreglo:  defaults write -g NSQuitAlwaysKeepsWindows -bool false"
echo
echo "  Recuerda: Columns/Rows se aplican al abrir una VENTANA nueva (⌘N),"
echo "  no una pestaña nueva (⌘T), que hereda el tamaño de la ventana actual."
echo "  Y en pantalla completa o ventana maximizada nunca se aplican."

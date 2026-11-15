#!/usr/bin/env bash
# =====================================================================
#  diagnostico.sh · ¿Por qué iTerm2 no aplica fuente/tamaño?
#  Uso:  bash diagnostico.sh
# =====================================================================
if [[ "$(uname)" != "Darwin" ]]; then
  echo "Este diagnóstico es para macOS: usa mdls, defaults y las rutas de iTerm2."
  exit 1
fi

DYN="$HOME/Library/Application Support/iTerm2/DynamicProfiles/UMH-Perfiles.json"

echo "=============================================================="
echo " 1. ¿Están cargados los perfiles?"
echo "=============================================================="
if [[ -f "$DYN" ]]; then
  echo "Archivo: OK"
  grep -nE '"(Name|Normal Font|Columns|Rows)"' "$DYN" | sed 's/^/  /'
else
  echo "NO EXISTE -> $DYN"
  echo "   (vuelve a ejecutar instalar-iterm2.sh)"
fi

echo
echo "=============================================================="
echo " 2. ¿Qué perfil usa iTerm2 al abrir una ventana nueva?"
echo "=============================================================="
ACTUAL="$(defaults read com.googlecode.iterm2 "Default Bookmark Guid" 2>/dev/null)"
echo "GUID predeterminado actual : ${ACTUAL:-(ninguno: usa el perfil 'Default')}"
echo "GUID de UMH · Base         : 415d01c5-71c8-5639-bd7e-0d90e99b4a0f"
if [[ "$ACTUAL" == "415d01c5-71c8-5639-bd7e-0d90e99b4a0f" ]]; then
  echo ">> CORRECTO"
else
  echo ">> ESTA ES LA CAUSA MÁS PROBABLE: el predeterminado NO es el perfil UMH · Base."
  echo "   Arreglo (cierra iTerm2 antes):"
  echo "     osascript -e 'quit app \"iTerm\"'; sleep 3"
  echo "     defaults write com.googlecode.iterm2 \"Default Bookmark Guid\" \\"
  echo "       -string \"415d01c5-71c8-5639-bd7e-0d90e99b4a0f\""
fi

echo
echo "=============================================================="
echo " 3. Fuente"
echo "=============================================================="
if [[ -e /System/Library/Fonts/Menlo.ttc ]]; then
  echo "  Menlo está en /System/Library/Fonts (viene con macOS): OK"
else
  echo "  No encuentro Menlo: algo raro en esta instalación de macOS."
fi
echo "  El JSON debe decir  \"Normal Font\": \"Menlo-Regular 12\""
echo "  (nombre PostScript + espacio + tamaño). Si el nombre no existe,"
echo "  iTerm2 cae en silencio a Monaco 12."
echo "  Fuente que usa el JSON instalado:"
grep -m1 '"Normal Font"' "$DYN" 2>/dev/null | sed 's/^/    /' || true

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
echo "  Si la ventana pedida no cabe en la pantalla, iTerm2 la recorta."
echo "  El tamaño de «UMH · Base» (lo que abre ⌘N) sale del valor más repetido de"
echo "  la columna «ventana»; se cambia con: python3 generar_perfiles.py --ventana 120x59 --instalar"

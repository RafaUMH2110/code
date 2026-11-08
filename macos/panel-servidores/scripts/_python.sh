# Auxiliar (se carga con `source`): elige un Python >= 3.10 y define $PYTHON_BASE.
# En macOS, `python3` suele ser el 3.9 de las Command Line Tools, demasiado viejo
# para esta aplicación; por eso se buscan versiones concretas antes.
PYTHON_BASE=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  ruta="$(command -v "$cand" 2>/dev/null || true)"
  [ -n "$ruta" ] || continue
  if "$ruta" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PYTHON_BASE="$ruta"
    break
  fi
done
if [ -z "$PYTHON_BASE" ]; then
  echo "ERROR: hace falta Python 3.10 o superior y solo se encontró:" >&2
  python3 --version >&2 || true
  echo "Instálalo con:  brew install python@3.12   (o desde https://www.python.org/downloads/)" >&2
  echo "y vuelve a ejecutar este script." >&2
  exit 1
fi
# Evita un fallo de pip/compileall en algunos terminales sin codificación definida.
export PYTHONIOENCODING=utf-8

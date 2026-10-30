#!/usr/bin/env bash
# Crea un paquete .deb "Architecture: all" de la variante pywebview.
# Usa el Python, GTK y WebKitGTK del sistema (dependencias de apt) y lleva dentro pywebview
# (paquete Python puro) en /opt/notas-rapidas-web/lib. Válido para Debian, Ubuntu y Mint.
#
# Uso:  ./crear_deb.sh
#       VERSION=1.2.0 MANTENEDOR="Nombre <correo@dominio>" ./crear_deb.sh
# Instalar:  sudo apt install ./dist/notas-rapidas-web_1.0.0_all.deb
# Quitar:    sudo apt remove notas-rapidas-web
# Requiere conexión a internet al construir (descarga pywebview de PyPI).
set -euo pipefail
cd "$(dirname "$0")"

PAQUETE="notas-rapidas-web"
VERSION="${VERSION:-1.0.0}"
MANTENEDOR="${MANTENEDOR:-Tu Nombre <tu@correo.example>}"
DESCRIPCION="Bloc de notas con interfaz HTML (ejemplo en Python con pywebview)"

command -v dpkg-deb >/dev/null || { echo "Falta dpkg-deb: este script es para Debian/Ubuntu/Mint." >&2; exit 1; }
python3 -c "import venv, ensurepip" 2>/dev/null || {
  echo "Falta python3-venv:  sudo apt install python3-venv" >&2; exit 1; }

STAGE="build/deb/${PAQUETE}_${VERSION}"
DESTINO="$STAGE/opt/$PAQUETE"
rm -rf build/deb
install -d -m755 \
  "$STAGE/DEBIAN" "$DESTINO" "$DESTINO/lib" "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/256x256/apps" \
  "$STAGE/usr/share/icons/hicolor/48x48/apps"

# Código, interfaz y recursos
install -m644 notas_web.py icono.png "$DESTINO/"
cp -r ui "$DESTINO/ui"
find "$DESTINO/ui" -type d -exec chmod 755 {} + ; find "$DESTINO/ui" -type f -exec chmod 644 {} +

# pywebview y sus dependencias (todas Python puro) dentro del paquete
python3 -m venv build/venv-deb
build/venv-deb/bin/python -m pip install --quiet --upgrade pip
build/venv-deb/bin/python -m pip install --quiet --target "$DESTINO/lib" pywebview
rm -rf "$DESTINO/lib/bin"
find "$DESTINO/lib" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$DESTINO/lib" -type d -exec chmod 755 {} + ; find "$DESTINO/lib" -type f -exec chmod a+r,u+w,go-w {} +

# Lanzador en el PATH
cat > "$STAGE/usr/bin/$PAQUETE" <<'LANZADOR'
#!/bin/sh
PYTHONPATH="/opt/notas-rapidas-web/lib${PYTHONPATH:+:$PYTHONPATH}" \
  exec /usr/bin/python3 /opt/notas-rapidas-web/notas_web.py "$@"
LANZADOR
chmod 755 "$STAGE/usr/bin/$PAQUETE"

# Entrada de menú e iconos
install -m644 "$PAQUETE.desktop" "$STAGE/usr/share/applications/$PAQUETE.desktop"
install -m644 icono_256.png "$STAGE/usr/share/icons/hicolor/256x256/apps/$PAQUETE.png"
install -m644 icono_48.png  "$STAGE/usr/share/icons/hicolor/48x48/apps/$PAQUETE.png"

# Metadatos. WebKitGTK 4.1 en Debian 12+, Ubuntu 22.04+ y Mint 21+; 4.0 en distros más antiguas.
TAM=$(du -sk "$STAGE" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: $PAQUETE
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.9), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1 | gir1.2-webkit2-4.0
Recommends: python3-gi-cairo
Installed-Size: $TAM
Maintainer: $MANTENEDOR
Description: $DESCRIPCION
 Ejemplo de aplicación de escritorio con interfaz HTML/CSS/JS dentro de una
 ventana nativa GTK (WebKitGTK). Incluye pywebview.
CONTROL

mkdir -p dist
SALIDA="dist/${PAQUETE}_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$STAGE" "$SALIDA" >/dev/null

echo "Paquete creado: $SALIDA"
dpkg-deb --info "$SALIDA" | sed -n '1,14p'
command -v lintian >/dev/null && { echo; echo "Revisión con lintian:"; lintian "$SALIDA" || true; }
echo
echo "Instalar:  sudo apt install ./$SALIDA"

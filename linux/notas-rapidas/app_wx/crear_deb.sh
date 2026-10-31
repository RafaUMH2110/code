#!/usr/bin/env bash
# Crea un paquete .deb "Architecture: all" que usa el Python del sistema.
# Válido para Debian, Ubuntu y Linux Mint (y derivadas), en cualquier arquitectura.
# Depende del paquete python3-wxgtk4.0 de la distribución (wxPython 4.x para el Python del sistema).
# Comprueba la disponibilidad con:  apt-cache policy python3-wxgtk4.0
#
# Uso:  ./crear_deb.sh
#       VERSION=1.2.0 MANTENEDOR="Nombre <correo@dominio>" ./crear_deb.sh
# Instalar:  sudo apt install ./dist/notas-rapidas-wx_1.0.0_all.deb
# Quitar:    sudo apt remove notas-rapidas-wx
set -euo pipefail
cd "$(dirname "$0")"

PAQUETE="notas-rapidas-wx"
VERSION="${VERSION:-1.0.0}"
MANTENEDOR="${MANTENEDOR:-Tu Nombre <tu@correo.example>}"
DESCRIPCION="Bloc de notas sencillo (ejemplo en Python con wxPython)"

command -v dpkg-deb >/dev/null || { echo "Falta dpkg-deb: este script es para Debian/Ubuntu/Mint." >&2; exit 1; }

STAGE="build/deb/${PAQUETE}_${VERSION}"
rm -rf build/deb
install -d -m755 \
  "$STAGE/DEBIAN" \
  "$STAGE/opt/$PAQUETE" \
  "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/256x256/apps" \
  "$STAGE/usr/share/icons/hicolor/48x48/apps"

# Código y recursos
install -m644 notas_wx.py icono_256.png "$STAGE/opt/$PAQUETE/"

# Lanzador en el PATH (usa el Python del sistema)
cat > "$STAGE/usr/bin/$PAQUETE" <<'LANZADOR'
#!/bin/sh
exec /usr/bin/python3 /opt/notas-rapidas-wx/notas_wx.py "$@"
LANZADOR
chmod 755 "$STAGE/usr/bin/$PAQUETE"

# Entrada de menú e iconos
install -m644 "$PAQUETE.desktop" "$STAGE/usr/share/applications/$PAQUETE.desktop"
install -m644 icono_256.png "$STAGE/usr/share/icons/hicolor/256x256/apps/$PAQUETE.png"
install -m644 icono_48.png  "$STAGE/usr/share/icons/hicolor/48x48/apps/$PAQUETE.png"

# Metadatos del paquete
TAM=$(du -sk "$STAGE" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: $PAQUETE
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.9), python3-wxgtk4.0
Installed-Size: $TAM
Maintainer: $MANTENEDOR
Description: $DESCRIPCION
 Ejemplo de aplicación de escritorio en Python que se inicia desde el menú
 de aplicaciones o con el comando notas-rapidas-wx.
CONTROL

mkdir -p dist
SALIDA="dist/${PAQUETE}_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$STAGE" "$SALIDA" >/dev/null

echo "Paquete creado: $SALIDA"
dpkg-deb --info "$SALIDA" | sed -n '1,14p'
command -v lintian >/dev/null && { echo; echo "Revisión con lintian:"; lintian "$SALIDA" || true; }
echo
echo "Instalar:  sudo apt install ./$SALIDA"

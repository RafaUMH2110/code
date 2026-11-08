#!/usr/bin/env python3
"""Genera el icono de la aplicación con Qt (sin depender de ningún fichero externo).

Produce ``src/panel_servidores/icono.png`` (1024×1024) y la carpeta ``icono.iconset`` con todos los
tamaños que necesita ``iconutil`` para crear el ``.icns`` de macOS (lo hace ``construir-app.sh``).

Dibujo: un rack de servidores estilizado (tres bandejas con luces) sobre un fondo azul redondeado.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "src", "panel_servidores", "icono.png")
TAMANOS = [16, 32, 64, 128, 256, 512, 1024]


def dibujar(lado: int = 1024) -> QImage:
    img = QImage(lado, lado, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    u = lado / 1024.0
    fondo = QLinearGradient(0, 0, 0, lado)
    fondo.setColorAt(0, QColor("#2f6fed"))
    fondo.setColorAt(1, QColor("#1c3f9e"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(fondo))
    p.drawRoundedRect(QRectF(60 * u, 60 * u, 904 * u, 904 * u), 200 * u, 200 * u)
    for i in range(3):
        y = (230 + i * 190) * u
        p.setBrush(QColor("#f4f7ff"))
        p.drawRoundedRect(QRectF(190 * u, y, 644 * u, 150 * u), 34 * u, 34 * u)
        p.setBrush(QColor("#c5d3f5"))
        p.drawRoundedRect(QRectF(230 * u, y + 52 * u, 330 * u, 46 * u), 14 * u, 14 * u)
        for k, color in enumerate(("#2e9e5b", "#2e9e5b" if i != 1 else "#e0a800")):
            p.setBrush(QColor(color))
            p.drawEllipse(QRectF((650 + k * 70) * u, y + 52 * u, 46 * u, 46 * u))
    p.end()
    return img


def main() -> int:
    QGuiApplication(sys.argv)
    base = dibujar(1024)
    base.save(DESTINO)
    carpeta = os.path.join(RAIZ, "icono.iconset")
    os.makedirs(carpeta, exist_ok=True)
    for t in (16, 32, 128, 256, 512):
        base.scaled(t, t, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation) \
            .save(os.path.join(carpeta, "icon_%dx%d.png" % (t, t)))
        base.scaled(t * 2, t * 2, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation) \
            .save(os.path.join(carpeta, "icon_%dx%d@2x.png" % (t, t)))
    print("Icono creado:", DESTINO)
    return 0


if __name__ == "__main__":
    sys.exit(main())

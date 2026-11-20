#!/usr/bin/env python3
"""Servidor de pruebas para esta app (solo biblioteca estándar).

Sirve los ficheros de esta carpeta y reenvía la API de TeleHome Enchufes a un servicio en marcha,
imitando lo que hace Apache en el servidor (la app busca la API en /rafa/telehome/enchufes/api/).

    python3 servir.py                          # app en http://127.0.0.1:8080/, servicio en 127.0.0.1:8765
    python3 servir.py --api http://127.0.0.1:8765 --port 8080
    python3 servir.py --host 0.0.0.0           # visible desde el iPhone/iPad de la misma red Wi-Fi

El servicio se arranca aparte (en simulación, sin enchufes reales):
    cd ../telehome-enchufes && python3 -m telehome_enchufes serve --simulate 3 --no-browser

Aviso: con --host 0.0.0.0 cualquiera de tu red puede abrir la app y, a través de ella, el servicio. Úsalo solo
para probar y con el servicio en simulación o con contraseña.
"""
import argparse
import http.client
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

AQUI = Path(__file__).resolve().parent
PREFIJO = "/rafa/telehome/enchufes/"          # ruta bajo la que Apache publica el servicio
SALTAR = {"host", "origin", "referer", "connection", "content-length", "accept-encoding"}


class Manejador(BaseHTTPRequestHandler):
    destino = urlsplit("http://127.0.0.1:8765")

    def log_message(self, fmt, *args):  # una línea por petición
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def _proxy(self):
        ruta = "/" + self.path[len(PREFIJO):]
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo) if largo else None
        cab = {k: v for k, v in self.headers.items() if k.lower() not in SALTAR}
        try:
            con = http.client.HTTPConnection(self.destino.hostname, self.destino.port or 80, timeout=30)
            con.request(self.command, ruta, body=cuerpo, headers=cab)   # Host = el del servicio (loopback)
            r = con.getresponse()
            datos = r.read()
        except OSError as exc:
            self.send_error(502, "No se puede conectar con el servicio (%s)" % exc)
            return
        self.send_response(r.status)
        for k, v in r.getheaders():
            if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _estatico(self):
        nombre = urlsplit(self.path).path.lstrip("/") or "index.html"
        f = (AQUI / nombre).resolve()
        if AQUI not in f.parents and f != AQUI or not f.is_file() or f.suffix in (".py", ".md"):
            self.send_error(404)
            return
        datos = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _atender(self):
        if self.path.startswith(PREFIJO) or self.path == PREFIJO.rstrip("/"):
            if self.path == PREFIJO.rstrip("/"):
                self.path = PREFIJO
            return self._proxy()
        if self.command == "GET":
            return self._estatico()
        self.send_error(405)

    do_GET = do_POST = do_PUT = do_DELETE = _atender


def main() -> int:
    ap = argparse.ArgumentParser(description="Servidor de pruebas: ficheros de la app + proxy a TeleHome Enchufes")
    ap.add_argument("--api", default="http://127.0.0.1:8765", help="URL del servicio (def.: %(default)s)")
    ap.add_argument("--host", default="127.0.0.1", help="dirección de escucha (def.: %(default)s)")
    ap.add_argument("--port", type=int, default=8080, help="puerto (def.: %(default)s)")
    a = ap.parse_args()
    Manejador.destino = urlsplit(a.api)
    srv = ThreadingHTTPServer((a.host, a.port), Manejador)
    print("App:       http://%s:%d/\nServicio:  %s  (visible en %s*)" % (a.host, a.port, a.api, PREFIJO))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

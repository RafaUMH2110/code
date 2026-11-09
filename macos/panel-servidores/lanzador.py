"""Punto de entrada para PyInstaller (y para ``python lanzador.py`` desde la raíz del proyecto).

Atiende ``--askpass`` antes de importar Qt: cuando la aplicación está empaquetada, ``ssh`` vuelve a
ejecutar este mismo programa para preguntar contraseñas, y debe responder rápido.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

if len(sys.argv) > 1 and sys.argv[1] == "--askpass":
    from panel_servidores.nucleo import askpass_cliente
    sys.exit(askpass_cliente.main(sys.argv[2:]))

from panel_servidores.app import main

if __name__ == "__main__":
    sys.exit(main())

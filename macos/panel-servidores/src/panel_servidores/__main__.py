"""Punto de entrada: ``python -m panel_servidores``.

Atiende primero ``--askpass`` (así se invoca el propio ejecutable desde ``ssh`` cuando la aplicación está
empaquetada) sin importar Qt, para que responda en milisegundos.
"""

import sys

if len(sys.argv) > 1 and sys.argv[1] == "--askpass":
    from .nucleo import askpass_cliente
    sys.exit(askpass_cliente.main(sys.argv[2:]))

from .app import main

sys.exit(main())

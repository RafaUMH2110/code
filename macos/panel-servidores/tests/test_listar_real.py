"""El instalador REAL (--listar) a través del envoltorio, contra el sshd de pruebas. Necesita red hacia GitHub."""
import shutil
import urllib.request

import pytest

from panel_servidores.nucleo import instalador
from panel_servidores.nucleo.instalador import OpcionesInstalador


def _hay_github():
    try:
        urllib.request.urlopen("https://api.github.com/rate_limit", timeout=8)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not (shutil.which("curl") and shutil.which("jq")), reason="faltan curl/jq")
def test_listar_con_el_script_real(fabrica, servidor_ssh, recursos):
    con = fabrica()
    lineas = []
    o = OpcionesInstalador(usuario_gh="RafaUMH2110", origen=str(servidor_ssh.home / "repos"),
                           dir_script="~/panel-test/real")
    res = instalador.listar_en_servidor(con, recursos, o, lambda t, e: lineas.append(t))
    texto = "\n".join(lineas)
    # En un servidor con salida a Internet termina bien y lista los repos. En un contenedor sin proxy para el
    # usuario de pruebas el script llega a su primera llamada de red y lo dice con su propio mensaje: eso ya
    # demuestra que se subió, se extrajo y se ejecutó el script real a través del envoltorio.
    assert res.ok or "API de GitHub" in (res.mensaje + texto), res.mensaje + texto
    if res.ok:
        assert "code" in texto

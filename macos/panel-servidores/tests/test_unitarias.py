"""Pruebas unitarias del núcleo: no necesitan red, servidor ni permisos especiales."""

from __future__ import annotations

import json
import subprocess
import tarfile
import io
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from panel_servidores.nucleo import ansi, github, remoto
from panel_servidores.nucleo.almacen import Almacen
from panel_servidores.nucleo.instalador import (AnalizadorLog, OpcionesInstalador, SELECCION_EXCLUIR,
                                                SELECCION_LISTA, SELECCION_TODOS, quitar_entradas_cron)
from panel_servidores.nucleo.modelos import (FuenteSecreto, Perfil, ORIGEN_ENTORNO, ORIGEN_LLAVERO, VARIANTE_ISA)
from panel_servidores.nucleo.recursos import Recursos
from panel_servidores.nucleo.secretos import Llavero, ResolutorSecretos
from panel_servidores.nucleo.ssh import analizar_destino
from tests.conftest import InteraccionGuion, LlaveroFalso


# ----------------------------------------------------------------------------- destino
@pytest.mark.parametrize("texto,usuario,host,puerto", [
    ("rafa@servidor.es", "rafa", "servidor.es", 0),
    ("rafa@servidor.es:2222", "rafa", "servidor.es", 2222),
    ("alias", "", "alias", 0),
    ("10.0.0.5:22", "", "10.0.0.5", 22),
])
def test_analizar_destino(texto, usuario, host, puerto):
    d = analizar_destino(texto)
    assert (d.usuario, d.host, d.puerto) == (usuario, host, puerto)


@pytest.mark.parametrize("texto", ["", "  ", "a b", "-oProxyCommand=x", "x@", "u@-oProxy=x", "-u@host", "a\tb"])
def test_destino_invalido(texto):
    assert analizar_destino(texto) is None


# ----------------------------------------------------------------------------- comandos remotos
def _sh(cmd: str, entrada: str = "", env=None):
    return subprocess.run(["sh", "-c", cmd], input=entrada, capture_output=True, text=True, env=env)


def test_sh_c_cita_todo():
    cmd = remoto.sh_c('printf "%s|" "$1" "$2"', "a b; rm -rf /", "$(id)'\"")
    r = _sh(cmd)
    assert r.stdout == "a b; rm -rf /|$(id)'\"|"


def test_leer_fichero_expande_tilde(tmp_path, monkeypatch):
    (tmp_path / "x.txt").write_text("uno\ndos\ntres\n")
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    assert _sh(remoto.comando_leer_fichero("~/x.txt"), env=env).stdout == "uno\ndos\ntres\n"
    assert _sh(remoto.comando_leer_fichero("~/x.txt", 2), env=env).stdout == "dos\ntres\n"
    assert _sh(remoto.comando_leer_fichero("~/no.txt"), env=env).returncode == 66


def test_instalar_y_revocar_clave(tmp_path):
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    clave = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIABCDEFG comentario"
    r = _sh(remoto.comando_instalar_clave(clave), env=env)
    assert "KEY=added" in r.stdout
    assert "KEY=already" in _sh(remoto.comando_instalar_clave(clave), env=env).stdout
    f = tmp_path / ".ssh" / "authorized_keys"
    assert f.read_text().count("AAAAC3NzaC1lZDI1NTE5AAAAIABCDEFG") == 1
    assert oct(f.stat().st_mode & 0o777) == "0o600"
    r = _sh(remoto.comando_revocar_clave("AAAAC3NzaC1lZDI1NTE5AAAAIABCDEFG"), env=env)
    assert "KEY=removed" in r.stdout and "COUNT=1" in r.stdout
    assert "AAAAC3" not in f.read_text()
    assert list((tmp_path / ".ssh").glob("authorized_keys.bak-*"))


def test_servicio_valida_nombre():
    with pytest.raises(ValueError):
        remoto.comando_accion_servicio("restart", "a; rm -rf /")
    with pytest.raises(ValueError):
        remoto.comando_accion_servicio("poweroff", "ssh")
    assert "systemctl restart" in remoto.comando_accion_servicio("restart", "telemet-colector")


def test_desinstalar_solo_en_opt(tmp_path):
    """El borrado del programa jamás sale de /opt (se prueba con un directorio ajeno)."""
    ajeno = tmp_path / "datos"
    ajeno.mkdir()
    cuerpo = remoto.comando_desinstalar_servicio("telemet-x", str(ajeno), True, False, usar_sudo=False)
    # Sustituimos systemctl por un falso para poder ejecutarlo sin systemd.
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "systemctl").write_text("#!/bin/sh\nexit 0\n")
    (bin_ / "systemctl").chmod(0o755)
    r = _sh(cuerpo, env={"PATH": "%s:/usr/bin:/bin" % bin_, "HOME": str(tmp_path)})
    assert ajeno.exists()
    assert "No se borra nada" in r.stdout


def test_cabecera_entrada_y_variables():
    datos = remoto.cabecera_entrada({"TELEMET_API_KEY": 'a"b$c\nd'})
    assert datos.startswith(b"1\nTELEMET_API_KEY=")
    with pytest.raises(ValueError):
        remoto.cabecera_entrada({"bad name": "x"})


def test_envoltorio_instalador_con_script_falso(tmp_path):
    """Ejecuta el envoltorio completo en local con un «instalador» de mentira."""
    falso = b'#!/bin/bash\necho "ARGS: $*"\necho "KEY=$TELEMET_API_KEY"\ntest -f index.html && echo PORTAL\n'
    paquete = remoto.empaquetar({"instalar-todo.sh": falso, "index.html": b"<html/>"})
    entrada = remoto.cabecera_entrada({"TELEMET_API_KEY": 'cl"a$ve\'x'}) + paquete
    destino = tmp_path / "dest"
    cmd = remoto.comando_instalador(str(destino), "instalar-todo.sh", ["-u", "x y", "--colector"])
    r = subprocess.run(["sh", "-c", cmd], input=entrada, capture_output=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    out = r.stdout.decode()
    assert r.returncode == 0, r.stderr.decode()
    assert "ARGS: -u x y --colector" in out
    assert "KEY=cl\"a$ve'x" in out
    assert "PORTAL" in out
    assert (destino / "instalar-todo.sh").stat().st_mode & 0o111


def test_empaquetar_modos():
    datos = remoto.empaquetar({"a.sh": b"x", "b.html": b"y"})
    with tarfile.open(fileobj=io.BytesIO(datos)) as t:
        assert t.getmember("a.sh").mode == 0o755
        assert t.getmember("b.html").mode == 0o644


# ----------------------------------------------------------------------------- instalador
def test_opciones_por_defecto_y_argumentos():
    o = OpcionesInstalador()
    assert o.validar() == []
    assert o.a_argumentos() == ["-u", "RafaUMH2110"]
    assert o.destino_efectivo() == "/var/www/html/rafa"
    assert o.entrada_web() == "/rafa/"


def test_opciones_completas():
    o = OpcionesInstalador(seleccion=SELECCION_LISTA, repos=["code/macos", "web"], modo="todo", colector=True,
                           cron="0 3 * * *", forzar=True, sin_indice=True)
    assert o.validar() == []
    a = o.a_argumentos()
    assert "--repos" in a and a[a.index("--repos") + 1] == "code/macos,web"
    assert a[a.index("--modo") + 1] == "todo"
    assert "--colector" in a and "--forzar" in a and "--sin-indice" in a
    assert a[a.index("--cron") + 1] == "0 3 * * *"
    assert "--repos 'code/macos,web'" not in o.comando_equivalente()   # no necesita comillas
    assert o.comando_equivalente().startswith("./instalar-todo.sh")


def test_opciones_isa():
    o = OpcionesInstalador(variante=VARIANTE_ISA, url="https://isa.umh.es/", entrada_raiz=True, json_dir="/var/www/htdocs/rafa-json")
    assert o.docroot_efectivo() == "/var/www/htdocs"
    a = o.a_argumentos()
    assert a[a.index("--url") + 1] == "https://isa.umh.es"
    assert "--entrada-raiz" in a
    assert o.comando_equivalente().startswith("./instalar-todo-isa.sh")


@pytest.mark.parametrize("cambios,fragmento", [
    ({"destino": "/"}, "Destino no permitido"),
    ({"destino": "/var/www"}, "Destino no permitido"),
    ({"destino": "/srv/web"}, "dentro de"),
    ({"cron": "0 3 *"}, "5 campos"),
    ({"seleccion": SELECCION_LISTA}, "al menos un repo"),
    ({"seleccion": SELECCION_EXCLUIR}, "excluir"),
    ({"repos": ["a b"]}, "no es válido"),
    ({"modo": "otro"}, "modo"),
    ({"usuario_gh": "a b"}, "usuario"),
    ({"variante": VARIANTE_ISA, "url": "https://x.es/ruta"}, "URL"),
])
def test_validaciones(cambios, fragmento):
    errores = OpcionesInstalador(**cambios).validar()
    assert any(fragmento in e for e in errores), errores


def test_opciones_serializacion():
    o = OpcionesInstalador(seleccion=SELECCION_TODOS, colector=True)
    assert OpcionesInstalador.desde_dict(o.a_dict()) == o
    assert OpcionesInstalador.desde_dict({"desconocido": 1, "modo": "html"}).modo == "html"


def test_analizador_log():
    a = AnalizadorLog()
    assert a.alimentar("[2026-11-08 10:00:00] === 2/6 Selección y clonado ===").tipo == "paso"
    assert a.paso == 2
    a.alimentar("[x] Repos -> nuevos: 3 | actualizados: 4 (con cambios: 1, sin cambios: 3) | errores: 0")
    a.alimentar("[x] Resumen despliegue -> nuevos: 5 | modificados: 2 | borrados: 1 | transferido 1,2MB")
    assert a.alimentar("[x] ERROR algo falló").tipo == "error"
    assert a.alimentar("[x] AVISO ojo").tipo == "aviso"
    a.alimentar("el destino tiene contenido ajeno y no hay terminal")
    ev = a.alimentar("[x] FIN. Entrada: http://h/rafa/  |  Errores: 1  |  Duración: 42s")
    assert ev.tipo == "fin"
    assert a.necesita_forzar
    assert a.resumen["nuevos"] == 3 and a.resumen["transferido"] == "1,2MB"
    assert a.resumen["url"] == "http://h/rafa/" and a.resumen["segundos"] == 42


def test_quitar_cron():
    cron = "# comentario instalar-todo\n0 3 * * * ~/x/instalar-todo.sh --todos\n5 * * * * otra cosa\n"
    nuevo, quitadas = quitar_entradas_cron(cron)
    assert len(quitadas) == 1 and "otra cosa" in nuevo and "comentario" in nuevo and "0 3" not in nuevo
    assert quitar_entradas_cron("0 3 * * * instalar-todo\n") == ("", ["0 3 * * * instalar-todo"])


# ----------------------------------------------------------------------------- ansi
def test_ansi():
    h = ansi.ansi_a_html("\x1b[1;31mrojo\x1b[0m <b> normal", envolver=False)
    assert "font-weight:bold" in h and "rojo" in h and "&lt;b&gt;" in h
    assert ansi.quitar_ansi("\x1b[32mverde\x1b[0m\x1b[K") == "verde"


# ----------------------------------------------------------------------------- modelos y almacén
def test_perfil_roundtrip():
    p = Perfil(nombre="N", destino="u@h", password=FuenteSecreto(ORIGEN_ENTORNO, "PW"))
    q = Perfil.desde_dict(json.loads(json.dumps(p.a_dict())))
    assert q == p and q.password.variable == "PW"
    assert Perfil.desde_dict({"nombre": "x", "campo_nuevo": 1}).nombre == "x"


def test_almacen(datos, tmp_path):
    a = Almacen()
    p = a.anadir(Perfil(nombre="uno", destino="u@h"))
    copia = a.duplicar(p.id)
    assert copia.id != p.id and copia.nombre == "uno (copia)"
    a.ajustes.idioma_informe = "en"
    a.guardar_ajustes()
    b = Almacen()
    assert len(b.perfiles) == 2 and b.ajustes.idioma_informe == "en"
    assert (datos / "perfiles.json").stat().st_mode & 0o777 == 0o600
    assert "password" in (datos / "perfiles.json").read_text()   # solo la FUENTE, nunca el valor
    n = b.exportar(tmp_path / "e.json")
    assert n == 2
    assert b.importar(tmp_path / "e.json") == 2 and len(b.perfiles) == 4
    assert len({x.id for x in b.perfiles}) == 4
    b.eliminar(p.id)
    assert b.obtener(p.id) is None


def test_almacen_json_corrupto(datos):
    datos.mkdir(parents=True)
    (datos / "perfiles.json").write_text("{no es json")
    a = Almacen()
    assert a.perfiles == []
    assert (datos / "perfiles.json.bak").exists()


# ----------------------------------------------------------------------------- secretos
def test_secretos_preguntar_y_recordar():
    inter = InteraccionGuion(["miclave"])
    s = ResolutorSecretos(Perfil(nombre="x"), inter, Llavero(LlaveroFalso()))
    assert s.obtener("password") == "miclave"
    assert s.obtener("password") == "miclave"        # no vuelve a preguntar
    assert len(inter.preguntas) == 1
    s.olvidar()
    assert s.obtener("password", preguntar_si_falta=False) is None


def test_secretos_entorno(monkeypatch):
    monkeypatch.setenv("MI_PW", "desde-entorno")
    p = Perfil(password=FuenteSecreto(ORIGEN_ENTORNO, "MI_PW"))
    s = ResolutorSecretos(p, InteraccionGuion(), Llavero(LlaveroFalso()))
    assert s.obtener("password") == "desde-entorno"


def test_secretos_llavero():
    falso = LlaveroFalso()
    ll = Llavero(falso)
    p = Perfil(password=FuenteSecreto(ORIGEN_LLAVERO))
    ll.guardar(p.id, "password", "guardada")
    s = ResolutorSecretos(p, InteraccionGuion(), ll)
    assert s.obtener("password") == "guardada"
    ll.borrar_todos(p.id)
    assert falso.datos == {}


def test_responder_askpass():
    inter = InteraccionGuion(["pw", "otro", "123456"])
    s = ResolutorSecretos(Perfil(), inter, Llavero(LlaveroFalso()))
    assert s.responder_askpass("rafa@h's password: ") == "pw"
    assert s.responder_askpass("rafa@h's password: ") == "pw"                 # cacheada
    assert s.responder_askpass("Verification code: ") == "otro"
    assert s.responder_askpass("Verification code: ") == "123456"             # 2FA: SIEMPRE se pregunta
    inter2 = InteraccionGuion(confirmar=True)
    s2 = ResolutorSecretos(Perfil(), inter2, Llavero(LlaveroFalso()))
    assert s2.responder_askpass("Are you sure you want to continue connecting (yes/no/[fingerprint])? ") == "yes"
    inter3 = InteraccionGuion(confirmar=False)
    s3 = ResolutorSecretos(Perfil(), inter3, Llavero(LlaveroFalso()))
    assert s3.responder_askpass("Are you sure you want to continue connecting (yes/no/[fingerprint])? ") == "no"


def test_askpass_ida_y_vuelta(askpass):
    token = askpass.registrar(lambda prompt: "resp:" + prompt)
    env = dict(askpass.entorno(token))
    import os
    r = subprocess.run([env["SSH_ASKPASS"], "Password: "], capture_output=True, text=True, env={**os.environ, **env})
    assert r.returncode == 0 and r.stdout.strip() == "resp:Password:" or r.stdout.strip() == "resp:Password: "
    askpass.liberar(token)
    r = subprocess.run([env["SSH_ASKPASS"], "Password: "], capture_output=True, text=True, env={**os.environ, **env})
    assert r.returncode != 0


# ----------------------------------------------------------------------------- recursos
def test_recursos_incluidos():
    r = Recursos()
    inv = {n: (o, h) for n, o, h in r.inventario()}
    for n in ("instalar-todo.sh", "instalar-todo-isa.sh", "telemet-collector-info.py", "index.html"):
        assert inv[n][0] != "no encontrado", n
    assert subprocess.run(["bash", "-n", str(r.ruta("instalar-todo.sh"))]).returncode == 0
    assert subprocess.run(["bash", "-n", str(r.ruta("instalar-todo-isa.sh"))]).returncode == 0


def test_recursos_carpeta_propia(tmp_path):
    (tmp_path / "instalar-todo.sh").write_text("#!/bin/bash\necho propio\n")
    r = Recursos(str(tmp_path))
    assert r.origen("instalar-todo.sh") == "carpeta propia"
    assert b"propio" in r.leer("instalar-todo.sh")


# ----------------------------------------------------------------------------- GitHub (servidor HTTP falso)
class _ApiFalsa(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if "/users/u/repos" in self.path:
            pagina = int(self.path.split("&page=")[1])
            cuerpo = [{"name": "a", "language": "Python", "size": 5},
                      {"name": "vieja", "archived": True, "size": 1}] if pagina == 1 else []
        elif self.path.endswith("/repos/u/a/contents"):
            cuerpo = [{"name": "src", "type": "dir"}, {"name": ".github", "type": "dir"}, {"name": "r.md", "type": "file"}]
        else:
            self.send_response(404)
            self.end_headers()
            return
        datos = json.dumps(cuerpo).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)


@pytest.fixture
def api_falsa():
    srv = HTTPServer(("127.0.0.1", 0), _ApiFalsa)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_port
    srv.shutdown()


def test_github_repos_y_carpetas(api_falsa):
    repos = github.listar_repos("u", api=api_falsa)
    assert [r.nombre for r in repos] == ["a"]          # el archivado se omite
    assert github.listar_carpetas("u", "a", api=api_falsa) == ["src"]
    with pytest.raises(github.ErrorGitHub):
        github.listar_carpetas("u", "no-existe", api=api_falsa)


# ----------------------------------------------------------------------------- ~/.ssh/config
def test_sshconfig(tmp_path):
    from panel_servidores.nucleo import sshconfig
    f = tmp_path / "config"
    f.write_text("""
# comentario
Host *
    ServerAliveInterval 30
Host web prod
    HostName 10.1.2.3
    User rafa
    Port 2222
    IdentityFile ~/.ssh/id_prod
Host dentro
    HostName 192.168.0.9
    ProxyJump web
Match host x
    User nadie
Host !excluido *.interno
    User z
""")
    hosts = sshconfig.leer_hosts(f)
    assert [h["alias"] for h in hosts] == ["web", "prod", "dentro"]
    assert hosts[0]["port"] == 2222 and hosts[0]["identity"] == "~/.ssh/id_prod"
    p = sshconfig.a_perfil(hosts[2])
    assert p.destino == "dentro" and "ProxyJump web" in p.notas
    assert sshconfig.leer_hosts(tmp_path / "no-existe") == []


def test_terminal_applescript():
    from panel_servidores.nucleo import terminal
    assert terminal.escapar_applescript('ssh -o "x" a\\b') == 'ssh -o \\"x\\" a\\\\b'
    assert 'tell application "Terminal"' in terminal.guion_terminal("ssh h")
    assert 'tell application "iTerm"' in terminal.guion_terminal("ssh h", "iTerm2")


# ----------------------------------------------------------------------------- «Acerca de»
def test_acerca_de():
    import re
    from panel_servidores import ULTIMA_MODIFICACION, __version__
    from panel_servidores.nucleo import acerca
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", ULTIMA_MODIFICACION)
    d = acerca.fecha_modificacion()                       # el formato es válido y no es una fecha futura
    assert d.year >= 2026
    assert "de" in acerca.fecha_modificacion_legible() and ("%02d:%02d" % (d.hour, d.minute)) in acerca.fecha_modificacion_legible()
    etiquetas = [e for e, _ in acerca.informacion()]
    assert etiquetas[:2] == ["Versión", "Última modificación"] and "Cliente SSH" in etiquetas
    texto = acerca.texto_para_copiar([("Qt", "6.x")])
    assert __version__ in texto and ULTIMA_MODIFICACION in texto and "Qt:" in texto
    assert "SECRETA" not in texto
    assert acerca.version_ssh("/ruta/que/no/existe").startswith("no encontrado")
